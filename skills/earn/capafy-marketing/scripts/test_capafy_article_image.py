#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capafy_article_image as m


def test_non_hook_lab_skill_writes_nothing(tmp_path):
    assert m.run(tmp_path, "slide-maker", base=tmp_path) is None
    assert not (tmp_path / "article-image.url").exists()


def test_cached_frame_url_is_reused_without_upload(tmp_path):
    reel = tmp_path / "hooklab-d20261022-smallbiz" / "renders-v2"
    reel.mkdir(parents=True)
    (reel / "video.mp4").write_bytes(b"x")
    (reel / "cards-frame.json").write_text(json.dumps({"url": "https://uploads.postiz.com/f.png"}))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    url = m.run(run_dir, "hook-lab", base=tmp_path, upload=lambda path: (_ for _ in ()).throw(AssertionError("no upload")))
    assert url == "https://uploads.postiz.com/f.png"
    assert (run_dir / "article-image.url").read_text().strip() == url
