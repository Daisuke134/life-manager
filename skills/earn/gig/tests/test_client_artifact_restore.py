import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import client_artifact_restore as restore


def manifest(tmp_path: Path) -> dict:
    return {
        "version": 1,
        "kind": "client_artifact_restore",
        "platform": "coconala",
        "project_id": "18211957",
        "ordered_assets": [
            {"label": label, "public_path": f"assets/{index}.jpeg", "sha256": hashlib.sha256(label.encode()).hexdigest()}
            for index, label in enumerate(("A", "B", "C"), start=1)
        ],
        "animation": {"preserve": True, "baseline_sha256": "a" * 64},
        "management": {"editable_fields": ["genreSlides"], "restore_controls": 3},
    }


def test_build_restore_plan_preserves_order_and_animation_baseline(tmp_path: Path):
    plan = restore.build_restore_plan(manifest(tmp_path))

    assert plan["labels"] == ["A", "B", "C"]
    assert plan["public_paths"] == ["assets/1.jpeg", "assets/2.jpeg", "assets/3.jpeg"]
    assert plan["animation"] == {"preserve": True, "baseline_sha256": "a" * 64}


def test_merge_content_document_changes_only_ordered_asset_field():
    spec = manifest(Path("/tmp"))
    document = {
        "genreSlides": [
            {"label": "A", "image": "old-a"},
            {"label": "B", "image": "old-b"},
            {"label": "C", "image": "old-c"},
        ],
        "profiles": [{"name": "unchanged"}],
    }

    merged = restore.merge_content_document(document, spec)

    assert [row["image"] for row in merged["genreSlides"]] == [
        "assets/1.jpeg", "assets/2.jpeg", "assets/3.jpeg"
    ]
    assert merged["profiles"] == document["profiles"]


def test_validate_readback_requires_animation_preservation_and_official_receipt(tmp_path: Path):
    spec = manifest(tmp_path)
    good = {
        "status": "ok",
        "manifest_sha256": restore.manifest_sha256(spec),
        "genre_slides": [
            {"label": "A", "image": "assets/1.jpeg"},
            {"label": "B", "image": "assets/2.jpeg"},
            {"label": "C", "image": "assets/3.jpeg"},
        ],
        "animation_sha256": "a" * 64,
        "management_restore_controls": 3,
        "official_receipt_id": "receipt-1",
        "replay_zero": True,
    }

    assert restore.validate_readback(spec, good) == []
    bad = {**good, "animation_sha256": "b" * 64}
    assert "animation_changed" in restore.validate_readback(spec, bad)


def test_manifest_rejects_duplicate_labels():
    spec = manifest(Path("/tmp"))
    spec["ordered_assets"][1]["label"] = "A"

    with pytest.raises(restore.ManifestError, match="labels_unique"):
        restore.build_restore_plan(spec)
