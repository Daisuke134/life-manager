import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/life-manager/investment-core"))

from telegram_outbox import claim_next, enqueue, mark_delivered  # noqa: E402

import effect_reconcile as effect_reconcile_module  # noqa: E402
from effect_reconcile import build_proof, reconcile  # noqa: E402


OWNER = "life-manager-cfo-hourly"
DATE = "2026-09-26"
RUN_ID = "current-run-1"
OCCURRENCE = f"{OWNER}:{RUN_ID}"
RELEASE_SHA = "b" * 40
EVENT_KEY = f"cfo-result:subject:telegram:{DATE}:12"
MESSAGE = "CFO current result fixture"
MESSAGE_SHA256 = hashlib.sha256(MESSAGE.encode()).hexdigest()


def _event(*, phase: str, status: str, timestamp: str, exit_code=None, effect_status: str):
    return {
        "version": 1,
        "event_id": hashlib.sha256(f"{phase}:{timestamp}".encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": OWNER,
        "domain": "financial",
        "run_id": RUN_ID,
        "phase": phase,
        "status": status,
        "release_sha": RELEASE_SHA,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "message",
        "effect_status": effect_status,
        "blocker": None,
        "evidence_refs": [f"lm-loop://{OWNER}/{RUN_ID}/summary.json"],
        "product_loop_id": None,
        "job_id": OWNER,
        "owner_id": OWNER,
        "wake_id": RUN_ID,
        "occurrence_id": OCCURRENCE,
        "loaded_argv_sha256": None,
        "loaded_env_sha256": None,
        "exit_code": exit_code,
        "failure_layer": "clean",
        "error_class": None,
        "retryable": False,
        "next_action": "none",
        "provider_receipt_id": None,
        "official_readback_ref": None,
    }


def _fixture(
    tmp_path: Path,
    *,
    resolution_kind="sent",
    outbox_status="delivered",
    delivered_at="2026-09-26T12:27:20Z",
    report_status="sent",
    terminal_status="pass",
    terminal_exit_code=0,
    admission_state="claimed",
    admission_effect_unknown=1,
):
    state_dir = tmp_path / "cfo"
    state_dir.mkdir(mode=0o700)
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            """CREATE TABLE occurrences(
                occurrence_id TEXT PRIMARY KEY,
                owner_id TEXT,
                state TEXT,
                effect_unknown INTEGER
            )"""
        )
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?)",
            (OCCURRENCE, OWNER, admission_state, admission_effect_unknown),
        )

    outbox = state_dir / "telegram-outbox.sqlite3"
    enqueue(
        database=outbox,
        event_key=EVENT_KEY,
        message=MESSAGE,
        created_at="2026-09-26T12:26:00Z",
        repeat_after_seconds=None,
    )
    claimed = claim_next(outbox)
    assert claimed is not None
    if outbox_status == "delivered":
        mark_delivered(
            outbox,
            EVENT_KEY,
            "94946",
            delivered_at,
            claimed_at=claimed.claimed_at,
        )
    elif outbox_status == "delivery_uncertain":
        from telegram_outbox import mark_delivery_uncertain

        mark_delivery_uncertain(outbox, EVENT_KEY, "fixture_uncertain", claimed_at=claimed.claimed_at)

    report = {
            "status": report_status,
            "subjectId": "subject",
            "periodKey": f"{DATE}:12",
            "reportingDate": DATE,
            "channel": "telegram",
            "eventKey": EVENT_KEY,
            "message": MESSAGE,
            "messageSha256": MESSAGE_SHA256,
            "occurrenceId": OCCURRENCE,
            "createdAt": "2026-09-26T12:26:00Z",
    }
    if report_status == "sent":
        report.update({
            "resolutionKind": resolution_kind,
            "providerMessageId": "94946",
            "sentAt": "2026-09-26T12:27:00Z",
            "deliveryCounters": {
                "attempted": 0 if resolution_kind == "duplicate" else 1,
                "delivered": 0 if resolution_kind == "duplicate" else 1,
                "delivery_uncertain": 0,
                "pre_send_failed": 0,
            },
        })
    (state_dir / "last-result-report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    (state_dir / "last-result-report.json").chmod(0o600)
    (state_dir / "events.jsonl").write_text(
        "".join(
            json.dumps(row, separators=(",", ":")) + "\n"
            for row in (
                _event(
                    phase="execute",
                    status="running",
                    effect_status="started",
                    timestamp="2026-09-26T12:27:07.145Z",
                ),
                _event(
                    phase="report",
                    status=terminal_status,
                    effect_status="unknown",
                    exit_code=terminal_exit_code,
                    timestamp="2026-09-26T12:27:38.256Z",
                ),
            )
        ),
        encoding="utf-8",
    )
    (state_dir / "events.jsonl").chmod(0o600)
    return state_dir, admission_db, OCCURRENCE


def _write_b7_snapshot(
    state_dir: Path,
    occurrence: str,
    *,
    resolution_kind="sent",
    schema_version=4,
    include_counters=True,
):
    run_id = occurrence.split(":", 1)[1]
    snapshot = {
        "schemaVersion": schema_version,
        "status": "sent",
        "resolutionKind": resolution_kind,
        "ownerId": OWNER,
        "runId": run_id,
        "releaseSha": RELEASE_SHA,
        "occurrenceId": occurrence,
        "channel": "telegram",
        "eventKey": EVENT_KEY,
        "messageSha256": MESSAGE_SHA256,
        "providerMessageId": "94946",
        "sentAt": "2026-09-26T12:27:20Z",
        "deliveryOccurrenceId": occurrence,
        "deliveryRunId": run_id,
        "reportingPeriod": {
            "key": f"{DATE}:12",
            "reportingDate": DATE,
            "timezone": "Asia/Tokyo",
            "snapshotAt": "2026-09-26T12:28:00Z",
            "trailingStart": "2026-08-27T12:28:00Z",
        },
    }
    if include_counters:
        duplicate = resolution_kind == "duplicate"
        snapshot["deliveryCounters"] = {
            "attempted": 0 if duplicate else 1,
            "delivered": 0 if duplicate else 1,
            "delivery_uncertain": 0,
            "pre_send_failed": 0,
        }
    directory = state_dir / "b7-readbacks"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / f"{occurrence}.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_exact_receipt_proves_already_released_occurrence_without_fence(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path, admission_state="released", admission_effect_unknown=0,
    )

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)

    assert proof["verified"] is True
    assert proof["provider_receipt_id"] == "telegram:94946"
    assert proof["occurrence_state"] == "released"
    assert proof["admission_effect_unknown"] is False
    assert proof["report_source"] == "last_result_report"

    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_unknown_occurrence",
        lambda *args, **kwargs: pytest.fail("released occurrence must not invoke a state resolver"),
    )
    result = reconcile(
        state_dir=state_dir, admission_db=admission_db,
        occurrence_id=occurrence, resolve=True,
    )
    assert result["resolution_state"] == "PROOF_READY_ALREADY_RELEASED"
    with sqlite3.connect(admission_db) as connection:
        assert connection.execute(
            "SELECT state,effect_unknown FROM occurrences WHERE occurrence_id=?", (occurrence,)
        ).fetchone() == ("released", 0)


