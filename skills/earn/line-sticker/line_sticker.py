"""Deterministic validation for a LINE animated-sticker package."""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from typing import Literal, TypedDict
import zipfile
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_NAMES = tuple(sorted(["main.png", "tab.png"] + [f"{number:02d}.png" for number in range(1, 25)]))
PACKAGE_NAMES = frozenset((*PNG_NAMES, "provenance.json", "submission.zip"))
KNOWN_CRITICAL_CHUNKS = frozenset(("IHDR", "PLTE", "IDAT", "IEND", "acTL", "fcTL", "fdAT"))
SINGLETON_CHUNKS = frozenset(
    {
        "IHDR",
        "PLTE",
        "tRNS",
        "cHRM",
        "gAMA",
        "iCCP",
        "sBIT",
        "sRGB",
        "bKGD",
        "hIST",
        "pHYs",
        "tIME",
        "eXIf",
        "acTL",
        "IEND",
    }
)
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
FFMPEG_TIMEOUT_SECONDS = 30.0
POLICY_SHA256_V1 = "3a3462f9b644c624836aa2a847cc7aae3fc9ce97dee87f8c0c02cdbb320fc8fe"

OWNER_STATES = (
    "NEW",
    "WAITING_REVIEW",
    "REJECTED",
    "APPROVED",
    "RELEASED",
    "TERMINAL_PENDING_REPLAY",
    "CLOSED",
    "RECONCILE_UNKNOWN",
    "NEEDS_OWNER_CEREMONY",
    "NEEDS_POLICY_REVIEW",
)
PROVIDER_STATUSES = ("absent", "draft", "submitted", "rejected", "approved", "released")
ProviderStatus = Literal["absent", "draft", "submitted", "rejected", "approved", "released"]


class ProviderObservation(TypedDict):
    account_id: str
    set_id: str
    revision: int
    artifact_sha256: str
    product_id: str | None
    status: ProviderStatus
    public_url: str | None


