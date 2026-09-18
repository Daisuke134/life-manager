#!/usr/bin/env python3
"""Content descriptors for immutable local and transformed public images."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


DHASH_SIZE = 8
# note's fixed 1280x670 eyecatch recrop measured distance 7 on 2026-07-25
# (earlier images measured 4). The bound tracks the platform transform
# envelope; identity stays anchored by same-key targets, ordered content
# match, and the aspect-ratio bound below.
MAX_DHASH_DISTANCE = 8
# note.com crops a 16:9 source to its 1280x670 eyecatch frame (7.52% ratio
# delta). Keep the bound below 8%.
MAX_ASPECT_RATIO_DELTA = 0.08


def _dhash(image: Image.Image) -> str:
    grayscale = image.convert("L").resize(
        (DHASH_SIZE + 1, DHASH_SIZE), Image.Resampling.LANCZOS
    )
    # Mode L guarantees one byte per pixel. tobytes() is stable across the
    # Pillow 10.4 shipped with the launchd system Python and newer releases.
    pixels = list(grayscale.tobytes())
    value = 0
    for row in range(DHASH_SIZE):
        offset = row * (DHASH_SIZE + 1)
        for column in range(DHASH_SIZE):
            value = (value << 1) | int(
                pixels[offset + column] > pixels[offset + column + 1]
            )
    return f"{value:0{DHASH_SIZE * DHASH_SIZE // 4}x}"


def _visible_dhash(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    visible = Image.new("RGBA", rgba.size, "white")
    visible.alpha_composite(rgba)
    return _dhash(visible)


def descriptor_from_bytes(data: bytes) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "width": None,
        "height": None,
        "dhash": None,
        "visible_dhash": None,
    }
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            descriptor.update(
                width=int(image.width),
                height=int(image.height),
                dhash=_dhash(image),
                visible_dhash=_visible_dhash(image),
            )
    except (OSError, ValueError, UnidentifiedImageError):
        pass
    return descriptor


def descriptor_from_file(path: Path) -> dict[str, Any]:
    return descriptor_from_bytes(Path(path).read_bytes())


def dhash_distance(left: str, right: str) -> int:
    # launchd invokes /usr/bin/python3 (3.9 on the production macOS host),
    # while int.bit_count() is only available from Python 3.10 onward.
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def _expected_visible_dhash(expected: dict[str, Any]) -> str | None:
    expected_hash = expected.get("visible_dhash")
    if not isinstance(expected_hash, str):
        expected_path = Path(str(expected.get("path", "")))
        if expected_path.is_file():
            try:
                expected_hash = descriptor_from_file(expected_path).get("visible_dhash")
            except (OSError, ValueError, UnidentifiedImageError):
                expected_hash = None
    if not isinstance(expected_hash, str):
        expected_hash = expected.get("dhash")
    return expected_hash if isinstance(expected_hash, str) else None


def _visual_match(expected: dict[str, Any], remote: dict[str, Any]) -> tuple[bool, int | None]:
    expected_hash = _expected_visible_dhash(expected)
    remote_hash = remote.get("visible_dhash") or remote.get("dhash")
    dimensions = (
        expected.get("width"),
        expected.get("height"),
        remote.get("width"),
        remote.get("height"),
    )
    if (
        not isinstance(expected_hash, str)
        or not isinstance(remote_hash, str)
        or any(not isinstance(value, int) or value <= 0 for value in dimensions)
    ):
        return False, None
    expected_ratio = dimensions[0] / dimensions[1]
    remote_ratio = dimensions[2] / dimensions[3]
    ratio_delta = abs(expected_ratio - remote_ratio) / expected_ratio
    distance = dhash_distance(expected_hash, remote_hash)
    return (
        distance <= MAX_DHASH_DISTANCE and ratio_delta <= MAX_ASPECT_RATIO_DELTA,
        distance,
    )


def content_proof(
    expected: dict[str, Any], remote_data: bytes, remote_url: str
) -> dict[str, Any] | None:
    remote = descriptor_from_bytes(remote_data)
    expected_sha = str(expected.get("sha256", ""))
    if remote["sha256"] == expected_sha:
        method = "exact-sha256"
        distance = 0 if expected.get("dhash") else None
    else:
        matched, distance = _visual_match(expected, remote)
        if not matched:
            return None
        method = "visual-dhash"
        proof_expected_hash = _expected_visible_dhash(expected)
        proof_remote_hash = remote.get("visible_dhash") or remote.get("dhash")
    if remote["sha256"] == expected_sha:
        proof_expected_hash = expected.get("dhash")
        proof_remote_hash = remote.get("dhash")
    return {
        "expected_sha256": expected_sha,
        "remote_sha256": remote["sha256"],
        "remote_url": remote_url,
        "match_method": method,
        "expected_dhash": proof_expected_hash,
        "remote_dhash": proof_remote_hash,
        "dhash_distance": distance,
        "expected_width": expected.get("width"),
        "expected_height": expected.get("height"),
        "remote_width": remote.get("width"),
        "remote_height": remote.get("height"),
    }


X_COVER_RATIO_WINDOW = (2.3, 2.7)
# note crops a 3:2 source into its 1280x670 eyecatch (1.91:1); plain dHash
# measured distance 15 against the full source on 2026-07-25, because the
# comparator was reading a crop as if it were the whole image.
NOTE_EYECATCH_RATIO_WINDOW = (1.8, 2.0)


def center_crop_content_proof(
    expected: dict[str, Any],
    remote_data: bytes,
    remote_url: str,
    ratio_window: tuple[float, float] = X_COVER_RATIO_WINDOW,
) -> dict[str, Any] | None:
    """Prove a platform's fixed wide cover against a centered crop of the source."""
    source_path = Path(str(expected.get("path", "")))
    if not source_path.is_file():
        return None
    try:
        with Image.open(source_path) as source:
            source.load()
            with Image.open(io.BytesIO(remote_data)) as remote_image:
                remote_image.load()
                if remote_image.height <= 0 or remote_image.width <= 0:
                    return None
                remote_ratio = remote_image.width / remote_image.height
                if not ratio_window[0] <= remote_ratio <= ratio_window[1]:
                    return None
                source_ratio = source.width / source.height
                if source_ratio > remote_ratio:
                    crop_width = round(source.height * remote_ratio)
                    left = (source.width - crop_width) // 2
                    box = (left, 0, left + crop_width, source.height)
                else:
                    crop_height = round(source.width / remote_ratio)
                    top = (source.height - crop_height) // 2
                    box = (0, top, source.width, top + crop_height)
                cropped = source.crop(box)
                crop_hash = _visible_dhash(cropped)
                remote_hash = _visible_dhash(remote_image)
                distance = dhash_distance(crop_hash, remote_hash)
                crop_vertical_hash = _visible_dhash(
                    cropped.rotate(90, expand=True)
                )
                remote_vertical_hash = _visible_dhash(
                    remote_image.rotate(90, expand=True)
                )
                vertical_distance = dhash_distance(
                    crop_vertical_hash,
                    remote_vertical_hash,
                )
                if (
                    distance > MAX_DHASH_DISTANCE
                    or vertical_distance > MAX_DHASH_DISTANCE
                ):
                    return None
                remote = descriptor_from_bytes(remote_data)
    except (OSError, ValueError, UnidentifiedImageError):
        return None
    return {
        "expected_sha256": str(expected.get("sha256", "")),
        "remote_sha256": remote["sha256"],
        "remote_url": remote_url,
        "match_method": "visual-center-crop-dhash",
        "expected_dhash": expected.get("dhash"),
        "expected_crop_dhash": crop_hash,
        "remote_dhash": remote_hash,
        "dhash_distance": distance,
        "expected_crop_vertical_dhash": crop_vertical_hash,
        "remote_vertical_dhash": remote_vertical_hash,
        "vertical_dhash_distance": vertical_distance,
        "expected_width": expected.get("width"),
        "expected_height": expected.get("height"),
        "expected_crop_box": list(box),
        "remote_width": remote.get("width"),
        "remote_height": remote.get("height"),
    }