@pytest.mark.parametrize("symlink_archive_directory", [False, True])
def test_historical_sent_result_uses_exact_per_occurrence_b7_snapshot(
    tmp_path, symlink_archive_directory
):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    current_report = state_dir / "last-result-report.json"
    rotated = json.loads(current_report.read_text())
    rotated["occurrenceId"] = f"{OWNER}:later-run"
    current_report.write_text(json.dumps(rotated), encoding="utf-8")
    current_report.chmod(0o600)

    snapshots = state_dir / "b7-readbacks"
    archive_directory = snapshots
    if symlink_archive_directory:
        archive_directory = tmp_path / "external-b7-readbacks"
        archive_directory.mkdir(mode=0o700)
        snapshots.symlink_to(archive_directory, target_is_directory=True)
    else:
        snapshots.mkdir(mode=0o700)
    snapshot = json.loads(_write_b7_snapshot(state_dir, occurrence).read_text())
    snapshot.update({"subjectId": "subject", "recipientHash": "c" * 64})
    archive = archive_directory / f"{occurrence}.json"
    archive.write_text(json.dumps(snapshot), encoding="utf-8")
    archive.chmod(0o600)

    if symlink_archive_directory:
        with pytest.raises(ValueError, match="b7_snapshot_directory_invalid"):
            build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
        return

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)

    assert proof["verified"] is True
    assert proof["provider_receipt_id"] == "telegram:94946"
    assert proof["report_source"] == "b7_occurrence_snapshot"


