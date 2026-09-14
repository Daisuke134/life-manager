#!/usr/bin/env python3
"""Recover real Coconala applications whose helper ACK was lost.

This is deliberately narrower than a generic ledger repair: every candidate must
come from an archived live-DOM observation, and every identity must be present in a
fresh code-owned read of Coconala's canonical applied pages before the ledger changes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coconala_applied_readback as readback


RETAINER_ULID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")


def _title(value: object) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"\s*[|｜]\s*ココナラ.*$", "", title).strip()


def candidate_from_evidence(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("observed") is not True
        or payload.get("not_found") is not False
    ):
        raise ValueError(f"candidate_live_dom_invalid:{path}")
    parsed = urlsplit(str(payload.get("url") or ""))
    single = re.fullmatch(r"/requests/(\d+)/?", parsed.path)
    retainer = re.fullmatch(
        r"/job_matching/outsources/([0-7][0-9A-HJKMNP-TV-Z]{25})/?",
        parsed.path,
    )
    if parsed.hostname not in {"coconala.com", "www.coconala.com"} or not (
        single or retainer
    ):
        raise ValueError(f"candidate_url_invalid:{path}")
    request_id = (single or retainer).group(1)
    title = _title(payload.get("title"))
    if not title:
        raise ValueError(f"candidate_title_missing:{path}")
    pass_id = ""
    for parent in path.parents:
        if parent.name.startswith("gig-pass-"):
            pass_id = parent.name.removeprefix("gig-pass-")
            break
    if not pass_id:
        raise ValueError(f"candidate_pass_id_missing:{path}")
    return {
        "request_id": request_id,
        "bucket": "single" if request_id.isdigit() else "retainer",
        "title": title,
        "url": str(payload["url"]),
        "pass_id": pass_id,
        "source_evidence": str(path.resolve()),
    }


def reconcile_orphans(
    rows: list[dict[str, Any]],
    *,
    candidates: list[dict[str, str]],
    captured: dict[str, Any],
    recovery_id: str,
    observed_at: int,
    evidence_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected = {candidate["request_id"] for candidate in candidates}
    observed = {
        str(value)
        for value in captured.get("request_ids") or []
        if str(value)
    }
    missing = expected - observed
    if missing:
        raise ValueError("canonical_application_missing:" + ",".join(sorted(missing)))
    offers = {
        str(offer.get("request_id") or ""): offer
        for offer in captured.get("offers") or []
        if isinstance(offer, dict)
    }
    reconciled = [dict(row) for row in rows]
    applications: list[dict[str, Any]] = []
    for candidate in candidates:
        request_id = candidate["request_id"]
        existing = next(
            (
                row
                for row in reconciled
                if "action" not in row
                and str(row.get("requestId") or row.get("request_id") or "")
                == request_id
            ),
            None,
        )
        row = existing if existing is not None else {}
        offer = offers.get(request_id) or {}
        row.update({
            "ts": observed_at,
            "pass_id": candidate["pass_id"],
            "requestId": request_id,
            "bucket": candidate["bucket"],
            "status": "applied",
            "title": candidate["title"],
            "url": candidate["url"],
            "offer_url": str(offer.get("offer_url") or ""),
            "category": row.get("category"),
            "category_source": row.get("category_source"),
            "recorded_by": "canonical_orphan_reconciliation",
            "recovery_id": recovery_id,
            "source_evidence": candidate["source_evidence"],
            "submit_verified": True,
            "applied_page_verified": True,
            "applied_page_verified_at": observed_at,
            "applied_page_evidence": str(evidence_path.resolve()),
        })
        if existing is None:
            reconciled.append(row)
        applications.append({
            "request_id": request_id,
            "bucket": candidate["bucket"],
            "title": candidate["title"],
            "url": candidate["url"],
            "offer_url": row["offer_url"],
            "pass_id": candidate["pass_id"],
        })
    payload = {
        "source": "canonical_orphan_reconciliation",
        "recovery_id": recovery_id,
        "observed_at": observed_at,
        "request_ids": sorted(expected),
        "applications": applications,
        "canonical_readback": captured,
    }
    return reconciled, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--candidate", action="append", required=True, type=Path)
    parser.add_argument("--recovery-id", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--screenshot", required=True, type=Path)
    args = parser.parse_args()
    try:
        candidates = [candidate_from_evidence(path) for path in args.candidate]
        identities = [candidate["request_id"] for candidate in candidates]
        if len(identities) != len(set(identities)):
            raise ValueError("candidate_duplicate")
        expected_titles = {
            candidate["request_id"]: candidate["title"]
            for candidate in candidates
            if candidate["bucket"] == "retainer"
        }
        captured = asyncio.run(readback.capture_readback(
            args.ws,
            screenshot_path=args.screenshot,
            expected_ids=set(identities),
            expected_retainer_titles=expected_titles,
        ))
        rows, payload = reconcile_orphans(
            readback._read_ledger(args.ledger),
            candidates=candidates,
            captured=captured,
            recovery_id=args.recovery_id,
            observed_at=int(time.time()),
            evidence_path=args.output,
        )
        readback._atomic_json(args.output, payload)
        readback._write_ledger(args.ledger, rows)
        print(json.dumps({
            "ok": True,
            "recovery_id": args.recovery_id,
            "verified": len(payload["applications"]),
            "output": str(args.output.resolve()),
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "error": f"{type(error).__name__}:{error}",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