OWNER_IDENTITY_KEYS = frozenset(
    {"account_id", "set_id", "character_id", "revision", "artifact_sha256", "package_sha256"}
)
OWNER_KEYS = frozenset({"version", "identity", "state", "product_id", "public_url", "pending_action"})
RECEIPT_KEYS = frozenset(
    {
        "receipt_id",
        "effect_key",
        "action",
        "account_id",
        "set_id",
        "revision",
        "artifact_sha256",
        "product_id",
        "before_status",
        "after_status",
        "effect",
        "readback",
        "duplicate_effect",
        "outcome",
    }
)
class OwnerStateError(ValueError):
    """A stable, non-sensitive durable-owner failure code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ReceiptPendingError(OwnerStateError):
    def __init__(self, action: str, effect_key: str, effect: int) -> None:
        super().__init__("receipt_pending")
        self.action = action
        self.effect_key = effect_key
        self.effect = effect


class PngError(ValueError):
    """A parse failure with a stable, non-sensitive error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_chunks(data: bytes) -> list[tuple[str, bytes, str]]:
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("png_signature_invalid")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[str, bytes, str]] = []
    seen: set[str] = set()
    ended = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise PngError("png_trailing_bytes" if ended else "png_chunk_truncated")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise PngError("png_chunk_truncated")
        kind_bytes = data[offset + 4 : offset + 8]
        if len(kind_bytes) != 4 or not all(65 <= c <= 122 and (c < 91 or c > 96) for c in kind_bytes):
            raise PngError("png_chunk_invalid")
        kind = kind_bytes.decode("ascii")
        payload_start = offset + 8
        payload_end = payload_start + length
        payload = data[payload_start:payload_end]
        actual_crc = struct.unpack(">I", data[payload_end : payload_end + 4])[0]
        expected_crc = zlib.crc32(kind_bytes + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise PngError("png_crc_invalid")
        if kind_bytes[0] & 0x20 == 0 and kind not in KNOWN_CRITICAL_CHUNKS:
            raise PngError("png_critical_chunk_unknown")
        if kind in SINGLETON_CHUNKS and kind in seen:
            raise PngError("png_duplicate_chunk")
        seen.add(kind)
        chunks.append((kind, payload, _sha256(kind_bytes + payload)))
        offset = end
        if kind == "IEND":
            if length != 0:
                raise PngError("png_iend_invalid")
            ended = True
            if offset != len(data):
                raise PngError("png_trailing_bytes")
            break
    if not ended:
        raise PngError("png_iend_missing")
    return chunks


def _parse_frame_control(payload: bytes) -> tuple[int, int, int, int, int, int, int, int, int]:
    if len(payload) != 26:
        raise PngError("fcTL_invalid")
    sequence, width, height, x, y, delay_num, delay_den, dispose, blend = struct.unpack(
        ">IIIIIHHBB", payload
    )
    if width == 0 or height == 0 or dispose > 2 or blend > 1:
        raise PngError("fcTL_invalid")
    return sequence, width, height, x, y, delay_num, delay_den or 100, dispose, blend


def parse_png(path: Path) -> dict[str, object]:
    """Parse PNG/APNG structure without trusting a decoder for metadata."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PngError("png_unreadable") from exc
    chunks = _read_chunks(data)
    if not chunks or chunks[0][0] != "IHDR":
        raise PngError("png_ihdr_missing")
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise PngError("png_ihdr_invalid")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if width == 0 or height == 0:
        raise PngError("dimensions_invalid")
    if bit_depth != 8 or compression != 0 or filter_method != 0 or interlace not in (0, 1):
        raise PngError("png_ihdr_invalid")
    if color_type not in (0, 2, 3, 4, 6):
        raise PngError("color_type_invalid")

    by_kind: dict[str, list[bytes]] = {}
    for kind, payload, _digest in chunks:
        by_kind.setdefault(kind, []).append(payload)
    if len(by_kind.get("IEND", [])) != 1:
        raise PngError("png_iend_missing")
    plte = by_kind.get("PLTE")
    if plte:
        plte_index = next(index for index, chunk in enumerate(chunks) if chunk[0] == "PLTE")
        first_idat_index = next((index for index, chunk in enumerate(chunks) if chunk[0] == "IDAT"), None)
        if color_type != 6 or not (3 <= len(plte[0]) <= 768) or len(plte[0]) % 3 or (first_idat_index is not None and plte_index > first_idat_index):
            raise PngError("png_palette_invalid")
    if "tRNS" in by_kind and color_type in (4, 6):
        raise PngError("png_trns_invalid")

    actl = by_kind.get("acTL")
    animated = actl is not None
    if actl is not None:
        if len(actl) != 1 or len(actl[0]) != 8:
            raise PngError("acTL_invalid")
        declared_frames, plays = struct.unpack(">II", actl[0])
        if declared_frames == 0:
            raise PngError("acTL_invalid")
        actl_index = next(index for index, chunk in enumerate(chunks) if chunk[0] == "acTL")
        first_idat_index = next((index for index, chunk in enumerate(chunks) if chunk[0] == "IDAT"), None)
        if first_idat_index is not None and actl_index > first_idat_index:
            raise PngError("png_apng_order_invalid")
    else:
        declared_frames, plays = 1, 1

    frame_controls: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    expected_sequence = 0
    saw_idat = False
    saw_fdat = False
    first_frame_has_data = False
    current_frame = -1
    frame_has_data: list[bool] = []
    for kind, payload, _digest in chunks:
        if kind == "fcTL":
            if not animated:
                raise PngError("png_apng_invalid")
            if current_frame >= 0 and not frame_has_data[current_frame]:
                raise PngError("png_apng_invalid")
            frame = _parse_frame_control(payload)
            sequence = frame[0]
            if sequence != expected_sequence:
                raise PngError("png_sequence_invalid")
            expected_sequence += 1
            _sequence, frame_width, frame_height, x, y, *_ = frame
            if x + frame_width > width or y + frame_height > height:
                raise PngError("dimensions_invalid")
            if frame_controls and (frame_width, frame_height) != frame_controls[0][1:3]:
                raise PngError("dimensions_invalid")
            frame_controls.append(frame)
            frame_has_data.append(False)
            current_frame += 1
        elif kind == "IDAT":
            if animated and current_frame != 0:
                raise PngError("png_apng_invalid")
            saw_idat = True
            if animated and current_frame == 0:
                first_frame_has_data = True
                frame_has_data[0] = True
        elif kind == "fdAT":
            if not animated or len(payload) < 5:
                raise PngError("png_apng_invalid")
            sequence = struct.unpack(">I", payload[:4])[0]
            if sequence != expected_sequence:
                raise PngError("png_sequence_invalid")
            expected_sequence += 1
            saw_fdat = True
            if current_frame <= 0:
                raise PngError("png_apng_invalid")
            frame_has_data[current_frame] = True
    if not saw_idat:
        raise PngError("png_image_data_missing")
    if animated:
        if not frame_controls or not first_frame_has_data or len(frame_controls) != declared_frames:
            raise PngError("frame_count_invalid")
        if not saw_fdat and declared_frames > 1:
            raise PngError("png_apng_invalid")
        if not all(frame_has_data):
            raise PngError("png_apng_invalid")
        if expected_sequence == 0:
            raise PngError("png_sequence_invalid")
        delays = [Fraction(frame[5], frame[6]) * 1000 for frame in frame_controls]
        if any(delay <= 0 for delay in delays):
            raise PngError("duration_invalid")
        total = sum(delays, Fraction(0, 1)) * plays
        duration_ms: int | float = int(total) if total.denominator == 1 else float(total)
        frames = declared_frames
    else:
        if by_kind.get("fcTL") or by_kind.get("fdAT") or len(by_kind.get("IDAT", [])) == 0:
            raise PngError("png_apng_invalid")
        frames, plays, duration_ms = 1, 1, 0

    chunk_hashes: dict[str, list[str]] = {}
    for kind, _payload, digest in chunks:
        chunk_hashes.setdefault(kind, []).append(digest)
    return {
        "width": width,
        "height": height,
        "color_type": color_type,
        "animated": animated,
        "frames": frames,
        "plays": plays,
        "duration_ms": duration_ms,
        "chunk_hashes": chunk_hashes,
    }


def _load_policy(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("policy_invalid") from exc
    if _sha256(raw) != POLICY_SHA256_V1:
        raise ValueError("policy_hash_mismatch")
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("policy_invalid") from exc
    if not isinstance(policy, dict):
        raise ValueError("policy_invalid")
    return policy


def _policy_is_stale(policy: dict[str, object]) -> bool:
    try:
        observed = date.fromisoformat(str(policy["observed_at"]))
        max_age = int(policy["max_policy_age_days"])
    except (TypeError, ValueError):
        return True
    # The host can be one local calendar day ahead while UTC is still the previous
    # date; use the later clock only for this boundary check.
    effective_today = max(datetime.now(timezone.utc).date(), date.today())
    age = (effective_today - observed).days
    return observed > effective_today or age > max_age


def _error_for_file(code: str, name: str) -> str:
    return code if ":" in code else f"{code}:{name}"


def _safe_zip_name(name: str) -> bool:
    return bool(name) and "\\" not in name and "\x00" not in name and not name.startswith("/") and ".." not in name.split("/")


def _hole_seeds(provenance: dict[str, object], name: str) -> set[tuple[int, int]]:
    values: object = []
    assets = provenance.get("assets")
    if isinstance(assets, dict) and isinstance(assets.get(name), dict):
        values = assets[name].get("intentional_alpha_holes", [])
    if not isinstance(values, list):
        return set()
    seeds: set[tuple[int, int]] = set()
    for value in values:
        if isinstance(value, dict) and isinstance(value.get("x"), int) and isinstance(value.get("y"), int):
            seeds.add((value["x"], value["y"]))
        elif isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(item, int) for item in value):
            seeds.add((value[0], value[1]))
    return seeds


def _alpha_frame_error(raw: bytes, width: int, height: int, seeds: set[tuple[int, int]]) -> str | None:
    if len(raw) != width * height * 4:
        return "decoded_byte_count"
    transparent = bytearray(width * height)
    for index in range(width * height):
        transparent[index] = raw[index * 4 + 3] == 0
    outside = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for y in range(height):
        for x in (0, width - 1):
            index = y * width + x
            if transparent[index] and not outside[index]:
                outside[index] = 1
                queue.append((x, y))
    for x in range(width):
        for y in (0, height - 1):
            index = y * width + x
            if transparent[index] and not outside[index]:
                outside[index] = 1
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                index = ny * width + nx
                if transparent[index] and not outside[index]:
                    outside[index] = 1
                    queue.append((nx, ny))
    if not any(outside):
        return "alpha_background_missing"
    visited = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            start = y * width + x
            if not transparent[start] or outside[start] or visited[start]:
                continue
            component: set[tuple[int, int]] = set()
            queue.append((x, y))
            visited[start] = 1
            while queue:
                cx, cy = queue.popleft()
                component.add((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        index = ny * width + nx
                        if transparent[index] and not outside[index] and not visited[index]:
                            visited[index] = 1
                            queue.append((nx, ny))
            if not component.intersection(seeds):
                return "alpha_hole_unexpected"
    return None


def _has_unexpected_alpha_hole(raw: bytes, width: int, height: int, seeds: set[tuple[int, int]]) -> bool:
    return _alpha_frame_error(raw, width, height, seeds) == "alpha_hole_unexpected"


def _decode_frames(path: Path, parsed: dict[str, object], ffmpeg: str) -> tuple[list[bytes], str | None]:
    width, height = int(parsed["width"]), int(parsed["height"])
    frame_count = int(parsed["frames"])
    if frame_count <= 0:
        return [], "decoded_byte_count"
    frame_bytes = width * height * 4
    expected_bytes = frame_bytes * frame_count
    try:
        with tempfile.TemporaryDirectory(prefix="line-sticker-decode-") as directory:
            output_path = Path(directory) / "frames.rgba"
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-xerror",
                    "-i",
                    str(path),
                    "-frames:v",
                    str(frame_count),
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgba",
                    str(output_path),
                ],
                check=True,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            metadata = output_path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_bytes:
                return [], "decoded_byte_count"
            decoded = output_path.read_bytes()
    except subprocess.TimeoutExpired:
        return [], "decode_timeout"
    except (OSError, subprocess.CalledProcessError):
        return [], "decode_failed"
    if len(decoded) != expected_bytes:
        return [], "decoded_byte_count"
    return [decoded[offset : offset + frame_bytes] for offset in range(0, expected_bytes, frame_bytes)], None


def _decode_and_check_alpha(path: Path, parsed: dict[str, object], ffmpeg: str, seeds: set[tuple[int, int]]) -> str | None:
    frames, error = _decode_frames(path, parsed, ffmpeg)
    if error:
        return error
    try:
        width, height = int(parsed["width"]), int(parsed["height"])
        for frame in frames:
            frame_error = _alpha_frame_error(frame, width, height, seeds)
            if frame_error:
                return frame_error
        if parsed["animated"] and len({hashlib.sha256(frame).digest() for frame in frames}) < 2:
            return "animation_static"
    except (KeyError, TypeError, ValueError):
        return "decoded_byte_count"
    return None


GENERATION_KEYS = frozenset({
    "rights_evidence", "character_sha256", "plan_sha256", "selection_sha256", "prompt_sha256",
    "model", "provider", "reserved_cost_usd", "actual_cost_usd", "batches", "candidate_bindings", "generation_sha256",
})


def _provenance_errors(provenance: object, file_hashes: dict[str, str]) -> list[str]:
    if not isinstance(provenance, dict):
        return ["provenance_missing"]
    required = {"set_id", "character_id", "rights", "providers", "prompt_hashes", "assets", "generation"}
    if set(provenance) != required:
        return ["provenance_invalid"] if required.intersection(provenance) else ["provenance_missing"]
    errors: list[str] = []
    if not isinstance(provenance.get("set_id"), str) or not provenance["set_id"]:
        errors.append("provenance_invalid")
    if not isinstance(provenance.get("character_id"), str) or not provenance["character_id"]:
        errors.append("provenance_invalid")
    if provenance.get("rights") != "original_ai_generated":
        errors.append("provenance_invalid")
    providers = provenance.get("providers")
    if not isinstance(providers, dict):
        errors.append("provenance_invalid")
    elif set(providers) != {"image", "animation"}:
        errors.append("provenance_invalid" if set(providers) else "provenance_missing")
    elif not all(type(providers[key]) is str and providers[key] for key in ("image", "animation")):
        errors.append("provenance_invalid")
    prompt_hashes = provenance.get("prompt_hashes")
    assets = provenance.get("assets")
    if not isinstance(prompt_hashes, dict) or not isinstance(assets, dict):
        return ["provenance_invalid"]
    if set(prompt_hashes) != set(PNG_NAMES):
        errors.append("provenance_missing" if set(prompt_hashes).issubset(PNG_NAMES) else "provenance_invalid")
    if set(assets) != set(PNG_NAMES):
        errors.append("provenance_missing" if set(assets).issubset(PNG_NAMES) else "provenance_invalid")
    for name in PNG_NAMES:
        if name not in prompt_hashes:
            continue
        if type(prompt_hashes[name]) is not str or not HEX64.fullmatch(prompt_hashes[name]):
            errors.append("provenance_invalid")
        entry = assets.get(name)
        if not isinstance(entry, dict):
            errors.append("provenance_invalid")
            continue
        if set(entry) != {"sha256", "intentional_alpha_holes"}:
            errors.append("provenance_invalid")
            continue
        if type(entry["sha256"]) is not str or not HEX64.fullmatch(entry["sha256"]):
            errors.append("provenance_invalid")
        holes = entry["intentional_alpha_holes"]
        if not isinstance(holes, list):
            errors.append("provenance_invalid")
        else:
            for hole in holes:
                if not isinstance(hole, dict) or set(hole) != {"x", "y"} or type(hole["x"]) is not int or type(hole["y"]) is not int:
                    errors.append("provenance_invalid")
    for name in PNG_NAMES:
        entry = assets.get(name)
        if isinstance(entry, dict) and set(entry) == {"sha256", "intentional_alpha_holes"} and type(entry["sha256"]) is str and HEX64.fullmatch(entry["sha256"]):
            actual = file_hashes.get(name)
            if actual is not None and actual.lower() != entry["sha256"].lower():
                errors.append(f"provenance_hash_mismatch:{name}")
    generation = provenance.get("generation")
    if not isinstance(generation, dict) or set(generation) != GENERATION_KEYS:
        errors.append("provenance_invalid")
        return sorted(set(errors))
    generation_body = dict(generation)
    generation_hash = generation_body.pop("generation_sha256")
    if not isinstance(generation_hash, str) or not HEX64.fullmatch(generation_hash) or _sha256(_canonical_json(generation_body)) != generation_hash:
        errors.append("provenance_invalid")
    if not all(type(generation.get(key)) is str and HEX64.fullmatch(str(generation[key])) for key in ("character_sha256", "plan_sha256", "selection_sha256", "prompt_sha256")):
        errors.append("provenance_invalid")
    rights = generation["rights_evidence"]
    if not isinstance(rights, dict) or set(rights) != {"receipt_sha256", "set_id", "character_id", "character_sha256", "creation_source", "rights"} or not isinstance(rights.get("receipt_sha256"), str) or not HEX64.fullmatch(str(rights["receipt_sha256"])) or rights.get("set_id") != provenance.get("set_id") or rights.get("character_id") != provenance.get("character_id") or rights.get("character_sha256") != generation["character_sha256"] or rights.get("rights") != "original_ai_generated" or not isinstance(rights.get("creation_source"), str) or not rights["creation_source"]:
        errors.append("provenance_invalid")
    elif _sha256(_canonical_json({key: rights[key] for key in ("set_id", "character_id", "character_sha256", "creation_source", "rights")})) != rights["receipt_sha256"]:
        errors.append("provenance_invalid")
    if not all(type(generation.get(key)) is str and generation[key] for key in ("model", "provider", "reserved_cost_usd", "actual_cost_usd")):
        errors.append("provenance_invalid")
    for key in ("reserved_cost_usd", "actual_cost_usd"):
        try:
            value = Decimal(str(generation[key]))
            if not value.is_finite() or value < 0:
                errors.append("provenance_invalid")
        except (InvalidOperation, ValueError):
            errors.append("provenance_invalid")
    batches = generation["batches"]
    bindings = generation["candidate_bindings"]
    if not isinstance(batches, dict) or set(batches) != {str(value) for value in range(1, 7)} or not isinstance(bindings, dict) or set(bindings) != {f"{value:02d}.png" for value in range(1, 25)}:
        errors.append("provenance_invalid")
    else:
        reserved_total = Decimal(0)
        actual_total = Decimal(0)
        valid_batches: set[str] = set()
        for batch_name, batch in batches.items():
            if not isinstance(batch, dict) or set(batch) != {"quote_request_id", "generation_request_id", "quote_token", "provider", "model", "reserved_cost_usd", "actual_cost_usd", "source_sha256", "regenerable"} or not all(type(batch.get(key)) is str and batch[key] for key in ("quote_request_id", "generation_request_id", "quote_token", "provider", "model", "reserved_cost_usd", "actual_cost_usd")) or not isinstance(batch.get("regenerable"), bool) or not isinstance(batch.get("source_sha256"), str) or not HEX64.fullmatch(str(batch["source_sha256"])):
                errors.append("provenance_invalid")
                break
            valid_batches.add(batch_name)
            if not isinstance(providers, dict) or batch.get("generation_request_id") != batch.get("quote_request_id") or batch.get("provider") != generation.get("provider") or batch.get("model") != generation.get("model") or batch.get("provider") != providers.get("animation"):
                errors.append("provenance_invalid")
                break
            try:
                reserved_cost = Decimal(batch["reserved_cost_usd"])
                actual_cost = Decimal(batch["actual_cost_usd"])
                if not reserved_cost.is_finite() or not actual_cost.is_finite() or reserved_cost < 0 or actual_cost < 0 or actual_cost > reserved_cost:
                    raise ValueError
                reserved_total += reserved_cost
                actual_total += actual_cost
            except (InvalidOperation, ValueError):
                errors.append("provenance_invalid")
                break
        if format(reserved_total, "f") != generation.get("reserved_cost_usd") or format(actual_total, "f") != generation.get("actual_cost_usd"):
            errors.append("provenance_invalid")
        for name, binding in bindings.items():
            motion_id = binding.get("motion_id") if isinstance(binding, dict) else None
            matched = re.fullmatch(r"motion-(0[1-9]|[1-5][0-9]|60)", motion_id) if isinstance(motion_id, str) else None
            expected_batch = str((int(matched.group(1)) - 1) // 10 + 1) if matched else ""
            expected = batches.get(expected_batch)
            if not isinstance(binding, dict) or set(binding) != {"motion_id", "source_sha256", "segment", "candidate_sha256", "conversion_argv_sha256", "asset_sha256"} or expected_batch not in valid_batches or not isinstance(expected, dict) or not isinstance(motion_id, str) or not matched or any(not isinstance(binding.get(key), str) or not HEX64.fullmatch(str(binding[key])) for key in ("source_sha256", "candidate_sha256", "conversion_argv_sha256", "asset_sha256")) or (name in file_hashes and (binding.get("asset_sha256") != file_hashes[name] or binding.get("candidate_sha256") != file_hashes[name])) or binding.get("source_sha256") != expected.get("source_sha256") or not isinstance(binding.get("segment"), dict) or set(binding["segment"]) != {"motion_id", "start_ms", "end_ms"} or binding["segment"].get("motion_id") != motion_id or type(binding["segment"].get("start_ms")) is not int or type(binding["segment"].get("end_ms")) is not int or binding["segment"]["start_ms"] < 0 or binding["segment"]["end_ms"] <= binding["segment"]["start_ms"]:
                errors.append("provenance_invalid")
                break
    return sorted(set(errors))


def _provenance_hole_range_errors(provenance: object, parsed_files: dict[str, dict[str, object]]) -> list[str]:
    if not isinstance(provenance, dict) or not isinstance(provenance.get("assets"), dict):
        return []
    for name, entry in provenance["assets"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("intentional_alpha_holes"), list):
            continue
        parsed = parsed_files.get(name)
        if parsed is None:
            continue
        width, height = int(parsed["width"]), int(parsed["height"])
        for hole in entry["intentional_alpha_holes"]:
            if isinstance(hole, dict) and type(hole.get("x")) is int and type(hole.get("y")) is int and not (0 <= hole["x"] < width and 0 <= hole["y"] < height):
                return ["provenance_invalid"]
    return []


def _canonical_package_hash(file_hashes: dict[str, str], provenance: object, zip_payloads: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in PNG_NAMES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hashes.get(name, "").encode("ascii"))
    if isinstance(provenance, dict):
        digest.update(json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for name in sorted(zip_payloads):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(zip_payloads[name])
    return digest.hexdigest()


def _preflight_png(root: Path, path: Path, name: str, max_file_bytes: int) -> tuple[object | None, str | None]:
    if path.name != name or path.parent != root:
        return None, f"unsafe_filename:{name}"
    try:
        metadata = path.lstat()
    except OSError:
        return None, f"file_missing:{name}"
    if not stat.S_ISREG(metadata.st_mode):
        return metadata, f"file_not_regular:{name}"
    if metadata.st_size >= max_file_bytes:
        return metadata, f"file_too_large:{name}"
    return metadata, None


def validate_package(root: Path, policy_path: Path, ffmpeg: str = "ffmpeg") -> dict[str, object]:
    """Return a stable, effect-free acceptance record for one package directory."""
    root = Path(root)
    policy = _load_policy(Path(policy_path))
    errors: set[str] = set()
    if _policy_is_stale(policy):
        errors.add("policy_stale")
    max_file_bytes = int(policy["max_file_bytes"])
    preflight: dict[str, tuple[object | None, str | None]] = {}
    for name in PNG_NAMES:
        path = root / name
        metadata, preflight_error = _preflight_png(root, path, name, max_file_bytes)
        preflight[name] = (metadata, preflight_error)
        if preflight_error:
            errors.add(preflight_error)
    try:
        provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        provenance = None
        errors.add("provenance_missing")

    try:
        actual_members = {entry.name for entry in root.iterdir()} if root.is_dir() else set()
    except OSError:
        actual_members = set()
    if actual_members != PACKAGE_NAMES:
        errors.add("package_membership_mismatch")

    parsed_files: dict[str, dict[str, object]] = {}
    file_records: list[dict[str, object]] = []
    file_hashes: dict[str, str] = {}
    for name in PNG_NAMES:
        path = root / name
        metadata, preflight_error = preflight[name]
        bytes_count = int(getattr(metadata, "st_size", 0))
        record: dict[str, object] = {"name": name, "bytes": bytes_count, "sha256": ""}
        if preflight_error or metadata is None:
            file_records.append(record)
            continue
        try:
            current = path.lstat()
        except OSError:
            errors.add(f"file_missing:{name}")
            file_records.append(record)
            continue
        if not stat.S_ISREG(current.st_mode):
            errors.add(f"file_not_regular:{name}")
            file_records.append(record)
            continue
        if current.st_size >= max_file_bytes:
            errors.add(f"file_too_large:{name}")
            file_records.append(record)
            continue
        contents = path.read_bytes()
        file_hashes[name] = _sha256(contents)
        record["bytes"] = len(contents)
        record["sha256"] = file_hashes[name]
        try:
            parsed = parse_png(path)
        except PngError as exc:
            errors.add(_error_for_file(exc.code, name))
        else:
            parsed_files[name] = parsed
            record.update(parsed)
        file_records.append(record)
    errors.update(_provenance_errors(provenance, file_hashes))
    errors.update(_provenance_hole_range_errors(provenance, parsed_files))

    for digest, names in _group_duplicate_hashes(file_hashes).items():
        if len(names) > 1:
            for left, right in zip(names, names[1:]):
                errors.add(f"duplicate_asset:{left}:{right}")

    main = parsed_files.get("main.png")
    tab = parsed_files.get("tab.png")
    if main is not None:
        expected_main = policy["main"]
        if not isinstance(expected_main, dict) or (main["width"], main["height"]) != (expected_main.get("width"), expected_main.get("height")):
            errors.add("dimensions_invalid:main.png")
        if bool(main["animated"]) != bool(expected_main.get("animated")):
            errors.add("animation_required:main.png")
    if tab is not None:
        expected_tab = policy["tab"]
        if not isinstance(expected_tab, dict) or (tab["width"], tab["height"]) != (expected_tab.get("width"), expected_tab.get("height")):
            errors.add("dimensions_invalid:tab.png")
        if bool(tab["animated"]) != bool(expected_tab.get("animated")):
            errors.add("animation_forbidden:tab.png")

    sticker_policy = policy["sticker"]
    apng_policy = policy["apng"]
    for name in PNG_NAMES:
        if name == "tab.png" or name not in parsed_files:
            continue
        parsed = parsed_files[name]
        if not parsed["animated"] and name != "main.png":
            errors.add(f"animation_required:{name}")
        if name != "main.png" and (not isinstance(sticker_policy, dict) or int(parsed["width"]) > int(sticker_policy["max_width"]) or int(parsed["height"]) > int(sticker_policy["max_height"]) or int(sticker_policy["required_side"]) not in (parsed["width"], parsed["height"])):
            errors.add(f"dimensions_invalid:{name}")
        if parsed["animated"] and isinstance(apng_policy, dict):
            if int(parsed["frames"]) < int(apng_policy["min_frames"]) or int(parsed["frames"]) > int(apng_policy["max_frames"]):
                errors.add(f"frame_count_invalid:{name}")
            if int(parsed["plays"]) < int(apng_policy["min_plays"]) or int(parsed["plays"]) > int(apng_policy["max_plays"]):
                errors.add(f"play_count_invalid:{name}")
            if float(parsed["duration_ms"]) <= 0 or float(parsed["duration_ms"]) > float(apng_policy["max_duration_ms"]):
                errors.add(f"duration_invalid:{name}")

    zip_payloads: dict[str, bytes] = {}
    zip_path = root / "submission.zip"
    max_zip_bytes = int(policy["max_zip_bytes"])
    zip_bytes: bytes | None = None
    try:
        zip_metadata = zip_path.lstat()
    except OSError:
        zip_metadata = None
    if zip_metadata is None or stat.S_ISLNK(zip_metadata.st_mode) or not stat.S_ISREG(zip_metadata.st_mode):
        errors.add("zip_membership_mismatch")
    elif zip_metadata.st_size >= max_zip_bytes:
        errors.add("zip_too_large")
    else:
        try:
            zip_bytes = zip_path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)) or set(names) != set(PNG_NAMES) or any(not _safe_zip_name(name) for name in names):
                    errors.add("zip_membership_mismatch")
                for info in infos:
                    if info.file_size >= max_file_bytes:
                        if info.filename in PNG_NAMES and f"file_too_large:{info.filename}" in errors:
                            continue
                        errors.add(f"zip_file_too_large:{info.filename}")
                        continue
                    if not _safe_zip_name(info.filename) or info.is_dir() or info.filename not in PNG_NAMES:
                        continue
                    try:
                        zip_payloads[info.filename] = archive.read(info)
                    except (OSError, RuntimeError, zipfile.BadZipFile):
                        errors.add("zip_invalid")
        except (OSError, zipfile.BadZipFile, RuntimeError):
            errors.add("zip_invalid")
        for name in PNG_NAMES:
            if name in zip_payloads and name in file_hashes and _sha256(zip_payloads[name]) != file_hashes[name]:
                errors.add(f"zip_content_mismatch:{name}")

    required_color_types = set(policy["required_color_types"])
    for name, parsed in parsed_files.items():
        if int(parsed["color_type"]) not in required_color_types:
            errors.add(f"color_type_invalid:{name}")
        if any(error.endswith(f":{name}") for error in errors):
            continue
        if isinstance(provenance, dict) and not ({"provenance_invalid", "provenance_missing"} & errors):
            alpha_error = _decode_and_check_alpha(root / name, parsed, ffmpeg, _hole_seeds(provenance, name))
            if alpha_error:
                errors.add(f"{alpha_error}:{name}")

    artifact_sha256 = _sha256(zip_bytes) if zip_bytes is not None else ""
    package_sha256 = _canonical_package_hash(file_hashes, provenance, zip_payloads)
    set_id = provenance.get("set_id") if isinstance(provenance, dict) and type(provenance.get("set_id")) is str else ""
    character_id = provenance.get("character_id") if isinstance(provenance, dict) and type(provenance.get("character_id")) is str else ""
    errors_list = sorted(errors)
    return {
        "status": "ready" if not errors_list else "invalid",
        "effect": 0,
        "readback": 0,
        "set_id": set_id,
        "character_id": character_id,
        "artifact_sha256": artifact_sha256,
        "package_sha256": package_sha256,
        "files": sorted(file_records, key=lambda record: str(record["name"])),
        "errors": errors_list,
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _effect_key(identity: dict[str, object], action: str) -> str:
    return _sha256(
        _canonical_json(
            {
                "account_id": identity["account_id"],
                "set_id": identity["set_id"],
                "revision": identity["revision"],
                "action": action,
            }
        )
    )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise OwnerStateError("state_sync_failed") from exc


def _state_target(path: Path, label: str, *, missing_ok: bool = True) -> stat._struct_stat | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise OwnerStateError(f"{label}_missing")
    except OSError as exc:
        raise OwnerStateError(f"{label}_unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise OwnerStateError(f"{label}_symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise OwnerStateError(f"{label}_not_regular")
    return metadata


def _ensure_state_dir(path: Path, *, create: bool) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if not create:
            return False
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return _ensure_state_dir(path, create=False)
        except OSError as exc:
            raise OwnerStateError("state_dir_unavailable") from exc
        return True
    except OSError as exc:
        raise OwnerStateError("state_dir_unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise OwnerStateError("state_dir_symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise OwnerStateError("state_dir_not_directory")
    return True


def atomic_json(path: Path, value: object) -> None:
    """Atomically replace one regular JSON file and durably sync its directory."""
    path = Path(path)
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise OwnerStateError("state_dir_unavailable")
    label = "owner" if path.name == "owner.json" else "state"
    _state_target(path, label)
    temporary: str | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(parent))
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    except OwnerStateError:
        raise
    except OSError as exc:
        raise OwnerStateError("state_write_failed") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _append_receipt(path: Path, receipt: dict[str, object]) -> None:
    """Append one canonical receipt line, refusing links and non-regular targets."""
    path = Path(path)
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise OwnerStateError("state_dir_unavailable")
    _state_target(path, "ledger")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(str(path), flags, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            descriptor = None
            stream.write(_canonical_json(receipt) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(parent)
    except OwnerStateError:
        raise
    except OSError as exc:
        raise OwnerStateError("ledger_write_failed") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_owner(path: Path) -> dict[str, object]:
    _state_target(path, "owner", missing_ok=False)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OwnerStateError("owner_malformed") from exc
    if not isinstance(value, dict):
        raise OwnerStateError("owner_malformed")
    return value


def _public_url_matches(product_id: str, public_url: object) -> bool:
    if type(public_url) is not str:
        return False
    prefix = f"https://store.line.me/stickershop/product/{product_id}/"
    return public_url.startswith(prefix) and len(public_url) > len(prefix)


def _validate_owner(owner: dict[str, object]) -> None:
    required = {"version", "identity", "state", "product_id", "public_url"}
    if not required.issubset(owner) or not set(owner).issubset(OWNER_KEYS):
        raise OwnerStateError("owner_malformed")
    if owner.get("version") != 1 or owner.get("state") not in OWNER_STATES:
        raise OwnerStateError("owner_malformed")
    identity = owner.get("identity")
    if not isinstance(identity, dict) or set(identity) != OWNER_IDENTITY_KEYS:
        raise OwnerStateError("owner_malformed")
    for key in ("account_id", "set_id", "character_id"):
        if type(identity.get(key)) is not str or not identity[key]:
            raise OwnerStateError("owner_malformed")
    if type(identity.get("revision")) is not int or isinstance(identity["revision"], bool) or identity["revision"] <= 0:
        raise OwnerStateError("owner_malformed")
    for key in ("artifact_sha256", "package_sha256"):
        if type(identity.get(key)) is not str or not HEX64.fullmatch(identity[key]):
            raise OwnerStateError("owner_malformed")
    product_id = owner.get("product_id")
    if product_id is not None and (type(product_id) is not str or not product_id):
        raise OwnerStateError("owner_malformed")
    public_url = owner.get("public_url")
    if public_url is not None and (
        product_id is None
        or not _public_url_matches(product_id, public_url)
    ):
        raise OwnerStateError("owner_malformed")
    pending = owner.get("pending_action")
    if "pending_action" in owner and pending not in ("submit", "release"):
        raise OwnerStateError("owner_malformed")
    if owner["state"] == "RECONCILE_UNKNOWN" and pending not in ("submit", "release"):
        raise OwnerStateError("owner_malformed")
    if owner["state"] != "RECONCILE_UNKNOWN" and "pending_action" in owner:
        raise OwnerStateError("owner_malformed")


def _read_receipts(path: Path, identity: dict[str, object]) -> list[dict[str, object]]:
    metadata = _state_target(path, "ledger")
    if metadata is None:
        return []
    try:
        raw_lines = path.read_bytes().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise OwnerStateError("ledger_malformed") from exc
    rows: list[dict[str, object]] = []
    seen_receipt_ids: set[str] = set()
    seen_outcomes: set[tuple[str, str]] = set()
    intent_rows: dict[str, dict[str, object]] = {}
    unknown_rows: dict[str, int] = {}
    acknowledged_rows: dict[str, int] = {}
    for raw in raw_lines:
        if not raw.strip():
            raise OwnerStateError("ledger_malformed")
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OwnerStateError("ledger_malformed") from exc
        if not isinstance(row, dict) or set(row) != RECEIPT_KEYS:
            raise OwnerStateError("ledger_malformed")
        if type(row["receipt_id"]) is not str or not row["receipt_id"]:
            raise OwnerStateError("ledger_malformed")
        receipt_body = dict(row)
        receipt_body.pop("receipt_id")
        if row["receipt_id"] != _sha256(_canonical_json(receipt_body)):
            raise OwnerStateError("ledger_conflict")
        if row["receipt_id"] in seen_receipt_ids:
            raise OwnerStateError("ledger_duplicate")
        seen_receipt_ids.add(row["receipt_id"])
        if type(row["effect_key"]) is not str or not HEX64.fullmatch(row["effect_key"]):
            raise OwnerStateError("ledger_malformed")
        if row["action"] not in ("submit", "release", "replay"):
            raise OwnerStateError("ledger_malformed")
        if type(row["account_id"]) is not str or type(row["set_id"]) is not str:
            raise OwnerStateError("ledger_malformed")
        if type(row["revision"]) is not int or isinstance(row["revision"], bool) or row["revision"] <= 0:
            raise OwnerStateError("ledger_malformed")
        if type(row["artifact_sha256"]) is not str or not HEX64.fullmatch(row["artifact_sha256"]):
            raise OwnerStateError("ledger_malformed")
        if row["product_id"] is not None and (type(row["product_id"]) is not str or not row["product_id"]):
            raise OwnerStateError("ledger_malformed")
        if row["before_status"] not in (*PROVIDER_STATUSES, "unknown") or row["after_status"] not in (*PROVIDER_STATUSES, "unknown"):
            raise OwnerStateError("ledger_malformed")
        for key in ("effect", "duplicate_effect"):
            value = row[key]
            if value is not None and (type(value) is not int or value not in (0, 1)):
                raise OwnerStateError("ledger_malformed")
        if type(row["readback"]) is not int or row["readback"] not in (0, 1):
            raise OwnerStateError("ledger_malformed")
        if row["outcome"] not in ("intent", "acknowledged", "unknown"):
            raise OwnerStateError("ledger_malformed")
        if row["action"] == "replay" and (
            row["outcome"] != "acknowledged"
            or row["before_status"] != "released"
            or row["after_status"] != "released"
        ):
            raise OwnerStateError("ledger_conflict")
        if row["account_id"] != identity["account_id"] or row["set_id"] != identity["set_id"] or row["revision"] != identity["revision"] or row["artifact_sha256"] != identity["artifact_sha256"]:
            raise OwnerStateError("ledger_identity_mismatch")
        expected_key = _effect_key(identity, str(row["action"]))
        if row["effect_key"] != expected_key:
            raise OwnerStateError("ledger_identity_mismatch")
        outcome_key = (row["effect_key"], str(row["outcome"]))
        if outcome_key in seen_outcomes:
            raise OwnerStateError("ledger_duplicate")
        seen_outcomes.add(outcome_key)
        outcome = str(row["outcome"])
        key = str(row["effect_key"])
        if outcome == "intent":
            intent_rows[key] = row
        elif outcome == "unknown":
            intent = intent_rows.get(key)
            if intent is None or row["before_status"] != intent["before_status"]:
                raise OwnerStateError("ledger_conflict")
            unknown_rows[str(row["effect_key"])] = len(rows)
        elif outcome == "acknowledged":
            if row["action"] != "replay":
                intent = intent_rows.get(key)
                resolving = key in unknown_rows
                expected_before = "unknown" if resolving else {"submit": "absent", "release": "approved"}[str(row["action"])]
                if intent is None or row["before_status"] != expected_before or (
                    not resolving and row["before_status"] != intent["before_status"]
                ):
                    raise OwnerStateError("ledger_conflict")
            acknowledged_rows[str(row["effect_key"])] = len(rows)
        expected = (0, 1, 0) if row["action"] == "replay" else {
            "intent": (1, 0, 0),
            "acknowledged": (None, 1, None) if str(row["effect_key"]) in unknown_rows else (1, 1, 0),
            "unknown": (None, 0, None),
        }[outcome]
        if (row["effect"], row["readback"], row["duplicate_effect"]) != expected:
            raise OwnerStateError("ledger_conflict" if row["action"] == "replay" else "ledger_malformed")
        if outcome == "unknown" and row["after_status"] != "unknown":
            raise OwnerStateError("ledger_malformed")
        if outcome == "acknowledged" and row["action"] == "submit" and row["after_status"] not in ("submitted", "rejected", "approved"):
            raise OwnerStateError("ledger_conflict")
        if outcome == "acknowledged" and row["action"] == "release" and row["after_status"] != "released":
            raise OwnerStateError("ledger_conflict")
        rows.append(row)
    by_effect: dict[str, set[str]] = {}
    action_by_effect: dict[str, str] = {}
    for row in rows:
        by_effect.setdefault(str(row["effect_key"]), set()).add(str(row["outcome"]))
        action_by_effect[str(row["effect_key"])] = str(row["action"])
    for key, outcomes in by_effect.items():
        if action_by_effect[key] == "replay":
            if outcomes != {"acknowledged"}:
                raise OwnerStateError("ledger_conflict")
            continue
        if ("acknowledged" in outcomes or "unknown" in outcomes) and "intent" not in outcomes:
            raise OwnerStateError("ledger_conflict")
    for key in set(unknown_rows).intersection(acknowledged_rows):
        if acknowledged_rows[key] < unknown_rows[key]:
            raise OwnerStateError("ledger_conflict")
    _validate_receipt_transitions(rows, identity)
    return rows


def _validate_receipt_transitions(rows: list[dict[str, object]], identity: dict[str, object]) -> None:
    actions = [str(row["action"]) for row in rows]
    order = {"submit": 0, "release": 1, "replay": 2}
    if any(order[left] > order[right] for left, right in zip(actions, actions[1:])):
        raise OwnerStateError("ledger_conflict")
    grouped = {action: [row for row in rows if row["action"] == action] for action in order}
    submit = grouped["submit"]
    release = grouped["release"]
    replay = grouped["replay"]
    if submit:
        if submit[0]["outcome"] != "intent" or submit[0]["before_status"] != "absent" or submit[0]["after_status"] != "submitted" or submit[0]["product_id"] is not None:
            raise OwnerStateError("ledger_conflict")
        expected = ["intent"] + (["unknown"] if len(submit) > 1 and submit[1]["outcome"] == "unknown" else [])
        if [row["outcome"] for row in submit] != expected[:len(submit)] + (["acknowledged"] if len(submit) == len(expected) + 1 else []):
            raise OwnerStateError("ledger_conflict")
        submit_unknown = next((row for row in submit if row["outcome"] == "unknown"), None)
    else:
        submit_unknown = None
    submit_ack = next((row for row in submit if row["outcome"] == "acknowledged"), None)
    if submit_ack is not None and (not isinstance(submit_ack["product_id"], str) or not submit_ack["product_id"]):
        raise OwnerStateError("ledger_conflict")
    if submit_unknown is not None and submit_unknown["product_id"] is not None and (
        not isinstance(submit_unknown["product_id"], str)
        or submit_ack is not None and submit_unknown["product_id"] != submit_ack["product_id"]
    ):
        raise OwnerStateError("ledger_conflict")
    if release:
        if submit_ack is None or release[0]["outcome"] != "intent" or release[0]["before_status"] != "approved":
            raise OwnerStateError("ledger_conflict")
        expected = ["intent"] + (["unknown"] if len(release) > 1 and release[1]["outcome"] == "unknown" else [])
        if [row["outcome"] for row in release] != expected[:len(release)] + (["acknowledged"] if len(release) == len(expected) + 1 else []):
            raise OwnerStateError("ledger_conflict")
        product = submit_ack["product_id"]
        if not isinstance(product, str) or not product or any(row["product_id"] != product for row in release):
            raise OwnerStateError("ledger_conflict")
    release_ack = next((row for row in release if row["outcome"] == "acknowledged"), None)
    if replay:
        if release_ack is None or len(replay) != 1 or replay[0]["outcome"] != "acknowledged" or replay[0]["product_id"] != release_ack["product_id"]:
            raise OwnerStateError("ledger_conflict")


def _receipt(
    identity: dict[str, object],
    *,
    action: str,
    product_id: str | None,
    before_status: str,
    after_status: str,
    outcome: str,
    resolving: bool = False,
) -> dict[str, object]:
    replay_ack = action == "replay" and outcome == "acknowledged"
    effect = 0 if replay_ack else (1 if outcome in ("intent", "acknowledged") and not resolving else None)
    readback = 1 if outcome == "acknowledged" else 0
    duplicate_effect = 0 if replay_ack or (outcome in ("intent", "acknowledged") and not resolving) else None
    row: dict[str, object] = {
        "receipt_id": "",
        "effect_key": _effect_key(identity, action),
        "action": action,
        "account_id": identity["account_id"],
        "set_id": identity["set_id"],
        "revision": identity["revision"],
        "artifact_sha256": identity["artifact_sha256"],
        "product_id": product_id,
        "before_status": before_status,
        "after_status": after_status,
        "effect": effect,
        "readback": readback,
        "duplicate_effect": duplicate_effect,
        "outcome": outcome,
    }
    receipt_body = dict(row)
    receipt_body.pop("receipt_id")
    row["receipt_id"] = _sha256(_canonical_json(receipt_body))
    return row


def _initial_owner(identity: dict[str, object]) -> dict[str, object]:
    return {
        "version": 1,
        "identity": dict(identity),
        "state": "NEW",
        "product_id": None,
        "public_url": None,
    }


def _owner_result(
    owner: dict[str, object] | None,
    *,
    status: str,
    effect: int | None,
    readback: int,
    duplicate_effect: int | None,
    effect_key: str,
    reason: str,
) -> dict[str, object]:
    return {
        "status": status,
        "state": str(owner.get("state", "NEW")) if owner else "NEW",
        "effect": effect,
        "readback": readback,
        "duplicate_effect": duplicate_effect,
        "effect_key": effect_key,
        "product_id": owner.get("product_id") if owner else None,
        "public_url": owner.get("public_url") if owner else None,
        "reason": reason,
    }


def _identity_from_package(package: Path, policy: Path, account_id: str, revision: int, ffmpeg: str) -> dict[str, object]:
    if type(account_id) is not str or not account_id:
        raise OwnerStateError("account_id_invalid")
    if type(revision) is not int or isinstance(revision, bool) or revision <= 0:
        raise OwnerStateError("revision_invalid")
    package = Path(package)
    try:
        package_metadata = package.lstat()
    except OSError as exc:
        raise OwnerStateError("package_unavailable") from exc
    if stat.S_ISLNK(package_metadata.st_mode) or not stat.S_ISDIR(package_metadata.st_mode):
        raise OwnerStateError("package_not_directory")
    try:
        result = validate_package(package, Path(policy), ffmpeg=ffmpeg)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        code = str(exc) if str(exc) in {"policy_invalid", "policy_hash_mismatch"} else "package_validation_failed"
        raise OwnerStateError(code) from exc
    if result.get("status") != "ready":
        errors = result.get("errors")
        reason = str(errors[0]) if isinstance(errors, list) and errors else "invalid"
        raise OwnerStateError(f"package_invalid:{reason}")
    set_id = result.get("set_id")
    character_id = result.get("character_id")
    artifact_sha256 = result.get("artifact_sha256")
    package_sha256 = result.get("package_sha256")
    if type(set_id) is not str or not set_id or type(character_id) is not str or not character_id or type(artifact_sha256) is not str or not HEX64.fullmatch(artifact_sha256) or type(package_sha256) is not str or not HEX64.fullmatch(package_sha256):
        raise OwnerStateError("package_identity_invalid")
    return {
        "account_id": account_id,
        "set_id": set_id,
        "character_id": character_id,
        "revision": revision,
        "artifact_sha256": artifact_sha256,
        "package_sha256": package_sha256,
    }


def _verify_submission_artifact(package: Path, identity: dict[str, object]) -> None:
    path = Path(package) / "submission.zip"
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            raise OwnerStateError("artifact_not_regular")
        if _sha256(path.read_bytes()) != identity["artifact_sha256"]:
            raise OwnerStateError("artifact_changed")
    except OwnerStateError:
        raise
    except OSError as exc:
        raise OwnerStateError("artifact_unavailable") from exc


def _owner_identity_conflict(owner: dict[str, object], identity: dict[str, object]) -> str | None:
    stored = owner.get("identity")
    if not isinstance(stored, dict):
        return "owner_malformed"
    for key in ("account_id", "set_id", "character_id", "revision"):
        if stored.get(key) != identity.get(key):
            return f"identity_mismatch:{key}"
    if stored.get("artifact_sha256") != identity.get("artifact_sha256"):
        return "artifact_changed"
    if stored.get("package_sha256") != identity.get("package_sha256"):
        return "package_changed"
    return None


def _validate_observation(
    raw: object,
    identity: dict[str, object],
    *,
    expected_product: str | None = None,
    expected_url: str | None = None,
) -> ProviderObservation:
    if not isinstance(raw, dict) or set(raw) != {"account_id", "set_id", "revision", "artifact_sha256", "product_id", "status", "public_url"}:
        raise OwnerStateError("provider_observation_invalid")
    for key in ("account_id", "set_id", "artifact_sha256"):
        if type(raw.get(key)) is not str:
            raise OwnerStateError("provider_observation_invalid")
        if raw[key] != identity[key]:
            raise OwnerStateError(f"identity_mismatch:{key}")
    if type(raw.get("revision")) is not int or isinstance(raw["revision"], bool):
        raise OwnerStateError("provider_observation_invalid")
    if raw["revision"] != identity["revision"]:
        raise OwnerStateError("identity_mismatch:revision")
    if not HEX64.fullmatch(str(raw["artifact_sha256"])):
        raise OwnerStateError("provider_observation_invalid")
    status = raw.get("status")
    if type(status) is not str or status not in PROVIDER_STATUSES:
        raise OwnerStateError("provider_status_invalid")
    product_id = raw.get("product_id")
    if product_id is not None and (type(product_id) is not str or not product_id):
        raise OwnerStateError("provider_mismatch:product_id")
    public_url = raw.get("public_url")
    if public_url is not None and type(public_url) is not str:
        raise OwnerStateError("provider_url_invalid")
    if status == "absent":
        if product_id is not None or public_url is not None:
            raise OwnerStateError("provider_url_invalid" if public_url is not None else "provider_mismatch:product_id")
    else:
        if product_id is None:
            raise OwnerStateError("provider_mismatch:product_id")
        if expected_product is not None and product_id != expected_product:
            raise OwnerStateError("provider_mismatch:product_id")
        if status == "released":
            if public_url is None or not _public_url_matches(product_id, public_url):
                raise OwnerStateError("provider_url_invalid")
            if expected_url is not None and public_url != expected_url:
                raise OwnerStateError("provider_url_mismatch")
        elif public_url is not None:
            raise OwnerStateError("provider_url_invalid")
    return raw  # type: ignore[return-value]


def _observe(
    provider: object,
    identity: dict[str, object],
    *,
    expected_product: str | None = None,
    expected_url: str | None = None,
) -> ProviderObservation:
    try:
        observer = getattr(provider, "observe")
        raw = observer(identity)
    except Exception as exc:
        raise OwnerStateError("provider_observe_failed") from exc
    return _validate_observation(raw, identity, expected_product=expected_product, expected_url=expected_url)


def _rows_for_action(rows: list[dict[str, object]], identity: dict[str, object], action: str) -> dict[str, dict[str, object]]:
    key = _effect_key(identity, action)
    return {str(row["outcome"]): row for row in rows if row["effect_key"] == key}


def _restore_unknown_receipt(
    ledger_path: Path,
    rows: list[dict[str, object]],
    identity: dict[str, object],
    owner: dict[str, object],
) -> None:
    action = str(owner.get("pending_action"))
    prior = _rows_for_action(rows, identity, action)
    intent = prior.get("intent")
    if intent is None:
        raise OwnerStateError("ledger_conflict")
    if "unknown" in prior or "acknowledged" in prior:
        return
    unknown = _receipt(
        identity,
        action=action,
        product_id=intent["product_id"] if isinstance(intent.get("product_id"), str) else None,
        before_status=str(intent["before_status"]),
        after_status="unknown",
        outcome="unknown",
    )
    try:
        _append_receipt(ledger_path, unknown)
    except OwnerStateError as exc:
        raise OwnerStateError("reconcile_unknown") from exc
    rows.append(unknown)


def _acknowledge_unknown(
    owner_path: Path,
    ledger_path: Path,
    rows: list[dict[str, object]],
    identity: dict[str, object],
    owner: dict[str, object],
    *,
    action: str,
    observation: ProviderObservation,
) -> dict[str, object]:
    prior = _rows_for_action(rows, identity, action)
    if "unknown" not in prior:
        raise OwnerStateError("ledger_conflict")
    if "acknowledged" in prior:
        return owner
    if action == "submit":
        targets = {"submitted": "WAITING_REVIEW", "rejected": "REJECTED", "approved": "APPROVED"}
        target_state = targets.get(str(observation["status"]))
        if target_state is None:
            raise OwnerStateError("owner_state_conflict")
    elif observation["status"] == "released":
        target_state = "RELEASED"
    else:
        raise OwnerStateError("owner_state_conflict")
    next_owner = dict(owner)
    next_owner.pop("pending_action", None)
    next_owner["state"] = target_state
    next_owner["product_id"] = observation["product_id"]
    next_owner["public_url"] = observation["public_url"] if target_state == "RELEASED" else None
    if next_owner != owner:
        atomic_json(owner_path, next_owner)
    acknowledged = _receipt(
        identity,
        action=action,
        product_id=observation["product_id"],
        before_status="unknown",
        after_status=str(observation["status"]),
        outcome="acknowledged",
        resolving=True,
    )
    try:
        _append_receipt(ledger_path, acknowledged)
    except OwnerStateError as exc:
        raise ReceiptPendingError(action, _effect_key(identity, action), 0) from exc
    rows.append(acknowledged)
    return next_owner


def _acknowledge_intent(
    owner_path: Path,
    ledger_path: Path,
    rows: list[dict[str, object]],
    identity: dict[str, object],
    owner: dict[str, object],
    *,
    action: str,
    observation: ProviderObservation,
) -> dict[str, object]:
    prior = _rows_for_action(rows, identity, action)
    intent = prior.get("intent")
    if intent is None or "unknown" in prior or "acknowledged" in prior:
        raise OwnerStateError("ledger_conflict")
    if action == "submit":
        target_state = {"submitted": "WAITING_REVIEW", "rejected": "REJECTED", "approved": "APPROVED"}.get(str(observation["status"]))
        if target_state is None:
            raise OwnerStateError("owner_state_conflict")
    elif observation["status"] == "released":
        target_state = "RELEASED"
    else:
        raise OwnerStateError("owner_state_conflict")
    next_owner = dict(owner)
    next_owner["state"] = target_state
    next_owner["product_id"] = observation["product_id"]
    next_owner["public_url"] = observation["public_url"]
    if action == "submit":
        next_owner["public_url"] = None
    if next_owner != owner:
        atomic_json(owner_path, next_owner)
    acknowledged = _receipt(
        identity,
        action=action,
        product_id=observation["product_id"],
        before_status=str(intent["before_status"]),
        after_status=str(observation["status"]),
        outcome="acknowledged",
    )
    try:
        _append_receipt(ledger_path, acknowledged)
    except OwnerStateError as exc:
        raise ReceiptPendingError(action, _effect_key(identity, action), 0) from exc
    rows.append(acknowledged)
    return next_owner


def _close_with_replay(
    owner_path: Path,
    ledger_path: Path,
    rows: list[dict[str, object]],
    identity: dict[str, object],
    owner: dict[str, object],
    observation: ProviderObservation,
) -> tuple[dict[str, object], int]:
    prior = _rows_for_action(rows, identity, "replay")
    if "intent" in prior or "unknown" in prior:
        raise OwnerStateError("ledger_conflict")
    if "acknowledged" not in prior:
        replay = _receipt(
            identity,
            action="replay",
            product_id=observation["product_id"],
            before_status="released",
            after_status="released",
            outcome="acknowledged",
        )
        try:
            _append_receipt(ledger_path, replay)
        except OwnerStateError as exc:
            raise ReceiptPendingError("replay", _effect_key(identity, "replay"), 0) from exc
        rows.append(replay)
    closed = dict(owner)
    closed["state"] = "CLOSED"
    if owner.get("state") != "CLOSED":
        atomic_json(owner_path, closed)
    return closed, 1


def _persist_unknown(
    owner_path: Path,
    ledger_path: Path,
    owner: dict[str, object],
    identity: dict[str, object],
    *,
    action: str,
    product_id: str | None,
    before_status: str,
) -> tuple[dict[str, object], dict[str, object]]:
    unknown_owner = dict(owner)
    unknown_owner["state"] = "RECONCILE_UNKNOWN"
    unknown_owner["product_id"] = product_id
    unknown_owner["public_url"] = None
    unknown_owner["pending_action"] = action
    atomic_json(owner_path, unknown_owner)
    unknown = _receipt(
        identity,
        action=action,
        product_id=product_id,
        before_status=before_status,
        after_status="unknown",
        outcome="unknown",
    )
    _append_receipt(ledger_path, unknown)
    return unknown_owner, unknown


def _fenced_mutation(
    owner_path: Path,
    ledger_path: Path,
    owner: dict[str, object],
    rows: list[dict[str, object]],
    identity: dict[str, object],
    provider: object,
    package: Path,
    *,
    action: str,
    before: ProviderObservation,
    expected_status: str,
) -> tuple[dict[str, object], dict[str, object]]:
    prior = _rows_for_action(rows, identity, action)
    if "unknown" in prior:
        unknown_owner = dict(owner)
        unknown_owner["state"] = "RECONCILE_UNKNOWN"
        unknown_owner["pending_action"] = action
        if owner.get("state") != "RECONCILE_UNKNOWN" or owner.get("pending_action") != action:
            atomic_json(owner_path, unknown_owner)
        return unknown_owner, {"effect": None, "readback": 0, "duplicate_effect": None, "reason": "reconcile_unknown"}
    if "acknowledged" in prior:
        if before["status"] != expected_status:
            raise OwnerStateError("ledger_state_conflict")
        return owner, {"effect": 0, "readback": 1, "duplicate_effect": 0, "reason": "acknowledged"}
    if "intent" in prior:
        unknown_owner, _unknown = _persist_unknown(
            owner_path,
            ledger_path,
            owner,
            identity,
            action=action,
            product_id=owner.get("product_id") if isinstance(owner.get("product_id"), str) else None,
            before_status=str(before["status"]),
        )
        return unknown_owner, {"effect": None, "readback": 0, "duplicate_effect": None, "reason": "reconcile_unknown"}

    if action == "submit":
        _verify_submission_artifact(package, identity)

    intent = dict(identity)
    intent.update({"action": action, "effect_key": _effect_key(identity, action), "product_id": owner.get("product_id")})
    intent_receipt = _receipt(
        identity,
        action=action,
        product_id=owner.get("product_id") if isinstance(owner.get("product_id"), str) else None,
        before_status=str(before["status"]),
        after_status=str(expected_status),
        outcome="intent",
    )
    _append_receipt(ledger_path, intent_receipt)
    rows.append(intent_receipt)
    try:
        mutation = getattr(provider, action)
        returned = mutation(intent)
    except Exception:
        unknown_owner, _unknown = _persist_unknown(
            owner_path,
            ledger_path,
            owner,
            identity,
            action=action,
            product_id=owner.get("product_id") if isinstance(owner.get("product_id"), str) else None,
            before_status=str(before["status"]),
        )
        return unknown_owner, {"effect": None, "readback": 0, "duplicate_effect": None, "reason": "reconcile_unknown"}
    try:
        returned_observation = _validate_observation(
            returned,
            identity,
            expected_product=owner.get("product_id") if isinstance(owner.get("product_id"), str) else None,
        )
        if returned_observation["status"] != expected_status:
            raise OwnerStateError("provider_mutation_invalid")
    except OwnerStateError:
        unknown_owner, _unknown = _persist_unknown(
            owner_path,
            ledger_path,
            owner,
            identity,
            action=action,
            product_id=owner.get("product_id") if isinstance(owner.get("product_id"), str) else None,
            before_status=str(before["status"]),
        )
        return unknown_owner, {"effect": None, "readback": 0, "duplicate_effect": None, "reason": "reconcile_unknown"}
    try:
        post = _observe(
            provider,
            identity,
            expected_product=returned_observation.get("product_id") if expected_status == "released" else None,
        )
        if post["status"] != expected_status:
            raise OwnerStateError("provider_postcondition_failed")
    except OwnerStateError:
        unknown_owner, _unknown = _persist_unknown(
            owner_path,
            ledger_path,
            owner,
            identity,
            action=action,
            product_id=returned_observation.get("product_id"),
            before_status=str(before["status"]),
        )
        return unknown_owner, {"effect": None, "readback": 0, "duplicate_effect": None, "reason": "reconcile_unknown"}
    acknowledged = _receipt(
        identity,
        action=action,
        product_id=post["product_id"],
        before_status=str(before["status"]),
        after_status=str(post["status"]),
        outcome="acknowledged",
    )
    next_owner = dict(owner)
    next_owner.pop("pending_action", None)
    next_owner["state"] = "WAITING_REVIEW" if action == "submit" else "RELEASED"
    next_owner["product_id"] = post["product_id"]
    next_owner["public_url"] = post["public_url"]
    atomic_json(owner_path, next_owner)
    try:
        _append_receipt(ledger_path, acknowledged)
    except OwnerStateError as exc:
        raise ReceiptPendingError(action, _effect_key(identity, action), 1) from exc
    return next_owner, {"effect": 1, "readback": 1, "duplicate_effect": 0, "reason": action + "_acknowledged"}


def _next_action(owner: dict[str, object]) -> str:
    pending = owner.get("pending_action")
    if pending in ("submit", "release"):
        return str(pending)
    if owner.get("state") in ("TERMINAL_PENDING_REPLAY", "CLOSED"):
        return "replay"
    if owner.get("state") in ("NEW",) and owner.get("product_id") is None:
        return "submit"
    return "release"


def _validate_owner_ledger_state(
    owner: dict[str, object],
    rows: list[dict[str, object]],
    identity: dict[str, object],
    *,
    allow_release_ack_gap: bool = False,
) -> None:
    receipts = {action: _rows_for_action(rows, identity, action) for action in ("submit", "release", "replay")}
    acknowledged = {action: "acknowledged" in receipts[action] for action in ("submit", "release")}
    replay_ack = "acknowledged" in receipts["replay"]
    release_complete = "intent" in receipts["release"] and acknowledged["release"]
    submit_ack = receipts["submit"].get("acknowledged")
    chain_product = submit_ack.get("product_id") if submit_ack is not None else None
    state = str(owner["state"])
    if submit_ack is not None and owner.get("product_id") != chain_product:
        raise OwnerStateError("owner_state_conflict")
    if submit_ack is not None:
        after_status = submit_ack["after_status"]
        if after_status == "rejected" and state != "REJECTED":
            raise OwnerStateError("owner_state_conflict")
        if after_status == "approved" and state not in ("APPROVED", "RELEASED", "TERMINAL_PENDING_REPLAY", "CLOSED", "RECONCILE_UNKNOWN"):
            raise OwnerStateError("owner_state_conflict")
        if after_status == "submitted" and state not in ("WAITING_REVIEW", "REJECTED", "APPROVED", "RELEASED", "TERMINAL_PENDING_REPLAY", "CLOSED", "RECONCILE_UNKNOWN"):
            raise OwnerStateError("owner_state_conflict")
    if replay_ack and state not in ("CLOSED", "TERMINAL_PENDING_REPLAY"):
        raise OwnerStateError("owner_state_conflict")
    if state == "CLOSED" and not replay_ack:
        raise OwnerStateError("owner_state_conflict")
    if state == "NEW" and any(acknowledged.values()):
        raise OwnerStateError("owner_state_conflict")
    if state == "RECONCILE_UNKNOWN" and (
        acknowledged.get(str(owner.get("pending_action")), False)
    ):
        raise OwnerStateError("owner_state_conflict")
    if state in ("WAITING_REVIEW", "REJECTED", "APPROVED") and acknowledged["release"]:
        raise OwnerStateError("owner_state_conflict")
    if state in ("WAITING_REVIEW", "REJECTED", "APPROVED") and not acknowledged["submit"] and "intent" not in receipts["submit"]:
        raise OwnerStateError("owner_state_conflict")
    if state == "RELEASED" and not (
        release_complete or (allow_release_ack_gap and "intent" in receipts["release"])
    ):
        raise OwnerStateError("owner_state_conflict")
    if state in ("TERMINAL_PENDING_REPLAY", "CLOSED") and not release_complete:
        raise OwnerStateError("owner_state_conflict")
    if state in ("RELEASED", "TERMINAL_PENDING_REPLAY", "CLOSED") and (
        not isinstance(owner.get("product_id"), str) or not owner.get("product_id")
        or not isinstance(owner.get("public_url"), str) or not owner.get("public_url")
    ):
        raise OwnerStateError("owner_state_conflict")


def _state_summary(state_dir: Path) -> dict[str, object]:
    state_dir = Path(state_dir)
    if not _ensure_state_dir(state_dir, create=False):
        return {"status": "uninitialized", "effect": 0, "readback": 0}
    owner_path = state_dir / "owner.json"
    ledger_path = state_dir / "effects.jsonl"
    owner_metadata = _state_target(owner_path, "owner")
    ledger_metadata = _state_target(ledger_path, "ledger")
    if owner_metadata is None and ledger_metadata is None:
        return {"status": "uninitialized", "effect": 0, "readback": 0}
    if owner_metadata is None and ledger_metadata is not None:
        raise OwnerStateError("state_conflict")
    owner = _read_owner(owner_path)
    _validate_owner(owner)
    identity = owner["identity"]
    if not isinstance(identity, dict):
        raise OwnerStateError("owner_malformed")
    rows = _read_receipts(ledger_path, identity) if ledger_metadata is not None else []
    _validate_owner_ledger_state(owner, rows, identity)
    replay_ack = "acknowledged" in _rows_for_action(rows, identity, "replay")
    summary_owner = dict(owner)
    if summary_owner["state"] == "TERMINAL_PENDING_REPLAY" and replay_ack:
        summary_owner["state"] = "CLOSED"
    latest = rows[-1] if rows else None
    action = _next_action(owner)
    summary: dict[str, object] = {
        "status": "ok",
        "state": summary_owner["state"],
        "effect": latest["effect"] if latest is not None else 0,
        "readback": latest["readback"] if latest is not None else 0,
        "duplicate_effect": latest["duplicate_effect"] if latest is not None else 0,
        "effect_key": latest["effect_key"] if latest is not None else _effect_key(identity, action),
        "product_id": summary_owner["product_id"],
        "public_url": summary_owner["public_url"],
        "reason": latest["outcome"] if latest is not None else "uninitialized",
        "outcome": latest["outcome"] if latest is not None else None,
        "identity": dict(identity),
    }
    return summary


def _wake_owner_unlocked(
    state_dir: Path,
    package: Path,
    policy: Path,
    provider: object,
    account_id: str,
    revision: int,
    ffmpeg: str = "ffmpeg",
    identity: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run one bounded, restart-safe owner wake against an injected provider."""
    if identity is None:
        try:
            identity = _identity_from_package(Path(package), Path(policy), account_id, revision, ffmpeg)
        except OwnerStateError as exc:
            return _owner_result(None, status="error", effect=0, readback=0, duplicate_effect=0, effect_key="", reason=exc.code)
    state_dir = Path(state_dir)
    owner_path = state_dir / "owner.json"
    ledger_path = state_dir / "effects.jsonl"
    owner: dict[str, object] | None = None
    try:
        _ensure_state_dir(state_dir, create=True)
        owner_metadata = _state_target(owner_path, "owner")
        ledger_metadata = _state_target(ledger_path, "ledger")
        if owner_metadata is None:
            if ledger_metadata is not None:
                raise OwnerStateError("state_conflict")
            owner = _initial_owner(identity)
            atomic_json(owner_path, owner)
        else:
            owner = _read_owner(owner_path)
            _validate_owner(owner)
            conflict = _owner_identity_conflict(owner, identity)
            if conflict:
                return _owner_result(owner, status="error", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, _next_action(owner)), reason=conflict)
        rows = _read_receipts(ledger_path, identity)
        if owner is None:
            raise OwnerStateError("owner_malformed")
        if owner["state"] == "RECONCILE_UNKNOWN":
            try:
                _restore_unknown_receipt(ledger_path, rows, identity, owner)
            except OwnerStateError as exc:
                if exc.code == "reconcile_unknown":
                    return _owner_result(owner, status="unknown", effect=None, readback=0, duplicate_effect=None, effect_key=_effect_key(identity, str(owner["pending_action"])), reason="reconcile_unknown")
                raise
        _validate_owner_ledger_state(owner, rows, identity, allow_release_ack_gap=True)
        state = str(owner["state"])
        replay = _rows_for_action(rows, identity, "replay")
        if state == "TERMINAL_PENDING_REPLAY" and "acknowledged" in replay:
            closed = dict(owner)
            closed["state"] = "CLOSED"
            atomic_json(owner_path, closed)
            return _owner_result(closed, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "replay"), reason="closed")
        expected_product = owner.get("product_id") if isinstance(owner.get("product_id"), str) else None
        if state == "RECONCILE_UNKNOWN" and owner.get("pending_action") == "submit":
            expected_product = None
        expected_url = owner.get("public_url") if isinstance(owner.get("public_url"), str) else None
        observation = _observe(provider, identity, expected_product=expected_product, expected_url=expected_url)
        action = _next_action(owner)
        key = _effect_key(identity, action)

        unknown_submit = state == "RECONCILE_UNKNOWN" and owner.get("pending_action") == "submit"
        pending_submit = _rows_for_action(rows, identity, "submit")
        pending_release = _rows_for_action(rows, identity, "release")
        unknown_submit_receipt = pending_submit.get("unknown")
        if unknown_submit_receipt is not None and observation["status"] in ("submitted", "rejected", "approved") and isinstance(unknown_submit_receipt.get("product_id"), str) and observation["product_id"] != unknown_submit_receipt["product_id"]:
            raise OwnerStateError("ledger_conflict")
        if observation["status"] == "released" and "intent" not in pending_release:
            raise OwnerStateError("provider_state_conflict")
        if observation["status"] == "absent" and state != "NEW" and not unknown_submit:
            raise OwnerStateError("provider_absent_after_submit")

        if state in ("NEW", "WAITING_REVIEW", "REJECTED", "APPROVED") and "intent" in pending_submit and "acknowledged" not in pending_submit and "unknown" not in pending_submit:
            submit_statuses = {"submitted", "rejected", "approved"}
            allowed_statuses = submit_statuses
            if state == "REJECTED":
                allowed_statuses = {"rejected", "approved"}
            elif state == "APPROVED":
                allowed_statuses = {"approved"}
            if observation["status"] in allowed_statuses:
                recovered = _acknowledge_intent(
                    owner_path,
                    ledger_path,
                    rows,
                    identity,
                    owner,
                    action="submit",
                    observation=observation,
                )
                return _owner_result(recovered, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "submit"), reason="reconciled")
            if not (state == "NEW" and observation["status"] == "absent"):
                raise OwnerStateError("owner_state_conflict")

        if state in ("WAITING_REVIEW", "REJECTED", "APPROVED") and "unknown" in pending_submit and "acknowledged" not in pending_submit:
            submit_statuses = {"submitted", "rejected", "approved"}
            allowed_statuses = submit_statuses
            if state == "REJECTED":
                allowed_statuses = {"rejected"}
            elif state == "APPROVED":
                allowed_statuses = {"approved"}
            if observation["status"] in allowed_statuses:
                reconciled = _acknowledge_unknown(owner_path, ledger_path, rows, identity, owner, action="submit", observation=observation)
                return _owner_result(reconciled, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "submit"), reason="reconciled")
            raise OwnerStateError("owner_state_conflict")

        if state in ("APPROVED", "RELEASED") and "intent" in pending_release and "acknowledged" not in pending_release and "unknown" not in pending_release:
            if observation["status"] == "released":
                recovered = _acknowledge_intent(
                    owner_path,
                    ledger_path,
                    rows,
                    identity,
                    owner,
                    action="release",
                    observation=observation,
                )
                return _owner_result(recovered, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "release"), reason="reconciled")
            if not (state == "APPROVED" and observation["status"] == "approved"):
                raise OwnerStateError("owner_state_conflict")

        if state in ("RELEASED",) and "unknown" in pending_release and "acknowledged" not in pending_release:
            if observation["status"] != "released":
                raise OwnerStateError("owner_state_conflict")
            reconciled = _acknowledge_unknown(owner_path, ledger_path, rows, identity, owner, action="release", observation=observation)
            return _owner_result(reconciled, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "release"), reason="reconciled")

        if state == "CLOSED":
            if observation["status"] != "released":
                raise OwnerStateError("provider_state_conflict")
            replay = _rows_for_action(rows, identity, "replay")
            if "acknowledged" not in replay:
                closed, replay_readback = _close_with_replay(owner_path, ledger_path, rows, identity, owner, observation)
                return _owner_result(closed, status="ok", effect=0, readback=replay_readback, duplicate_effect=0, effect_key=_effect_key(identity, "replay"), reason="closed")
            return _owner_result(owner, status="ok", effect=0, readback=0, duplicate_effect=0, effect_key=key, reason="closed")

        if state == "TERMINAL_PENDING_REPLAY":
            if observation["status"] != "released":
                raise OwnerStateError("provider_state_conflict")
            closed, replay_readback = _close_with_replay(owner_path, ledger_path, rows, identity, owner, observation)
            return _owner_result(closed, status="ok", effect=0, readback=replay_readback, duplicate_effect=0, effect_key=_effect_key(identity, "replay"), reason="closed")

        if state == "RELEASED":
            if observation["status"] != "released":
                raise OwnerStateError("provider_state_conflict")
            pending = dict(owner)
            pending["state"] = "TERMINAL_PENDING_REPLAY"
            atomic_json(owner_path, pending)
            return _owner_result(pending, status="ok", effect=0, readback=0, duplicate_effect=0, effect_key=key, reason="awaiting_replay")

        if state == "RECONCILE_UNKNOWN":
            pending_action = str(owner.get("pending_action"))
            submit_statuses = {"submitted", "rejected", "approved"}
            if pending_action == "submit" and observation["status"] in submit_statuses:
                reconciled = _acknowledge_unknown(owner_path, ledger_path, rows, identity, owner, action=pending_action, observation=observation)
                return _owner_result(reconciled, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, "submit"), reason="reconciled")
            if pending_action == "release" and observation["status"] == "released":
                reconciled = _acknowledge_unknown(owner_path, ledger_path, rows, identity, owner, action=pending_action, observation=observation)
                return _owner_result(reconciled, status="ok", effect=0, readback=1, duplicate_effect=0, effect_key=_effect_key(identity, pending_action), reason="reconciled")
            return _owner_result(owner, status="unknown", effect=None, readback=0, duplicate_effect=None, effect_key=_effect_key(identity, pending_action), reason="reconcile_unknown")

        if state == "NEW":
            if observation["status"] != "absent":
                raise OwnerStateError("provider_state_conflict")
            mutation_owner, metrics = _fenced_mutation(
                owner_path,
                ledger_path,
                owner,
                rows,
                identity,
                provider,
                package,
                action="submit",
                before=observation,
                expected_status="submitted",
            )
            return _owner_result(mutation_owner, status="unknown" if metrics["effect"] is None else "ok", effect=metrics["effect"], readback=int(metrics["readback"]), duplicate_effect=metrics["duplicate_effect"], effect_key=_effect_key(identity, "submit"), reason=str(metrics["reason"]))

        if state == "WAITING_REVIEW":
            if observation["status"] in ("draft", "submitted"):
                return _owner_result(owner, status="ok", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, "release"), reason="waiting_review")
            if observation["status"] == "rejected":
                rejected = dict(owner)
                rejected["state"] = "REJECTED"
                atomic_json(owner_path, rejected)
                return _owner_result(rejected, status="ok", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, "release"), reason="rejected")
            if observation["status"] == "approved":
                approved = dict(owner)
                approved["state"] = "APPROVED"
                atomic_json(owner_path, approved)
                owner = approved
                state = "APPROVED"
            else:
                raise OwnerStateError("provider_state_conflict")

        if state == "REJECTED":
            if observation["status"] != "rejected":
                raise OwnerStateError("provider_state_conflict")
            return _owner_result(owner, status="ok", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, "release"), reason="rejected")

        if state == "APPROVED":
            if observation["status"] != "approved":
                raise OwnerStateError("provider_state_conflict")
            mutation_owner, metrics = _fenced_mutation(
                owner_path,
                ledger_path,
                owner,
                rows,
                identity,
                provider,
                package,
                action="release",
                before=observation,
                expected_status="released",
            )
            return _owner_result(mutation_owner, status="unknown" if metrics["effect"] is None else "ok", effect=metrics["effect"], readback=int(metrics["readback"]), duplicate_effect=metrics["duplicate_effect"], effect_key=_effect_key(identity, "release"), reason=str(metrics["reason"]))

        raise OwnerStateError("owner_state_invalid")
    except ReceiptPendingError as exc:
        actual = _read_owner(owner_path) if owner is not None else None
        return _owner_result(actual, status="ok", effect=exc.effect, readback=1, duplicate_effect=0, effect_key=exc.effect_key, reason="receipt_pending")
    except OwnerStateError as exc:
        if owner is None:
            return _owner_result(None, status="error", effect=0, readback=0, duplicate_effect=0, effect_key="", reason=exc.code)
        if exc.code == "reconcile_unknown":
            return _owner_result(owner, status="unknown", effect=None, readback=0, duplicate_effect=None, effect_key=_effect_key(identity, str(owner.get("pending_action", _next_action(owner)))), reason="reconcile_unknown")
        return _owner_result(owner, status="error", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, _next_action(owner)), reason=exc.code)
    except (OSError, TypeError, ValueError) as exc:
        reason = str(exc) if str(exc) else "state_error"
        return _owner_result(owner, status="error", effect=0, readback=0, duplicate_effect=0, effect_key=_effect_key(identity, _next_action(owner)) if owner else "", reason=reason)


