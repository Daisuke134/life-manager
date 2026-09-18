from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "substack-publish" / "substack_paid_payload.py"
SPEC = importlib.util.spec_from_file_location("substack_paid_payload_display", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_substack_image_display_width_keeps_portrait_headline_under_preview_gate() -> None:
    node = MODULE._image_node("headline", "https://substack-post-media.s3.amazonaws.com/image.png")

    attrs = node["content"][0]["attrs"]
    assert attrs["resizeWidth"] == 600
    assert 1536 * attrs["resizeWidth"] / 1024 <= 950
