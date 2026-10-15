#!/usr/bin/env python3
"""Give a Hook Lab article one real output image ($0).

Takes the newest voiced reel (capafy-videos/hooklab-*/renders-v2/video.mp4), cuts the frame
where the three Hook Lab hooks are on screen, uploads it once to Postiz's public media host,
caches the URL next to the reel, and writes <run_dir>/article-image.url for
capafy_free_article.load_draft. Other skills, or any failure, leave the article unchanged.
Usage: capafy_article_image.py <run_dir> <capafy_skill_slug>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

BASE = Path.home() / ".local/state/life-manager/marketing/capafy-videos"
CARDS_AT = 9.0  # seconds: the three hook cards are fully visible


def _postiz_upload(png: Path) -> str:
    key = os.environ.get("LM_POSTIZ_API_KEY") or os.environ["POSTIZ_API_KEY"]
    bnd = uuid.uuid4().hex
    data = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{png.name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + png.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
    req = urllib.request.Request("https://api.postiz.com/public/v1/upload", data=data, method="POST",
                                 headers={"Authorization": key, "Content-Type": f"multipart/form-data; boundary={bnd}"})
    return json.load(urllib.request.urlopen(req, timeout=120))["path"]


def run(run_dir: Path, skill: str, *, base: Path = BASE, upload=_postiz_upload) -> str | None:
    if skill != "hook-lab":
        return None
    reels = sorted(base.glob("hooklab-*/renders-v2/video.mp4"), key=lambda p: p.stat().st_mtime)
    if not reels:
        return None
    out = reels[-1].parent
    cache = out / "cards-frame.json"
    if cache.exists():
        url = json.loads(cache.read_text())["url"]
    else:
        png = out / "cards-frame.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(CARDS_AT), "-i", str(reels[-1]),
                        "-frames:v", "1", "-vf", "scale=720:-1", str(png)], check=True)
        url = upload(png)
        cache.write_text(json.dumps({"url": url, "source": str(reels[-1])}) + "\n")
    (Path(run_dir) / "article-image.url").write_text(url + "\n")
    return url


if __name__ == "__main__":
    try:
        print(run(Path(sys.argv[1]), sys.argv[2]) or "")
    except Exception as exc:  # an image is optional; never block the article
        print(f"capafy_article_image: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
