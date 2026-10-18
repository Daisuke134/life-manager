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
    assert len(labels) == 14  # article-learn-whitelist retired: it commits into the read-only release
    assert len(manifest_labels) == len(set(manifest_labels))
    assert set(manifest_labels) == labels
    assert manifest["path_audit"]["installed_writer_launchagents"] == len(labels)
    assert manifest["path_audit"]["life_manager_registry_entries"] == len(labels)
    assert len(manifest["worker_plist_cutover"]["labels"]) == len(
        set(manifest["worker_plist_cutover"]["labels"])
    )


def test_article_learn_whitelist_is_retired() -> None:
    # It ran `git fetch/commit/push` against the immutable release (no .git,
    # read-only whitelist), so every wake exited 75 and none ever succeeded.
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())
    assert "article-learn-whitelist" not in registry["loops"]
    assert "ai.anicca.article-learn-whitelist" in registry["retired_labels"]
    assert not (ROOT / "skills/writer-agent/scripts/learn-whitelist.sh").exists()
    assert not (ROOT / "skills/writer-agent/scripts/learn_whitelist.py").exists()
