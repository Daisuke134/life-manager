#!/usr/bin/env python3
"""Make one LINE animated sticker set: one Seedance clip per motion, keyed into APNG candidates.

clips    submit every plan motion without a receipt to fal Seedance image-to-video, wait, download
apng     key each clip's green screen and write a 320x270 APNG candidate plus a contact sheet
package  write 01..24.png, main.png, tab.png and submission.zip from an ordered selection

Plan JSON: {"reference": "ref-padded.png", "motions": [{"id": "wave", "prompt": "...",
            "start": 0.3, "seconds": 2.0, "plays": 2}, ...]}
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from decimal import Decimal
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ENDPOINT = "fal-ai/bytedance/seedance/v1/lite/image-to-video"
USD_PER_MILLION_TOKENS = 1.0
CANVAS = (320, 270)
FPS = 10
STYLE = (" Static locked camera, the flat solid green background stays unchanged, 2D cel animation, "
         "clean outlines, the character stays fully inside the frame, no text.")


def _fal(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={
        "Authorization": "Key " + os.environ["FAL_KEY"], "Content-Type": "application/json"})
    # Only reads (status/result) are retried; a retried submit could start a second paid job.
    attempts = 4 if body is None else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            transient = not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(10 * (attempt + 1))


def clips(set_dir: Path, plan: dict) -> None:
    out = set_dir / "clips"
    out.mkdir(exist_ok=True)
    image = "data:image/png;base64," + base64.b64encode((set_dir / plan["reference"]).read_bytes()).decode()
    pending = {}
    for motion in plan["motions"]:
        receipt = out / f"{motion['id']}.json"
        if receipt.exists():
            continue
        queued = _fal(f"https://queue.fal.run/{ENDPOINT}", {
            "prompt": motion["prompt"] + STYLE, "image_url": image, "resolution": "720p",
            "duration": str(motion.get("duration", 3)), "camera_fixed": True})
        # Write the request id before waiting so a crash never resubmits a paid job.
        receipt.with_suffix(".queued").write_text(json.dumps(queued))
        pending[motion["id"]] = queued
    for queued_file in out.glob("*.queued"):
        pending.setdefault(queued_file.stem, json.loads(queued_file.read_text()))
    for motion_id, queued in pending.items():
        for _ in range(90):
            if _fal(queued["status_url"]).get("status") == "COMPLETED":
                break
            time.sleep(8)
        else:
            print(json.dumps({"id": motion_id, "status": "still_running"}))
            continue
        result = _fal(queued["response_url"])
        mp4 = out / f"{motion_id}.mp4"
        urllib.request.urlretrieve(result["video"]["url"], mp4)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                "stream=width,height,nb_frames", "-of", "json", str(mp4)],
                               capture_output=True, text=True, check=True)
        stream = json.loads(probe.stdout)["streams"][0]
        tokens = stream["width"] * stream["height"] * int(stream["nb_frames"]) / 1024
        receipt = {"id": motion_id, "endpoint": ENDPOINT, "request_id": queued["request_id"],
                   "seed": result.get("seed"), "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
                   "estimated_usd": round(tokens * USD_PER_MILLION_TOKENS / 1e6, 4)}
        (out / f"{motion_id}.json").write_text(json.dumps(receipt, indent=1))
        (out / f"{motion_id}.queued").unlink()
        print(json.dumps(receipt))


def _frames(mp4: Path, start: float, seconds: float) -> list[np.ndarray]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(mp4)],
                           capture_output=True, text=True, check=True)
    width, height = map(int, probe.stdout.strip().split(","))
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(start), "-t", str(seconds), "-i", str(mp4),
                          "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return list(np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3))


def _key(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.int32) for i in range(3))
    spill = g - np.maximum(r, b)
    # Fully green -> transparent; a soft band keeps antialiased outline edges.
    alpha = np.clip(255 - (spill - 40) * 255 // 60, 0, 255).astype(np.uint8)
    alpha[spill <= 40] = 255
    out = rgb.copy()
    out[..., 1] = np.minimum(g, np.maximum(r, b) + 10).astype(np.uint8)  # despill green fringe
    return np.dstack([out, alpha])


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _enclosed_holes(alpha: np.ndarray) -> tuple[np.ndarray, int]:
    labels, count = ndimage.label(alpha == 0)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    return np.where(np.isin(labels, border), 0, labels), count


def _fill_pinholes(image: Image.Image) -> Image.Image:
    # Keying noise leaves 1-2 px fully transparent dots inside the character; paint them with the
    # nearest opaque colour. Larger enclosed gaps (arm/body) are real art and are declared instead.
    rgba = np.array(image.convert("RGBA"))
    holes, count = _enclosed_holes(rgba[..., 3])
    if not holes.any():
        return image
    sizes = ndimage.sum(np.ones_like(holes), holes, index=np.arange(count + 1))
    small = (holes > 0) & (sizes[holes] <= 40)
    _, (iy, ix) = ndimage.distance_transform_edt(rgba[..., 3] == 0, return_indices=True)
    rgba[small] = rgba[iy[small], ix[small]]
    rgba[small, 3] = 255
    return Image.fromarray(rgba, "RGBA")


def _hole_seeds(path: Path) -> list[dict[str, int]]:
    image, seeds = Image.open(path), []
    for index in range(getattr(image, "n_frames", 1)):
        image.seek(index)
        holes, _ = _enclosed_holes(np.array(image.convert("RGBA"))[..., 3])
        for label in np.unique(holes[holes > 0]):
            y, x = np.argwhere(holes == label)[0]
            seeds.append({"x": int(x), "y": int(y)})
    return seeds


def _write_apng(images: list[Image.Image], path: Path, plays: int) -> None:
    # LINE requires every frame at full canvas size; PIL and ffmpeg both crop frames to the changed
    # region, so assemble full-size frames directly from each frame's own PNG encoding.
    out = [b"\x89PNG\r\n\x1a\n"]
    sequence = 0
    for index, image in enumerate(images):
        image = _fill_pinholes(image)
        buffer = io.BytesIO()
        image.save(buffer, "PNG", optimize=True)
        raw, chunks, offset = buffer.getvalue(), [], 8
        while offset < len(raw):
            length, kind = struct.unpack(">I4s", raw[offset:offset + 8])
            chunks.append((kind, raw[offset + 8:offset + 8 + length]))
            offset += 12 + length
        if index == 0:
            out.append(_chunk(b"IHDR", dict(chunks)[b"IHDR"]))
            out.append(_chunk(b"acTL", struct.pack(">II", len(images), plays)))
        width, height = image.size
        out.append(_chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, width, height, 0, 0, 1, FPS, 0, 0)))
        sequence += 1
        for kind, data in chunks:
            if kind != b"IDAT":
                continue
            if index == 0:
                out.append(_chunk(b"IDAT", data))
            else:
                out.append(_chunk(b"fdAT", struct.pack(">I", sequence) + data))
                sequence += 1
    out.append(_chunk(b"IEND", b""))
    path.write_bytes(b"".join(out))


def apng(set_dir: Path, plan: dict) -> None:
    out = set_dir / "candidates"
    out.mkdir(exist_ok=True)
    thumbs = []
    for motion in plan["motions"]:
        mp4 = set_dir / "clips" / f"{motion['id']}.mp4"
        if not mp4.exists():
            continue
        frames = [_key(f) for f in _frames(mp4, motion.get("start", 0.3), motion.get("seconds", 2.0))][:20]
        ys, xs = np.nonzero(np.max([f[..., 3] for f in frames], axis=0) > 16)
        top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        scale = min((CANVAS[0] - 12) / (right - left), (CANVAS[1] - 12) / (bottom - top))
        size = (max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale)))
        offset = ((CANVAS[0] - size[0]) // 2, (CANVAS[1] - size[1]) // 2)
        images = []
        for frame in frames:
            canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
            canvas.paste(Image.fromarray(frame[top:bottom, left:right], "RGBA").resize(size, Image.LANCZOS), offset)
            # Flatten video-compression noise so the RGBA APNG stays far below the 1 MB limit.
            images.append(canvas.quantize(64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGBA"))
        path = out / f"{motion['id']}.png"
        _write_apng(images, path, motion.get("plays", 2))
        thumbs.append((motion["id"], images[0], images[len(images) // 2], path.stat().st_size))
        print(json.dumps({"id": motion["id"], "frames": len(images), "bytes": path.stat().st_size}))
    # Contact sheet: first and middle frame of every candidate on a checker-free grey for inspection.
    cols = 6
    sheet = Image.new("RGB", (cols * 330, ((len(thumbs) + cols - 1) // cols) * 290), (200, 200, 200))
    for index, (_, first, middle, _) in enumerate(thumbs):
        cell = Image.new("RGBA", (330, 290), (200, 200, 200, 255))
        cell.alpha_composite(middle, (5, 10))
        sheet.paste(cell.convert("RGB"), ((index % cols) * 330, (index // cols) * 290))
    sheet.save(set_dir / "candidates-sheet.png")


CHARACTER_ID = "char-hamster-001"
IMAGE_PROVIDER = "google:gemini-3.1-flash-image"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_provenance(set_dir: Path, plan_path: Path, out: Path, names: list[str], order: list[str]) -> None:
    assets = {name: {"sha256": _sha256_file(out / name), "intentional_alpha_holes": _hole_seeds(out / name)} for name in names}
    clip_receipts = []
    for motion_id in order:
        receipt = json.loads((set_dir / "clips" / f"{motion_id}.json").read_text())
        clip_receipts.append({
            "id": receipt["id"], "request_id": receipt["request_id"],
            "sha256": receipt["sha256"], "estimated_usd": str(receipt["estimated_usd"]),
        })
    actual_cost_usd = sum(Decimal(receipt["estimated_usd"]) for receipt in clip_receipts)
    provenance = {
        "set_id": set_dir.name,
        "character_id": CHARACTER_ID,
        "rights": "original_ai_generated",
        "providers": {"image": IMAGE_PROVIDER, "animation": ENDPOINT},
        "assets": assets,
        "generation": {
            "character_sha256": _sha256_file(set_dir / "char-ref.png"),
            "plan_sha256": _sha256_file(plan_path),
            "clip_receipts": clip_receipts,
            "actual_cost_usd": str(actual_cost_usd),
        },
    }
    (out / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")


def package(set_dir: Path, plan_path: Path, order: list[str], main_id: str, tab_id: str) -> None:
    if len(order) != 24 or len(set(order)) != 24:
        sys.exit("order must name 24 distinct candidates")
    out = set_dir / "package"
    out.mkdir(exist_ok=True)
    candidates = set_dir / "candidates"
    for number, motion_id in enumerate(order, 1):
        (out / f"{number:02d}.png").write_bytes((candidates / f"{motion_id}.png").read_bytes())
    source = Image.open(candidates / f"{main_id}.png")
    frames = []
    for index in range(getattr(source, "n_frames", 1)):
        source.seek(index)
        frame = source.convert("RGBA")
        square = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        fitted = frame.resize((240, round(240 * frame.height / frame.width)), Image.LANCZOS)
        square.paste(fitted, (0, (240 - fitted.height) // 2))
        frames.append(square)
    _write_apng(frames, out / "main.png", source.info.get("loop", 2))
    tab = Image.open(candidates / f"{tab_id}.png").convert("RGBA")
    tab.thumbnail((96, 74), Image.LANCZOS)
    tab_canvas = Image.new("RGBA", (96, 74), (0, 0, 0, 0))
    tab_canvas.paste(tab, ((96 - tab.width) // 2, (74 - tab.height) // 2))
    _fill_pinholes(tab_canvas).save(out / "tab.png")
    names = sorted(["main.png", "tab.png"] + [f"{n:02d}.png" for n in range(1, 25)])
    _write_provenance(set_dir, plan_path, out, names, order)
    with zipfile.ZipFile(out / "submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(out / name, name)
    print(json.dumps({"package": str(out), "zip_bytes": (out / "submission.zip").stat().st_size}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["clips", "apng", "package"])
    parser.add_argument("--set-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--order", nargs="*")
    parser.add_argument("--main")
    parser.add_argument("--tab")
    args = parser.parse_args()
    if args.command == "package":
        if args.plan is None:
            sys.exit("--plan is required for package")
        package(args.set_dir, args.plan, args.order, args.main, args.tab)
        return
    plan = json.loads(args.plan.read_text())
    (clips if args.command == "clips" else apng)(args.set_dir, plan)


if __name__ == "__main__":
    main()
