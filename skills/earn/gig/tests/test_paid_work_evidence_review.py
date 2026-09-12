import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "paid_work_evidence.py"
SPEC = importlib.util.spec_from_file_location("paid_work_evidence_review_test", SCRIPT)
evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evidence)


def test_review_ready_wav_is_valid_only_through_review_aperture(tmp_path):
    artifact = tmp_path / "draft_v1.wav"
    artifact.write_bytes(b"RIFF" + b"review-audio" * 100)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    requirements = tmp_path / "requirements.json"
    requirements.write_text("{}")
    acceptance = tmp_path / "acceptance.json"
    delta = ["Playable WAV is ready for buyer review; reference correspondence is unresolved."]
    acceptance.write_text(json.dumps({"status": "REVIEW_READY", "acceptance_delta": delta}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "status": "REVIEW_READY",
        "project_root": str(tmp_path),
        "requirements_path": str(requirements),
        "artifact_path": str(artifact),
        "artifact_version": "v1",
        "acceptance_evidence_path": str(acceptance),
        "acceptance_status": "REVIEW_READY",
        "acceptance_delta": delta,
        "package_sha256": digest,
        "required_assets": [],
        "artifact_assets": [{
            "asset_id": "draft_audio",
            "path": str(artifact),
            "bytes": artifact.stat().st_size,
            "mime_type": "audio/wav",
            "sha256": digest,
            "provenance": "builder:review-draft",
        }],
    }))

    blocked_ok, _ = evidence.validate_paid_work(
        tmp_path, tmp_path / "unused-delivery-evidence.json", manifest_path=manifest,
        require_delivery_evidence=False,
        artifact_judge=lambda *_: ("deliverable", "reviewable"),
    )
    review_ok, errors = evidence.validate_paid_work(
        tmp_path, manifest, manifest_path=manifest,
        artifact_judge=lambda *_: ("deliverable", "reviewable"),
        allow_review_ready=True,
    )

    assert blocked_ok is False
    assert review_ok is True, errors


def test_non_delegable_claim_reaches_review_but_never_normal_delivery(tmp_path):
    artifact = tmp_path / "research-v1.zip"
    artifact.write_bytes(b"PK" + b"researched-ledger" * 100)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    requirements = tmp_path / "requirements.json"
    requirements.write_text("{}")
    acceptance = tmp_path / "acceptance.json"
    delta = ["Current candidate was measured and rejected."]
    acceptance.write_text(json.dumps({
        "status": "BLOCKED_NON_DELEGABLE",
        "blocking_action": "Provide another public source archive.",
        "acceptance_delta": delta,
    }))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "status": "BLOCKED_NON_DELEGABLE",
        "project_root": str(tmp_path),
        "requirements_path": str(requirements),
        "artifact_path": str(artifact),
        "artifact_version": "v1",
        "acceptance_evidence_path": str(acceptance),
        "acceptance_status": "BLOCKED_NON_DELEGABLE",
        "acceptance_delta": delta,
        "package_sha256": digest,
        "required_assets": [],
        "artifact_assets": [{
            "asset_id": "research",
            "path": str(artifact),
            "bytes": artifact.stat().st_size,
            "mime_type": "application/zip",
            "sha256": digest,
            "provenance": "builder:public-research",
        }],
    }))

    normal_ok, _ = evidence.validate_paid_work(
        tmp_path, manifest, manifest_path=manifest,
        artifact_judge=lambda *_: ("deliverable", "unused"),
    )
    review_ok, errors = evidence.validate_paid_work(
        tmp_path, manifest, manifest_path=manifest,
        artifact_judge=evidence.STRUCTURE_ONLY,
        allow_fresh_blocked_for_review=True, require_delivery_evidence=False,
    )

    assert normal_ok is False
    assert review_ok is True, errors
