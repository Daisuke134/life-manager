#!/usr/bin/env python3
"""Write the apply lane's ledger row from the model's structured report, in code.

X8b (2026-07-27). Measured: applied.jsonl held 224 rows and only 27 carried a
category (12%). category_bandit's arm is the category, so with no category there is
no arm -- the identity chain landed two payments on real applications
(observation_by_stage.paid=2) and the bandit still saw by_stage.paid=0, because both
rows had category=None. Every learner downstream (bandit, EVAL, keep/revert) was
optimising against a reward it structurally could not observe.

The cause was not a bug in the bandit. It was that no line of code had ever recorded
what an application WAS. gig_pass.sh does not contain the word "category"; the B2 step
prompt carried no field contract, so the ledger row was composed freehand by the model
and its shape drifted (price_jpy/price_proposed, ts/applied_at, evidence/evidence_dir).
The one artifact that did hold categories, ~/gig/_b2_candidates.json, was a model
output no code reads or writes, and it stopped on 7/20.

The fix follows the same rule as listing_ledger and lane_productivity: THE MODEL
REPORTS, THE CODE WRITES THE LEDGER. Under strict structured outputs the B2-only
schema carries a required-but-nullable `applications` array; this module turns its
rows into ledger rows.

Three properties make the resulting number trustworthy rather than merely present:

1. It cannot invent an application. A reported application is written only when the
   pass left a "<requestId>-submitted.png" behind -- the same proof normalize_applied
   requires, taken after the submission is visible on screen. An unproven report is
   counted, never written.

2. It cannot invent a category. A missing category is stored as null, and the gap
   shows up in category_bandit's coverage rather than being filled by a guess.

3. It records WHERE the category came from. category_source is "dom" when it was read
   off the page snapshot and "agent" when it is the model's own claim, so a later
   reader can discount self-report. Note as of 2026-07-27 no snapshot carries a
   category at all: cdp_nav_snapshot.py writes only {url,not_found,observed,title}, so
   every real row will be "agent" until that observation is added. The dom path is
   implemented and tested so the day it appears it wins automatically.

4. A silent model cannot erase a real browser side effect. Fresh
   "gig-*-B2-<requestId>-submitted.png" evidence recovers a minimal application row
   with category=None. b2_result_gate then rejects the contradictory model result,
   while the recovered identity makes the retry dedupe-safe.

Division of labour with normalize_applied.py: that module REPAIRS rows the model wrote
itself (fills ts, promotes status) and never adds a row. This module ADDS the reported
row, recovers a minimal proof-only row, or enriches an existing row that is missing a
category. It runs first, so anything it writes is already well-formed and the
normalizer has nothing to fix.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

_NORMALIZE = Path(__file__).resolve().parent / "normalize_applied.py"
_RETAINER_ULID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from market_snapshot import MARKET_FIELDS, empty_market  # noqa: E402


# A5-(1) (2026-07-31). Measured: bid_jpy on 0 of 311 rows, price_jpy on 95 (30%),
# and zero of the 90 loss rows carrying any price at all -- so the (price, outcome)
# pairs that could be joined were 8, all losses, and the AFT likelihood is monotone
# in the parameter. No pricing model could be fitted. Not fitted badly: not fitted.
#
# The B2 prompt has asked for price_jpy since X8b. Asking harder is the intervention
# that already failed, so these fields are stamped by the same rule this module
# already applies to identity and category: THE MODEL REPORTS, THE CODE WRITES THE
# LEDGER. The values come from the eligibility sidecar the submit path wrote at the
# moment of the click, never from the report.
#
# Every write path stamps the whole set, including the recovery paths, because a row
# that merely OMITS these keys is indistinguishable from a row whose market was
# nothing -- which is exactly the confusion that made 90 loss rows useless.
MARKET_LEDGER_FIELDS: tuple[str, ...] = MARKET_FIELDS + (
    "market_source",
    "market_missing",
)
MARKET_EVIDENCE_ABSENT = "submit_evidence_absent"
_MARKET_SIDECAR_GLOB = "*-submitted.eligibility.json"


def _valid_identity(value: object) -> bool:
    identity = str(value or "").strip()
    return bool(identity.isdigit() or _RETAINER_ULID.fullmatch(identity))


def _identity_bucket(identity: str) -> str:
    return "single" if identity.isdigit() else "retainer"


def _identity_sort_key(identity: str) -> tuple[int, int | str]:
    return (0, int(identity)) if identity.isdigit() else (1, identity)


def _proven_ids(evidence_root: Path) -> set[str]:
    """requestIds whose submission was photographed, per normalize_applied's rule.

    Imported rather than reimplemented so the two modules can never disagree about
    what counts as proof of an application.
    """
    spec = importlib.util.spec_from_file_location("normalize_applied", _NORMALIZE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._evidence_ids(evidence_root)


def _fresh_proven_ids(evidence_root: Path, min_mtime: float) -> set[str]:
    """Submission identities this pass proved even when the model omitted its row."""
    found: set[str] = set()
    try:
        candidates = evidence_root.glob("gig-*-B2-*-submitted.png")
        for path in candidates:
            match = re.fullmatch(
                r"gig-.*-B2-([0-9A-Z]+)-submitted\.png",
                path.name,
            )
            if not match:
                continue
            if not _valid_identity(match.group(1)):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if path.is_file() and stat.st_size > 0 and stat.st_mtime >= min_mtime:
                found.add(match.group(1))
    except OSError:
        return found
    return found


def _fresh_submit_intents(
    evidence_root: Path,
    min_mtime: float,
) -> dict[str, dict]:
    """Return fresh, filename-bound mutation intents for parent reconciliation."""
    found: dict[str, dict] = {}
    try:
        candidates = evidence_root.rglob("gig-*-B2-*-submitted.intent.json")
        for path in candidates:
            match = re.fullmatch(
                r"gig-.*-B2-([0-9A-Z]+)-submitted\.intent\.json",
                path.name,
            )
            if not match or not _valid_identity(match.group(1)):
                continue
            try:
                stat = path.stat()
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request_id = match.group(1)
            if (
                not path.is_file()
                or stat.st_size <= 0
                or stat.st_mtime < min_mtime
                or not isinstance(payload, dict)
                or str(payload.get("request_id") or "") != request_id
                or payload.get("bucket") != _identity_bucket(request_id)
                or payload.get("state") not in {"prepared", "confirmed"}
            ):
                continue
            parsed = urlparse(str(payload.get("url") or ""))
            expected_path = (
                f"/requests/{request_id}"
                if request_id.isdigit()
                else f"/job_matching/outsources/{request_id}"
            )
            if (
                parsed.hostname not in {"coconala.com", "www.coconala.com"}
                or parsed.path.rstrip("/") != expected_path
            ):
                continue
            found[request_id] = {**payload, "evidence": path.name}
    except OSError:
        return found
    return found


def _text(value: object) -> str | None:
    """A label is only a label if it survives stripping. Blank is missing, not empty."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _request_id_from_url(url: object) -> str | None:
    """The 募集 id as the page itself states it, so no filename is ever parsed."""
    if not isinstance(url, str):
        return None
    parts = urlparse(url).path.rstrip("/").split("/")
    tail = parts[-2] if parts and parts[-1] == "apply" and len(parts) > 1 else parts[-1]
    return tail if _valid_identity(tail) else None


