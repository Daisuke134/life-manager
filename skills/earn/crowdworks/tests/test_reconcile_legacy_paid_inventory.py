import importlib.util
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_legacy_paid_inventory.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_legacy_paid_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def event(status, timestamp, *, blocker=None, refs=None):
    return {
        "version": 1, "event_id": f"event-{status}", "timestamp": timestamp,
        "loop_id": "crowdworks-revenue-paid", "domain": "earn", "run_id": "run-1",
        "phase": "execute" if status == "running" else "report", "status": status,
        "release_sha": "a" * 40, "provider": "deterministic", "profile_alias": None,
        "effect_class": "money", "effect_status": "started" if status == "running" else "unknown",
        "blocker": blocker,
        "evidence_refs": refs or ["lm-loop://crowdworks-revenue-paid/run-1/summary.json"],
    }


def write_fixture(tmp_path, latest):
    events = tmp_path / "events.jsonl"
    events.write_text("".join(json.dumps(row) + "\n" for row in [
        event("running", "2026-09-17T22:16:28.142021+00:00"),
        event("fail", "2026-09-17T22:16:57.677072+00:00",
              blocker="entrypoint_exit_1",
              refs=["lm-loop://crowdworks-revenue-paid/run-1/summary.json",
                    "lm-occurrence://crowdworks-revenue-paid/old-1/claim"]),
    ]), encoding="utf-8")
    latest_path = tmp_path / "paid-latest.json"
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    os.utime(latest_path, (1789683411.0, 1789683411.0))
    return events, latest_path


def test_exact_inventory_failure_window_is_pre_effect_proof(tmp_path):
    module = load()
    events, latest = write_fixture(tmp_path, {
        "status": "failed", "failed_step": "provider_inventory", "effect": 0,
        "observed": 0, "readback": 0, "items": [],
    })
    proof = module.find_legacy_proof(
        events, latest, "crowdworks-revenue-paid",
        "crowdworks-revenue-paid:old-1",
    )
    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"


def test_inventory_effect_or_out_of_window_is_rejected(tmp_path):
    module = load()
    events, latest = write_fixture(tmp_path, {
        "status": "failed", "failed_step": "provider_inventory", "effect": 1,
        "observed": 0, "readback": 0, "items": [],
    })
    assert module.find_legacy_proof(
        events, latest, "crowdworks-revenue-paid",
        "crowdworks-revenue-paid:old-1",
    ) is None

    latest.write_text(json.dumps({
        "status": "failed", "failed_step": "provider_inventory", "effect": 0,
        "observed": 0, "readback": 0, "items": [],
    }), encoding="utf-8")
    os.utime(latest, (1789680000.0, 1789680000.0))
    assert module.find_legacy_proof(
        events, latest, "crowdworks-revenue-paid",
        "crowdworks-revenue-paid:old-1",
    ) is None


def test_reconcile_is_read_only_without_resolve(tmp_path, monkeypatch):
    module = load()
    events, latest = write_fixture(tmp_path, {
        "status": "failed", "failed_step": "provider_inventory", "effect": 0,
        "observed": 0, "readback": 0, "items": [],
    })
    monkeypatch.setattr(module, "resolve_pre_effect_occurrence",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("resolve must be opt-in")))
    result = module.reconcile(
        events_path=events, latest_path=latest,
        owner="crowdworks-revenue-paid",
        occurrence="crowdworks-revenue-paid:old-1", resolve=False,
    )
    assert result["resolved"] is False