def test_legacy_b7_without_counter_contract_cannot_prove_delivery(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    current_report = state_dir / "last-result-report.json"
    report = json.loads(current_report.read_text())
    report["occurrenceId"] = f"{OWNER}:later-run"
    current_report.write_text(json.dumps(report), encoding="utf-8")
    current_report.chmod(0o600)
    _write_b7_snapshot(
        state_dir, occurrence, schema_version=3, include_counters=False,
    )

    with pytest.raises(ValueError, match="delivery_counters_unverified"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_b7_receipt_for_another_delivery_occurrence_cannot_prove_current_effect(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    current_report = state_dir / "last-result-report.json"
    report = json.loads(current_report.read_text())
    report["occurrenceId"] = f"{OWNER}:later-run"
    current_report.write_text(json.dumps(report), encoding="utf-8")
    current_report.chmod(0o600)
    archive = _write_b7_snapshot(state_dir, occurrence)
    snapshot = json.loads(archive.read_text())
    snapshot["deliveryOccurrenceId"] = f"{OWNER}:later-run"
    snapshot["deliveryRunId"] = "later-run"
    archive.write_text(json.dumps(snapshot), encoding="utf-8")
    archive.chmod(0o600)

    with pytest.raises(ValueError, match="b7_delivery_occurrence_mismatch"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_released_occurrence_without_provider_receipt_stays_rejected(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        admission_state="released",
        admission_effect_unknown=0,
        outbox_status="delivery_uncertain",
    )

    with pytest.raises(ValueError, match="provider_receipt_not_delivered"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_sent_current_result_proves_exact_receipt_without_subject_or_body(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)

    assert proof["verified"] is True
    assert proof["resolution_kind"] == "sent"
    assert proof["provider_receipt_id"] == "telegram:94946"
    assert proof["message_sha256"] == MESSAGE_SHA256
    assert proof["delivery_counters"] == {
        "attempted": 1, "delivered": 1, "delivery_uncertain": 0, "pre_send_failed": 0,
    }
    assert "subject" not in json.dumps(proof)
    assert "CFO current result fixture" not in json.dumps(proof)


@pytest.mark.parametrize("counters", [
    {"attempted": 2, "delivered": 1, "delivery_uncertain": 0, "pre_send_failed": 1},
    {"attempted": 1, "delivered": 1, "delivery_uncertain": 0},
    {"attempted": 1, "delivered": 1, "delivery_uncertain": 0, "pre_send_failed": 1},
])
def test_sent_report_with_invalid_counters_cannot_prove_or_resolve(tmp_path, monkeypatch, counters):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    report_path = state_dir / "last-result-report.json"
    report = json.loads(report_path.read_text())
    report["deliveryCounters"] = counters
    report_path.write_text(json.dumps(report), encoding="utf-8")
    report_path.chmod(0o600)
    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_unknown_occurrence",
        lambda *args, **kwargs: pytest.fail("invalid delivery counters must not release the fence"),
    )

    with pytest.raises(ValueError, match="delivery_counters_invalid"):
        reconcile(
            state_dir=state_dir,
            admission_db=admission_db,
            occurrence_id=occurrence,
            resolve=True,
        )


def test_pending_report_cannot_recover_from_outbox_without_b7_counter_evidence(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        report_status="pending",
        terminal_status="fail",
        terminal_exit_code=1,
    )
    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_unknown_occurrence",
        lambda *args, **kwargs: pytest.fail("outbox receipt alone must not release the fence"),
    )

    with pytest.raises(ValueError, match="b7_snapshot_missing"):
        reconcile(
            state_dir=state_dir,
            admission_db=admission_db,
            occurrence_id=occurrence,
            resolve=True,
        )


def test_pending_current_result_recovers_provider_receipt_after_crash(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        report_status="pending",
        terminal_status="fail",
        terminal_exit_code=1,
        delivered_at="2026-09-26T12:27:20Z",
    )
    _write_b7_snapshot(state_dir, occurrence)
    calls = []

    def resolver(owner_id, occurrence_id, **kwargs):
        calls.append((owner_id, occurrence_id, kwargs["official_readback"]()))
        return True

    monkeypatch.setattr(effect_reconcile_module, "resolve_unknown_occurrence", resolver)
    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_pre_effect_occurrence",
        lambda *args, **kwargs: pytest.fail("receipt recovery must not use pre-effect resolver"),
    )

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
    assert proof["verified"] is True
    assert proof["resolution_kind"] == "receipt_recovered"
    assert proof["provider_receipt_id"] == "telegram:94946"
    assert proof["report_source"] == "b7_occurrence_snapshot"

    result = reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
        resolve=True,
    )
    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][2]["provider_receipt_id"] == "telegram:94946"


