#!/usr/bin/env python3
"""Independently verify new applications on Coconala's applied-offers page.

The B2 agent performs the customer-facing submit.  After it exits, parent code opens
a separate authenticated CDP context, reads the canonical applied-offers page, and
marks only current-pass ledger rows whose request identity is visible there.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets


APPLIED_OFFERS_URL = "https://coconala.com/mypage/job_matching/applied/offers"
RETAINER_APPLIED_URL = (
    "https://coconala.com/mypage/job_matching/applied/outsource_applications"
)
LOAD_TIMEOUT_SECONDS = 30
RETAINER_HYDRATION_TIMEOUT_SECONDS = 5
RETAINER_ULID_PATTERN = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")

# Exit contract.  A failure to READ the applied page and a failure to APPLY are
# different facts and the pass must never confuse them: only the second one says
# anything about a submission, and only the second one is evidence the loop can
# act on.  0 = every claim agreed, 1 = a claimed application is absent from the
# canonical page, EXIT_UNREADABLE = the page was never observed at all.
EXIT_VERIFICATION_MISMATCH = 1
EXIT_UNREADABLE = 3

# Coconala indexes a submit asynchronously, so a single DOM read is not proof of
# absence.  Re-read a bounded number of times with growing backoff before any
# identity is called absent.
READBACK_ATTEMPTS = 3
READBACK_BACKOFF_SECONDS = 4.0


def _valid_identity(value: object) -> bool:
    identity = str(value or "").strip()
    return bool(identity.isdigit() or RETAINER_ULID_PATTERN.fullmatch(identity))


def _identity_sort_key(identity: str) -> tuple[int, int | str]:
    return (0, int(identity)) if identity.isdigit() else (1, identity)


def extract_request_ids(hrefs: list[object]) -> list[str]:
    """Return stable request IDs from public request links on the applied page."""
    found: set[str] = set()
    for value in hrefs:
        if not isinstance(value, str):
            continue
        parsed = urlsplit(value)
        if parsed.hostname not in {"coconala.com", "www.coconala.com"}:
            continue
        match = re.fullmatch(r"/(?:job_matching/)?requests/(\d+)/?", parsed.path)
        if match:
            found.add(match.group(1))
    return sorted(found, key=int)


def extract_retainer_ids(hrefs: list[object]) -> list[str]:
    """Return stable retainer ULIDs from the canonical applied-retainer page."""
    found: set[str] = set()
    for value in hrefs:
        if not isinstance(value, str):
            continue
        parsed = urlsplit(value)
        if parsed.hostname not in {"coconala.com", "www.coconala.com"}:
            continue
        match = re.fullmatch(
            r"/job_matching/outsources/([0-7][0-9A-HJKMNP-TV-Z]{25})/?",
            parsed.path,
        )
        if match:
            found.add(match.group(1))
    return sorted(found)


def _normalized_title(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_offer_fields(text: object) -> dict[str, object]:
    """Parse seller-owned values rendered on an applied-offer card."""
    body = _normalized_title(text)
    result: dict[str, object] = {}
    amount = re.search(r"提案額\s*[:：]?\s*([\d,]+)\s*円", body)
    if amount:
        result["price_jpy"] = int(amount.group(1).replace(",", ""))
    due = re.search(r"納品予定日\s*[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", body)
    if due:
        result["deliver_date"] = f"{int(due.group(1)):04d}-{int(due.group(2)):02d}-{int(due.group(3)):02d}"
    return result


def match_retainer_ids_by_title(
    cards: list[object],
    expected_titles: dict[str, str],
) -> tuple[set[str], list[dict[str, str]]]:
    """Bind a hidden listing ULID only when its applied-card title is unique."""
    indexed: dict[str, list[dict[str, str]]] = {}
    for raw in cards:
        if not isinstance(raw, dict):
            continue
        title = _normalized_title(raw.get("title"))
        talkroom_url = str(raw.get("talkroom_url") or "")
        if not title or not talkroom_url:
            continue
        indexed.setdefault(title, []).append({
            "title": title,
            "talkroom_url": talkroom_url,
        })
    matched: set[str] = set()
    observations: list[dict[str, str]] = []
    for request_id, raw_title in expected_titles.items():
        title = _normalized_title(raw_title)
        candidates = indexed.get(title, [])
        if (
            not _valid_identity(request_id)
            or request_id.isdigit()
            or len(candidates) != 1
        ):
            continue
        matched.add(request_id)
        observations.append({
            "request_id": request_id,
            "bucket": "retainer",
            "offer_url": candidates[0]["talkroom_url"],
            "title": title,
            "identity_binding": "exact_title_unique",
        })
    return matched, observations


def extract_request_id(detail: dict[str, Any]) -> str | None:
    """Recover the request identity exposed by Coconala's offer-edit page."""
    hidden = str(detail.get("hidden_request_id") or "").strip()
    if re.fullmatch(r"\d+", hidden):
        return hidden
    linked = extract_request_ids(detail.get("hrefs") or [])
    if linked:
        return linked[0]
    match = re.search(r"\(\s*No\.(\d+)\s*\)", str(detail.get("body") or ""))
    return match.group(1) if match else None


