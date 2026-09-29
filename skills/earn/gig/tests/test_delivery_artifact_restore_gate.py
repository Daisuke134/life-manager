from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import client_artifact_restore as restore  # noqa: E402
import delivery_project  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "version": 1,
        "kind": "client_artifact_restore",
        "platform": "coconala",
        "project_id": "18211957",
        "ordered_assets": [{
            "label": "A",
            "public_path": "assets/1.jpeg",
            "sha256": hashlib.sha256(b"asset").hexdigest(),
        }],
        "animation": {"preserve": True, "baseline_sha256": "a" * 64},
        "management": {"editable_fields": ["genreSlides"], "restore_controls": 1},
    }


def _fixture(tmp_path: Path) -> tuple[Path, dict, dict]:
    root = tmp_path / "project"
    artifact = root / "delivery" / "artifact-v1.txt"
    artifact_bytes = b"accepted artifact"
    _write(artifact, artifact_bytes)
    acceptance = root / "delivery" / "acceptance.json"
    _write(acceptance, {"status": "PASS"})
    feedback = root / "requirements" / "feedback.json"
    _write(feedback, {
        "feedback_first_observed_at": "2020-01-01T00:00:00+00:00",
        "feedback_sha256": "f" * 64,
    })
    stable = {
        "status": "ok",
        "project_root": str(root),
        "artifact_path": str(artifact),
        "artifact_version": "v1",
        "acceptance_evidence_path": str(acceptance),
        "acceptance_status": "PASS",
        "acceptance_delta": {"status": "PASS"},
        "package_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "requirements_path": str(feedback),
    }
    evidence_path = root / "delivery" / "stable-evidence.json"
    _write(evidence_path, stable)
    evidence = {
        "present": True,
        "status": "ok",
        "path": str(evidence_path),
        **{key: stable[key] for key in (
            "project_root", "artifact_path", "artifact_version", "acceptance_evidence_path",
            "acceptance_status", "acceptance_delta", "package_sha256",
        )},
    }
    item = {
        "delivery_evidence": evidence,
        "buyer_feedback_requirements_path": str(feedback),
        "buyer_feedback_sha256": "f" * 64,
    }
    return root, item, stable


def test_accepted_artifact_requires_client_restore_readback(tmp_path: Path):
    root, item, stable = _fixture(tmp_path)
    _write(root / "requirements" / "client-artifact-restore.json", _manifest())

    assert delivery_project._validated_accepted_artifact(root, item) is None

    manifest = _manifest()
    _write(root / "delivery" / "client-artifact-restore-readback.json", {
        "status": "ok",
        "manifest_sha256": restore.manifest_sha256(manifest),
        "genre_slides": [{"label": "A", "image": "assets/1.jpeg"}],
        "animation_sha256": "a" * 64,
        "management_restore_controls": 1,
        "official_receipt_id": "receipt-1",
        "replay_zero": True,
    })

    accepted = delivery_project._validated_accepted_artifact(root, item)
    assert accepted is not None
    assert accepted[0] == stable
