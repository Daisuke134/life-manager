#!/usr/bin/env python3
"""Close Reply fences only when official CrowdWorks readback shows no send in the run.

A Reply run marker lists every thread the run touched. Items with effect=0 and
failed=0 returned before ``adapter.mutate`` (CrowdWorks has no classified
mutation errors). A failed item may have crashed after ``mutate``, so each such
thread must show, on the live CrowdWorks conversation, no seller message whose
minute overlaps the run window, and no Google Form fence may be written in it.
accept_contract posts no message, so a contracted thread or a visible
"awaiting client" acceptance also keeps the fence, as do effect=1 items and
missing markers or windows.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence

OWNER = "crowdworks-revenue-reply"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
JST = timezone(timedelta(hours=9))
MINUTE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日 (\d{2}):(\d{2})\Z")
SLACK = 60.0  # CrowdWorks shows minutes; also absorb host/provider clock skew.
ADMISSION_DB = Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3")


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _epoch(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _events(state_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in [state_root / "events.jsonl", *sorted(state_root.glob("events-*.jsonl.gz"))]:
        try:
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get("loop_id") == OWNER:
                        rows.append(value)
        except OSError:
            continue
    return rows


def _window(rows: list[dict[str, Any]], run_id: str,
            marker_written: float) -> tuple[float, float] | None:
    exact = [row for row in rows if row.get("run_id") == run_id]
    starts = [_epoch(r.get("timestamp")) for r in exact
              if r.get("phase") == "execute" and r.get("status") == "running"]
    ends = [_epoch(r.get("timestamp")) for r in exact if r.get("phase") == "report"]
    # The kernel writes the marker after its last item, so every mutate precedes
    # it; a killed child that left no terminal event is still bounded.
    ends = ends or [marker_written]
    if len(starts) != 1 or len(ends) != 1 or None in starts + ends or starts[0] > ends[0]:
        return None
    return starts[0], max(ends[0], marker_written)


def _overlaps(minute: float, window: tuple[float, float]) -> bool:
    return minute <= window[1] + SLACK and minute + 60 >= window[0] - SLACK


def _seller_minutes(conversation: list[dict[str, Any]]) -> list[float] | None:
    minutes = []
    for row in conversation:
        if row.get("role") != "seller":
            continue
        match = MINUTE.fullmatch(str(row.get("sent_at") or ""))
        if match is None:
            return None
        minutes.append(datetime(*map(int, match.groups()), tzinfo=JST).timestamp())
    return minutes


def _form_fence_times(state_root: Path) -> list[float]:
    times = []
    for path in (state_root / "reply/external-actions").glob("*.json"):
        times.append(path.stat().st_mtime)
        value = _json(path)
        if isinstance(value, dict):
            times += [t for k, v in value.items() if k.endswith("_at") and (t := _epoch(v)) is not None]
    return times


def _marker_path(state_root: Path, occurrence: str) -> Path:
    return state_root / "reply/runs" / f"{hashlib.sha256(occurrence.encode()).hexdigest()}.json"


def _marker(state_root: Path, occurrence: str) -> dict[str, Any] | None:
    path = _marker_path(state_root, occurrence)
    value = _json(path)
    if (not isinstance(value, dict) or value.get("version") != 1
            or value.get("occurrence_id") != occurrence
            or not isinstance(value.get("items"), list) or not value["items"]
            or not all(isinstance(item, dict) and isinstance(item.get("thread_id"), str)
                       for item in value["items"])):
        return None
    return value


def risky_threads(state_root: Path, occurrence: str) -> list[str]:
    marker = _marker(state_root, occurrence)
    return sorted({i["thread_id"] for i in marker["items"] if i.get("failed") != 0}) if marker else []


def evaluate(state_root: Path, occurrences: list[str],
             read_conversation: Callable[[str], list[dict[str, Any]] | str | None]
             ) -> dict[str, tuple[dict[str, Any] | None, str]]:
    rows = _events(state_root)
    fences = _form_fence_times(state_root)
    result: dict[str, tuple[dict[str, Any] | None, str]] = {}
    for occurrence in occurrences:
        result[occurrence] = _prove(state_root, occurrence, rows, fences, read_conversation)
    return result


def _prove(state_root, occurrence, rows, fences, read_conversation):
    if not SAFE_ID.fullmatch(occurrence) or not occurrence.startswith(f"{OWNER}:"):
        return None, "invalid_occurrence"
    run_id = occurrence[len(OWNER) + 1:]
    marker = _marker(state_root, occurrence)
    if marker is None:
        return None, "run_marker_unavailable"
    risky = []
    for item in marker["items"]:
        if item.get("effect") != 0:
            return None, f"effect_marked:{item['thread_id']}"
        if item.get("failed") != 0:
            risky.append(item["thread_id"])
    window = _window(rows, run_id, _marker_path(state_root, occurrence).stat().st_mtime)
    if window is None:
        return None, "run_window_unavailable"
    if any(_overlaps(t - 60, window) for t in fences):
        return None, "form_fence_in_window"
    evidence = {}
    for thread_id in sorted(set(risky)):
        conversation = read_conversation(thread_id)
        if isinstance(conversation, str):
            return None, f"{conversation}:{thread_id}"
        minutes = _seller_minutes(conversation) if conversation else None
        if minutes is None:
            return None, f"official_conversation_unavailable:{thread_id}"
        if any(_overlaps(m, window) for m in minutes):
            return None, f"seller_message_in_window:{thread_id}"
        evidence[thread_id] = max(minutes, default=None)
    digest = hashlib.sha256(json.dumps(
        {"window": window, "latest_seller_minute": evidence}, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "owner_id": OWNER, "occurrence_id": occurrence, "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-crowdworks-reply-readback://{OWNER}/{run_id}/{digest}",
        "window": list(window), "risky_threads": sorted(evidence),
        "latest_seller_minute": evidence,
    }, "ok"


AWAITING_CLIENT = ("まだクライアントが契約に同意していません", "クライアントが契約に同意すると契約成立")


def contract_blocker(page: Any, row: dict[str, Any] | None) -> str | None:
    """accept_contract posts no message; any trace of an acceptance keeps the fence."""
    if row is None:
        return "official_thread_unavailable"
    if row.get("proposal_status") == "contracted":
        return "contract_accepted"
    progress = page.locator("div.progress_detail")
    text = progress.inner_text() if progress.count() else ""
    if any(marker in text for marker in AWAITING_CLIENT):
        return "contract_acceptance_awaiting_client"
    return None


def accept_intent_threads(state_root: Path) -> set[str]:
    threads = set()
    for path in (state_root / "reply/threads").glob("*/state.json"):
        intent = (_json(path) or {}).get("intent")
        if isinstance(intent, dict) and intent.get("action") == "accept_contract":
            threads.add(str(intent.get("thread_id")))
    return threads


def fenced_occurrences(database: Path) -> list[str]:
    with sqlite3.connect(f"file:{database.expanduser()}?mode=ro", uri=True) as connection:
        return [row[0] for row in connection.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND state='claimed' "
            "AND effect_unknown=1 ORDER BY queued_at", (OWNER,))]


@contextmanager
def _provider_lease(state_root: Path):
    # Same lease every CrowdWorks browser owner takes via run_with_file_lock.py.
    with (state_root / "provider-browser.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--occurrence", action="append", default=[])
    parser.add_argument("--all-fenced", action="store_true")
    parser.add_argument("--admission-db", type=Path, default=ADMISSION_DB)
    parser.add_argument("--resolve", action="store_true",
                        help="release each proven claimed occurrence")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    occurrences = list(args.occurrence)
    if args.all_fenced:
        occurrences += fenced_occurrences(args.admission_db)
    occurrences = sorted(set(occurrences))
    threads = sorted({t for o in occurrences for t in risky_threads(state_root, o)})
    accepts = accept_intent_threads(state_root)
    conversations: dict[str, list[dict[str, Any]] | str | None] = {
        thread_id: "accept_contract_intent" for thread_id in threads if thread_id in accepts}
    threads = [thread_id for thread_id in threads if thread_id not in accepts]
    with _provider_lease(state_root):
        import reply_adapter
        adapter, _ = reply_adapter.build(["--state-path", str(state_root / "reply/state.json")])
        try:
            if threads:
                adapter.observe_threads()
            for thread_id in threads:
                try:
                    rows = adapter._detail(thread_id)
                    blocker = contract_blocker(adapter.page, adapter.rows.get(thread_id))
                    conversations[thread_id] = blocker or rows
                except Exception:
                    conversations[thread_id] = None
        finally:
            adapter.close()
    results = evaluate(state_root, occurrences, conversations.get)
    report = {"owner_id": OWNER, "checked": len(occurrences), "resolved": [], "fenced": {}}
    for occurrence, (proof, reason) in results.items():
        if proof is None:
            report["fenced"][occurrence] = reason
            continue
        if not args.resolve:
            report["resolved"].append({"occurrence_id": occurrence, "dry_run": True,
                                       "evidence_ref": proof["evidence_ref"]})
            continue
        receipt = state_root / "reconciliation" / f"reply-no-send-{occurrence[len(OWNER) + 1:]}.json"
        receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"schema_version": 1, "receipt_type":
                                       "CROWDWORKS_REPLY_NO_SEND_READBACK", **proof},
                                      sort_keys=True) + "\n", encoding="utf-8")
        receipt.chmod(0o600)
        if resolve_pre_effect_occurrence(OWNER, occurrence, pre_effect_readback=lambda p=proof: p,
                                         expected_state="claimed"):
            report["resolved"].append({"occurrence_id": occurrence,
                                       "evidence_ref": proof["evidence_ref"]})
        else:
            report["fenced"][occurrence] = "close_rejected"
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