def claims_submission(row: dict[str, Any]) -> bool:
    """True when the ledger row asserts the irreversible submit already happened.

    `application_report.recover_from_intents` deliberately writes the opposite --
    a candidate that does NOT claim the external effect succeeded -- because the
    intent file it recovers from is written BEFORE the click, purely so a lost ACK
    cannot lose the identity.  Only a row that claims a submit can disagree with
    the applied page; a candidate that is absent has simply been answered.
    """
    return (
        row.get("submit_verified") is True
        or str(row.get("status") or "") == "applied"
    )


def reconcile_rows(
    rows: list[dict[str, Any]],
    *,
    pass_id: str,
    observed_ids: set[str],
    evidence_path: str,
    observed_at: int,
    observations: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Attach code-owned readback proof only to this pass's observed applications."""
    reconciled = [dict(row) for row in rows]
    by_id = {
        str(observation.get("request_id") or ""): observation
        for observation in (observations or [])
        if isinstance(observation, dict)
    }
    stats = {"current_pass": 0, "verified": 0, "missing": 0, "unresolved": 0}
    for row in reconciled:
        if "action" in row or str(row.get("pass_id") or "") != pass_id:
            continue
        request_id = str(row.get("requestId") or row.get("request_id") or "")
        if not request_id:
            continue
        stats["current_pass"] += 1
        if request_id not in observed_ids:
            # Absence is recorded on the row either way; what differs is the
            # verdict.  A claimed submit that the canonical page cannot confirm is
            # a real three-way disagreement.  A candidate that is absent stays
            # exactly what it was -- unverified, uncounted, reconcilable -- and is
            # never upgraded and never re-submitted on the strength of this read.
            row["applied_page_absent_at"] = int(observed_at)
            row["applied_page_absent_checks"] = (
                int(row.get("applied_page_absent_checks") or 0) + 1
            )
            row["applied_page_absent_evidence"] = evidence_path
            if claims_submission(row):
                stats["missing"] += 1
                continue
            stats["unresolved"] += 1
            row["status"] = "reconcile_pending"
            row["submit_verified"] = False
            row["applied_page_verified"] = False
            continue
        row["submit_verified"] = True
        row["applied_page_verified"] = True
        row["status"] = "applied"
        row["applied_page_verified_at"] = int(observed_at)
        row["applied_page_evidence"] = evidence_path
        observation = by_id.get(request_id) or {}
        if _normalized_title(observation.get("title")):
            row["title"] = _normalized_title(observation["title"])
        # The applied-offers card is the seller-owned source of truth for these
        # fields. Replace stale/model-reported values after identity readback.
        if observation.get("price_jpy") is not None:
            row["price_jpy"] = observation["price_jpy"]
        if observation.get("deliver_date"):
            row["deliver_date"] = observation["deliver_date"]
            row["delivery_date"] = observation["deliver_date"]
        if observation.get("offer_url"):
            row["offer_url"] = str(observation["offer_url"])
        stats["verified"] += 1
    return reconciled, stats


async def _call(
    ws: Any, method: str, params: dict[str, Any], call_id: int
) -> dict[str, Any]:
    await ws.send(json.dumps({"id": call_id, "method": method, "params": params}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=LOAD_TIMEOUT_SECONDS)
        message = json.loads(raw)
        if message.get("id") != call_id:
            continue
        if "error" in message:
            raise RuntimeError(f"{method}:{message['error']}")
        return message.get("result", {})


async def _wait_for_retainer_page(
    ws: Any,
    call_id: int,
    *,
    expected_titles: dict[str, str],
    poll_seconds: float = 0.25,
    timeout_seconds: float = RETAINER_HYDRATION_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], int]:
    """Wait for Next.js to hydrate applied-retainer cards after readyState."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        result = await _call(
            ws,
            "Runtime.evaluate",
            {
                "expression": """JSON.stringify({
                  url: location.href,
                  title: document.title,
                  hrefs: [...document.querySelectorAll("a[href]")].map(a => a.href),
                  cards: [...document.querySelectorAll(
                    "a[href*='/mypage/job_matching/job_talkroom/']"
                  )].map(a => ({
                    title: (a.innerText || '').trim(),
                    talkroom_url: a.href
                  })),
                  body_sample: (document.body?.innerText || '').slice(0, 12000),
                  not_found: /404|ページが見つかりません|お探しのページ/.test(
                    document.title + ' ' + (document.body?.innerText || '')
                  )
                })""",
                "returnByValue": True,
            },
            call_id,
        )
        call_id += 1
        raw = result.get("result", {}).get("value")
        if not isinstance(raw, str):
            raise RuntimeError("retainer_readback_dom_missing")
        page = json.loads(raw)
        cards = page.get("cards")
        normalized_observed_titles = {
            _normalized_title(card.get("title"))
            for card in cards or []
            if isinstance(card, dict)
        }
        normalized_expected_titles = {
            _normalized_title(title)
            for title in expected_titles.values()
            if _normalized_title(title)
        }
        if (
            normalized_observed_titles & normalized_expected_titles
            or asyncio.get_running_loop().time() >= deadline
        ):
            return page, call_id
        if poll_seconds:
            await asyncio.sleep(poll_seconds)


async def capture_readback(
    ws_url: str,
    *,
    screenshot_path: Path,
    expected_ids: set[str],
    expected_retainer_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Navigate a fresh leased target and capture machine-readable page evidence."""
    async with websockets.connect(
        ws_url, ping_interval=None, open_timeout=10, max_size=40 * 1024 * 1024
    ) as ws:
        call_id = 1
        await _call(ws, "Page.enable", {}, call_id)
        call_id += 1
        await _call(
            ws, "Page.navigate", {"url": APPLIED_OFFERS_URL}, call_id
        )
        call_id += 1
        deadline = asyncio.get_running_loop().time() + LOAD_TIMEOUT_SECONDS
        while True:
            ready = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": "document.readyState",
                    "returnByValue": True,
                },
                call_id,
            )
            call_id += 1
            state = ready.get("result", {}).get("value")
            if state in {"interactive", "complete"}:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("navigation_timeout")
            await asyncio.sleep(0.2)
        evaluated = await _call(
            ws,
            "Runtime.evaluate",
            {
                "expression": """JSON.stringify({
                  url: location.href,
                  title: document.title,
                  cards: [...document.querySelectorAll("a[href*='/mypage/offers/']")]
                    .map(a => {
                      const card = a.closest('.d-offerContents_contentsWrapper');
                      return {
                        offer_url: a.href,
                        title: (card?.querySelector(
                          '.d-offerContents_applicationTitle'
                        )?.innerText || '').trim(),
                        card_text: (card?.innerText || '').trim()
                      };
                    })
                    .filter((x, i, all) =>
                      x.offer_url && all.findIndex(y => y.offer_url === x.offer_url) === i
                    ),
                  has_next_page: !!document.querySelector(
                    "a[href*='/applied/offers?page=']"
                  ),
                  body_sample: (document.body?.innerText || '').slice(0, 12000),
                  not_found: /404|ページが見つかりません|お探しのページ/.test(
                    document.title + ' ' + (document.body?.innerText || '')
                  )
                })""",
                "returnByValue": True,
            },
            call_id,
        )
        call_id += 1
        raw_value = evaluated.get("result", {}).get("value")
        if not isinstance(raw_value, str):
            raise RuntimeError("readback_dom_missing")
        page = json.loads(raw_value)
        parsed = urlsplit(str(page.get("url") or ""))
        if (
            parsed.hostname not in {"coconala.com", "www.coconala.com"}
            or parsed.path.rstrip("/") != urlsplit(APPLIED_OFFERS_URL).path
        ):
            raise RuntimeError(f"applied_page_route_mismatch:{page.get('url')}")
        if page.get("not_found") is True:
            raise RuntimeError("applied_page_not_found")
        shot = await _call(
            ws, "Page.captureScreenshot", {"format": "png"}, call_id
        )
        encoded = shot.get("data")
        if not encoded:
            raise RuntimeError("applied_page_screenshot_missing")
        observations: list[dict[str, Any]] = []
        observed_ids: set[str] = set()
        expected_single_ids = {value for value in expected_ids if value.isdigit()}
        expected_retainer_ids = expected_ids - expected_single_ids
        for card in page.get("cards") or []:
            if observed_ids >= expected_single_ids:
                break
            offer_url = str(card.get("offer_url") or "")
            if not re.fullmatch(r"https://(?:www\.)?coconala\.com/mypage/offers/\d+", offer_url):
                continue
            await _call(ws, "Page.navigate", {"url": offer_url}, call_id)
            call_id += 1
            detail_deadline = asyncio.get_running_loop().time() + LOAD_TIMEOUT_SECONDS
            while True:
                ready = await _call(
                    ws,
                    "Runtime.evaluate",
                    {"expression": "document.readyState", "returnByValue": True},
                    call_id,
                )
                call_id += 1
                if ready.get("result", {}).get("value") in {"interactive", "complete"}:
                    break
                if asyncio.get_running_loop().time() >= detail_deadline:
                    raise RuntimeError(f"offer_navigation_timeout:{offer_url}")
                await asyncio.sleep(0.1)
            detail_result = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": """JSON.stringify({
                      url: location.href,
                      hidden_request_id:
                        document.querySelector('#OfferRequestId')?.value || null,
                      hrefs: [...document.querySelectorAll(
                        "a[href*='/requests/'],a[href*='/job_matching/requests/']"
                      )].map(a => a.href),
                      body: (document.body?.innerText || '').slice(0, 5000)
                    })""",
                    "returnByValue": True,
                },
                call_id,
            )
            call_id += 1
            detail_raw = detail_result.get("result", {}).get("value")
            if not isinstance(detail_raw, str):
                continue
            detail = json.loads(detail_raw)
            request_id = extract_request_id(detail)
            if request_id is None:
                continue
            observed_ids.add(request_id)
            observations.append({
                "request_id": request_id,
                "bucket": "single",
                "offer_url": offer_url,
                "title": str(card.get("title") or ""),
                **_parse_offer_fields(card.get("card_text")),
            })
        observed_urls = [APPLIED_OFFERS_URL]
        retainer_page: dict[str, Any] | None = None
        if expected_retainer_ids:
            await _call(
                ws, "Page.navigate", {"url": RETAINER_APPLIED_URL}, call_id
            )
            call_id += 1
            retainer_deadline = (
                asyncio.get_running_loop().time() + LOAD_TIMEOUT_SECONDS
            )
            while True:
                ready = await _call(
                    ws,
                    "Runtime.evaluate",
                    {
                        "expression": "document.readyState",
                        "returnByValue": True,
                    },
                    call_id,
                )
                call_id += 1
                if ready.get("result", {}).get("value") in {
                    "interactive",
                    "complete",
                }:
                    break
                if (
                    asyncio.get_running_loop().time()
                    >= retainer_deadline
                ):
                    raise RuntimeError("retainer_readback_navigation_timeout")
                await asyncio.sleep(0.2)
            retainer_page, call_id = await _wait_for_retainer_page(
                ws,
                call_id,
                expected_titles=expected_retainer_titles or {},
            )
            parsed_retainer = urlsplit(
                str(retainer_page.get("url") or "")
            )
            if (
                parsed_retainer.hostname
                not in {"coconala.com", "www.coconala.com"}
                or parsed_retainer.path.rstrip("/")
                != urlsplit(RETAINER_APPLIED_URL).path
            ):
                raise RuntimeError(
                    "retainer_applied_page_route_mismatch:"
                    f"{retainer_page.get('url')}"
                )
            if retainer_page.get("not_found") is True:
                raise RuntimeError("retainer_applied_page_not_found")
            retainer_ids = set(
                extract_retainer_ids(retainer_page.get("hrefs") or [])
            )
            title_ids, title_observations = match_retainer_ids_by_title(
                retainer_page.get("cards") or [],
                expected_retainer_titles or {},
            )
            retainer_ids.update(title_ids)
            observed_ids.update(retainer_ids)
            observed_urls.append(RETAINER_APPLIED_URL)
            observations.extend(
                {
                    "request_id": request_id,
                    "bucket": "retainer",
                    "offer_url": (
                        "https://coconala.com/job_matching/outsources/"
                        f"{request_id}"
                    ),
                    "title": "",
                }
                for request_id in sorted(retainer_ids)
                if request_id not in title_ids
            )
            observations.extend(title_observations)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_bytes(base64.b64decode(encoded))
    return {
        "source": "code_owned_cdp_readback",
        "url": page["url"],
        "urls": observed_urls,
        "title": page.get("title"),
        "observed": True,
        "not_found": False,
        "request_ids": sorted(observed_ids, key=_identity_sort_key),
        "offers": observations,
        # Scope of the absence claim, recorded so it is never read as more than it
        # is.  Only the first applied-offers page is walked.  Measured live
        # 2026-07-31: the list is 20 cards per page over 10 pages and is ordered
        # strictly newest-offer-first and monotonically across every page
        # (92000009 down to 92000004), so an application submitted during this wake
        # is always on page 1.  That is what makes page-1 absence conclusive for a
        # same-wake submit -- and it stops being conclusive the moment Coconala
        # changes that ordering, which is why both facts are written down.
        "cards_seen": len(page.get("cards") or []),
        "has_next_page": bool(page.get("has_next_page")),
        "pages_walked": 1,
        "body_sample": page.get("body_sample") or "",
        "screenshot_path": str(screenshot_path.resolve()),
    }


def capture_with_retry(
    capture: Any,
    *,
    expected_ids: set[str],
    attempts: int,
    backoff_seconds: float,
    sleeper: Any,
) -> tuple[dict[str, Any], int]:
    """Re-read the applied page until every expected identity appears, bounded.

    Coconala does not index a submit synchronously, so one read that misses an
    identity is a race, not a verdict.  Retrying costs seconds; declaring a landed
    submit absent costs a duplicate application.
    """
    if int(attempts) < 1:
        raise ValueError("readback_attempts_invalid")
    captured = capture()
    used = 1
    while used < int(attempts):
        observed = {
            str(value) for value in (captured.get("request_ids") or [])
        }
        if expected_ids.issubset(observed):
            break
        sleeper(float(backoff_seconds) * used)
        captured = capture()
        used += 1
    return captured, used


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            rows.append({"_unparsed": raw})
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            if "_unparsed" in row:
                handle.write(str(row["_unparsed"]) + "\n")
            else:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ws")
    source.add_argument("--fixture", type=Path)
    parser.add_argument("--pass-id", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--screenshot", required=True, type=Path)
    args = parser.parse_args()
    try:
        rows = _read_ledger(args.ledger)
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(error).__name__}:{error}"},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return EXIT_VERIFICATION_MISMATCH
    try:
        expected_ids = {
            str(row.get("requestId") or row.get("request_id") or "")
            for row in rows
            if "action" not in row
            and str(row.get("pass_id") or "") == args.pass_id
            and _valid_identity(
                row.get("requestId") or row.get("request_id")
            )
        }
        expected_retainer_titles = {
            str(row.get("requestId") or row.get("request_id") or ""):
            str(row.get("title") or "")
            for row in rows
            if "action" not in row
            and str(row.get("pass_id") or "") == args.pass_id
            and RETAINER_ULID_PATTERN.fullmatch(
                str(row.get("requestId") or row.get("request_id") or "")
            )
        }
        if args.fixture is not None:
            captured = json.loads(args.fixture.read_text(encoding="utf-8"))
            if (
                captured.get("source") != "code_owned_cdp_readback"
                or captured.get("observed") is not True
                or not {
                    urlsplit(str(url)).path.rstrip("/")
                    for url in (
                        captured.get("urls")
                        or [captured.get("url")]
                    )
                }.issubset({
                    "/mypage/job_matching/applied/offers",
                    "/mypage/job_matching/applied/outsource_applications",
                })
            ):
                raise RuntimeError("readback_fixture_invalid")
            attempts_used = 1
        else:
            captured, attempts_used = capture_with_retry(
                lambda: asyncio.run(
                    capture_readback(
                        args.ws,
                        screenshot_path=args.screenshot,
                        expected_ids=expected_ids,
                        expected_retainer_titles=expected_retainer_titles,
                    )
                ),
                expected_ids=expected_ids,
                attempts=int(
                    os.environ.get("GIG_B2_READBACK_ATTEMPTS")
                    or READBACK_ATTEMPTS
                ),
                backoff_seconds=float(
                    os.environ.get("GIG_B2_READBACK_BACKOFF_SECONDS")
                    or READBACK_BACKOFF_SECONDS
                ),
                sleeper=time.sleep,
            )
        if captured.get("observed") is not True:
            raise RuntimeError("applied_page_not_observed")
    except Exception as error:
        # Nothing was observed, so nothing may be concluded about any submit and
        # the canonical ledger is left exactly as it was.
        print(
            json.dumps(
                {
                    "ok": False,
                    "unreadable": True,
                    "error": f"{type(error).__name__}:{error}",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return EXIT_UNREADABLE
    try:
        observed_at = int(time.time())
        observed_ids = {str(value) for value in (captured.get("request_ids") or [])}
        reconciled, stats = reconcile_rows(
            rows,
            pass_id=args.pass_id,
            observed_ids=observed_ids,
            evidence_path=str(args.output.resolve()),
            observed_at=observed_at,
            observations=captured.get("offers"),
        )
        payload = {
            **captured,
            "pass_id": args.pass_id,
            "observed_at": observed_at,
            "readback_attempts": int(attempts_used),
            "current_pass_count": stats["current_pass"],
            "verified_count": stats["verified"],
            "missing_count": stats["missing"],
            "unresolved_count": stats["unresolved"],
            "applied_page_absent_request_ids": sorted(
                expected_ids - observed_ids, key=_identity_sort_key
            ),
        }
        _atomic_json(args.output, payload)
        # The page WAS read, so every identity it confirmed keeps its proof even
        # when a sibling row disagreed.  Withholding the whole write on one
        # mismatch is how genuinely submitted applications stayed uncounted.
        _write_ledger(args.ledger, reconciled)
        if stats["missing"]:
            print(json.dumps({"ok": False, **stats}, separators=(",", ":")))
            return EXIT_VERIFICATION_MISMATCH
        print(json.dumps({"ok": True, **stats}, separators=(",", ":")))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(error).__name__}:{error}"},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
