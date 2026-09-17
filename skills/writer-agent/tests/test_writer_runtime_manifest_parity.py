from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _writer_labels() -> set[str]:
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())[
        "loops"
    ]
    return {
        row["label"]
        for row in registry.values()
        if row.get("domain") == "earn"
        and str(row.get("label", "")).startswith(
            ("ai.anicca.article-", "ai.anicca.writer-")
        )
    }


def test_writer_runtime_manifest_matches_registry_labels_and_counts() -> None:
    labels = _writer_labels()
    manifest = json.loads(
        (ROOT / "config/writer/runtime-manifest.json").read_text()
    )
    manifest_labels = manifest["launchd_labels"]
    assert len(labels) == 15
    assert len(manifest_labels) == len(set(manifest_labels))
    assert set(manifest_labels) == labels
    assert manifest["path_audit"]["installed_writer_launchagents"] == len(labels)
    assert manifest["path_audit"]["life_manager_registry_entries"] == len(labels)
    assert len(manifest["worker_plist_cutover"]["labels"]) == len(
        set(manifest["worker_plist_cutover"]["labels"])
    )
