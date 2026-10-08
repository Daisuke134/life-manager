#!/usr/bin/env python3
"""Animated LINE stickers without fal.

fal's Seedance balance is exhausted (-$10.95, HTTP 403) and Dais wants image cost to stay at
$0 (2026-10-08 instruction), so the animated line no longer calls fal at all. Per motion this
asks ChatGPT, via the user's own subscription (``~/.agents/skills/chatgpt-imagegen``, no API
key, no metered $ cost), for ONE grid sprite sheet of the SAME character in several poses of
that motion, slices the sheet into frames, then reuses seedance_set's crop/scale/APNG-writer
pipeline unchanged — the only thing that differs from the fal path is where the RGBA frames
come from.

Character consistency: chatgpt-imagegen is generate-only (no reference-image input — see its
SKILL.md), so there is no true image-conditioning here. Consistency instead comes from (a) one
sprite-sheet image per motion = one model call, so every pose in it shares the same sampling and
therefore the same look, and (b) reusing plan["character_prompt"] verbatim (the same text that
produced char-ref.png) in every motion's prompt. This is a documented quality ceiling, not a
bug: a true reference-conditioned model (Gemini image-to-image, as character_image() already
uses for char-ref.png) would be more consistent across *different* sprite sheets, but costs
money or requires an API key; chatgpt-imagegen is the $0 option Dais asked for.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import seedance_set  # noqa: E402

CLI = Path.home() / ".agents/skills/chatgpt-imagegen/chatgpt-imagegen"
GRID = (3, 2)  # cols, rows -> 6 poses per motion: within LINE's apng min_frames=5/max_frames=20.
BACKGROUND = "a flat solid chroma-green (#00FF00) background"
PROVIDER = "chatgpt-imagegen"


class ChatGptImageGenUnavailable(RuntimeError):
    pass


def sheet_prompt(character_prompt: str, motion_prompt: str) -> str:
    cols, rows = GRID
    n = cols * rows
    return (
        f"{character_prompt} Draw a {cols}x{rows} grid sprite sheet: {n} equal square cells "
        f"separated by thin white gridlines, each cell showing the SAME character in a "
        f"different pose of this action: {motion_prompt}. Pose 1 in the top-left cell, "
        f"continuing left-to-right then top-to-bottom through pose {n}, as a smooth continuous "
        f"motion loop (the last pose should flow back into the first). {BACKGROUND} in every "
        f"cell. 2D cel animation style, clean bold outlines, no text, no shadows, the character "
        f"fully inside each cell."
    )


def generate_sheet(prompt: str, out_path: Path, *, timeout: int = 280) -> None:
    if not CLI.is_file():
        raise ChatGptImageGenUnavailable(f"chatgpt-imagegen is not installed at {CLI}")
    done = subprocess.run(
        [str(CLI), prompt, "-o", str(out_path), "--size", "1024x1024", "--backend", "auto",
         "--quiet", "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 30, check=False,
    )
    if done.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise ChatGptImageGenUnavailable(f"chatgpt-imagegen failed rc={done.returncode}: {done.stderr[-400:]}")


def slice_grid(sheet: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    width, height = sheet.size
    cell_w, cell_h = width // cols, height // rows
    frames = []
    for row in range(rows):
        for col in range(cols):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            frames.append(sheet.crop(box).convert("RGB"))
    return frames


def clips(set_dir: Path, plan: dict) -> None:
    """clips() counterpart: no video, no fal call. Writes a sprite-sheet PNG and a $0 receipt
    per motion so factory.run_clips's existing cost-summation and missing-receipt retry logic
    work unchanged."""
    out = set_dir / "clips"
    out.mkdir(exist_ok=True)
    character_prompt = plan.get("character_prompt", "")
    for motion in plan["motions"]:
        receipt = out / f"{motion['id']}.json"
        if receipt.exists():
            continue
        sheet_path = out / f"{motion['id']}-sheet.png"
        prompt = sheet_prompt(character_prompt, motion["prompt"])
        try:
            generate_sheet(prompt, sheet_path)
        except ChatGptImageGenUnavailable as exc:
            print(f"chatgpt_keyframes_unavailable:{motion['id']}:{exc}", file=sys.stderr)
            continue
        receipt.write_text(json.dumps({
            "id": motion["id"], "provider": PROVIDER, "grid": list(GRID),
            "sheet_sha256": seedance_set._sha256_file(sheet_path), "estimated_usd": 0,
        }, indent=1))
        print(json.dumps({"id": motion["id"], "provider": PROVIDER, "estimated_usd": 0}))


def apng(set_dir: Path, plan: dict) -> None:
    """apng() counterpart: slices each motion's sprite sheet into frames, chroma-keys them with
    seedance_set._key() (same green-screen convention as the fal path) and reuses
    seedance_set.assemble_candidate()/_write_apng() verbatim."""
    out = set_dir / "candidates"
    out.mkdir(exist_ok=True)
    cols, rows = GRID
    thumbs = []
    for motion in plan["motions"]:
        sheet_path = set_dir / "clips" / f"{motion['id']}-sheet.png"
        if not sheet_path.exists():
            continue
        sheet = Image.open(sheet_path)
        keyed = [seedance_set._key(np.array(frame)) for frame in slice_grid(sheet, cols, rows)]
        images = seedance_set.assemble_candidate(keyed)
        path = out / f"{motion['id']}.png"
        seedance_set._write_apng(images, path, motion.get("plays", 2))
        thumbs.append((motion["id"], images[0], images[len(images) // 2], path.stat().st_size))
        print(json.dumps({"id": motion["id"], "frames": len(images), "bytes": path.stat().st_size}))
    seedance_set.write_contact_sheet(thumbs, set_dir / "candidates-sheet.png")
