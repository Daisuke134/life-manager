from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

import pytest

import postiz_video


def test_pre_effect_marker_is_cleared_at_the_first_upload(tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
    media = tmp_path / "candidate.mp4"
    media.write_bytes(b"video")
    args = Namespace(image=[], video=media, title="Reflection", integration="ig-1", platform="instagram")
    observed = {}

    def upload(video, _api_key):
        observed["marker_exists_at_upload"] = hint.exists()
        return "upload-1", "/uploads/video-1"

    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    with (patch.object(postiz_video, "read_recent_posts", return_value=[]),
          patch.object(postiz_video, "find_existing_post", return_value=None),
          patch.object(postiz_video, "upload_video", side_effect=upload),
          patch.object(postiz_video, "build_payload", return_value={}),
          patch.object(postiz_video, "create_post", return_value="post-1"),
          patch.object(postiz_video, "read_publish_state", return_value={
              "state": "PUBLISHED", "post_url": "https://www.instagram.com/reel/abc123",
          }),
          patch.object(postiz_video.time, "sleep")):
        assert postiz_video._publish(args, "token", "caption") == 0

    assert observed["marker_exists_at_upload"] is False
    assert hint.exists() is False


def test_read_only_postiz_preflight_failure_preserves_no_effect_marker(tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
    media = tmp_path / "candidate.mp4"
    media.write_bytes(b"video")
    args = Namespace(image=[], video=media, title="Reflection", integration="ig-1", platform="instagram")

    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    with (patch.object(postiz_video, "read_recent_posts", side_effect=postiz_video.PostizError("offline")),
          pytest.raises(postiz_video.PostizError, match="offline")):
        postiz_video._publish(args, "token", "caption")

    assert hint.exists() is True


@pytest.mark.parametrize("integration,own_business", [
    ("cmo5rwq2p00twn10yrsdglng3", True),
    ("cmo5s4edx00vgn10ygnu34a0n", True),
    ("unregistered-tiktok-route", False),
])
def test_ebook_tiktok_payload_uses_own_business_disclosure(tmp_path, integration, own_business):
    media = tmp_path / "monk.mp4"
    media.write_bytes(b"original-monk-video")
    args = Namespace(image=[], video=media, title="Reflection",
                     integration=integration, platform="tiktok")
    captured = []
    with (patch.object(postiz_video, "read_recent_posts", return_value=[]),
          patch.object(postiz_video, "find_existing_post", return_value=None),
          patch.object(postiz_video, "upload_video", return_value=("upload-1", "/uploads/monk.mp4")),
          patch.object(postiz_video, "create_post", side_effect=lambda payload, key: captured.append(payload) or "post-1"),
          patch.object(postiz_video, "read_publish_state", return_value={
              "state": "PUBLISHED", "post_url": "https://www.tiktok.com/@monk_anicca/video/123",
          }), patch.object(postiz_video.time, "sleep")):
        assert postiz_video._publish(args, "token", "Our original reflection book") == 0
    settings = captured[0]["posts"][0]["settings"]
    assert settings["brand_organic_toggle"] is own_business
    assert settings["brand_content_toggle"] is False
    assert settings["video_made_with_ai"] is True