def dom_categories(evidence_root: Path) -> dict[str, str]:
    """Categories recoverable from this pass's own page snapshots.

    Returns {} today: the live-DOM JSON the browser lane writes carries only
    url/not_found/observed/title. That emptiness is the honest answer, not a failure --
    claiming a category no snapshot contains is the one thing this file must not do.
    """
    found: dict[str, str] = {}
    try:
        entries = sorted(Path(evidence_root).glob("*-B2-*.json"))
    except OSError:
        return found
    for entry in entries:
        try:
            snapshot = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(snapshot, dict):
            continue
        category = _text(snapshot.get("category"))
        request_id = _request_id_from_url(snapshot.get("url"))
        if category and request_id:
            found[request_id] = category
    return found


def read_markets(*roots: Path) -> dict[str, dict]:
    """Markets observed by the submit path, keyed by the request they were read for.

    Identity comes from the payload's own `request_id`, not from the filename: the
    filename carries an abbreviated pass id and is written by a caller, while the
    request_id inside was written by the code that had the page open. Trusting the
    name is how one application's market ends up attached to another's row.
    """
    found: dict[str, dict] = {}
    for root in roots:
        try:
            paths = sorted(Path(root).rglob(_MARKET_SIDECAR_GLOB))
        except OSError:
            continue
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            request_id = _text(payload.get("request_id"))
            market = payload.get("market")
            if not request_id or not isinstance(market, dict):
                continue
            found[request_id] = market
    return found


def _stamp_market(row: dict, markets: dict[str, dict] | None) -> dict:
    """Give a ledger row the full market field set, present or explicitly absent."""
    request_id = str(row.get("requestId") or "")
    market = (markets or {}).get(request_id)
    if not isinstance(market, dict):
        market = empty_market(MARKET_EVIDENCE_ABSENT)
        source = None
    else:
        source = "submit_evidence"
    missing = market.get("missing")
    for field in MARKET_FIELDS:
        row[field] = market.get(field)
    row["market_source"] = source
    row["market_missing"] = dict(missing) if isinstance(missing, dict) else {}
    return row


