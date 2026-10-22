from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_search_caption_replaces_links_postiz_strips_from_x() -> None:
    """2026-10-11: Postiz drops every URL (with or without https://) from X posts, so the
    live h18 Hook Lab tweet ended at "Hook Lab:" with no link. Buyers can still reach
    the Agent by searching its name on Capafy, where Hook Lab ranks first."""
    module = load_module()
    caption = ("Build an opening that earns the next second: https://aniccaai.com/blog/x\n"
               "Hook Lab: capafy.ai/agent/8123079349?ct=hooklab_x")
    out = module.search_caption(caption, "Hook Lab")
    assert "http" not in out and "capafy.ai/" not in out
    assert out.endswith('Search "Hook Lab" on Capafy.')
    assert "Build an opening that earns the next second" in out


def test_agent_name_from_slug() -> None:
    module = load_module()
    assert module.agent_name("hook-lab") == "Hook Lab"
    assert module.agent_name("tiktok-script-pro") == "TikTok Script Pro"


@pytest.mark.parametrize(("body", "expected_body"), [
    ("日" * 54 + "a" * 154, "日" * 54 + "a" * 140 + "…"),
    ("a" * 300, "a" * 248 + "…"),
    ("日" * 200, "日" * 124 + "…"),
    ("🎥" * 140, "🎥" * 124 + "…"),
], ids=["observed-mixed-292", "ascii", "cjk", "emoji"])
def test_search_caption_fits_weighted_limit_without_cutting_search_cta(body, expected_body):
    module = load_module()
    assert module.search_caption(body, "Hook Lab") == expected_body + '\n\nSearch "Hook Lab" on Capafy.'


def test_search_caption_keeps_exact_limit_unchanged():
    module = load_module()
    body = "日" * 125
    assert module.search_caption(body, "Hook Lab") == body + '\n\nSearch "Hook Lab" on Capafy.'


def test_search_caption_url_like_prefix_and_space_passes_payload_preflight():
    module = load_module()
    caption = module.search_caption("a" * 239 + "https:// " + "b" * 248, "Hook Lab")
    assert caption.endswith('Search "Hook Lab" on Capafy.')
    module.build_payload(integration_id="int-1", caption=caption, scheduled_at="fixture")


def test_search_caption_rejects_an_unfittable_search_cta():
    module = load_module()
    with pytest.raises(ValueError, match="CTA"):
        module.search_caption("Body", "x" * 281)


def test_oversized_nonsearch_caption_is_rejected_before_http(monkeypatch):
    module = load_module()
    def unexpected_http():
        pytest.fail("HTTP client loaded for an oversized caption")
    monkeypatch.setattr(module, "_load_http_postiz_client", unexpected_http)
    with pytest.raises(ValueError, match="280 weighted"):
        module.main(["--caption", "日" * 141, "--integration-id", "int-1", "--api-key", "fixture"])
