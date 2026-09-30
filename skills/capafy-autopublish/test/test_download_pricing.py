"""Download-mode (one-time fee) pricing support in build_config.py / lint_listing.py.

Capafy's Download agent_type has no hosted LLM and skips CP2 entirely
(verified 2026-09-28 via publish-remote-status on agent 3332784488:
agent_type=download, is_confirmed_config_keys=false, billings=one row with no
price). A "| download | $X | - | - |" pricing row is the download-mode
equivalent of the day/week/month subscription table.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BUILD_CONFIG = Path(__file__).parents[1] / "scripts" / "build_config.py"
LINT = Path(__file__).parents[1] / "scripts" / "lint_listing.py"
CONTRACT = Path(__file__).parents[1] / "scripts" / "publish_input_contract.py"
PREPARE = Path(__file__).parents[1] / "scripts" / "publish_prepare.sh"

DOWNLOAD_LISTING = """category: ライティング · tags: humanizer, japanese, download

| cycle | price | cap | trial |
|---|---|---|---|
| download | $9.99 | - | - |

## Title
Japanese Humanizer — Sound Human, Not AI

## shortDescription
Test short description.

## welcomeMessage
Welcome. Example: "test input"

## detailedDescription
Detailed body.
"""


def test_build_config_parses_download_mode_without_model(tmp_path: Path) -> None:
    listing = tmp_path / "LISTING.md"
    listing.write_text(DOWNLOAD_LISTING, encoding="utf-8")
    icon = tmp_path / "icon.svg"
    icon.write_text("<svg/>", encoding="utf-8")
    out = tmp_path / "config.json"

    result = subprocess.run(
        [sys.executable, str(BUILD_CONFIG), str(listing), str(icon), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    cfg = json.loads(out.read_text(encoding="utf-8"))
    assert cfg["pricing_mode"] == "download"
    assert cfg["one_time_fee"] == "9.99"
    assert cfg["plans"] == []
    assert cfg["model"] is None
    assert cfg["model_id"] is None
    assert cfg["max_tokens"] is None


def test_lint_listing_accepts_download_row_without_cap_or_trial(tmp_path: Path) -> None:
    listing = tmp_path / "LISTING.md"
    listing.write_text(DOWNLOAD_LISTING, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(LINT), str(listing)], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout


def test_inventory_status_accepts_price_only_update_request(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "inventory_status", Path(__file__).parents[1] / "scripts" / "inventory_status.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    catalog = tmp_path / "catalog"
    entry = catalog / "download-skill"
    entry.mkdir(parents=True)
    (entry / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (entry / "LISTING.md").write_text("## Title\nDownload Skill\n", encoding="utf-8")
    (entry / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (entry / "UPDATE.json").write_text(json.dumps({
        "agent_id": "3332784488",
        "from_version_id": "2070082655366180864",
        "target_one_time_fee": "9.99",
    }), encoding="utf-8")

    import os
    module.FEATURES = str(tmp_path / "no-legacy")
    module.CATALOG = str(catalog)

    items = module.ready_inventory()
    item = next(i for i in items if i["feature"] == "catalog:download-skill")
    assert item["update_request"]["target_one_time_fee"] == "9.99"
    assert "target_model_id" not in item["update_request"]


def test_publish_input_contract_accepts_download_mode_without_hosted_provider(tmp_path: Path) -> None:
    """publish_input_contract.py (the package/model binding used by
    publish_prepare.sh + publish_finish.sh) must accept a download-mode
    (model_id=None) config with no .openclaw/openclaw.json — a run_online
    listing still requires the full hosted-provider contract, unchanged."""
    agent_id = "3332784488"
    home = tmp_path / "home"
    workspace = home / ".openclaw/workspace"
    skill_dir = workspace / "skills" / "japanese-humanizer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# jp humanizer\n", encoding="utf-8")
    icon = tmp_path / "icon.svg"
    icon.write_text("<svg/>", encoding="utf-8")
    config = home / "listing-config.json"
    config.write_text(json.dumps({
        "title": "Japanese Humanizer", "model_id": None, "max_tokens": None,
        "icon": str(icon), "pricing_mode": "download", "one_time_fee": "9.99",
    }))
    work = tmp_path / "work"
    work.mkdir()
    (work / "publish-work-state.json").write_text(json.dumps({
        "agent_id": agent_id, "agent_version_id": "version-1",
        "extra": {"runtime_dir": str(workspace),
                  "explicit_skill": {"source_path": str(skill_dir)}},
    }))
    args = ["--agent-id", agent_id, "--skill-name", "japanese-humanizer",
            "--config", str(config), "--workspace", str(workspace),
            "--publisher-home", str(home), "--work-dir", str(work)]

    written = subprocess.run([sys.executable, str(CONTRACT), "write", *args],
                              text=True, capture_output=True)
    assert written.returncode == 0, written.stderr

    verified = subprocess.run([sys.executable, str(CONTRACT), "verify", *args],
                               text=True, capture_output=True)
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout.strip() == ""


def test_download_prepare_creates_minimal_openclaw_root_for_publish_init() -> None:
    source = PREPARE.read_text(encoding="utf-8")
    assert "Download agents deliberately have" in source
    assert "printf '{}\\n' > \"$CAPAFY_PUBLISH_HOME/.openclaw/openclaw.json\"" in source
