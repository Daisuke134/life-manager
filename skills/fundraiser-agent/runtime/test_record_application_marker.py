import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "record-application.py"


def _run(script_args, env):
    return subprocess.run(
        ["python3", str(SCRIPT), *script_args],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_prepare_and_verified_record_advance_the_occurrence_marker(tmp_path):
    occurrence_id = "fundraiser:marker-test"
    marker = tmp_path / "effect-marker.json"
    marker.write_text(json.dumps({
        "schema_version": 1,
        "owner_id": "fundraiser",
        "occurrence_id": occurrence_id,
        "phase": "pre_effect",
        "effect": 0,
        "updated_at": "2026-10-01T00:00:00Z",
    }) + "\n")
    marker.chmod(0o600)
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({
        "organization": "Example Fund",
        "program": "Example Intake",
        "cohort_window": "rolling 2026",
        "account": "account:example",
        "official_url": "https://example.test/apply",
        "contact": {"method": "email", "destination": "founder@example.test"},
        "question_answers": [{"question": "What do you build?", "answer": "A useful tool."}],
        "attachments": ["deck.pdf"],
        "context_used": {"product": "startup"},
        "context_version": "ctx-1",
        "context_digest": "digest-1",
    }) + "\n")
    ledger = tmp_path / "receipts.jsonl"
    applications = tmp_path / "applications"
    env = {
        "FUNDRAISER_EFFECT_MARKER": str(marker),
        "FUNDRAISER_OCCURRENCE_ID": occurrence_id,
    }

    prepared = _run([
        "--prepare", "--draft", str(draft), "--ledger", str(ledger),
        "--applications-dir", str(applications),
        "--expected-context-version", "ctx-1", "--expected-context-digest", "digest-1",
    ], env)
    assert prepared.returncode == 0, prepared.stderr
    assert json.loads(marker.read_text())["phase"] == "effect_attempted"

    data = json.loads(draft.read_text())
    completion = tmp_path / "completion.png"
    completion.write_bytes(b"png")
    submitted_at = (
        datetime.fromisoformat(data["previewed_at"].replace("Z", "+00:00"))
        + timedelta(seconds=1)
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    data.update({
        "submitted_at": submitted_at,
        "evidence": {
            "completion_png": str(completion),
            "telegram_photo_message_id": 1,
            "provider_readback": "official confirmation",
        },
    })
    draft.write_text(json.dumps(data) + "\n")
    recorded = _run([
        "--draft", str(draft), "--ledger", str(ledger),
        "--applications-dir", str(applications), "--run-id", "20261001T000100Z-1",
        "--expected-context-version", "ctx-1", "--expected-context-digest", "digest-1",
    ], env)
    assert recorded.returncode == 0, recorded.stderr
    assert json.loads(marker.read_text())["phase"] == "post_effect_verified"
    assert json.loads(ledger.read_text()) ["status"] == "submitted_verified"
