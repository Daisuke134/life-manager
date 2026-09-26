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
                  refs: list[str]) -> dict:
    return {
        "version": 1,
        "event_id": ("a" if phase == "execute" else "b") * 24,
        "timestamp": timestamp,
        "loop_id": OWNER_ID,
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


def start_terminal_events(run_id: str, *, extra_terminal_refs: list[str] | None = None) -> list[dict]:
    ref = f"lm-loop://{OWNER_ID}/{run_id}/summary.json"
    return [
        runtime_event(
            run_id, "execute", "1970-01-01T00:05:00+00:00",
            status="running", effect_status="started", refs=[ref],
        ),
        runtime_event(
            run_id, "report", "1970-01-01T00:05:10+00:00",
            status="fail", effect_status="unknown",
            refs=[ref, *(extra_terminal_refs or [])],
        ),
    ]


def pass_line(*, observed_at_epoch: int, status: str = "failed", effect: int = 0,
             actionable: int = 0, readback: int = 0,
             reason: str = "official_service_contract_invalid") -> dict:
    return {
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
    write_jsonl(state_root / "events.jsonl", start_terminal_events(run_id))
    write_stdout_log(stdout_log, [pass_line(observed_at_epoch=300, **overrides)])
    write_admission_db(database, occurrence_id)
    return state_root, stdout_log, database, run_id


def test_happy_path_is_proof_ready(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
        resolve=False, database=database,
    )

    assert result["state"] == "PROOF_READY"
    assert result["occurrence_id"] == f"{OWNER_ID}:{run_id}"
    assert result["evidence"]["reason"] == "official_service_contract_invalid"
    assert result["evidence"]["pass_id"].startswith("storefront-direct-")


def test_resolve_writes_private_receipt_and_uses_exact_proof(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
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
    write_stdout_log(stdout_log, [pass_line(observed_at_epoch=300)])
    write_admission_db(database, occurrence_id, state="released")
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
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
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "stdout_pass_count_invalid"}
    resolver.assert_not_called()


def test_nonzero_effect_refuses(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path, effect=1)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
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
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
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
    write_stdout_log(stdout_log, [pass_line(observed_at_epoch=300)])
    write_admission_db(database, occurrence_id)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "runtime_event_shape_invalid"}
    resolver.assert_not_called()


def test_dry_run_does_not_call_resolver(tmp_path):
    module = load_module()
    state_root, stdout_log, database, run_id = fixture(tmp_path)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
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
    write_stdout_log(stdout_log, [pass_line(observed_at_epoch=300)])
    write_admission_db(database, occurrence_id, effect_unknown=0)
    resolver = Mock(return_value=True)

    result = module.reconcile(
        state_root=state_root, stdout_log=stdout_log, run_id=run_id,
        resolve=True, database=database, resolver=resolver,
    )

    assert result == {"state": "HELD", "reason": "admission_occurrence_not_effect_unknown"}
    resolver.assert_not_called()


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
