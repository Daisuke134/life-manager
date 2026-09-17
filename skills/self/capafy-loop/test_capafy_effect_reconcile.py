from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


SCRIPT = Path(__file__).with_name("capafy-effect-reconcile.py")


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_effect_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    events = tmp_path / "events.jsonl"
    terminals = tmp_path / "terminals.jsonl"
    events.write_text(json.dumps({
        "run_id": "run-1",
        "phase": "report",
        "status": "pass",
        "blocker": None,
        "effect_status": "not_applicable",
        "timestamp": "2026-09-17T05:37:29Z",
    }) + "\n")
    terminals.write_text(json.dumps({
        "phase": "terminal",
        "rc": 0,
        "verdict": "CAP_FULL",
        "observed_at": "2026-09-17T05:37:29Z",
        "execution_id": "exec-1",
    }) + "\n")
    return events, terminals


def test_cap_full_proof_requires_pass_and_matching_no_write_terminal(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    events, terminals = fixture_files(tmp_path)
    monkeypatch.setattr(module, "_inventory", lambda _root: {
        "verdict": "CAP_FULL", "counts": {"occupied": 5},
    })

    proof = module.build_proof(
        owner_id="capafy-loop-daily",
        occurrence_id="capafy-loop-daily:occ-1",
        run_id="run-1",
        events=events,
        terminals=terminals,
        release_root=tmp_path,
    )

    assert proof["verified"] is True
    assert proof["proof_kind"] == "official_cap_full_no_write"
    assert proof["provider_receipt_id"].startswith("capafy-no-write:")


def test_cap_full_proof_rejects_missing_terminal(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    events, terminals = fixture_files(tmp_path)
    terminals.write_text("")
    monkeypatch.setattr(module, "_inventory", lambda _root: {
        "verdict": "CAP_FULL", "counts": {"occupied": 5},
    })

    try:
        module.build_proof(
            owner_id="capafy-loop-daily",
            occurrence_id="capafy-loop-daily:occ-1",
            run_id="run-1",
            events=events,
            terminals=terminals,
            release_root=tmp_path,
        )
    except ValueError as exc:
        assert "CAP_FULL" in str(exc)
    else:
        raise AssertionError("missing no-write terminal was accepted")


def test_reconcile_released_unknown_requires_exact_run_and_never_reads_claimed(
        tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    events, terminals = fixture_files(tmp_path)
    admission_root = tmp_path / "admission"
    admission_root.mkdir()
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
        connection.executescript("""
            CREATE TABLE occurrences (
                occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT,
                effect_unknown INTEGER, sequence INTEGER
            );
            INSERT INTO occurrences VALUES
              ('capafy-loop-daily:run-1', 'capafy-loop-daily', 'released', 1, 1),
              ('capafy-loop-daily:claimed', 'capafy-loop-daily', 'claimed', 1, 2);
        """)

    monkeypatch.setattr(module, "_inventory", lambda _root: {
        "verdict": "CAP_FULL", "counts": {"occupied": 5},
    })
    resolved = []
    monkeypatch.setattr(
        "runtime.host.resource_admission.resolve_unknown_occurrence",
        lambda owner, occurrence, official_readback: resolved.append(
            (owner, occurrence, official_readback())) or True,
    )

    result = module.reconcile_released_unknowns(
        owner_id="capafy-loop-daily", events=events, terminals=terminals,
        release_root=tmp_path,
    )

    assert [item["occurrence_id"] for item in result] == [
        "capafy-loop-daily:run-1"
    ]
    assert [item[1] for item in resolved] == ["capafy-loop-daily:run-1"]
