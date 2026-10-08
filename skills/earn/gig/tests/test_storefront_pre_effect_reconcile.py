from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "storefront_pre_effect_reconcile.py"
OWNER_ID = "hf-gig-storefront-direct"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "gig_storefront_pre_effect_reconcile", SCRIPT,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)


def write_stdout_log(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def runtime_event(run_id: str, phase: str, timestamp: str, *,
                  status: str, effect_status: str,
                  refs: list[str], owner_id: str = OWNER_ID,
                  occurrence_id: str | None = None) -> dict:
    return {
        "version": 1,
        "event_id": ("a" if phase == "execute" else "b") * 24,
        "timestamp": timestamp,
        "loop_id": OWNER_ID,
        "product_loop_id": "gig-coconala",
        "job_id": OWNER_ID,
        "owner_id": owner_id,
        "wake_id": run_id,
        "occurrence_id": occurrence_id or f"{OWNER_ID}:{run_id}",
        "loaded_argv_sha256": None,
        "loaded_env_sha256": None,
        "exit_code": None,
        "failure_layer": "clean",
        "error_class": None,
        "retryable": False,
        "next_action": "monitor_running" if phase == "execute" else "none",
        "provider_receipt_id": None,
        "official_readback_ref": None,
        "domain": "earn",
        "run_id": run_id,
        "phase": phase,
        "status": status,
        "release_sha": "1" * 40,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "publish",
        "effect_status": effect_status,
        "blocker": "host_admission_deferred:resource_effect_unknown" if phase == "report" else None,
        "evidence_refs": refs,
    }


def start_terminal_events(
    run_id: str, *, terminal_occurrence_id: str | None = None,
    terminal_status: str = "fail",
    extra_terminal_refs: list[str] | None = None,
) -> list[dict]:
    ref = f"lm-loop://{OWNER_ID}/{run_id}/summary.json"
    claimed_occurrence_id = terminal_occurrence_id or f"{OWNER_ID}:{run_id}"
    claimed_id = claimed_occurrence_id.removeprefix(f"{OWNER_ID}:")
    return [
        runtime_event(
            run_id, "execute", "1970-01-01T00:05:00+00:00",
            status="running", effect_status="started", refs=[ref],
            occurrence_id=f"{OWNER_ID}:{run_id}",
        ),
        runtime_event(
            run_id, "report", "1970-01-01T00:05:10+00:00",
            status=terminal_status, effect_status="unknown",
            refs=[ref, f"lm-occurrence://{OWNER_ID}/{claimed_id}/claim",
                  *(extra_terminal_refs or [])],
            occurrence_id=claimed_occurrence_id,
        ),
    ]


def pass_line(*, observed_at_epoch: int, status: str = "failed", effect: int = 0,
             actionable: int = 0, readback: int = 0,
             reason: str = "official_service_contract_invalid",
             runtime_run_id: str | None = None,
             runtime_occurrence_id: str | None = None) -> dict:
    row = {
        "version": 1,
        "pass_id": f"storefront-direct-{observed_at_epoch}-123",
        "observed_at_epoch": observed_at_epoch,
        "status": status,
        "decision": None,
        "reason": reason,
        "actionable": actionable,
        "effect": effect,
        "readback": readback,
        "duplicate": 0,
    }
    if runtime_run_id is not None:
        row["runtime_run_id"] = runtime_run_id
    if runtime_occurrence_id is not None:
        row["runtime_occurrence_id"] = runtime_occurrence_id
    return row


def write_admission_db(database: Path, occurrence_id: str, *,
                       state: str = "claimed", effect_unknown: int = 1,
                       owner_id: str = OWNER_ID) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE occurrences(
                   occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT,
                   effect_unknown INTEGER
               )"""
        )
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?)",
            (occurrence_id, owner_id, state, effect_unknown),
        )


def fixture(tmp_path: Path, *, run_id: str = "run-1", **overrides) -> tuple[Path, Path, Path, str]:
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    write_jsonl(state_root / "events.jsonl", start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id,
    ))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=300, runtime_run_id=run_id,
        runtime_occurrence_id=occurrence_id, **overrides,
    )])
    write_admission_db(database, occurrence_id)
    return state_root, stdout_log, database, run_id


def test_happy_path_is_proof_ready(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=False, database=database,
    )

    assert result["state"] == "PROOF_READY"
    assert result["occurrence_id"] == f"{OWNER_ID}:{run_id}"
    assert result["evidence"]["reason"] == "official_service_contract_invalid"
    assert result["evidence"]["pass_id"].startswith("storefront-direct-")


def test_legacy_unique_pass_id_timestamp_binds_stdout_to_runtime_window(tmp_path):
    module = load_module()
    run_id = "18d8d2b3f46565c8-28218"
    occurrence_id = "hf-gig-storefront-direct:18d8d288748508e8-23902"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    events = start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id, terminal_status="fail",
    )
    events[0]["timestamp"] = "2026-09-26T08:48:42.226213+00:00"
    events[1]["timestamp"] = "2026-09-26T08:50:02.527789+00:00"
    write_jsonl(state_root / "events.jsonl", events)
    row = pass_line(
        observed_at_epoch=1790412601,
        status="failed",
        reason="official_service_contract_invalid",
    )
    row["pass_id"] = "storefront-direct-1790412524275908000-28241"
    write_stdout_log(stdout_log, [row])
    write_admission_db(database, occurrence_id)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log,
        occurrence_id=occurrence_id, resolve=False, database=database,
    )

    assert result["state"] == "PROOF_READY", result
    assert result["evidence"]["run_id"] == run_id
    assert result["evidence"]["stdout_binding_method"] == "pass_id_timestamp"


def test_legacy_pass_id_timestamp_outside_runtime_window_refuses(tmp_path):
    module = load_module()
    run_id = "18d8d2b3f46565c8-28218"
    occurrence_id = "hf-gig-storefront-direct:18d8d288748508e8-23902"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    events = start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id, terminal_status="fail",
    )
    events[0]["timestamp"] = "2026-09-26T08:48:42.226213+00:00"
    events[1]["timestamp"] = "2026-09-26T08:50:02.527789+00:00"
    write_jsonl(state_root / "events.jsonl", events)
    row = pass_line(
        observed_at_epoch=1790412601,
        status="failed",
        reason="official_service_contract_invalid",
    )
    row["pass_id"] = "storefront-direct-1790412520000000000-28241"
    write_stdout_log(stdout_log, [row])
    write_admission_db(database, occurrence_id)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log,
        occurrence_id=occurrence_id, resolve=False, database=database,
    )

    assert result == {
        "state": "HELD", "reason": "stdout_runtime_binding_invalid",
    }


def test_resolve_writes_private_receipt_and_uses_exact_proof(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result["state"] == "RECONCILED"
    receipt = Path(result["receipt_path"])
    assert receipt.stat().st_mode & 0o777 == 0o600
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["resolution_state"] == "RESOLVED"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    proof = resolver.call_args.kwargs["pre_effect_readback"]()
    assert proof == {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": result["evidence_ref"],
    }
    assert resolver.call_args.kwargs["expected_state"] == "claimed"
    assert resolver.call_args.args == (OWNER_ID, occurrence_id)


def test_released_admission_state_is_passed_through(tmp_path):
    module = load_module()
    run_id = "run-released"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    write_jsonl(state_root / "events.jsonl", start_terminal_events(run_id))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=300, runtime_run_id=run_id,
        runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id, state="released")
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result["state"] == "RECONCILED"
    assert resolver.call_args.kwargs["expected_state"] == "released"


def test_two_pass_lines_in_window_refuses(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    write_stdout_log(stdout_log, [
        pass_line(observed_at_epoch=301),
        pass_line(observed_at_epoch=302),
    ])
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "stdout_pass_count_invalid"}
    resolver.assert_not_called()


def test_nonzero_effect_refuses(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path, effect=1)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "pass_line_not_pre_effect_proof"}
    resolver.assert_not_called()


def test_reason_not_allowlisted_refuses(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(
        tmp_path, reason="storefront_browser_unavailable",
    )
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "pass_line_not_pre_effect_proof"}
    resolver.assert_not_called()


def test_lm_effect_ref_present_refuses(tmp_path):
    module = load_module()
    run_id = "run-effect-ref"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    write_jsonl(state_root / "events.jsonl", start_terminal_events(
        run_id, extra_terminal_refs=[f"lm-effect://{OWNER_ID}/{run_id}/identity"],
    ))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=300, runtime_run_id=run_id,
        runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "runtime_event_shape_invalid"}
    resolver.assert_not_called()


def test_dry_run_does_not_call_resolver(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=False, database=database, resolver=resolver,
    )

    assert result["state"] == "PROOF_READY"
    resolver.assert_not_called()
    assert not (state_root / "reconciliation").exists()


def test_admission_not_effect_unknown_refuses(tmp_path):
    module = load_module()
    run_id = "run-clean"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    database = tmp_path / "admission.sqlite3"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    write_jsonl(state_root / "events.jsonl", start_terminal_events(run_id))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=300, runtime_run_id=run_id,
        runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id, effect_unknown=0)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, occurrence_id=f"{OWNER_ID}:{run_id}",
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "admission_occurrence_not_effect_unknown"}
    resolver.assert_not_called()


def test_cli_joins_pending_inventory_to_claimed_occurrence_not_run_suffix(
    tmp_path, monkeypatch, capsys,
):
    module = load_module()
    run_id = "runtime-run-1"
    occurrence_id = f"{OWNER_ID}:claimed-occurrence-1"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    host_root = tmp_path / "host-admission"
    database = host_root / "admission-v2.sqlite3"
    host_root.mkdir()
    write_jsonl(state_root / "events.jsonl", start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id, terminal_status="pass",
    ))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=305, status="pending", reason="official_inventory_empty_or_invalid",
        runtime_run_id=run_id, runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id)
    monkeypatch.setattr(module, "admission_root", lambda: host_root)

    return_code = module.main([
        "--occurrence", occurrence_id, "--state-root", str(state_root),
        "--stdout-log", str(stdout_log), "--dry-run",
    ])
    result = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert result["state"] == "PROOF_READY"
    assert result["occurrence_id"] == occurrence_id
    assert result["evidence"]["run_id"] == run_id


def test_cli_refuses_a_pre_effect_line_for_a_different_occurrence(tmp_path, monkeypatch, capsys):
    module = load_module()
    run_id = "runtime-run-2"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    other_occurrence_id = f"{OWNER_ID}:other-claim"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    host_root = tmp_path / "host-admission"
    database = host_root / "admission-v2.sqlite3"
    host_root.mkdir()
    write_jsonl(state_root / "events.jsonl", start_terminal_events(
        run_id, terminal_occurrence_id=other_occurrence_id,
    ))
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=305, runtime_run_id=run_id,
        runtime_occurrence_id=other_occurrence_id,
    )])
    write_admission_db(database, occurrence_id)
    monkeypatch.setattr(module, "admission_root", lambda: host_root)

    return_code = module.main([
        "--occurrence", occurrence_id, "--state-root", str(state_root),
        "--stdout-log", str(stdout_log), "--dry-run",
    ])
    result = json.loads(capsys.readouterr().out)

    assert return_code == 1
    assert result["state"] == "HELD"


def test_cli_refuses_multiple_terminal_reports_for_one_occurrence(tmp_path, monkeypatch, capsys):
    module = load_module()
    occurrence_id = f"{OWNER_ID}:claimed-occurrence-4"
    original_run = "runtime-run-original"
    resumed_run = "runtime-run-resumed"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    host_root = tmp_path / "host-admission"
    database = host_root / "admission-v2.sqlite3"
    host_root.mkdir()
    original = start_terminal_events(original_run, terminal_occurrence_id=occurrence_id)
    original[1]["event_id"] = "b" * 23 + "1"
    original[1]["evidence_refs"] = [f"lm-loop://{OWNER_ID}/{original_run}/summary.json"]
    resumed = start_terminal_events(
        resumed_run, terminal_occurrence_id=occurrence_id, terminal_status="pass",
    )
    resumed[0]["event_id"] = "a" * 23 + "2"
    resumed[1]["event_id"] = "b" * 23 + "2"
    write_jsonl(state_root / "events.jsonl", [*original, *resumed])
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=305, status="pending", reason="official_inventory_empty_or_invalid",
        runtime_run_id=resumed_run, runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id)
    monkeypatch.setattr(module, "admission_root", lambda: host_root)

    return_code = module.main([
        "--occurrence", occurrence_id, "--state-root", str(state_root),
        "--stdout-log", str(stdout_log), "--dry-run",
    ])
    result = json.loads(capsys.readouterr().out)

    assert return_code == 1
    assert result["state"] == "HELD"


@pytest.mark.parametrize("field", ["loop_id", "owner_id"])
def test_cli_refuses_runtime_event_from_another_owner(field, tmp_path, monkeypatch, capsys):
    module = load_module()
    run_id = "runtime-run-foreign"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    host_root = tmp_path / "host-admission"
    database = host_root / "admission-v2.sqlite3"
    host_root.mkdir()
    events = start_terminal_events(run_id, terminal_occurrence_id=occurrence_id)
    events[1][field] = "another-owner"
    write_jsonl(state_root / "events.jsonl", events)
    write_stdout_log(stdout_log, [pass_line(
        observed_at_epoch=305, runtime_run_id=run_id,
        runtime_occurrence_id=occurrence_id,
    )])
    write_admission_db(database, occurrence_id)
    monkeypatch.setattr(module, "admission_root", lambda: host_root)

    return_code = module.main([
        "--occurrence", occurrence_id, "--state-root", str(state_root),
        "--stdout-log", str(stdout_log), "--dry-run",
    ])
    result = json.loads(capsys.readouterr().out)

    assert return_code == 1
    assert result["state"] == "HELD"


def test_cli_holds_legacy_stdout_without_runtime_binding(tmp_path, monkeypatch, capsys):
    module = load_module()
    run_id = "runtime-run-3"
    occurrence_id = f"{OWNER_ID}:{run_id}"
    state_root = tmp_path / "storefront"
    stdout_log = state_root / "logs" / "launchd.out.log"
    host_root = tmp_path / "host-admission"
    database = host_root / "admission-v2.sqlite3"
    host_root.mkdir()
    write_jsonl(state_root / "events.jsonl", start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id,
    ))
    write_stdout_log(stdout_log, [pass_line(observed_at_epoch=305)])
    write_admission_db(database, occurrence_id)
    monkeypatch.setattr(module, "admission_root", lambda: host_root)

    return_code = module.main([
        "--occurrence", occurrence_id, "--state-root", str(state_root),
        "--stdout-log", str(stdout_log), "--dry-run",
    ])
    result = json.loads(capsys.readouterr().out)

    assert return_code == 1
    assert result["state"] == "HELD"


def test_cli_dry_run_defaults_stdout_log_under_state_root(tmp_path, capsys):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    module.reconcile = Mock(return_value={"state": "PROOF_READY", "occurrence_id":
                                          f"{OWNER_ID}:{run_id}", "evidence_ref": "x",
                                          "evidence": {}})

    return_code = module.main([
        "--occurrence", f"{OWNER_ID}:{run_id}",
        "--state-root", str(state_root),
        "--dry-run",
    ])

    assert return_code == 0
    call_kwargs = module.reconcile.call_args.kwargs
    assert call_kwargs["stdout_log"] == (state_root / "logs" / "launchd.out.log").resolve()
    assert call_kwargs["resolve"] is False


def test_cli_occurrence_owner_mismatch_refuses(capsys, tmp_path):
    module = load_module()
    return_code = module.main([
        "--occurrence", "some-other-owner:run-1",
        "--state-root", str(tmp_path / "storefront"),
        "--dry-run",
    ])

    assert return_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "state": "HELD", "reason": "occurrence_owner_mismatch",
    }
