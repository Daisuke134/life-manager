import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_pre_effect.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_reconcile_pre_effect_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_find_matching_intent_requires_one_exact_form_binding(tmp_path):
    module = load()
    state = tmp_path / "items" / "item" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({
        "version": 1,
        "status": "intent_persisted",
        "occurrence_id": "crowdworks-revenue-paid:run-1",
        "observation": {"work_id": "63659463"},
        "intent": {"action": "submit", "account_id": "7145638",
                    "payload": {"form_sha256": "a" * 64,
                                "milestone_id": "13820867"}},
    }), encoding="utf-8")
    result = module.find_matching_intent(
        tmp_path, "63659463", "a" * 64, "crowdworks-revenue-paid:run-1")
    assert result["intent"]["payload"]["milestone_id"] == "13820867"


def test_find_matching_intent_rejects_missing_or_ambiguous_match(tmp_path):
    module = load()
    assert module.find_matching_intent(
        tmp_path, "63659463", "a" * 64, "crowdworks-revenue-paid:run-1") is None


def test_find_matching_intent_rejects_different_occurrence(tmp_path):
    module = load()
    state = tmp_path / "items" / "item" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({
        "version": 1, "status": "intent_persisted",
        "occurrence_id": "crowdworks-revenue-paid:run-1",
        "observation": {"work_id": "63659463"},
        "intent": {"action": "submit", "payload": {"form_sha256": "a" * 64}},
    }), encoding="utf-8")
    assert module.find_matching_intent(
        tmp_path, "63659463", "a" * 64, "crowdworks-revenue-paid:other") is None


def test_run_marker_must_prove_the_same_occurrence_was_pre_effect(tmp_path):
    module = load()
    marker = tmp_path / "run.json"
    marker.write_text(json.dumps({
        "version": 1, "occurrence_id": "crowdworks-revenue-paid:run-1",
        "status": "pre_effect",
    }), encoding="utf-8")
    assert module._run_proves_no_dispatch(marker, "crowdworks-revenue-paid:run-1") is True
    assert module._run_proves_no_dispatch(marker, "crowdworks-revenue-paid:other") is False
