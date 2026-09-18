import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_host_deferred.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_reconcile_host_deferred_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def event(*, owner, run, status, effect_status, blocker=None, refs=None):
    return {
        "version": 1,
        "event_id": f"{run}-{status}",
        "timestamp": "2026-09-18T00:00:00+00:00",
        "loop_id": owner,
        "domain": "earn",
        "run_id": run,
        "phase": "execute" if status == "running" else "report",
        "status": status,
        "release_sha": "a" * 40,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "application",
        "effect_status": effect_status,
        "blocker": blocker,
        "evidence_refs": refs or [f"lm-loop://{owner}/{run}/summary.json"],
    }


def write_events(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_host_deferred_event_is_explicit_pre_effect_proof(tmp_path):
    module = load()
    owner = "crowdworks-revenue-application"
    run = "run-1"
    events = tmp_path / "events.jsonl"
    write_events(events, [
        event(owner=owner, run=run, status="running", effect_status="started"),
        event(owner=owner, run=run, status="blocked", effect_status="unknown",
              blocker="host_admission_deferred:resource_capacity_busy"),
    ])

    proof = module.find_host_deferred_proof(events, owner, f"{owner}:{run}")

    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].startswith("lm-event://")


def test_host_deferred_proof_rejects_effect_identity_and_non_deferred_terminal(tmp_path):
    module = load()
    owner = "crowdworks-revenue-reply"
    run = "run-2"
    events = tmp_path / "events.jsonl"
    write_events(events, [
        event(owner=owner, run=run, status="running", effect_status="started"),
        event(owner=owner, run=run, status="blocked", effect_status="unknown",
              blocker="host_admission_deferred:resource_capacity_busy",
              refs=[f"lm-loop://{owner}/{run}/summary.json",
                    f"lm-effect://{owner}/{run}/identity.jsonl"]),
    ])
    assert module.find_host_deferred_proof(events, owner, f"{owner}:{run}") is None

    write_events(events, [
        event(owner=owner, run=run, status="running", effect_status="started"),
        event(owner=owner, run=run, status="fail", effect_status="unknown",
              blocker="entrypoint_exit_1"),
    ])
    assert module.find_host_deferred_proof(events, owner, f"{owner}:{run}") is None


def test_reconcile_does_not_mutate_without_resolve_flag(tmp_path, monkeypatch):
    module = load()
    owner = "crowdworks-revenue-application"
    run = "run-3"
    events = tmp_path / "events.jsonl"
    write_events(events, [
        event(owner=owner, run=run, status="running", effect_status="started"),
        event(owner=owner, run=run, status="blocked", effect_status="unknown",
              blocker="host_admission_deferred:resource_capacity_busy"),
    ])
    monkeypatch.setattr(module, "resolve_pre_effect_occurrence",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("resolve must be opt-in")))

    result = module.reconcile(state_root=tmp_path, owner=owner,
                              occurrence=f"{owner}:{run}", resolve=False)

    assert result["resolved"] is False
    assert result["proof_type"] == "pre_effect"
