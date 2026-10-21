"""Managed Gig Writer calls Codex directly without an alternate model proxy."""

from __future__ import annotations

import json
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[1] / "config" / "launchd-jobs.json"


def test_writer_launchd_model_provider_is_codex_direct():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    writer_env = config["writer_env"]
    assert writer_env["ARTICLE_PROVIDER"] == "codex"
    assert "ARTICLE_CODEX_PROVIDER_ID" not in writer_env
    assert "ARTICLE_CODEX_PROVIDER_ENV_KEY" not in writer_env
    assert "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE" not in writer_env
