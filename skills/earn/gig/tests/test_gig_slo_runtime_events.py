import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gig_slo.py"
SPEC = importlib.util.spec_from_file_location("gig_slo_runtime_events", SCRIPT)
gig_slo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gig_slo)


def _timestamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _event(*, loop_id: str, phase: str, status: str, epoch: int, blocker=None):
    return {
        "version": 1,
        "event_id": f"{epoch:024x}",
        "timestamp": _timestamp(epoch),
        "loop_id": loop_id,
        "domain": "earn",
        "run_id": f"run-{epoch}",
        "phase": phase,
        "status": status,
        "release_sha": "a" * 40,
        "provider": "shared-agent-runner",
        "profile_alias": None,
        "effect_class": "none",
        "effect_status": "not_applicable",
        "blocker": blocker,
        "evidence_refs": [],
    }


def test_collect_snapshot_uses_current_runtime_lane_events(tmp_path):
    now = 1_800_000_000
    legacy = tmp_path / "gig"
    legacy.mkdir()
    (legacy / ".last-pass").touch()
    runtime = tmp_path / "coconala"
    for lane, loop_id in {
        "apply": "hf-gig-apply-direct",
        "reply": "hf-gig-reply-detector",
        "fulfill": "hf-gig-paid-direct",
        "list": "hf-gig-storefront-direct",
    }.items():
        directory = {"apply": "apply", "reply": "reply", "fulfill": "paid", "list": "storefront"}[lane]
        lane_dir = runtime / directory
        lane_dir.mkdir(parents=True)
        rows = [
            _event(loop_id=loop_id, phase="execute", status="running", epoch=now - 20),
            _event(loop_id=loop_id, phase="report", status="pass", epoch=now - 10),
        ]
        (lane_dir / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    snapshot = gig_slo.collect_snapshot(
        state_dir=legacy,
        runtime_state_dir=runtime,
        telegram_database=tmp_path / "telegram.sqlite3",
        now=now,
    )

    assert snapshot["last_pass_at"] == now - 10
    assert all(snapshot["lanes"][lane]["last_attempt_at"] == now - 10
               for lane in ("apply", "reply", "fulfill", "list"))
    incidents = gig_slo.evaluate(snapshot, now=now)
    assert not any(item["fingerprint"].endswith(":attempt_silence") for item in incidents)


def test_telegram_state_uses_latest_sent_report_kind(tmp_path):
    database = tmp_path / "telegram.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE telegram_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                owner TEXT,
                fencing_token INTEGER NOT NULL DEFAULT 0,
                lease_until INTEGER NOT NULL DEFAULT 0,
                send_started_at INTEGER,
                message_id TEXT,
                error_class TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO telegram_reports(event_key,kind,message,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("old", "pass", "old", "sent", 100, 100),
        )
        connection.execute(
            "INSERT INTO telegram_reports(event_key,kind,message,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("new", "paid-direct", "new", "sent", 200, 200),
        )
        connection.execute(
            "INSERT INTO telegram_reports(event_key,kind,message,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("incident", "incident", "incident", "sent", 300, 300),
        )

    state = gig_slo._telegram_state(database, now=250)
    assert state["latest_pass_created_at"] == 200
    assert state["latest_pass_state"] == "sent"


def test_incident_only_telegram_rows_do_not_hide_report_silence(tmp_path):
    database = tmp_path / "telegram.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE telegram_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO telegram_reports(event_key,kind,message,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("incident", "incident", "incident", "sent", 200, 200),
        )

    state = gig_slo._telegram_state(database, now=10_000)
    assert state["latest_pass_created_at"] is None
    snapshot = {"last_pass_at": 10_000, "lanes": {}, "telegram": state}
    assert any(
        row["fingerprint"] == "telegram:pass_report_silence"
        for row in gig_slo.evaluate(snapshot, now=10_000)
    )
