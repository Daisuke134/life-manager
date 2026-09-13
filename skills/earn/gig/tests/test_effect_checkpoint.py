import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "effect_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("effect_checkpoint", MODULE)
effect_checkpoint = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(effect_checkpoint)


def test_prepares_agent_receipt_without_repeating_official_fields():
    digest = "a" * 64
    value = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "message_sha256": digest,
        "semantic_contract_sha256": "b" * 64,
        "quality_status": "invalid",
        "qualification_sources": ["https://www.tiktok.com/messages"],
        "official_readback": {
            "official_url": "https://www.tiktok.com/messages",
            "exact_readback": True,
        },
    }

    prepared = effect_checkpoint.prepare_checkpoint(value)

    assert prepared["payload_sha256"] == digest
    assert prepared["official_receipt_url"] == "https://www.tiktok.com/messages"
    assert prepared["exact_readback"] is True
    assert effect_checkpoint.valid_checkpoint(prepared)


def test_does_not_invent_missing_effect_evidence():
    value = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "semantic_contract_sha256": "b" * 64,
        "quality_status": "invalid",
        "qualification_sources": ["https://www.tiktok.com/messages"],
        "official_readback": {"official_url": "https://www.tiktok.com/messages"},
    }

    assert not effect_checkpoint.valid_checkpoint(effect_checkpoint.prepare_checkpoint(value))


@pytest.mark.parametrize("value", [
    {"payload_sha256": "a" * 64, "message_sha256": "b" * 64},
    {"payload_sha256": "a" * 64, "message_sha256": None},
    {"official_receipt_url": "https://one.example", "official_readback": {
        "official_url": "https://two.example",
    }},
    {"official_receipt_url": "https://one.example", "official_readback": {
        "official_url": None,
    }},
    {"exact_readback": False, "official_readback": {"exact_readback": True}},
    {"exact_readback": True, "official_readback": {"exact_readback": 1}},
    {"exact_readback": True, "official_readback": {"exact_readback": None}},
])
def test_rejects_conflicting_flat_and_official_fields(value):

    with pytest.raises(ValueError, match="conflicting checkpoint field"):
        effect_checkpoint.prepare_checkpoint(value)


def _run_cli(tmp_path, value):
    project = tmp_path / "project"
    effect = project / "delivery" / "effect.json"
    effect.parent.mkdir(parents=True, exist_ok=True)
    effect.write_text(json.dumps(value), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(MODULE), "--project-root", str(project), "--effect-json", str(effect)],
        text=True, capture_output=True,
    )
    return result, project / "delivery" / "paid-remote-progress.jsonl"


def test_cli_appends_normalized_receipt_and_replays_identically(tmp_path):
    digest = "a" * 64
    value = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "message_sha256": digest,
        "semantic_contract_sha256": "b" * 64,
        "quality_status": "qualified",
        "qualification_sources": ["https://www.tiktok.com/messages"],
        "official_readback": {
            "official_url": "https://www.tiktok.com/messages",
            "exact_readback": True,
        },
    }

    first, ledger = _run_cli(tmp_path, value)
    second, _ = _run_cli(tmp_path, value)

    assert first.returncode == second.returncode == 0
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_cli_rejects_different_receipt_for_existing_effect_key(tmp_path):
    base = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "payload_sha256": "a" * 64,
        "semantic_contract_sha256": "b" * 64,
        "official_receipt_url": "https://www.tiktok.com/messages",
        "exact_readback": True,
        "quality_status": "qualified",
        "qualification_sources": ["https://www.tiktok.com/messages"],
    }
    first, _ = _run_cli(tmp_path, base)
    changed = {**base, "payload_sha256": "c" * 64}
    second, _ = _run_cli(tmp_path, changed)

    assert first.returncode == 0
    assert second.returncode != 0
    assert "differs from durable receipt" in second.stderr


def test_cli_rejects_changed_aggregate_field_for_existing_effect_key(tmp_path):
    base = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "payload_sha256": "a" * 64,
        "semantic_contract_sha256": "b" * 64,
        "official_receipt_url": "https://www.tiktok.com/messages",
        "exact_readback": True,
        "quality_status": "qualified",
        "qualification_sources": ["https://www.tiktok.com/messages"],
        "counts_toward_50": False,
    }
    first, _ = _run_cli(tmp_path, base)
    second, _ = _run_cli(tmp_path, {**base, "counts_toward_50": True})

    assert first.returncode == 0
    assert second.returncode != 0
    assert "differs from durable receipt" in second.stderr


def test_cli_rejects_json_type_drift_for_existing_effect_key(tmp_path):
    base = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "payload_sha256": "a" * 64,
        "semantic_contract_sha256": "b" * 64,
        "official_receipt_url": "https://www.tiktok.com/messages",
        "exact_readback": True,
        "quality_status": "qualified",
        "qualification_sources": ["https://www.tiktok.com/messages"],
        "counts_toward_50": True,
    }
    first, _ = _run_cli(tmp_path, base)
    second, _ = _run_cli(tmp_path, {**base, "counts_toward_50": 1})

    assert first.returncode == 0
    assert second.returncode != 0


def test_cli_accepts_explicit_classification_revision(tmp_path):
    base = {
        "effect_key": "tiktok:campaign:recipient",
        "target": "https://www.tiktok.com/messages",
        "payload_sha256": "a" * 64,
        "semantic_contract_sha256": "b" * 64,
        "official_receipt_url": "https://www.tiktok.com/messages",
        "exact_readback": True,
        "quality_status": "qualification",
        "qualification_sources": ["https://www.tiktok.com/messages"],
    }
    first, ledger = _run_cli(tmp_path, base)
    revision = {
        **base,
        "quality_status": "qualified",
        "classification_revision": True,
        "revision_reason": "Official reply supplied the missing qualification.",
    }
    second, _ = _run_cli(tmp_path, revision)
    replay, _ = _run_cli(tmp_path, revision)

    assert first.returncode == second.returncode == replay.returncode == 0
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[1]["record_type"] == "classification_revision"
