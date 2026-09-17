#!/usr/bin/env python3
"""Pure active-four schedule decisions and durable dormant-destination receipts."""

from __future__ import annotations

import fcntl
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from publication_contract import ACTIVE_PAIRS, DORMANT_PAIRS
from publication_contract_resolver import infer_publication_contract


JST = ZoneInfo("Asia/Tokyo")
IMMEDIATE_ORDER = ACTIVE_PAIRS
ZENN_OWNER = "ai.anicca.article-zenn-retry"


def x_article_en_decision(
    ja_published_at: datetime, now: datetime
) -> dict[str, str | None]:
    """Use the remotely observed JA timestamp and retain no missed-window deadline."""
    if (
        ja_published_at.tzinfo is None
        or ja_published_at.utcoffset() is None
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("schedule timestamps must be timezone-aware")
    not_before = ja_published_at + timedelta(hours=6)
    return {
        "action": "WAIT" if now < not_before else "PUBLISH",
        "not_before": not_before.isoformat(),
        "deadline": None,
    }


class XPostSlotStore:
    """One atomic owner assignment per JST date, oldest ready run first."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            value = {}
        slots = value.get("slots") if isinstance(value, dict) else {}
        return {"version": 1, "slots": slots if isinstance(slots, dict) else {}}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def assign(
        self, candidates: list[dict[str, str]], now: datetime
    ) -> dict[str, str | bool | None]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("slot timestamp must be timezone-aware")
        local = now.astimezone(JST)
        date_jst = local.date().isoformat()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            state = self._load()
            existing = state["slots"].get(date_jst)
            if isinstance(existing, dict):
                return dict(existing)
            if local.time() < time(12, 0):
                return {
                    "date_jst": date_jst,
                    "status": "WAIT",
                    "owner_run_id": None,
                }
            # Today's run owns today's slot. Measured 2026-07-26: the 07-25
            # slot was held by daily-2026-07-24, which could not publish, so
            # the X post face missed two days running. An older run's post
            # belongs to its own (already past) date, never to today's.
            eligible = sorted(
                (
                    candidate
                    for candidate in candidates
                    if candidate.get("run_id")
                    and candidate.get("run_date_jst")
                    and candidate.get("ready_at")
                    and datetime.fromisoformat(candidate["ready_at"]) <= now
                ),
                key=lambda candidate: (
                    0 if candidate["run_date_jst"] == date_jst else 1,
                    candidate["run_date_jst"],
                    datetime.fromisoformat(candidate["ready_at"]),
                    candidate["run_id"],
                ),
            )
            if not eligible:
                return {
                    "date_jst": date_jst,
                    "status": "WAIT",
                    "owner_run_id": None,
                }
            assigned: dict[str, str | bool | None] = {
                "date_jst": date_jst,
                "status": "ASSIGNED",
                "owner_run_id": eligible[0]["run_id"],
                "assigned_at": local.isoformat(),
            }
            state["slots"][date_jst] = assigned
            self._write(state)
            return dict(assigned)


def _published_at(state: dict[str, Any], pair: str) -> datetime | None:
    value = (
        state.get("pairs", {})
        .get(pair, {})
        .get("receipt", {})
        .get("evidence", {})
        .get("published_at")
    )
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def eligible_pairs(
    state: dict[str, Any],
    pending_pairs: list[str],
    now: datetime,
    *,
    x_post_owner: str | None,
) -> tuple[list[str], dict[str, Any]]:
    """Filter one immutable run's pending pairs by platform schedule only."""
    pending = set(pending_pairs)
    legacy_exact8 = infer_publication_contract(state) == "legacy-exact8"
    eligible = [pair for pair in IMMEDIATE_ORDER if pair in pending]
    schedule: dict[str, Any] = {}
    if legacy_exact8:
        if "zenn-article/ja" in pending:
            schedule["zenn-article/ja"] = {
                "action": "DELEGATED",
                "owner": ZENN_OWNER,
            }
        if "devto/en" in pending:
            eligible.append("devto/en")
        if "x-article/en" in pending:
            ja_published_at = _published_at(state, "x-article/ja")
            if ja_published_at is None:
                schedule["x-article/en"] = {
                    "action": "WAIT",
                    "reason": "missing-remote-ja-published-at",
                    "deadline": None,
                }
            else:
                decision = x_article_en_decision(ja_published_at, now)
                schedule["x-article/en"] = decision
                if decision["action"] == "PUBLISH":
                    eligible.append("x-article/en")
        if "x-post/ja" in pending:
            assigned = x_post_owner == state.get("run_id")
            schedule["x-post/ja"] = {
                "action": "PUBLISH" if assigned else "WAIT",
                "owner_run_id": x_post_owner,
            }
            if assigned:
                eligible.append("x-post/ja")
        return eligible, schedule
    for dormant_pair in DORMANT_PAIRS:
        if dormant_pair in pending:
            schedule[dormant_pair] = {
                "action": "SKIP",
                "reason": "dormant-destination",
                "slo": "not-applicable",
            }
    return eligible, schedule


def _current_circuit_context(
    state: dict[str, Any], pair: str, code_files: list[str]
) -> dict[str, str] | None:
    try:
        digest = hashlib.sha256()
        for raw_path in code_files:
            path = Path(raw_path)
            digest.update(str(path).encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        state_path = Path(str(state.get("state_path", "")))
        from resume_failure_circuit import state_identity_sha256

        return {
            "state_sha256": state_identity_sha256(state_path, pair),
            "code_sha256": digest.hexdigest(),
        }
    except OSError:
        return None


def _open_resume_circuit_pairs(state: dict[str, Any]) -> tuple[set[str], bool]:
    """Return pairs explicitly frozen by the per-run publisher circuit.

    The circuit is deliberately separate from publication state: an external
    publisher failure must not be rewritten as a fake live/unavailable receipt.
    Once it is open, the scheduler excludes only that pair so independent
    destinations can continue on later ticks.
    """
    run_dir = state.get("run_dir")
    if not isinstance(run_dir, str) or not run_dir:
        return set(), False
    path = Path(run_dir) / "gates" / "resume-failure-circuit.json"
    if not path.exists():
        return set(), False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return set(), True
    pairs = value.get("pairs") if isinstance(value, dict) else None
    if not isinstance(pairs, dict):
        return set(), True
    blocked: set[str] = set()
    for pair, row in pairs.items():
        if not isinstance(pair, str) or not isinstance(row, dict) or row.get("open") is not True:
            continue
        code_files = row.get("code_files")
        if not isinstance(code_files, list) or not all(isinstance(item, str) for item in code_files):
            blocked.add(pair)
            continue
        current = _current_circuit_context(state, pair, code_files)
        if current is None:
            return set(), True
        if row.get("state_sha256") == current["state_sha256"] and row.get("code_sha256") == current["code_sha256"]:
            blocked.add(pair)
    return blocked, False


def _run_date(run_id: str, created_at: str) -> str:
    if run_id.startswith("daily-") and len(run_id) == len("daily-YYYY-MM-DD"):
        return run_id.removeprefix("daily-")
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(JST).date().isoformat()
    except (AttributeError, ValueError):
        return "9999-12-31"


def run_priority(state: dict[str, Any], now: datetime) -> tuple[Any, ...]:
    """Prefer today's obligation, then newest active-four, then legacy backlog."""
    run_id = str(state.get("run_id", ""))
    created_at = str(state.get("created_at", ""))
    run_date = _run_date(run_id, created_at)
    today_jst = now.astimezone(JST).date().isoformat()
    try:
        created_epoch = datetime.fromisoformat(
            created_at.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        created_epoch = 0.0
    if run_date == today_jst:
        return (0, -created_epoch, run_id)
    if infer_publication_contract(state) == "active-four":
        return (1, -created_epoch, run_id)
    return (2, run_date, created_at, run_id)


def plan_oldest(state_root: Path, now: datetime) -> dict[str, Any]:
    """Select the oldest valid incomplete run and return only eligible same-run pairs."""
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from publication_resume import PublicationStore  # pylint: disable=import-outside-toplevel

    ledger = state_root / "articles.jsonl"
    discovered: list[tuple[dict[str, Any], dict[str, Any]]] = []
    blocked_runs: list[dict[str, str]] = []
    for state_path in sorted((state_root / "runs").glob("*/gates/publication-state.json")):
        run_dir = state_path.parent.parent
        try:
            store = PublicationStore(state_path, ledger)
            worker_plan = store.worker_plan()
            if worker_plan.get("resumable") is not True:
                # A terminal run is not an invalid incomplete run.  Its
                # durable completion is already represented by the verified
                # live ledger set; do not feed its full pair set into the
                # partial-initialization validator on every future tick.
                if worker_plan.get("reason") == "all-complete":
                    continue
                initialization = store.initialization_plan()
                if initialization.get("initializable") is not True:
                    blocked_reason = str(
                        initialization.get(
                            "reason", "run-or-draft-boundary-invalid"
                        )
                    )
                    try:
                        raw_state = json.loads(
                            state_path.read_text(encoding="utf-8")
                        )
                        identities = raw_state.get("destination_identities", {})
                        if (
                            isinstance(identities, dict)
                            and identities.get("substack/ja")
                            and identities.get("substack/ja")
                            == identities.get("substack/en")
                        ):
                            blocked_reason = "substack-publication-identity-conflict"
                    except (OSError, TypeError, json.JSONDecodeError):
                        pass
                    blocked_runs.append(
                        {
                            "run_id": run_dir.name,
                            "reason": blocked_reason,
                        }
                    )
                    continue
                worker_plan = {
                    "resumable": False,
                    "pending_pairs": [],
                    "recovery_pairs": [],
                    "initialization_pairs": initialization[
                        "initialization_pairs"
                    ],
                    "missing_dormant_skip_pairs": initialization.get(
                        "missing_dormant_skip_pairs", []
                    ),
                    "existing_pairs": initialization["existing_pairs"],
                }
            state = store.read()
        except Exception:
            blocked_runs.append(
                {"run_id": run_dir.name, "reason": "state-read-failed"}
            )
            continue
        discovered.append((worker_plan, state))
    if not discovered:
        if blocked_runs:
            return {
                "status": "BLOCKED",
                "reason": "invalid-incomplete-run",
                "blocked_runs": blocked_runs,
            }
        return {"status": "IDLE", "reason": "no-valid-incomplete-run"}

    # Today's run comes first: an older stuck run must never starve today's
    # publishing obligation (Dais 2026-07-26 — on 07-25 the worker kept
    # picking the stuck 07-24 run and today's staged drafts never published).
    # Older incomplete runs still get served, oldest-first, once today's run
    # has no eligible work left.
    discovered.sort(key=lambda item: run_priority(item[1], now))
    x_post_candidates = [
        {
            "run_id": str(state["run_id"]),
            "run_date_jst": _run_date(str(state["run_id"]), str(state.get("created_at", ""))),
            "ready_at": str(state.get("created_at", "")),
        }
        for plan, state in discovered
        if "x-post/ja" in plan.get("pending_pairs", [])
    ]
    slot = XPostSlotStore(state_root / "x-post-slots.json").assign(
        x_post_candidates, now
    )
    x_post_owner = (
        str(slot.get("owner_run_id")) if slot.get("owner_run_id") else None
    )
    # Serve the first run in preference order that actually has work; a run
    # with nothing eligible must not block the ones behind it.
    plan, state = discovered[0]
    initialization_pairs = list(plan.get("initialization_pairs", []))
    recovery_pairs = list(plan.get("recovery_pairs", []))
    eligible, schedule = eligible_pairs(
        state, list(plan["pending_pairs"]), now, x_post_owner=x_post_owner
    )
    blocked_pairs, circuit_invalid = _open_resume_circuit_pairs(state)
    if circuit_invalid:
        blocked_pairs = set(plan["pending_pairs"])
    if blocked_pairs:
        eligible = [pair for pair in eligible if pair not in blocked_pairs]
        recovery_pairs = [pair for pair in recovery_pairs if pair not in blocked_pairs]
        for pair in sorted(blocked_pairs):
            schedule[pair] = {
                "action": "BLOCK",
                "reason": "resume-failure-circuit-unreadable" if circuit_invalid else "same-failure-circuit-open",
            }
    selected_recovery = next(
        (
            pair
            for pair in ("note/ja", "devto/en", "x-article/ja", "x-post/ja")
            if pair in recovery_pairs and pair not in blocked_pairs
        ),
        "",
    )
    if selected_recovery:
        eligible = [
            pair for pair in eligible if pair != selected_recovery
        ] + [selected_recovery]
        schedule[selected_recovery] = {
            "action": "RECOVER",
            "reason": "bounded-ambiguous-same-id-recovery",
        }
    if not eligible and not initialization_pairs:
        for candidate_plan, candidate_state in discovered[1:]:
            candidate_init = list(candidate_plan.get("initialization_pairs", []))
            candidate_recovery = list(
                candidate_plan.get("recovery_pairs", [])
            )
            candidate_eligible, candidate_schedule = eligible_pairs(
                candidate_state,
                list(candidate_plan["pending_pairs"]),
                now,
                x_post_owner=x_post_owner,
            )
            candidate_blocked, candidate_circuit_invalid = _open_resume_circuit_pairs(candidate_state)
            if candidate_circuit_invalid:
                candidate_blocked = set(candidate_plan["pending_pairs"])
            if candidate_blocked:
                candidate_eligible = [
                    pair for pair in candidate_eligible if pair not in candidate_blocked
                ]
                candidate_recovery = [
                    pair for pair in candidate_recovery if pair not in candidate_blocked
                ]
                for pair in sorted(candidate_blocked):
                    candidate_schedule[pair] = {
                        "action": "BLOCK",
                        "reason": "resume-failure-circuit-unreadable" if candidate_circuit_invalid else "same-failure-circuit-open",
                    }
            selected_recovery = next(
                (
                    pair
                    for pair in (
                        "note/ja",
                        "devto/en",
                        "x-article/ja",
                        "x-post/ja",
                    )
                    if pair in candidate_recovery and pair not in candidate_blocked
                ),
                "",
            )
            if selected_recovery:
                candidate_eligible = [
                    pair
                    for pair in candidate_eligible
                    if pair != selected_recovery
                ] + [selected_recovery]
                candidate_schedule[selected_recovery] = {
                    "action": "RECOVER",
                    "reason": "bounded-ambiguous-same-id-recovery",
                }
            if candidate_eligible or candidate_init:
                plan, state = candidate_plan, candidate_state
                initialization_pairs = candidate_init
                recovery_pairs = candidate_recovery
                eligible, schedule = candidate_eligible, candidate_schedule
                break
    return {
        "status": "READY" if eligible or initialization_pairs else "WAIT",
        "run_id": state["run_id"],
        "run_dir": state["run_dir"],
        "state_path": state["state_path"],
        "ledger_path": state["ledger_path"],
        "topic_id": state["topic_id"],
        "pending_pairs": plan["pending_pairs"],
        "recovery_pairs": recovery_pairs,
        "initialization_pairs": initialization_pairs,
        "missing_dormant_skip_pairs": plan.get(
            "missing_dormant_skip_pairs", []
        ),
        "existing_pairs": plan.get("existing_pairs", {}),
        "eligible_pairs": eligible,
        "blocked_pairs": sorted(blocked_pairs),
        "schedule": schedule,
        "x_post_slot": slot,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--now")
    args = parser.parse_args()
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if args.now
        else datetime.now(JST)
    )
    print(json.dumps(plan_oldest(args.state_root, now), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
