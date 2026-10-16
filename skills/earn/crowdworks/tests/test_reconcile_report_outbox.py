from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reconcile_report_outbox as adapter  # noqa: E402

OWNER = "crowdworks-revenue-report"
RUN = "18d91fd1ceb915e8-28392"
OCC = f"{OWNER}:{RUN}"
SHA = "4f6e8ef50ee6460b20fc4bb1687661d3a93ffe11"


def _events(root: Path, run: str = RUN, occ: str | None = OCC) -> None:
    rows = [
        {"loop_id": OWNER, "run_id": run, "occurrence_id": occ, "phase": "execute",
         "status": "running", "timestamp": "2026-09-27T08:21:52+00:00", "release_sha": SHA,
         "evidence_refs": []},
        {"loop_id": OWNER, "run_id": run, "occurrence_id": occ, "phase": "report",
         "status": "pass", "effect_status": "unknown", "timestamp": "2026-09-27T08:21:57+00:00",
         "release_sha": SHA, "evidence_refs": []},
    ]
    (root / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _outbox(root: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(root / "telegram-outbox.sqlite3") as db:
        db.execute("""CREATE TABLE telegram_outbox (event_key TEXT PRIMARY KEY, message_sha256 TEXT,
            message TEXT, status TEXT, attempt_count INTEGER, provider_message_id TEXT UNIQUE,
            created_at TEXT, claimed_at TEXT, delivered_at TEXT, last_error_code TEXT)""")
        db.executemany("INSERT INTO telegram_outbox VALUES (?,'x','m',?,1,?,'c',?,'d',NULL)", rows)


def _admission(root: Path, state: str = "claimed", unknown: int = 1) -> Path:
    path = root / "admission-v2.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE occurrences (occurrence_id TEXT, owner_id TEXT, state TEXT, effect_unknown INTEGER)")
        db.execute("INSERT INTO occurrences VALUES (?,?,?,?)", (OCC, OWNER, state, unknown))
    return path


WAKE = f"crowdworks:wake:{OCC}:2026-09-27T08:15:26+00:00"


def test_bound_delivered_wake_message_is_the_receipt(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [(WAKE, "delivered", "97503", "2026-09-27T08:21:55.5Z"),
                       ("crowdworks:wake:other:x", "delivered", "97497", "2026-09-27T08:15:59Z")])
    proof = adapter.find_proof(tmp_path, OCC, _admission(tmp_path))
    assert proof["verified"] is True
    assert proof["provider_receipt_id"] == "telegram:97503"
    assert proof["release_sha"] == SHA and proof["occurrence_state"] == "claimed"
    assert proof["window_receipts"] == ["97503"]


def test_uncertain_send_in_window_keeps_fence(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [(WAKE, "delivered", "97503", "2026-09-27T08:21:55Z"),
                       ("crowdworks:application:1", "delivery_uncertain", None, "2026-09-27T08:21:56Z")])
    with pytest.raises(RuntimeError, match="outbox_window_not_settled"):
        adapter.find_proof(tmp_path, OCC, _admission(tmp_path))


def test_missing_bound_message_keeps_fence(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [("crowdworks:wake:other:x", "delivered", "97497", "2026-09-27T08:21:55Z")])
    with pytest.raises(RuntimeError, match="bound_receipt_unavailable"):
        adapter.find_proof(tmp_path, OCC, _admission(tmp_path))


def test_bound_message_claimed_outside_run_keeps_fence(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [(WAKE, "delivered", "97503", "2026-09-27T09:30:00Z")])
    with pytest.raises(RuntimeError, match="bound_receipt_unavailable"):
        adapter.find_proof(tmp_path, OCC, _admission(tmp_path))


def test_not_fenced_occurrence_is_rejected(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [(WAKE, "delivered", "97503", "2026-09-27T08:21:55Z")])
    with pytest.raises(RuntimeError, match="occurrence_not_effect_unknown"):
        adapter.find_proof(tmp_path, OCC, _admission(tmp_path, unknown=0))


def test_resolve_uses_receipt_resolver_with_exact_state(tmp_path):
    _events(tmp_path)
    _outbox(tmp_path, [(WAKE, "delivered", "97503", "2026-09-27T08:21:55Z")])
    calls = []

    def resolver(owner, occurrence, *, official_readback, expected_state):
        calls.append((owner, occurrence, official_readback()["provider_receipt_id"], expected_state))
        return True

    result = adapter.reconcile(state_root=tmp_path, occurrence=OCC,
                               admission_db=_admission(tmp_path, state="released"),
                               resolve=True, resolver=resolver)
    assert result["resolved"] is True
    assert calls == [(OWNER, OCC, "telegram:97503", "released")]