def read_report(summary_path: Path, step_evidence: Path) -> list[dict]:
    """The applications the model reported, taken only from its validated result.

    The result is read through the runner summary, the same route b1_conversation_gate
    uses, and only when it names a file inside the step's own evidence directory. A
    summary that points anywhere else is not this step's output and is not trusted.
    """
    summary_path = Path(summary_path)
    step_evidence = Path(step_evidence).resolve()
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(summary, dict) or summary.get("status") != "success":
        return []
    raw_path = summary.get("result_path")
    if not isinstance(raw_path, str) or not raw_path:
        return []
    try:
        result_path = Path(raw_path).resolve()
        result_path.relative_to(step_evidence)
    except (OSError, ValueError):
        return []
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(result, dict):
        return []
    reported = result.get("applications")
    if not isinstance(reported, list):
        return []
    return [item for item in reported if isinstance(item, dict)]


def _is_application_row(row: dict) -> bool:
    """Application rows have no `action`; paid_progress rows do.

    This matters because a paid_progress row keys on the TALKROOM id while an
    application row keys on the 募集 id, and the two namespaces can collide. Matching
    on requestId alone would let a delivery reply suppress a real application's row.
    """
    return isinstance(row, dict) and "action" not in row and "_unparsed" not in row


def plan(
    *,
    report: list[dict],
    existing_rows: list[dict],
    proven: set[str],
    dom_categories: dict[str, str],
    now: float,
    pass_id: str,
    markets: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """Return the whole ledger as it should be, plus what changed. Pure, so testable."""
    rows = [dict(row) if isinstance(row, dict) else row for row in existing_rows]
    stats = {
        "appended": 0, "enriched": 0, "unproven": 0, "refused": 0,
        "skipped_duplicate": 0, "category_dom": 0, "category_agent": 0,
        "category_missing": 0,
    }

    for item in report:
        request_id = _text(item.get("request_id")) or _text(item.get("requestId"))
        if not request_id:
            stats["refused"] += 1
            continue
        if request_id not in proven:
            # The browser never showed the submission, so nothing here may claim it did.
            stats["unproven"] += 1
            continue

        category = dom_categories.get(request_id)
        source = "dom" if category else None
        if not category:
            category = _text(item.get("category"))
            source = "agent" if category else None
        if source == "dom":
            stats["category_dom"] += 1
        elif source == "agent":
            stats["category_agent"] += 1
        else:
            stats["category_missing"] += 1

        existing = next(
            (row for row in rows
             if _is_application_row(row) and str(row.get("requestId") or "") == request_id),
            None,
        )
        if existing is not None:
            stats["skipped_duplicate"] += 1
            # The model wrote its own row already. Adding a second would double-count a
            # single application, so the category is folded into the row that is there.
            # An existing label is never overwritten: it may have come from a better
            # source than this pass's report.
            if category and not _text(existing.get("category")):
                existing["category"] = category
                existing["category_source"] = source
                existing["category_recorded_at"] = int(now)
                stats["enriched"] += 1
            if not _text(existing.get("pass_id")):
                existing["pass_id"] = pass_id
            existing["submit_verified"] = True
            # The model wrote this row freehand, so it is exactly the row most
            # likely to be missing the market. Stamping it here is what makes the
            # guarantee hold for every application rather than for the tidy ones.
            _stamp_market(existing, markets)
            continue

        row = {
            "ts": int(now),
            "pass_id": pass_id,
            "requestId": request_id,
            "bucket": _text(item.get("bucket")) or _identity_bucket(request_id),
            "status": "applied",
            "category": category,
            "category_source": source,
            "evidence": f"{request_id}-submitted.png",
            "recorded_by": "application_report",
            "submit_verified": True,
        }
        for key, target in (
            ("title", "title"),
            ("price_jpy", "price_jpy"),
            ("deliver_date", "deliver_date"),
            ("url", "url"),
            ("compensation_type", "compensation_type"),
            ("weekly_days", "weekly_days"),
            ("weekly_hours_min", "weekly_hours_min"),
            ("weekly_hours_max", "weekly_hours_max"),
        ):
            value = item.get(key)
            if value not in (None, ""):
                row[target] = value
        _stamp_market(row, markets)
        rows.append(row)
        stats["appended"] += 1

    return rows, stats


def recover_from_proofs(
    *,
    existing_rows: list[dict],
    request_ids: set[str],
    now: float,
    pass_id: str,
    markets: dict[str, dict] | None = None,
) -> tuple[list[dict], int]:
    """Recover identity/counting from fresh browser proof, without inventing metadata."""
    rows = [dict(row) if isinstance(row, dict) else row for row in existing_rows]
    recovered = 0
    for request_id in sorted(request_ids, key=_identity_sort_key):
        existing = next(
            (
                row
                for row in rows
                if _is_application_row(row)
                and str(row.get("requestId") or "") == request_id
            ),
            None,
        )
        if existing is not None:
            continue
        rows.append(
            _stamp_market(
                {
                    "ts": int(now),
                    "pass_id": pass_id,
                    "requestId": request_id,
                    "bucket": _identity_bucket(request_id),
                    "status": "applied",
                    "category": None,
                    "category_source": None,
                    "evidence": f"{request_id}-submitted.png",
                    "recorded_by": "application_report_proof_recovery",
                },
                markets,
            )
        )
        recovered += 1
    return rows, recovered


def recover_from_intents(
    *,
    existing_rows: list[dict],
    intents: dict[str, dict],
    now: float,
    pass_id: str,
    markets: dict[str, dict] | None = None,
) -> tuple[list[dict], int]:
    """Create readback candidates without claiming the external effect succeeded."""
    rows = [dict(row) if isinstance(row, dict) else row for row in existing_rows]
    recovered = 0
    for request_id in sorted(intents, key=_identity_sort_key):
        intent = intents[request_id]
        existing = next(
            (
                row
                for row in rows
                if _is_application_row(row)
                and str(row.get("requestId") or "") == request_id
            ),
            None,
        )
        if existing is not None and (
            existing.get("submit_verified") is True
            and existing.get("applied_page_verified") is True
        ):
            continue
        candidate = existing if existing is not None else {}
        candidate.update({
            "ts": int(now),
            "pass_id": pass_id,
            "requestId": request_id,
            "bucket": _identity_bucket(request_id),
            "status": "reconcile_pending",
            "title": _text(intent.get("title")),
            "url": str(intent["url"]),
            "category": candidate.get("category"),
            "category_source": candidate.get("category_source"),
            "evidence": str(intent["evidence"]),
            "recorded_by": "application_report_intent_recovery",
            "submit_verified": False,
            "applied_page_verified": False,
        })
        _stamp_market(candidate, markets)
        if existing is None:
            rows.append(candidate)
        recovered += 1
    return rows, recovered


def _read_ledger(ledger: Path) -> list[dict]:
    rows: list[dict] = []
    if not ledger.exists():
        return rows
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # Preserved verbatim. Dropping a torn line would understate real work,
            # which is the exact failure this lane exists to stop.
            rows.append({"_unparsed": line})
    return rows


def _write_ledger(ledger: Path, rows: list[dict]) -> None:
    tmp = ledger.with_suffix(f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            if isinstance(row, dict) and "_unparsed" in row:
                handle.write(row["_unparsed"] + "\n")
            else:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, ledger)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner-summary", required=True, type=Path)
    ap.add_argument("--step-evidence", required=True, type=Path)
    ap.add_argument("--ledger", default=str(Path.home() / "gig" / "applied.jsonl"))
    ap.add_argument("--evidence-root", default=str(Path.home() / "gig" / "evidence"))
    ap.add_argument("--pass-id", default="")
    ap.add_argument("--min-mtime", default=0.0, type=float)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report = read_report(args.runner_summary, args.step_evidence)
    ledger = Path(args.ledger)
    before = _read_ledger(ledger)
    evidence_root = Path(args.evidence_root)
    # The screenshot lands under EVIDENCE_ROOT and the sidecar under the step's own
    # evidence dir (gig_pass.sh passes different paths for the two), so both are read.
    markets = read_markets(evidence_root, Path(args.step_evidence))
    rows, stats = plan(
        report=report,
        existing_rows=before,
        proven=_proven_ids(evidence_root),
        dom_categories=dom_categories(evidence_root),
        now=time.time(),
        pass_id=args.pass_id,
        markets=markets,
    )
    rows, recovered = recover_from_proofs(
        existing_rows=rows,
        request_ids=_fresh_proven_ids(evidence_root, args.min_mtime),
        now=time.time(),
        pass_id=args.pass_id,
        markets=markets,
    )
    rows, intent_recovered = recover_from_intents(
        existing_rows=rows,
        intents=_fresh_submit_intents(evidence_root, args.min_mtime),
        now=time.time(),
        pass_id=args.pass_id,
        markets=markets,
    )

    changed = rows != before
    if not args.dry_run and changed:
        _write_ledger(ledger, rows)
    print(json.dumps({
        "status": (
            "dry_run"
            if args.dry_run
            else ("written" if changed else ("no_report" if not report else "unchanged"))
        ),
        "reported": len(report),
        "recovered_from_proof": recovered,
        "recovered_from_intent": intent_recovered,
        **stats,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
