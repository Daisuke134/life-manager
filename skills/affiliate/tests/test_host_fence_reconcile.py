from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "host_fence_reconcile.py"


def load_module():
    spec = importlib.util.spec_from_file_location("affiliate_host_fence_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)


def runtime_event(run_id: str, phase: str, timestamp: str, *,
                  status: str, blocker: str | None = None,
                  refs: list[str] | None = None) -> dict:
    return {
        "version": 1,
        "event_id": ("a" if phase == "execute" else "b") * 24,
        "loop_id": "affiliate-loop",
        "domain": "growth",
        "provider": "deterministic",
        "profile_alias": None,
        "phase": phase,
        "status": status,
        "effect_status": "started" if phase == "execute" else "unknown",
        "effect_class": "publish",
        "blocker": blocker,
        "evidence_refs": refs or [f"lm-loop://affiliate-loop/{run_id}/summary.json"],
        "run_id": run_id,
        "release_sha": "1" * 40,
        "timestamp": timestamp,
    }


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    loop_state = tmp_path / "loop"
    affiliate_state = tmp_path / "affiliate"
    database = tmp_path / "admission.sqlite3"
    predecessor = "affiliate-loop:previous"
    target = "affiliate-loop:target"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE occurrences(
                   occurrence_id TEXT PRIMARY KEY, owner_id TEXT, resource_class TEXT,
                   admission_class TEXT, base_priority TEXT, queued_at REAL,
                   state TEXT, sequence INTEGER, effect_unknown INTEGER
               )"""
        )
        connection.executemany(
            "INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?)",
            [
                (predecessor, "affiliate-loop", "deterministic", "revenue",
                 "revenue", 100.0, "released", 1, 0),
                (target, "affiliate-loop", "deterministic", "revenue",
                 "revenue", 200.0, "claimed", 2, 1),
                ("affiliate-loop:newer", "affiliate-loop", "deterministic", "revenue",
                 "revenue", 400.0, "queued", 3, 0),
            ],
        )
    write_jsonl(loop_state / "events.jsonl", [
        runtime_event(
            "previous-run", "report", "1970-01-01T00:05:00+00:00", status="pass",
            refs=[
                "lm-loop://affiliate-loop/previous-run/summary.json",
                "lm-occurrence://affiliate-loop/previous/claim",
            ],
        ),
        runtime_event(
            "blocked-run", "execute", "1970-01-01T00:05:10+00:00", status="running",
        ),
        runtime_event(
            "blocked-run", "report", "1970-01-01T00:05:20+00:00", status="blocked",
            blocker="host_admission_deferred:resource_effect_unknown",
        ),
    ])
    for name in ("job-events.jsonl", "run-receipts.jsonl", "tool-attempt-receipts.jsonl"):
        write_jsonl(affiliate_state / name, [])
    return database, loop_state, affiliate_state, target


def test_exact_fifo_window_builds_pre_effect_proof(tmp_path):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
    )

    assert result["state"] == "PROOF_READY"
    assert result["occurrence_id"] == target
    assert result["evidence"]["predecessor_occurrence_id"] == "affiliate-loop:previous"
    assert result["evidence"]["job_events_in_window"] == 0
    assert result["evidence"]["child_receipts_in_window"] == 0
    assert result["evidence"]["tool_attempts_in_window"] == 0


def test_external_job_event_in_window_keeps_fence(tmp_path):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)
    write_jsonl(affiliate_state / "job-events.jsonl", [{
        "kind": "TELEGRAM_SEND", "state": "EFFECT_STARTED", "updated_at": 315,
    }])

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
    )

    assert result == {"state": "HELD", "reason": "effect_journal_nonempty"}


@pytest.mark.parametrize("journal", [
    "run-receipts.jsonl",
    "tool-attempt-receipts.jsonl",
])
def test_child_or_tool_evidence_in_window_keeps_fence(tmp_path, journal):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)
    write_jsonl(affiliate_state / journal, [{
        "receipt_type": "AFFILIATE_RUN_RECEIPT",
        "started_at": "1970-01-01T00:05:12+00:00",
        "finished_at": "1970-01-01T00:05:18+00:00",
    }])

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
    )

    assert result == {"state": "HELD", "reason": "child_evidence_nonempty"}


def test_existing_read_only_run_receipt_journal_is_accepted(tmp_path):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)
    (affiliate_state / "run-receipts.jsonl").chmod(0o644)

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
    )

    assert result["state"] == "PROOF_READY"


def test_non_fifo_or_malformed_evidence_keeps_fence(tmp_path):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?)",
            ("affiliate-loop:older-open", "affiliate-loop", "deterministic", "revenue",
             "revenue", 150.0, "queued", 4, 0),
        )

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
    )

    assert result == {"state": "HELD", "reason": "older_occurrence_open"}


def test_resolve_writes_private_receipt_and_uses_exact_proof(tmp_path):
    module = load_module()
    database, loop_state, affiliate_state, target = fixture(tmp_path)
    resolver = Mock(return_value=True)

    result = module.reconcile_host_fence(
        database, loop_state, affiliate_state, occurrence_id=target,
        resolve=True, resolver=resolver,
    )

    assert result["state"] == "RECONCILED"
    receipt = Path(result["receipt_path"])
    assert receipt.stat().st_mode & 0o777 == 0o600
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["resolution_state"] == "RESOLVED"
    proof = resolver.call_args.kwargs["pre_effect_readback"]()
    assert proof == {
        "owner_id": "affiliate-loop",
        "occurrence_id": target,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": result["evidence_ref"],
    }
    assert resolver.call_args.kwargs["expected_state"] == "claimed"


def test_cli_refuses_resolution_against_noncanonical_database(tmp_path, capsys):
    module = load_module()
    database, loop_state, affiliate_state, _ = fixture(tmp_path)
    module.reconcile_host_fence = Mock(side_effect=AssertionError("must not resolve"))

    return_code = module.main([
        "--database", str(database),
        "--loop-state", str(loop_state),
        "--affiliate-state", str(affiliate_state),
        "--resolve",
    ])

    assert return_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "state": "HELD",
        "reason": "resolution_database_not_canonical",
    }
    module.reconcile_host_fence.assert_not_called()


def test_registry_enables_existing_atomic_wake_coalescing():
    registry = json.loads((Path(__file__).parents[3] / "config/loop-registry.json").read_text())
    assert registry["loops"]["affiliate-loop"]["coalesce_reserved_wakes"] is True
    assert registry["loops"]["affiliate-loop"]["coalesce_queued_wakes"] is True
