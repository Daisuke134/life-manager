from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "capafy_x_post.py"


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_x_post", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_payload_is_a_text_only_draft_with_no_media() -> None:
    module = load_module()
    payload = module.build_payload(
        integration_id="int-1",
        caption="New Capafy skill https://capafy.ai/agent/111?ct=capafy-distribute-hook-lab",
        scheduled_at="2026-09-29T07:15:00.000Z",
    )
    assert payload["type"] == "draft"
    assert payload["posts"][0]["integration"]["id"] == "int-1"
    assert payload["posts"][0]["value"][0]["image"] == []
    assert "capafy.ai/agent/111?ct=capafy-distribute-hook-lab" in payload["posts"][0]["value"][0]["content"]


def test_dry_run_cli_makes_no_network_call() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--caption", "hello https://capafy.ai/agent/1?ct=x",
         "--integration-id", "int-1", "--dry-run"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["payload"]["posts"][0]["integration"]["id"] == "int-1"
