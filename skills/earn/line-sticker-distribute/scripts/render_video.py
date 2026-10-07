#!/usr/bin/env python3
"""render_video.py -- compose a 9:16 short MP4 from sticker clips + end card.

Reuses the already-rendered per-sticker clips the line-sticker build loop
produces (set-*/clips/<id>.mp4, h264 square), scaling/padding each onto a
pastel 720x1280 canvas with the sticker name overlaid, then appends a still
end card ("〈title〉をLINEスタンプで検索" + store URL). All composition is
deterministic bookkeeping -- no model call, no new media generation.

Text is pre-rendered to transparent PNGs with Pillow and composited via
ffmpeg's `overlay` filter: this host's ffmpeg build has no drawtext
(libfreetype not compiled in), so overlay+PNG is the native-tool substitute
rather than adding a new dependency. Kept small (no audio track, 720x1280,
crf 30) because the host disk is near-full.

The build loop's clips/*.mp4 (fal-ai/bytedance/seedance image-to-video
outputs) are rendered on a flat green-screen background (confirmed by
sampling: ~RGB(8,235,8)), not the sticker's own transparent background --
`colorkey` removes it here so the sticker appears to float on our pastel
canvas instead of showing green.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 720
CANVAS_H = 1280
PASTEL_BG = (0xFC, 0xEF, 0xEA)
TEXT_COLOR = (0x5B, 0x46, 0x36)
FONT_FILE = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
CLIP_SECONDS = 2.2
END_CARD_SECONDS = 2.5
FPS = 24


def _text_png(text: str, *, width: int, font_size: int, path: Path) -> None:
    font = ImageFont.truetype(FONT_FILE, font_size)
    dummy = Image.new("RGBA", (10, 10))
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    image = Image.new("RGBA", (width, text_h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text(((width - text_w) / 2 - bbox[0], 10 - bbox[1]), text, font=font, fill=(*TEXT_COLOR, 255))
    image.save(path)


def build_filter_complex(clip_count: int, overlay_heights: list[int]) -> str:
    bg_hex = f"0x{PASTEL_BG[0]:02X}{PASTEL_BG[1]:02X}{PASTEL_BG[2]:02X}"
    chains = []
    for i in range(clip_count):
        chains.append(f"color=c={bg_hex}:s={CANVAS_W}x{CANVAS_H}:d={CLIP_SECONDS}:r={FPS}[bg{i}]")
        chains.append(
            f"[{i}:v]trim=duration={CLIP_SECONDS},setpts=PTS-STARTPTS,fps={FPS},"
            f"colorkey=0x00FF00:0.30:0.12,"
            f"scale={CANVAS_W}:{CANVAS_W}:force_original_aspect_ratio=decrease,"
            f"format=yuva420p[sprite{i}]"
        )
        chains.append(f"[bg{i}][sprite{i}]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[base{i}]")
        title_input = clip_count + i
        chains.append(f"[base{i}][{title_input}:v]overlay=(W-w)/2:80[v{i}]")
    end_input = clip_count * 2
    chains.append(
        f"color=c=0x{PASTEL_BG[0]:02X}{PASTEL_BG[1]:02X}{PASTEL_BG[2]:02X}:"
        f"s={CANVAS_W}x{CANVAS_H}:d={END_CARD_SECONDS}:r={FPS}[endbg]"
    )
    chains.append(f"[endbg][{end_input}:v]overlay=(W-w)/2:(H-h)/2-60[endv1]")
    chains.append(f"[endv1][{end_input + 1}:v]overlay=(W-w)/2:(H-h)/2+40[vend]")
    concat_inputs = "".join(f"[v{i}]" for i in range(clip_count)) + "[vend]"
    chains.append(f"{concat_inputs}concat=n={clip_count + 1}:v=1:a=0[outv]")
    return ";".join(chains)


def render(clip_paths: list[Path], title_ja: str, store_url: str, output_path: Path) -> None:
    if not clip_paths:
        raise ValueError("at least one clip is required")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="lsd-render-") as tmp:
        tmp_dir = Path(tmp)
        title_png = tmp_dir / "title.png"
        _text_png(title_ja, width=CANVAS_W - 40, font_size=42, path=title_png)
        end_title_png = tmp_dir / "end-title.png"
        _text_png(f"「{title_ja}」を", width=CANVAS_W - 40, font_size=38, path=end_title_png)
        end_cta_png = tmp_dir / "end-cta.png"
        _text_png("LINEスタンプで検索", width=CANVAS_W - 40, font_size=44, path=end_cta_png)

        cmd = ["ffmpeg", "-y"]
        for clip in clip_paths:
            cmd += ["-i", str(clip)]
        for _ in clip_paths:
            cmd += ["-loop", "1", "-t", str(CLIP_SECONDS), "-i", str(title_png)]
        cmd += ["-loop", "1", "-t", str(END_CARD_SECONDS), "-i", str(end_title_png)]
        cmd += ["-loop", "1", "-t", str(END_CARD_SECONDS), "-i", str(end_cta_png)]
        cmd += [
            "-filter_complex", build_filter_complex(len(clip_paths), []),
            "-map", "[outv]",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg render failed: {result.stderr[-2000:]}")
    del store_url  # URL goes in the caption, not burned into the video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clips-dir", required=True)
    parser.add_argument("--clip-order", required=True, help="comma-separated clip ids")
    parser.add_argument("--title-ja", required=True)
    parser.add_argument("--store-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    clips_dir = Path(args.clips_dir).expanduser()
    clip_order = [c for c in args.clip_order.split(",") if c]
    clip_paths = [clips_dir / f"{clip_id}.mp4" for clip_id in clip_order]
    missing = [str(p) for p in clip_paths if not p.is_file()]
    if missing:
        print(json.dumps({"state": "missing_clips", "missing": missing}))
        return 1

    output_path = Path(args.output).expanduser()
    render(clip_paths, args.title_ja, args.store_url, output_path)
    size_bytes = output_path.stat().st_size
    print(json.dumps({
        "state": "rendered",
        "output": str(output_path),
        "size_bytes": size_bytes,
        "clip_order": clip_order,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