def _canonical_lock_root() -> Path:
    return Path.home() / ".local" / "state" / "life-manager" / "line-sticker" / "locks"


def _canonical_lock_identity(identity: dict[str, object]) -> dict[str, object]:
    return {key: identity[key] for key in ("account_id", "set_id", "revision")}


def _canonical_lock_path(identity: dict[str, object]) -> Path:
    return _canonical_lock_root() / (_sha256(_canonical_json(_canonical_lock_identity(identity))) + ".lock")


def _ensure_canonical_lock_root(root: Path) -> None:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = root.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise OwnerStateError("lock_root_invalid")
    os.chmod(root, 0o700)


@contextmanager
def _state_lock(state_dir: Path, identity: dict[str, object]):
    root = _canonical_lock_root()
    descriptor: int | None = None
    try:
        _ensure_canonical_lock_root(root)
        path = _canonical_lock_path(identity)
        try:
            existing = path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)):
            raise OwnerStateError("lock_symlink" if stat.S_ISLNK(existing.st_mode) else "lock_not_regular")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        created = False
        try:
            descriptor = os.open(str(path), flags, 0o600)
            created = True
        except FileExistsError:
            flags = os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(str(path), flags)
        opened = os.fstat(descriptor)
        listed = path.lstat()
        if stat.S_ISLNK(listed.st_mode) or not stat.S_ISREG(opened.st_mode):
            raise OwnerStateError("lock_symlink" if stat.S_ISLNK(listed.st_mode) else "lock_not_regular")
        if (opened.st_dev, opened.st_ino) != (listed.st_dev, listed.st_ino):
            raise OwnerStateError("lock_replaced")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state_binding = str(Path(state_dir).resolve())
        if created:
            os.fchmod(descriptor, 0o600)
            lock_metadata = {
                "identity": _canonical_lock_identity(identity),
                "state_dir": state_binding,
                "st_dev": opened.st_dev,
                "st_ino": opened.st_ino,
            }
            os.write(descriptor, _canonical_json(lock_metadata) + b"\n")
            os.fsync(descriptor)
            _fsync_directory(root)
        else:
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw = os.read(descriptor, 4096)
            try:
                lock_metadata = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OwnerStateError("lock_malformed") from exc
            if not isinstance(lock_metadata, dict) or lock_metadata != {
                "identity": _canonical_lock_identity(identity),
                "state_dir": state_binding,
                "st_dev": opened.st_dev,
                "st_ino": opened.st_ino,
            }:
                raise OwnerStateError("lock_state_dir_conflict")
        yield
    except OwnerStateError:
        raise
    except OSError as exc:
        raise OwnerStateError("lock_unavailable") from exc
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(descriptor)
            except OSError:
                pass


