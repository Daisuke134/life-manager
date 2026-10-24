#!/usr/bin/env python3
"""measure-sales.py — measures REAL, currently-displayed sales/revenue figures for note and
Substack (JA, plus EN when SUBSTACK_PUBLICATION_EN is configured). Each platform driver runs in
the Life Manager managed Python as a subprocess and launches its own short-lived headless
CloakBrowser context (cloakbrowser.launch_context, the note-publish/publish-paid.py precedent),
which it closes when done: no shared or resident browser is ever attached. Credentials come from
LIFE_MANAGER_ENV_FILE; note's session is kept in a Writer-owned 0600 storage_state file so the
ordinary login runs only when that session expires, and a failed login backs off for a day.
NEVER estimate or fabricate a number: if a metric cannot be safely parsed from the real screen
text today, emit null + a reason string, exactly like measure-funnel.py does. DOM reading uses
document.body.innerText + regex on labels, never brittle CSS selectors and never an LLM judge.

Per-platform measurement (MEASURED 2026-07-18 against the real logged-in dashboards):
  - note:      note.com/sitesettings/salesmanage ("売上管理", redirects to
               note.com/dashboard/salesmanage once logged in) requires a one-time password
               re-confirmation step (note's own step-up auth for money pages) -- filled from the
               NOTE_PASSWORD env var only if a password field actually appears on the page,
               skipped otherwise (session already confirmed earlier). The "今月の売上" card's
               "総額" line = sales_revenue (¥, this calendar month).
               note.com/sitesettings/purchasers ("販売履歴", redirects to note.com/dashboard/sales)
               shows the literal sentence "<year>年<month>月は購入者がいません" when there were
               zero purchases this month -- parsed as sales_count=0. A populated (non-zero) month
               has not been observed yet in this account, so that layout is reported as
               null+reason rather than guessed at (do not invent a row-counting rule for a layout
               never seen).
               note.com/sitesettings/stats loads the authenticated, paginated
               /api/v1/stats/pv response. Article views join by exact note key and owner;
               absence means zero only after the terminal page, after publication, and when
               every returned row proves that zero-view articles are omitted.
  - substack:  {pub}/publish/home 's "有料登録者" overview card and
               {pub}/publish/stats/earnings 's "累計収益" (Lifetime earnings) card. Substack's
               formatter prints 0 and null alike as "-" (MEASURED 2026-10-18 in the reactPublish
               bundle), so a dash alone is never converted into zero. The same page also
               reads the JSON those cards render: /api/v1/publish-dashboard/summary `subscribers`
               and user_pub_stats/payouts.totalAmount + payouts.totalEarnings (minor units, USD).
               An explicit JSON number is recorded only when the card agrees with it ("-" only
               with 0); otherwise the metric stays null + reason. Substack shows no MRR card, so
               mrr is 0 only when paid subscribers were measured as 0, else null + reason.

SCOPE (added 2026-07-31): every emitted row carries `scope` — "artifact" (this number is one
article's) or "account" (publication-wide). Both note dashboard totals and all three Substack
figures are structurally account-wide, so they are written as scope="account" with a reason and
NO artifact key. An account number is never divided or guessed onto an article. The rules and
the `artifact_id` encoding live in scripts/artifact_attribution.py; join with
scripts/attribution-join.py.

CLI:
    measure-sales.py [--out <path>]
stdout: one JSON line summary {"date": "...", "measured": N, "results": [...]}
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Every emitted row declares whether its number is per-article or account-wide. The scope rules
# and the artifact_id encoding live in one place: scripts/artifact_attribution.py.
_ATTRIBUTION_SPEC = importlib.util.spec_from_file_location(
    "article_artifact_attribution",
    Path(__file__).resolve().parent / "artifact_attribution.py",
)
attribution = importlib.util.module_from_spec(_ATTRIBUTION_SPEC)
assert _ATTRIBUTION_SPEC.loader is not None
_ATTRIBUTION_SPEC.loader.exec_module(attribution)

DEFAULT_STATE_DIR = Path(
    os.environ.get("ARTICLE_STATE_DIR", os.environ.get("WRITER_STATE_DIR", Path(__file__).resolve().parents[1] / "state"))
)
DEFAULT_OUT = str(DEFAULT_STATE_DIR / "sales-ledger.jsonl")
VENV_CLOAK_PYTHON = os.environ.get("WRITER_BROWSER_PYTHON", sys.executable)

NOTE_SALES_URL = "https://note.com/sitesettings/salesmanage"
NOTE_PURCHASES_URL = "https://note.com/sitesettings/purchasers"
NOTE_STATS_URL = "https://note.com/sitesettings/stats"
JST = timezone(timedelta(hours=9))
# Writer-owned, private, outside the repository and release: note's measured session and the
# marker that stops repeated password logins after a failure.
NOTE_SESSION_DIR = Path(os.environ.get("ARTICLE_STATE_DIR") or os.environ.get("WRITER_STATE_DIR")
                        or "~/.local/state/life-manager/writer").expanduser()
NOTE_STORAGE_STATE = NOTE_SESSION_DIR / "note-measure-storage.json"
NOTE_LOGIN_BACKOFF = NOTE_SESSION_DIR / "note-measure-login-backoff.json"
NOTE_LOGIN_BACKOFF_SECONDS = 24 * 3600
# (publication env keys, session cookie env keys) per publication, first non-empty wins.
# Same fallback as publish-substack.sh: only JA may use the legacy unsuffixed keys.
SUBSTACK_TARGETS = {
    "ja": (("SUBSTACK_PUBLICATION_JA", "SUBSTACK_PUBLICATION"),
           ("SUBSTACK_SESSION_COOKIE_JA", "SUBSTACK_SESSION_COOKIE")),
    "en": (("SUBSTACK_PUBLICATION_EN",), ("SUBSTACK_SESSION_COOKIE_EN",)),
}


def substack_publication(lang: str) -> str:
    return next((value for key in SUBSTACK_TARGETS[lang][0]
                 if (value := os.environ.get(key, "").strip())), "")


def run_browser_script(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    if not os.path.exists(VENV_CLOAK_PYTHON):
        raise FileNotFoundError(f"Writer browser Python not found at {VENV_CLOAK_PYTHON}")
    return subprocess.run([VENV_CLOAK_PYTHON, "-c", script], capture_output=True,
                          text=True, timeout=timeout)


def extract_payload(proc: subprocess.CompletedProcess) -> dict:
    """Shared subprocess-result handling for both platform drivers below -- same pattern as
    measure-funnel.py's measure_x: look for a recognizable prefixed line, else build an honest
    reason from whatever stdout/stderr actually said."""
    line = next((l for l in proc.stdout.splitlines() if l.startswith("PAYLOAD_B64:")), None)
    if proc.returncode == 0 and line:
        return {"payload": json.loads(base64.b64decode(line[len("PAYLOAD_B64:"):]).decode("utf-8"))}
    if "NOTE_PASSWORD_MISSING" in proc.stdout:
        return {"error": "NOTE_PASSWORD missing (configure LIFE_MANAGER_ENV_FILE first)"}
    if "NOTE_CREDENTIALS_MISSING" in proc.stdout:
        return {"error": "NOTE_EMAIL/NOTE_PASSWORD missing (configure LIFE_MANAGER_ENV_FILE first)"}
    if "NOTE_LOGIN_FAILED" in proc.stdout:
        return {"error": "note ordinary login did not reach the requested dashboard"}
    if "SUBSTACK_COOKIE_MISSING" in proc.stdout:
        return {"error": "SUBSTACK_SESSION_COOKIE missing (configure LIFE_MANAGER_ENV_FILE first)"}
    reason = proc.stdout.strip() or proc.stderr.strip()[-300:] or "no PAYLOAD_B64 line and no recognizable error prefix"
    return {"error": f"browser DOM read failed: {reason}"}


def note_login_backoff() -> str | None:
    """A failed password login is not retried for a day: hourly retries risk an account lock."""
    try:
        failed_at = NOTE_LOGIN_BACKOFF.stat().st_mtime
    except FileNotFoundError:
        return None
    until = failed_at + NOTE_LOGIN_BACKOFF_SECONDS
    if datetime.now(timezone.utc).timestamp() >= until:
        return None
    return ("note login backoff after NOTE_LOGIN_FAILED until "
            f"{datetime.fromtimestamp(until, timezone.utc).isoformat()}; no login attempted")


def measure_note_pages() -> dict:
    """Drives one ephemeral page through the note.com dashboard pages this run needs, filling the
    login or password re-confirmation step only if the browser actually shows it. Returns
    {"error": ...} OR the pages' final URL + raw document.body.innerText, for the caller to
    regex-parse (subprocess fetches, parent parses, as in measure-funnel.py's measure_x)."""
    backoff = note_login_backoff()
    if backoff:
        return {"error": backoff}
    storage = str(NOTE_STORAGE_STATE)
    script = f"""
import base64, json, os, sys, time
from cloakbrowser import launch_context

storage = {storage!r}
options = {{"headless": True, "humanize": False}}
if os.path.exists(storage):
    options["storage_state"] = storage
try:
    ctx = launch_context(**options)
except Exception:
    # A corrupt saved session would fail every run and is only rewritten after a success.
    if "storage_state" not in options:
        raise
    os.replace(storage, storage + ".corrupt")
    options.pop("storage_state")
    ctx = launch_context(**options)

def login_if_shown():
    if pg.locator('input[name="login"]').count() == 0:
        return True
    email = os.environ.get("NOTE_EMAIL", "")
    pw = os.environ.get("NOTE_PASSWORD", "")
    if not email or not pw:
        print("NOTE_CREDENTIALS_MISSING")
        return False
    pg.fill('input[name="login"]', email)
    pg.fill('input[name="password"]', pw)
    pg.evaluate('''() => {{
        const btn = [...document.querySelectorAll('button')].find(
            b => (b.innerText || '').trim() === 'ログイン');
        if (btn) btn.click();
    }}''')
    time.sleep(4)
    if pg.locator('input[name="login"]').count() > 0:
        print("NOTE_LOGIN_FAILED")
        return False
    return True

def confirm_password_if_shown():
    if pg.locator('input[type="password"]').count() == 0:
        return True
    pw = os.environ.get("NOTE_PASSWORD", "")
    if not pw:
        print("NOTE_PASSWORD_MISSING")
        return False
    pg.fill('input[type="password"]', pw)
    pg.evaluate('''() => {{
        const btn = [...document.querySelectorAll('button')].find(
            b => (b.innerText || '').trim() === '確認して続ける');
        if (btn) btn.click();
    }}''')
    time.sleep(3)
    if pg.locator('input[type="password"]').count() > 0:
        print("NOTE_LOGIN_FAILED")
        return False
    return True

try:
    pg = ctx.new_page()
    pg.goto({NOTE_SALES_URL!r}, wait_until="domcontentloaded", timeout=40000)
    time.sleep(3)
    if not login_if_shown():
        sys.exit(1)
    if not confirm_password_if_shown():
        sys.exit(1)
    # The money dashboard answered, so this session is authenticated: keep it (0600) for the next pass.
    os.makedirs(os.path.dirname(storage), mode=0o700, exist_ok=True)
    temporary = f"{{storage}}.{{os.getpid()}}.tmp"
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        json.dump(ctx.storage_state(), handle)
    os.replace(temporary, storage)

    sales_url = pg.url
    sales_body = pg.evaluate("() => document.body.innerText")

    pg.goto({NOTE_PURCHASES_URL!r}, wait_until="domcontentloaded", timeout=40000)
    time.sleep(3)
    if not confirm_password_if_shown():
        sys.exit(1)
    purchases_url = pg.url
    purchases_body = pg.evaluate("() => document.body.innerText")

    pg.goto({NOTE_STATS_URL!r}, wait_until="domcontentloaded", timeout=40000)
    time.sleep(3)
    stats_pages = pg.evaluate('''async () => {{
        const pages = [];
        for (let page = 1; page <= 100; page++) {{
            const response = await fetch(
                `/api/v1/stats/pv?filter=all&page=${{page}}&sort=pv`,
                {{credentials: "same-origin", cache: "no-store"}}
            );
            if (!response.ok) throw new Error(`note stats HTTP ${{response.status}}`);
            const envelope = await response.json();
            const data = envelope && envelope.data;
            if (!data || !Array.isArray(data.note_stats))
                throw new Error("note stats response is malformed");
            pages.push(data);
            if (data.last_page === true) return pages;
        }}
        throw new Error("note stats pagination exceeded 100 pages");
    }}''')

    payload = {{
        "sales_url": sales_url, "sales_body": sales_body,
        "purchases_url": purchases_url, "purchases_body": purchases_body,
        "stats_url": pg.url, "stats_pages": stats_pages,
    }}
    print("PAYLOAD_B64:" + base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"))
finally:
    ctx.close()
"""
    try:
        proc = run_browser_script(script)
    except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as e:
        return {"error": f"note browser driver failed to run: {e}"}
    if "NOTE_LOGIN_FAILED" in proc.stdout:
        NOTE_LOGIN_BACKOFF.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        NOTE_LOGIN_BACKOFF.unlink(missing_ok=True)
        with os.fdopen(os.open(NOTE_LOGIN_BACKOFF, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
            json.dump({"failed_at": datetime.now(timezone.utc).isoformat(),
                       "backoff_seconds": NOTE_LOGIN_BACKOFF_SECONDS}, handle)
    result = extract_payload(proc)
    if "payload" in result:
        NOTE_LOGIN_BACKOFF.unlink(missing_ok=True)
    return result


def measure_substack_pages(lang: str = "ja") -> dict:
    """Same shape as measure_note_pages: one ephemeral page, two page loads (overview home +
    earnings stats), raw body text handed back to the parent for regex parsing."""
    pub = substack_publication(lang)
    if not pub:
        return {"error": f"{SUBSTACK_TARGETS[lang][0][0]} missing (configure LIFE_MANAGER_ENV_FILE first)"}
    cookie_keys = SUBSTACK_TARGETS[lang][1]
    home_url = f"https://{pub}/publish/home"
    earnings_url = f"https://{pub}/publish/stats/earnings"
    script = f"""
import base64, json, os, sys, time
from cloakbrowser import launch_context

raw_cookie = next((value for key in {cookie_keys!r}
                   if (value := os.environ.get(key, "").strip())), "")
cookies = []
for item in raw_cookie.split(";"):
    name, separator, value = item.strip().partition("=")
    if separator and name:
        cookies.append({{"name": name, "value": value, "domain": ".substack.com", "path": "/"}})
if not cookies:
    print("SUBSTACK_COOKIE_MISSING")
    sys.exit(1)
ctx = launch_context(headless=True, humanize=False)
try:
    ctx.add_cookies(cookies)
    pg = ctx.new_page()
    pg.goto({home_url!r}, wait_until="domcontentloaded", timeout=40000)
    time.sleep(4)
    home_url_final = pg.url
    home_body = pg.evaluate("() => document.body.innerText")

    pg.goto({earnings_url!r}, wait_until="domcontentloaded", timeout=40000)
    time.sleep(4)
    earnings_url_final = pg.url
    earnings_body = pg.evaluate("() => document.body.innerText")
    # The JSON these two dashboard pages render (reactPublish bundle): the cards show 0 and
    # null alike as "-", the JSON does not.
    api = pg.evaluate('''async () => {{
        const read = async (path) => {{
            try {{
                const response = await fetch(path, {{credentials: "same-origin", cache: "no-store"}});
                return response.ok ? await response.json() : {{error: `HTTP ${{response.status}}`}};
            }} catch (error) {{
                return {{error: String(error)}};
            }}
        }};
        const pub = window._preloads && window._preloads.pub;
        const payouts = pub && Number.isInteger(pub.id)
            ? await read(`/api/v1/user_pub_stats/payouts?pubId=${{pub.id}}&limit=20`)
            : {{error: "publication id unavailable"}};
        return {{
            summary: await read("/api/v1/publish-dashboard/summary"),
            payouts,
            payout_totals: typeof payouts.currency === "string"
                ? await read(`/api/v1/payouts?currency=${{encodeURIComponent(payouts.currency)}}`)
                : {{error: "payout currency unavailable"}},
        }};
    }}''')

    payload = {{
        "home_url": home_url_final, "home_body": home_body,
        "earnings_url": earnings_url_final, "earnings_body": earnings_body,
        "api": api,
    }}
    print("PAYLOAD_B64:" + base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"))
finally:
    ctx.close()
"""
    try:
        proc = run_browser_script(script)
    except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as e:
        return {"error": f"substack browser driver failed to run: {e}"}
    return extract_payload(proc)


def parse_note_metrics(payload: dict) -> list[tuple[str, object, bool, str | None, str]]:
    """Returns a list of (metric, value, ok, reason, source_url) tuples. Regex-only, no LLM
    judgment (per task requirement): each label is anchored on its own literal Japanese heading,
    non-greedy up to the first matching amount, so the two "総額" occurrences on the sales page
    (this month's total vs the unpaid-transfer total) never get confused with each other."""
    sales_body = payload["sales_body"]
    purchases_body = payload["purchases_body"]
    out = []

    m = re.search(r"今月の売上.*?総額\s*\n?\s*¥\s*([\d,]+)", sales_body, re.S)
    if m:
        out.append(("sales_revenue", int(m.group(1).replace(",", "")), True, None, payload["sales_url"]))
    else:
        out.append((
            "sales_revenue", None, False,
            "label '今月の売上 ... 総額 ¥N' not found in note.com dashboard/salesmanage body text",
            payload["sales_url"],
        ))

    m2 = re.search(r"\d{4}年\d{1,2}月は購入者がいません", purchases_body)
    if m2:
        out.append(("sales_count", 0, True, None, payload["purchases_url"]))
    else:
        out.append((
            "sales_count", None, False,
            "no verified zero-purchase phrase ('<year>年<month>月は購入者がいません') found on "
            "note.com dashboard/sales -- a populated (non-zero) month's layout has not been "
            "observed yet in this account, so no safe count-extraction rule exists for it (do "
            "not guess a row-counting rule for an unseen layout)",
            payload["purchases_url"],
        ))
    return out


def _note_stats_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("note stats calculation time is missing")
    parsed = datetime.strptime(value, "%Y/%m/%d %H:%M").replace(tzinfo=JST)
    return parsed.astimezone(timezone.utc)


def _iso_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("artifact publication time is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("artifact publication time has no timezone")
    return parsed.astimezone(timezone.utc)


def parse_note_view_rows(
    pages: list[dict], artifacts: list[dict]
) -> list[dict]:
    """Turn a fully paginated authenticated note stats receipt into article views.

    note omits zero-view articles from this endpoint.  Absence is accepted as
    zero only after the terminal page, when every returned row has a positive
    read_count and the dashboard calculation happened after publication.
    """

    if not pages or pages[-1].get("last_page") is not True:
        raise ValueError("note stats pagination is incomplete")
    calculated_values = {page.get("last_calculate_at") for page in pages}
    ranges = {(page.get("start_date"), page.get("end_date")) for page in pages}
    if len(calculated_values) != 1 or len(ranges) != 1:
        raise ValueError("note stats pages do not share one frozen calculation")
    calculated_raw = next(iter(calculated_values))
    calculated = _note_stats_time(calculated_raw)
    observed_at = calculated.isoformat().replace("+00:00", "Z")
    stats: dict[str, dict] = {}
    for page in pages:
        values = page.get("note_stats")
        if not isinstance(values, list):
            raise ValueError("note stats page has no article collection")
        for item in values:
            if not isinstance(item, dict):
                raise ValueError("note stats article is malformed")
            key = item.get("key")
            read_count = item.get("read_count")
            if (
                not isinstance(key, str)
                or not key
                or not isinstance(read_count, int)
                or isinstance(read_count, bool)
                or read_count < 0
                or key in stats
            ):
                raise ValueError("note stats article identity/count is invalid")
            stats[key] = item
    omission_means_zero = bool(stats) and all(
        int(item["read_count"]) > 0 for item in stats.values()
    )
    pages_sha256 = hashlib.sha256(
        json.dumps(
            pages, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    rows = []
    for artifact in artifacts:
        if artifact.get("platform") != "note":
            continue
        artifact_id = artifact.get("artifact_id")
        key = artifact.get("public_id")
        live_url = artifact.get("live_url")
        if not all(isinstance(value, str) and value for value in (artifact_id, key, live_url)):
            raise ValueError("note artifact identity is incomplete")
        published = _iso_time(artifact.get("published_at"))
        item = stats.get(key)
        value: int | None = None
        reason = None
        ok = False
        if calculated < published:
            reason = "note stats calculation predates publication"
        elif item is not None:
            owner = item.get("user", {}).get("urlname") if isinstance(item.get("user"), dict) else None
            if not isinstance(owner, str) or f"note.com/{owner}/n/{key}" not in live_url:
                reason = "note stats owner/key differs from the live artifact"
            else:
                value = int(item["read_count"])
                ok = True
        elif omission_means_zero:
            value = 0
            ok = True
        else:
            reason = "complete note stats response does not prove absent article means zero"
        receipt = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "public_id": key,
            "published_at": artifact.get("published_at"),
            "observed_at": observed_at,
            "pages_sha256": pages_sha256,
            "read_count": value,
            "status": "scorable" if ok else "unknown",
        }
        row = {
            "ts": observed_at,
            "platform": "note",
            "metric": "views",
            "value": value,
            "source_url": NOTE_STATS_URL,
            "ok": ok,
            "status": "scorable" if ok else "unknown",
            "unit": "count",
            "window": "all_since_publication",
            "scope": "artifact",
            "artifact_id": artifact_id,
            "receipt_sha256": hashlib.sha256(
                json.dumps(
                    receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
        }
        if reason:
            row["reason"] = reason
        rows.append(row)
    return rows


def _substack_api(payload: dict) -> tuple[int | None, float | None]:
    """Paid subscribers and lifetime earnings (USD) as the dashboard JSON states them.

    Lifetime earnings is the earnings card's own sum: user_pub_stats/payouts.totalAmount +
    payouts.totalEarnings, both in minor units. Missing or malformed parts give None."""
    api = payload.get("api") if isinstance(payload.get("api"), dict) else {}
    part = {name: api[name] if isinstance(api.get(name), dict) else {}
            for name in ("summary", "payouts", "payout_totals")}

    def whole(name: str, key: str) -> int | None:
        value = part[name].get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    amount, earnings = whole("payouts", "totalAmount"), whole("payout_totals", "totalEarnings")
    usd = part["payouts"].get("currency") == part["payout_totals"].get("currency") == "usd"
    revenue = (amount + earnings) / 100 if usd and amount is not None and earnings is not None else None
    return whole("summary", "subscribers"), revenue


def _card_agrees(shown: str | None, value: float) -> bool:
    """Substack prints 0 and null alike as '-'; a card that shows a number must equal the JSON.

    No card means no visible anchor for the JSON field, so the value stays unknown."""
    if shown is None:
        return False
    if shown == "-":
        return value == 0
    cleaned = re.sub(r"[^\d.]", "", shown)
    return bool(cleaned) and abs(float(cleaned) - value) < 0.01


def parse_substack_metrics(payload: dict) -> list[tuple[str, object, bool, str | None, str]]:
    home_body = payload["home_body"]
    earnings_body = payload["earnings_body"]
    out = []
    api_paid, api_revenue = _substack_api(payload)

    m = re.search(r"(?:有料登録者|有料購読者)\s*\n\s*(-|[\d,]+)\s*\n\s*([\d,]+)から", home_body)
    if api_paid is not None and _card_agrees(m.group(1) if m else None, api_paid):
        out.append(("paid_subscribers", api_paid, True, None, payload["home_url"]))
    elif not m:
        out.append((
            "paid_subscribers", None, False,
            "'有料登録者' overview card not found in publish/home body text",
            payload["home_url"],
        ))
    else:
        raw, baseline = m.group(1), m.group(2).replace(",", "")
        if raw != "-":
            out.append(("paid_subscribers", int(raw.replace(",", "")), True, None, payload["home_url"]))
        else:
            out.append((
                "paid_subscribers", None, False,
                f"dashboard displays '-' instead of an explicit subscriber count (nearby baseline: "
                f"'{baseline}から'); a dash is not converted into a guessed zero",
                payload["home_url"],
            ))

    mrr = re.search(
        r"(?:月間経常収益|Monthly recurring revenue|MRR)"
        r"\s*\n\s*([^\n]+)",
        earnings_body,
        re.I,
    )
    # Substack shows no MRR card; zero paid subscribers measured above means zero recurring revenue.
    if out[0][2] is True and out[0][1] == 0 and (not mrr or mrr.group(1).strip() == "-"):
        out.append(("mrr", 0.0, True, None, payload["earnings_url"]))
    elif not mrr:
        out.append((
            "mrr", None, False,
            "monthly recurring revenue label not found in Substack earnings body text",
            payload["earnings_url"],
        ))
    else:
        raw_mrr = mrr.group(1).strip()
        cleaned_mrr = re.sub(r"[^\d.]", "", raw_mrr)
        if raw_mrr != "-" and cleaned_mrr:
            out.append((
                "mrr",
                float(cleaned_mrr),
                True,
                None,
                payload["earnings_url"],
            ))
        else:
            out.append((
                "mrr", None, False,
                f"dashboard does not display an explicit numeric MRR ({raw_mrr!r}); unknown is not zero",
                payload["earnings_url"],
            ))

    m2 = re.search(r"累計収益\s*\n\s*([^\n]+)\n\s*([^\n]*)", earnings_body)
    if api_revenue is not None and _card_agrees(m2.group(1).strip() if m2 else None, api_revenue):
        out.append(("revenue", api_revenue, True, None, payload["earnings_url"]))
    elif not m2:
        out.append((
            "revenue", None, False,
            "'累計収益' label not found in publish/stats/earnings body text",
            payload["earnings_url"],
        ))
    else:
        raw, note = m2.group(1).strip(), m2.group(2).strip()
        if raw != "-":
            cleaned = re.sub(r"[^\d.]", "", raw)
            if cleaned:
                out.append(("revenue", float(cleaned), True, None, payload["earnings_url"]))
            else:
                out.append((
                    "revenue", None, False,
                    f"could not parse a numeric revenue amount out of {raw!r}",
                    payload["earnings_url"],
                ))
        else:
            context = "no processed Stripe payments message is present" if "支払いが処理されると" in note else f"nearby text: {note!r}"
            out.append((
                "revenue", None, False,
                f"dashboard displays '-' instead of an explicit revenue amount ({context}); a "
                "dash is not converted into a guessed zero",
                payload["earnings_url"],
            ))
    return out


def build_rows(
    today: str,
    platform: str,
    metrics: list,
    fallback_url: str,
    artifact_index: dict | None = None,
) -> list[dict]:
    metadata = {
        ("note", "sales_revenue"): ("JPY", "current_calendar_month"),
        ("note", "sales_count"): ("purchases", "current_calendar_month"),
        ("substack", "paid_subscribers"): ("subscribers", "current"),
        ("substack", "mrr"): ("USD", "current_monthly_recurring"),
        ("substack", "revenue"): ("USD", "cumulative"),
    }
    rows = []
    for metric, value, ok, reason, source_url in metrics:
        unit, window = metadata.get(
            (platform, metric), ("unknown", "unknown")
        )
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "metric": metric,
            "value": value,
            "source_url": source_url or fallback_url,
            "ok": ok,
            "status": "scorable" if ok else "unknown",
            "unit": unit,
            "window": window,
        }
        if not ok:
            row["reason"] = reason
        # scope is decided by the (platform, metric) contract, never by the number itself:
        # an account-wide total can never become one article's revenue.
        rows.append(
            attribution.classify_sales_row(
                row, artifact_index or {"artifacts": {}, "by_url": {}}
            )
        )
    return rows


def load_note_artifacts(path: Path) -> list[dict]:
    artifacts = []
    if not path.is_file():
        return artifacts
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        language = row.get("lang") or row.get("language")
        if not (
            row.get("platform") == "note"
            and row.get("state") == "live"
            and row.get("published") is True
            and row.get("reality_gate") == "PASS"
            and row.get("verified") is True
            and isinstance(row.get("run_id"), str)
            and isinstance(language, str)
        ):
            continue
        artifacts.append({
            **row,
            "lang": language,
            "artifact_id": f"{row['run_id']}__note__{language}",
        })
    return artifacts


def unknown_note_view_rows(artifacts: list[dict], reason: str) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [
        {
            "ts": now,
            "platform": "note",
            "metric": "views",
            "value": None,
            "source_url": NOTE_STATS_URL,
            "ok": False,
            "status": "unknown",
            "unit": "count",
            "window": "all_since_publication",
            "scope": "artifact",
            "artifact_id": artifact["artifact_id"],
            "reason": reason,
        }
        for artifact in artifacts
    ]


def measure_platform(platform: str, metric_sources: list[tuple[str, str]], fetch_fn, parse_fn, today: str) -> list[dict]:
    try:
        result = fetch_fn()
        if "error" in result:
            reason = result["error"]
            metrics = [(name, None, False, reason, source_url) for name, source_url in metric_sources]
        else:
            metrics = parse_fn(result["payload"])
    except Exception as e:
        # One honest failure row per expected metric. A single platform's unexpected page or
        # parser change must not prevent the other platform from being measured and recorded.
        reason = f"unexpected {platform} measurement failure: {type(e).__name__}: {e}"
        metrics = [(name, None, False, reason, source_url) for name, source_url in metric_sources]
    return build_rows(today, platform, metrics, metric_sources[0][1])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument(
        "--articles",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "state/articles.jsonl",
    )
    args = p.parse_args(argv)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    note_artifacts = load_note_artifacts(args.articles)
    try:
        note_result = measure_note_pages()
        if "error" in note_result:
            raise ValueError(str(note_result["error"]))
        note_payload = note_result["payload"]
        rows += build_rows(
            today,
            "note",
            parse_note_metrics(note_payload),
            NOTE_SALES_URL,
        )
        rows += parse_note_view_rows(note_payload["stats_pages"], note_artifacts)
    except Exception as error:
        reason = f"note dashboard measurement unavailable: {type(error).__name__}: {error}"
        rows += build_rows(
            today,
            "note",
            [
                ("sales_revenue", None, False, reason, NOTE_SALES_URL),
                ("sales_count", None, False, reason, NOTE_PURCHASES_URL),
            ],
            NOTE_SALES_URL,
        )
        rows += unknown_note_view_rows(note_artifacts, reason)
    for lang in SUBSTACK_TARGETS:
        substack_pub = substack_publication(lang)
        if lang != "ja" and not substack_pub:
            continue  # optional publication not configured on this host
        # Each publication is its own account; its rows name it so JA and EN never mix.
        for row in measure_platform(
            "substack",
            [
                ("paid_subscribers", f"https://{substack_pub}/publish/home"),
                ("mrr", f"https://{substack_pub}/publish/stats/earnings"),
                ("revenue", f"https://{substack_pub}/publish/stats/earnings"),
            ],
            functools.partial(measure_substack_pages, lang), parse_substack_metrics, today,
        ):
            rows.append({**row, "publication": substack_pub})

    # Preserve the host's exact identity in the row whose hash money_sync stores.
    # Article run_id identifies the published product; keep it distinct from
    # the measurement run so per-artifact attribution remains unchanged.
    runtime_identity = {
        field: value
        for field, key in (
            ("measurement_run_id", "LIFE_MANAGER_RUN_ID"),
            ("owner_id", "LIFE_MANAGER_LOOP_ID"),
            ("occurrence_id", "LIFE_MANAGER_OCCURRENCE_ID"),
            ("release_sha", "LIFE_MANAGER_RELEASE_SHA"),
        )
        if (value := os.environ.get(key))
    }
    for row in rows:
        row.update(runtime_identity)

    with open(out_path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps({"date": today, "measured": len(rows), "results": rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
