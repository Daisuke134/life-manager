from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def test_slideshow_renders_a_vertical_local_video_without_external_effects(tmp_path):
    renderer_path = Path(__file__).parent / "render_eval" / "slideshow_candidate.py"
    assert renderer_path.is_file(), "local English slideshow renderer is missing"
    spec = importlib.util.spec_from_file_location("slideshow_candidate", renderer_path)
    assert spec is not None and spec.loader is not None
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)

    script = {
        "language": "en",
        "hook": "When the room feels too loud",
        "pain_angle": "your thoughts keep asking for an answer",
        "teaching": "a thought is a visitor, not a command",
        "action": "name one sound you can hear",
        "cta": "Read The Anicca Reset",
    }
    commands = []
    slide_texts = []

    def execute(args, **kwargs):
        commands.append(args)
        if len(args) > 1 and str(args[1]).endswith("render-slide-image.py"):
            slide_texts.append(args[-1])
            Path(args[3]).write_bytes(b"local-slide-jpeg")
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"text_contrast_ok": True}), "",
            )
        if args[0] == "fake-ffmpeg":
            Path(args[-1]).write_bytes(b"local-slideshow-mp4")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "fake-ffprobe":
            probe = {"streams": [{"codec_type": "video", "codec_name": "h264",
                                  "width": 1080, "height": 1920,
                                  "pix_fmt": "yuv420p", "color_range": "tv",
                                  "color_space": "bt709", "color_transfer": "bt709",
                                  "color_primaries": "bt709"}],
                     "format": {"duration": "18.0"}}
            return subprocess.CompletedProcess(args, 0, json.dumps(probe), "")
        raise AssertionError("renderer invoked a command outside the local media toolchain")

    output = tmp_path / "slideshow.mp4"
    receipt = renderer.render(
        script=script,
        output=output,
        ffmpeg="fake-ffmpeg",
        ffprobe="fake-ffprobe",
        executor=execute,
    )

    assert receipt["renderer_id"] == "slideshow"
    assert receipt["state"] == "rendered"
    assert receipt["external_effects"] == []
    assert receipt["sha256"]
    assert output.is_file()
    assert [" ".join(text.split()) for text in slide_texts] == [
        script[key] for key in ("hook", "pain_angle", "teaching", "action", "cta")
    ]
    assert {Path(command[0]).name for command in commands} == {
        Path(sys.executable).name, "fake-ffmpeg", "fake-ffprobe",
    }
    assert not any("heygen" in str(command).lower() for command in commands)