def test_pending_current_result_with_terminal_pass_is_inconsistent(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        report_status="pending",
        terminal_status="pass",
        terminal_exit_code=0,
    )

    with pytest.raises(ValueError, match="pending_runtime_terminal_invalid"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_pending_current_result_with_uncertain_outbox_stays_fenced(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        report_status="pending",
        terminal_status="fail",
        terminal_exit_code=1,
        outbox_status="delivery_uncertain",
    )
    _write_b7_snapshot(state_dir, occurrence)

    with pytest.raises(ValueError, match="provider_receipt_not_delivered"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_sent_current_result_accepts_terminal_fail_after_receipt_window(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        report_status="sent",
        terminal_status="fail",
        terminal_exit_code=1,
        delivered_at="2026-09-26T12:27:20Z",
    )

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
    assert proof["resolution_kind"] == "sent"
    assert proof["provider_receipt_id"] == "telegram:94946"


def test_duplicate_current_result_accepts_terminal_fail_before_current_start(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        resolution_kind="duplicate",
        terminal_status="fail",
        terminal_exit_code=1,
        delivered_at="2026-09-26T12:27:00Z",
    )

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
    assert proof["resolution_kind"] == "duplicate"
    assert proof["proof_type"] == "pre_effect"


def test_normal_path_rejects_legacy_snapshot_without_current_result_report(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    current = state_dir / "last-result-report.json"
    current.unlink()
    (state_dir / "last-delivered-snapshot.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "status": "delivered",
            "reportingDate": DATE,
            "digest": "d" * 64,
            "delivery": {"delivery": "delivered", "provider_message_id": "94946"},
        }),
        encoding="utf-8",
    )
    (state_dir / "last-delivered-snapshot.json").chmod(0o600)

    with pytest.raises(ValueError, match="result_report_missing"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_duplicate_result_uses_pre_effect_resolver_only(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path, resolution_kind="duplicate", delivered_at="2026-09-26T12:27:00Z"
    )
    calls = []

    def resolver(owner_id, occurrence_id, **kwargs):
        proof = kwargs["pre_effect_readback"]()
        calls.append((owner_id, occurrence_id, proof, kwargs["expected_state"]))
        return True

    monkeypatch.setattr(effect_reconcile_module, "resolve_pre_effect_occurrence", resolver)
    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_unknown_occurrence",
        lambda *args, **kwargs: pytest.fail("duplicate must not use unknown resolver"),
    )
    result = reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=OCCURRENCE,
        resolve=True,
    )

    assert result["resolution_kind"] == "duplicate"
    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][2]["proof_type"] == "pre_effect"
    assert calls[0][2]["evidence_ref"].startswith("lm-event://")


def test_sent_result_uses_unknown_effect_resolver(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    calls = []

    def resolver(owner_id, occurrence_id, **kwargs):
        calls.append((owner_id, occurrence_id, kwargs["official_readback"]()))
        return True

    monkeypatch.setattr(effect_reconcile_module, "resolve_unknown_occurrence", resolver)
    monkeypatch.setattr(
        effect_reconcile_module,
        "resolve_pre_effect_occurrence",
        lambda *args, **kwargs: pytest.fail("sent must not use pre-effect resolver"),
    )
    result = reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=OCCURRENCE,
        resolve=True,
    )

    assert result["resolution_kind"] == "sent"
    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][2]["proof_type"] == "cfo_result_telegram_provider_receipt"


