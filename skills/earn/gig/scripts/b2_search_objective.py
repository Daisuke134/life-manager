#!/usr/bin/env python3
"""Persist the B2 application-search objective across hourly process wakes."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit


_RETAINER_ULID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
_CATEGORY_PATH = re.compile(r"/requests/categories/\d+")
_MARKET_REFRESH_CURSOR = {
    "source_id": "single:new",
    "previous_url": "https://coconala.com/requests?sort=new&recruiting=true",
    "next_url": "https://coconala.com/requests?sort=new&recruiting=true&page=2",
    "reason": "continue_official_open_pages_after_refresh",
}
_WAKE_REFRESH_CURSOR = {
    "source_id": "single:new",
    "previous_url": "",
    "next_url": "https://coconala.com/requests?sort=new&recruiting=true",
    "reason": "newest_first_each_wake",
}


def _valid_request_id(value: Any) -> bool:
    request_id = str(value or "").strip()
    return bool(request_id.isdigit() or _RETAINER_ULID.fullmatch(request_id))


def _valid_search_url(value: Any, *, allow_empty: bool = False) -> bool:
    text = str(value or "")
    if allow_empty and not text:
        return True
    parsed = urlsplit(text)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"coconala.com", "www.coconala.com"}
        and (
            parsed.path
            in {
                "/requests",
                "/job_matching/requests",
                "/job_matching/outsources",
            }
            or _CATEGORY_PATH.fullmatch(parsed.path) is not None
        )
    )


def _newest_page(value: str, *, recruiting: bool) -> int | None:
    parsed = urlsplit(value)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    expected = [("sort", "new")] + (
        [("recruiting", "true")] if recruiting else []
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"coconala.com", "www.coconala.com"}
        or parsed.path != "/requests"
        or parsed.fragment
        or sorted((key, raw) for key, raw in pairs if key != "page")
        != sorted(expected)
    ):
        return None
    pages = [raw for key, raw in pairs if key == "page"]
    if len(pages) > 1 or (
        pages and re.fullmatch(r"[1-9][0-9]*", pages[0]) is None
    ):
        return None
    return int(pages[0]) if pages else 1


def _validated_cursor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("cursor_invalid")
    source_id = str(value.get("source_id") or "").strip()
    previous_url = str(value.get("previous_url") or "").strip()
    next_url = str(value.get("next_url") or "").strip()
    reason = str(value.get("reason") or "").strip()
    if not source_id:
        raise ValueError("cursor_source_id_invalid")
    if (
        source_id == "single:new"
        and _newest_page(next_url, recruiting=False) is not None
        and (
            not previous_url
            or _newest_page(previous_url, recruiting=False) is not None
        )
    ):
        previous_url = ""
        next_url = _WAKE_REFRESH_CURSOR["next_url"]
        reason = "recruiting_filter_migration"
    if (
        source_id == "single:new"
        and previous_url
        and _newest_page(previous_url, recruiting=True) is None
    ):
        raise ValueError("cursor_previous_url_invalid")
    if source_id == "single:new" and _newest_page(next_url, recruiting=True) is None:
        raise ValueError("cursor_next_url_invalid")
    if not _valid_search_url(previous_url, allow_empty=True):
        raise ValueError("cursor_previous_url_invalid")
    if not _valid_search_url(next_url):
        raise ValueError("cursor_next_url_invalid")
    if not reason:
        raise ValueError("cursor_reason_invalid")
    cursor: dict[str, Any] = {
        "source_id": source_id,
        "previous_url": previous_url,
        "next_url": next_url,
        "reason": reason,
    }
    if "prior_inspected_request_ids" in value:
        raw_ids = value.get("prior_inspected_request_ids")
        if not isinstance(raw_ids, list):
            raise ValueError("cursor_prior_inspected_request_ids_invalid")
        prior_ids = [str(item or "").strip() for item in raw_ids]
        if not all(_valid_request_id(item) for item in prior_ids):
            raise ValueError("cursor_prior_inspected_request_ids_invalid")
        cursor["prior_inspected_request_ids"] = list(dict.fromkeys(prior_ids))
    return cursor


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("objective_state_unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("objective_state_invalid")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def checkpoint(
    *,
    state_path: Path,
    cursor_path: Path,
    pass_id: str,
    now: int,
) -> dict[str, Any]:
    try:
        raw_cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cursor_unreadable") from error
    cursor = _validated_cursor(raw_cursor)
    state = {
        "version": 1,
        "status": "active",
        "last_pass_id": str(pass_id),
        "updated_at": int(now),
        "cursor": cursor,
        "next_action": "次の毎時サイクルで前回の次ページから探索を再開する",
    }
    _atomic_write(state_path, state)
    return state


def resume(
    *,
    state_path: Path,
    output_path: Path,
    pass_id: str,
    now: int,
) -> dict[str, Any] | None:
    del pass_id, now
    if not state_path.exists():
        return None
    state = _read_object(state_path)
    if state.get("version") != 1 or state.get("status") != "active":
        return None
    cursor = _validated_cursor(state.get("cursor"))
    _atomic_write(output_path, cursor)
    return cursor


def wake_plan(
    *,
    state_path: Path,
    refresh_output_path: Path,
    coverage_output_path: Path,
    pass_id: str,
    now: int,
) -> dict[str, Any] | None:
    """Plan one wake without replacing its durable deep-coverage cursor."""
    del pass_id, now
    if not state_path.exists():
        return None
    state = _read_object(state_path)
    if state.get("version") != 1 or state.get("status") != "active":
        return None
    coverage_cursor = _validated_cursor(state.get("cursor"))
    # Direct Apply now has one authoritative discovery stream: the official
    # recruiting=true list. Page 1 is always observed by first_cursor below, so an
    # old category/keyword cursor or another page-1 cursor resumes at page 2 rather
    # than repeating the refresh or preserving retired passprep routing.
    if (
        coverage_cursor["source_id"] != "single:new"
        or _newest_page(coverage_cursor["next_url"], recruiting=True) == 1
    ):
        coverage_cursor = dict(_MARKET_REFRESH_CURSOR)
    # These ids scope one wake's continuation only. A new wake must observe them once
    # again so PREPARED intents can reconcile against fresh official history.
    coverage_cursor.pop("prior_inspected_request_ids", None)
    first_cursor = dict(_WAKE_REFRESH_CURSOR)
    _atomic_write(refresh_output_path, first_cursor)
    _atomic_write(coverage_output_path, coverage_cursor)
    return {
        "version": 1,
        "first_cursor": first_cursor,
        "coverage_cursor": coverage_cursor,
    }


def _verified_application_ids(ledger_path: Path, pass_id: str) -> set[str]:
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    except OSError as error:
        raise ValueError("application_ledger_unreadable") from error
    verified: set[str] = set()
    for raw in lines:
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or "action" in row:
            continue
        request_id = str(
            row.get("requestId") or row.get("request_id") or ""
        ).strip()
        if (
            str(row.get("pass_id") or "") == str(pass_id)
            and row.get("status") == "applied"
            and row.get("submit_verified") is True
            and row.get("applied_page_verified") is True
            and _valid_request_id(request_id)
        ):
            verified.add(request_id)
    return verified


def finish(
    *,
    state_path: Path,
    ledger_path: Path,
    pass_id: str,
    target: int,
    now: int,
) -> dict[str, Any]:
    if isinstance(target, bool) or int(target) < 1:
        raise ValueError("target_invalid")
    verified = len(_verified_application_ids(ledger_path, pass_id))
    if verified >= int(target):
        state = {
            "version": 1,
            "status": "completed",
            "last_pass_id": str(pass_id),
            "updated_at": int(now),
            "target_applications": int(target),
            "verified_applications": verified,
            "next_action": "応募目標を達成したため、次の毎時サイクルでは新着案件を確認する",
        }
    else:
        state = {
            "version": 1,
            "status": "active",
            "last_pass_id": str(pass_id),
            "updated_at": int(now),
            "target_applications": int(target),
            "verified_applications": verified,
            "cursor": dict(_MARKET_REFRESH_CURSOR),
            "next_action": "次の毎時サイクルで新着案件から探索を再開する",
        }
    _atomic_write(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    checkpoint_parser = subparsers.add_parser("checkpoint")
    checkpoint_parser.add_argument("--state", type=Path, required=True)
    checkpoint_parser.add_argument("--cursor", type=Path, required=True)
    checkpoint_parser.add_argument("--pass-id", required=True)
    checkpoint_parser.add_argument("--now", type=int, default=None)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--state", type=Path, required=True)
    resume_parser.add_argument("--output", type=Path, required=True)
    resume_parser.add_argument("--pass-id", required=True)
    resume_parser.add_argument("--now", type=int, default=None)
    wake_parser = subparsers.add_parser("wake-plan")
    wake_parser.add_argument("--state", type=Path, required=True)
    wake_parser.add_argument("--refresh-output", type=Path, required=True)
    wake_parser.add_argument("--coverage-output", type=Path, required=True)
    wake_parser.add_argument("--pass-id", required=True)
    wake_parser.add_argument("--now", type=int, default=None)
    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--state", type=Path, required=True)
    finish_parser.add_argument("--ledger", type=Path, required=True)
    finish_parser.add_argument("--pass-id", required=True)
    finish_parser.add_argument("--target", type=int, required=True)
    finish_parser.add_argument("--now", type=int, default=None)
    args = parser.parse_args()
    now = int(time.time()) if args.now is None else args.now
    try:
        if args.command == "checkpoint":
            result = checkpoint(
                state_path=args.state,
                cursor_path=args.cursor,
                pass_id=args.pass_id,
                now=now,
            )
        elif args.command == "resume":
            result = resume(
                state_path=args.state,
                output_path=args.output,
                pass_id=args.pass_id,
                now=now,
            )
            if result is None:
                return 1
        elif args.command == "wake-plan":
            result = wake_plan(
                state_path=args.state,
                refresh_output_path=args.refresh_output,
                coverage_output_path=args.coverage_output,
                pass_id=args.pass_id,
                now=now,
            )
            if result is None:
                return 1
        else:
            result = finish(
                state_path=args.state,
                ledger_path=args.ledger,
                pass_id=args.pass_id,
                target=args.target,
                now=now,
            )
    except ValueError as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
