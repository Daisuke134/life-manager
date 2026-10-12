#!/usr/bin/env python3
"""Render an English eBook slideshow using local Pillow and FFmpeg tools."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image


WIDTH = 1080
HEIGHT = 1920
FPS = 30
SEGMENTS = (
    ("hook", 3.2, (18, 35, 63), (27, 55, 78)),
    ("pain_angle", 2.8, (24, 48, 65), (38, 61, 71)),
    ("teaching", 4.0, (31, 38, 72), (53, 47, 85)),
    ("action", 4.0, (17, 54, 63), (28, 78, 79)),
    ("cta", 4.0, (18, 35, 63), (54, 61, 86)),
)
DURATION = sum(row[1] for row in SEGMENTS)
REPO_ROOT = Path(__file__).resolve().parents[4]
SLIDE_RENDERER = REPO_ROOT / "apps/life-manager/scripts/render-slide-image.py"
LOCAL_ENV_KEYS = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR")


def _local_environment() -> dict[str, str]:
    return {key: os.environ[key] for key in LOCAL_ENV_KEYS if os.environ.get(key)}


def _run(executor, command: list[str]) -> subprocess.CompletedProcess[str]:
    return executor(command, text=True, capture_output=True, check=True,
                     env=_local_environment())


def _background(path: Path, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (1, HEIGHT))
    pixels = []
    for y in range(HEIGHT):
        ratio = y / max(HEIGHT - 1, 1)
        pixels.append(tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom)))
    image.putdata(pixels)
    image.resize((WIDTH, HEIGHT), Image.BICUBIC).save(path, format="JPEG", quality=92)


def _concat_file(path: Path) -> str:
    value = path.resolve().as_posix().replace("\\", "\\\\").replace("'", "'\\''")
    return f"file '{value}'"


def _slide_text(value: str) -> str:
    words = value.split()
    split = (len(words) + 1) // 2
    if split == len(words):
        return value
    return " ".join(words[:split]) + "\n" + " ".join(words[split:])


def _validate_video(probe: dict) -> float:
    stream = next(
        (row for row in probe.get("streams", []) if row.get("codec_type") == "video"),
        None,
    )
    if (not isinstance(stream, dict)
            or (stream.get("width"), stream.get("height")) != (WIDTH, HEIGHT)
            or stream.get("codec_name") != "h264"
            or stream.get("pix_fmt") != "yuv420p"
            or stream.get("color_range") != "tv"
            or (stream.get("color_space"), stream.get("color_transfer"),
                stream.get("color_primaries")) != ("bt709", "bt709", "bt709")):
        raise RuntimeError("slideshow output is not a vertical H.264 video")
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if DURATION - 1 <= duration <= DURATION + 1:
        return duration
    raise RuntimeError("slideshow output duration is invalid")


def render(
    *,
    script: dict,
    output: Path,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    executor=subprocess.run,
) -> dict:
    if script.get("language") != "en":
        raise ValueError("slideshow renderer requires an English script")
    for key, _, _, _ in SEGMENTS:
        value = script.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("slideshow script is incomplete")

    ffmpeg_bin = ffmpeg or shutil.which("ffmpeg")
    ffprobe_bin = ffprobe or shutil.which("ffprobe")
    missing = [name for name, value in (("ffmpeg", ffmpeg_bin), ("ffprobe", ffprobe_bin)) if not value]
    if missing:
        return {"renderer_id": "slideshow", "state": "setup_required",
                "missing": missing, "external_effects": []}
    if not SLIDE_RENDERER.is_file():
        return {"renderer_id": "slideshow", "state": "setup_required",
                "missing": ["local_slide_renderer"], "external_effects": []}

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists() or output.is_symlink():
        raise ValueError("slideshow output already exists without a completed receipt")

    with tempfile.TemporaryDirectory(prefix=".ebook-slideshow-", dir=output.parent) as temp:
        temp_root = Path(temp)
        slides: list[Path] = []
        concat_rows: list[str] = []
        for index, (key, duration, top, bottom) in enumerate(SEGMENTS, start=1):
            background = temp_root / f"background-{index}.jpg"
            slide = temp_root / f"slide-{index}.jpg"
            _background(background, top, bottom)
            result = _run(executor, [
                sys.executable, str(SLIDE_RENDERER), str(background), str(slide),
                str(WIDTH), str(HEIGHT), _slide_text(script[key]),
            ])
            if not slide.is_file() or slide.stat().st_size == 0:
                raise RuntimeError("local slide renderer did not produce an image")
            try:
                quality = json.loads(result.stdout)
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("local slide renderer returned invalid evidence") from exc
            if quality.get("text_contrast_ok") is not True:
                raise RuntimeError("local slide text contrast is not verified")
            slides.append(slide)
            concat_rows.extend((_concat_file(slide), f"duration {duration}"))

        concat_rows.append(_concat_file(slides[-1]))
        concat_list = temp_root / "slides.txt"
        concat_list.write_text("\n".join(concat_rows) + "\n", encoding="utf-8")
        partial = temp_root / "render.mp4"
        _run(executor, [
            str(ffmpeg_bin), "-hide_banner", "-loglevel", "error", "-y",
            "-safe", "0", "-f", "concat", "-i", str(concat_list),
            "-vf", (f"fps={FPS},scale={WIDTH}:{HEIGHT}:in_range=full:out_range=tv,"
                    "format=yuv420p,setparams=range=tv:colorspace=bt709:"
                    "color_primaries=bt709:color_trc=bt709"),
            "-t", str(DURATION),
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart", str(partial),
        ])
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError("FFmpeg did not produce a slideshow video")
        probe_result = _run(executor, [
            str(ffprobe_bin), "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(partial),
        ])
        duration = _validate_video(json.loads(probe_result.stdout))
        os.link(partial, output)
        os.chmod(output, 0o600)

    return {
        "renderer_id": "slideshow",
        "state": "rendered",
        "output": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "duration_seconds": duration,
        "external_effects": [],
    }