@pytest.mark.parametrize("delivered_at", ["2026-09-26T12:27:07.200Z", "2026-09-26T12:28:00Z"])
def test_duplicate_result_stays_fenced_if_delivery_is_at_or_after_current_start(tmp_path, delivered_at):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path, resolution_kind="duplicate", delivered_at="2026-09-26T12:27:00Z"
    )
    outbox = state_dir / "telegram-outbox.sqlite3"
    with sqlite3.connect(outbox) as connection:
        connection.execute("UPDATE telegram_outbox SET delivered_at=?", (delivered_at,))

    with pytest.raises(ValueError, match="duplicate_delivery_after_runtime_start"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


@pytest.mark.parametrize(
    ("delivered_at", "reason"),
    [
        ("2026-09-26T12:27:00Z", "sent_delivery_before_runtime_start"),
        ("2026-09-26T12:28:00Z", "sent_delivery_after_runtime_terminal"),
    ],
)
def test_sent_result_delivery_must_be_inside_current_runtime_pair(tmp_path, delivered_at, reason):
    state_dir, admission_db, occurrence = _fixture(tmp_path, delivered_at=delivered_at)

    with pytest.raises(ValueError, match=reason):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value.update({"occurrenceId": "life-manager-cfo-hourly:other"}), "occurrence_mismatch"),
        (lambda value: value.update({"channel": "email"}), "channel_not_telegram"),
        (lambda value: value.update({"resolutionKind": "unknown"}), "resolution_kind_invalid"),
        (lambda value: value.update({"messageSha256": "0" * 64}), "message_sha256_mismatch"),
        (lambda value: value.update({"providerMessageId": "other"}), "provider_message_id_mismatch"),
        (lambda value: value.update({"reportingDate": "2026-09-25"}), "reporting_date_mismatch"),
    ],
)
def test_normal_result_identity_mismatches_fail_closed(tmp_path, mutation, reason):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    path = state_dir / "last-result-report.json"
    value = json.loads(path.read_text())
    mutation(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ValueError, match=reason):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_missing_or_uncertain_current_receipt_stays_fenced(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path, outbox_status="delivery_uncertain")

    with pytest.raises(ValueError, match="provider_receipt_not_delivered"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_current_result_report_is_generated_by_real_producer_and_reconciled(tmp_path):
    state_dir = tmp_path / "producer-cfo"
    state_dir.mkdir(mode=0o700)
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute("INSERT INTO occurrences VALUES(?,?,?,?)", (OCCURRENCE, OWNER, "claimed", 1))

    script = """
const { runResultCfo } = require(process.env.CFO_RESULT_MODULE);
runResultCfo({
  stateDir: process.env.CFO_STATE_DIR,
  subjectId: "subject",
  occurrenceId: "life-manager-cfo-hourly:current-run-1",
  reportChannel: "telegram",
  chatId: "123456",
  reportCadence: "hourly",
  now: "2026-09-26T03:00:00Z",
  collect: async date => ({ reporting_date: date, rows: [{ loop_id: "capafy", revenue: { status: "verified", amounts: { USD: "1" }, receipts: ["receipt:1"] } }] }),
  notify: async () => ({ delivery: "delivered", provider_message_id: "94946", attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }),
}).then(result => process.stdout.write(JSON.stringify(result))).catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LIFE_MANAGER_RELEASE_SHA": RELEASE_SHA, "CFO_RESULT_MODULE": str(ROOT / "apps/life-manager/scripts/cfo-result-local.js"), "CFO_STATE_DIR": str(state_dir)},
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((state_dir / "last-result-report.json").read_text())
    assert report["occurrenceId"] == OCCURRENCE
    assert report["channel"] == "telegram"
    assert report["resolutionKind"] == "sent"
    assert report["deliveryCounters"] == {
        "attempted": 1, "delivered": 1, "delivery_uncertain": 0, "pre_send_failed": 0,
    }
    assert report["messageSha256"] == hashlib.sha256(report["message"].encode()).hexdigest()
    b7 = json.loads((state_dir / "b7-readbacks" / f"{OCCURRENCE}.json").read_text())
    assert b7["schemaVersion"] == 4
    assert b7["deliveryCounters"] == report["deliveryCounters"]

    enqueue(
        database=state_dir / "telegram-outbox.sqlite3",
        event_key=report["eventKey"],
        message=report["message"],
        created_at="2026-09-26T02:59:00Z",
        repeat_after_seconds=None,
    )
    claimed = claim_next(state_dir / "telegram-outbox.sqlite3")
    assert claimed is not None
    mark_delivered(
        state_dir / "telegram-outbox.sqlite3",
        report["eventKey"],
        "94946",
        "2026-09-26T03:00:20Z",
        claimed_at=claimed.claimed_at,
    )
    (state_dir / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in (
            _event(phase="execute", status="running", effect_status="started", timestamp="2026-09-26T03:00:07Z"),
            _event(phase="report", status="pass", effect_status="unknown", exit_code=0, timestamp="2026-09-26T03:00:38Z"),
        )),
        encoding="utf-8",
    )
    (state_dir / "events.jsonl").chmod(0o600)

    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=OCCURRENCE)
    assert proof["verified"] is True
    assert proof["resolution_kind"] == "sent"