def wake_owner(
    state_dir: Path,
    package: Path,
    policy: Path,
    provider: object,
    account_id: str,
    revision: int,
    ffmpeg: str = "ffmpeg",
) -> dict[str, object]:
    state_dir = Path(state_dir)
    try:
        identity = _identity_from_package(Path(package), Path(policy), account_id, revision, ffmpeg)
        _ensure_state_dir(state_dir, create=True)
        with _state_lock(state_dir, identity):
            return _wake_owner_unlocked(state_dir, package, policy, provider, account_id, revision, ffmpeg, identity)
    except OwnerStateError as exc:
        return _owner_result(None, status="error", effect=0, readback=0, duplicate_effect=0, effect_key="", reason=exc.code)


def _group_duplicate_hashes(hashes: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, digest in hashes.items():
        grouped.setdefault(digest, []).append(name)
    for names in grouped.values():
        names.sort()
    return grouped


def _configuration_result(code: str) -> dict[str, object]:
    return {"status": "error", "effect": 0, "readback": 0, "package_sha256": "", "files": [], "errors": [code]}


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("configuration_error")


def main(argv: list[str] | None = None) -> int:
    parser = _JsonArgumentParser(prog="line_sticker.py", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_JsonArgumentParser)
    validate = subparsers.add_parser("validate", add_help=False)
    validate.add_argument("--package", required=True, type=Path)
    validate.add_argument("--policy", required=True, type=Path)
    validate.add_argument("--ffmpeg", default="ffmpeg")
    state = subparsers.add_parser("state", add_help=False)
    state.add_argument("--state-dir", required=True, type=Path)
    try:
        args = parser.parse_args(argv)
    except (SystemExit, TypeError, ValueError):
        result = _configuration_result("configuration_error")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    if args.command == "state":
        try:
            result = _state_summary(args.state_dir)
        except OwnerStateError as exc:
            print(json.dumps({"status": "error", "reason": exc.code}, sort_keys=True, separators=(",", ":")))
            return 2
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.command != "validate":
        print(json.dumps(_configuration_result("configuration_error"), sort_keys=True, separators=(",", ":")))
        return 2
    if not args.package.is_dir() or not args.policy.is_file():
        print(json.dumps(_configuration_result("configuration_error"), sort_keys=True, separators=(",", ":")))
        return 2
    if shutil.which(str(args.ffmpeg)) is None:
        print(json.dumps(_configuration_result("configuration_error"), sort_keys=True, separators=(",", ":")))
        return 2
    try:
        result = validate_package(args.package, args.policy, ffmpeg=args.ffmpeg)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        code = str(exc) if str(exc) in {"policy_invalid", "policy_hash_mismatch"} else "configuration_error"
        result = _configuration_result(code)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
