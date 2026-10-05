"""Bounded media pipeline for creating a validated LINE animated-sticker set.

The model owns creative planning and visual selection.  This module only owns
machine contracts, hashes, process fences, media conversion, and bookkeeping.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

try:
    import line_sticker
except ImportError:  # pragma: no cover - only used when imported as a package
    from . import line_sticker  # type: ignore


MAX_COMMAND_OUTPUT = 1_048_576
COMMAND_TIMEOUT_SECONDS = 600.0
PNG_NAMES = tuple(sorted(["main.png", "tab.png"] + [f"{number:02d}.png" for number in range(1, 25)]))
MOTION_COUNT = 60
BATCH_COUNT = 6
MOTIONS_PER_BATCH = 10
MIN_DURATION_MS = 500
MAX_DURATION_MS = 2_000
MAX_BATCH_DURATION_MS = 10_000
HEX64 = set("0123456789abcdef")
SAFE_MOTION_IDS = frozenset(f"motion-{value:02d}" for value in range(1, MOTION_COUNT + 1))
GENERATION_KEYS = frozenset({
    "rights_evidence", "character_sha256", "plan_sha256", "selection_sha256", "prompt_sha256",
    "model", "provider", "reserved_cost_usd", "actual_cost_usd", "batches", "candidate_bindings", "generation_sha256",
})


class MediaError(ValueError):
    """Stable, non-sensitive media pipeline failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise MediaError("file_unreadable") from exc
    return digest.hexdigest()


def _is_hash(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value.lower()) <= HEX64


def _nonempty_text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _parse_argv(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise MediaError("configuration_error") from exc
    if type(value) is not list or not value or any(type(item) is not str or not item for item in value):
        raise MediaError("configuration_error")
    return list(value)


def _ensure_directory(path: Path) -> Path:
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        metadata = path.stat()
    except OSError as exc:
        raise MediaError("work_dir_invalid") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise MediaError("work_dir_invalid")
    return path


def _atomic_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            descriptor = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    except OSError as exc:
        raise MediaError("disk_full" if getattr(exc, "errno", None) == 28 else "write_failed") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(Path(path), _canonical(value) + b"\n")


def _load_json(path: Path, *, expected_object: bool = True) -> object:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MediaError("json_invalid") from exc
    if expected_object and type(value) is not dict:
        raise MediaError("json_invalid")
    return value


def _strict_json_object(raw: bytes) -> dict[str, object]:
    if len(raw) > MAX_COMMAND_OUTPUT:
        raise MediaError("command_output_overflow")
    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder()
        value, end = decoder.raw_decode(text)
        if text[end:].strip() or type(value) is not dict:
            raise MediaError("command_json_invalid")
        return value
    except UnicodeDecodeError as exc:
        raise MediaError("command_json_invalid") from exc
    except json.JSONDecodeError as exc:
        raise MediaError("command_json_invalid") from exc


def _run_external(argv: list[str], *, cwd: Path, stdin: bytes | None = None) -> tuple[bytes, bytes]:
    """Run one literal argv; stream-limit output and kill its whole process group."""
    if not argv or any(type(item) is not str or not item for item in argv):
        raise MediaError("configuration_error")
    cwd = _ensure_directory(cwd)
    try:
        process = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, start_new_session=True)
    except OSError as exc:
        raise MediaError("command_failed") from exc
    output, error_output = bytearray(), bytearray()
    overflow = False
    import threading
    lock = threading.Lock()

    def drain(stream: object, target: bytearray) -> None:
        nonlocal overflow
        reader = stream  # keep the pipe lifetime local to this reader
        while True:
            chunk = reader.read(65536)  # type: ignore[attr-defined]
            if not chunk:
                return
            with lock:
                if len(target) + len(chunk) > MAX_COMMAND_OUTPUT:
                    overflow = True
                    return
                target.extend(chunk)

    readers = [threading.Thread(target=drain, args=(process.stdout, output), daemon=True), threading.Thread(target=drain, args=(process.stderr, error_output), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            process.stdin.close()
        deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
        while process.poll() is None and not overflow and time.monotonic() < deadline:
            time.sleep(0.01)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        raise MediaError("command_failed") from exc
    finally:
        for reader in readers:
            reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if overflow:
        raise MediaError("command_output_overflow")
    if time.monotonic() >= deadline and process.returncode is not None and process.returncode < 0:
        raise MediaError("command_timeout")
    if process.returncode != 0:
        raise MediaError("command_failed")
    return bytes(output), bytes(error_output)


def _run_json_command(argv: list[str], request: dict[str, object], *, cwd: Path) -> dict[str, object]:
    output, _error_output = _run_external(argv, cwd=cwd, stdin=_canonical(request) + b"\n")
    return _strict_json_object(output)


def _public_result(
    status: str,
    reason: str,
    *,
    effect: int = 0,
    readback: int = 0,
    output: str = "",
    **hashes: str,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": status,
        "effect": int(effect),
        "readback": int(readback),
        "reason": reason,
        "hashes": {key: value for key, value in sorted(hashes.items()) if value},
        "output": output,
    }
    result.update({key: value for key, value in hashes.items() if value})
    return result


def _validate_plan_model(
    response: dict[str, object], *, set_id: str, character_id: str
) -> dict[str, object]:
    expected = {"version", "mode", "set_id", "character_id", "character_anchors", "motions"}
    if set(response) != expected:
        raise MediaError("model_schema_invalid")
    if type(response["version"]) is not int or response["version"] != 1 or response["mode"] != "plan":
        raise MediaError("model_schema_invalid")
    if response["set_id"] != set_id or response["character_id"] != character_id:
        raise MediaError("model_identity_mismatch")
    anchors = response["character_anchors"]
    if type(anchors) is not list or not anchors or any(not _nonempty_text(anchor) for anchor in anchors):
        raise MediaError("model_schema_invalid")
    motions = response["motions"]
    if type(motions) is not list or len(motions) != MOTION_COUNT:
        raise MediaError("motion_count_invalid")
    motion_keys = {"motion_id", "batch", "position", "intent", "action", "provider_prompt", "duration_ms"}
    ids: set[str] = set()
    pairs: set[tuple[int, int]] = set()
    normalized: list[dict[str, object]] = []
    for motion in motions:
        if type(motion) is not dict or set(motion) != motion_keys:
            raise MediaError("motion_schema_invalid")
        if not _nonempty_text(motion["motion_id"]) or motion["motion_id"] not in SAFE_MOTION_IDS or motion["motion_id"] in ids:
            raise MediaError("motion_id_invalid")
        batch, position, duration = motion["batch"], motion["position"], motion["duration_ms"]
        if type(batch) is not int or type(position) is not int or type(duration) is not int:
            raise MediaError("motion_arithmetic_invalid")
        if not 1 <= batch <= BATCH_COUNT or not 1 <= position <= MOTIONS_PER_BATCH:
            raise MediaError("motion_arithmetic_invalid")
        if (batch, position) in pairs:
            raise MediaError("motion_position_duplicate")
        if not MIN_DURATION_MS <= duration <= MAX_DURATION_MS:
            raise MediaError("duration_invalid")
        for field in ("intent", "action", "provider_prompt"):
            if not _nonempty_text(motion[field]):
                raise MediaError("motion_schema_invalid")
        ids.add(motion["motion_id"])
        pairs.add((batch, position))
        normalized.append(dict(motion))
    if pairs != {(batch, position) for batch in range(1, BATCH_COUNT + 1) for position in range(1, MOTIONS_PER_BATCH + 1)}:
        raise MediaError("motion_positions_invalid")
    if any(sum(int(motion["duration_ms"]) for motion in normalized if motion["batch"] == batch) > MAX_BATCH_DURATION_MS for batch in range(1, BATCH_COUNT + 1)):
        raise MediaError("duration_invalid")
    return {
        "version": 1,
        "mode": "plan",
        "set_id": set_id,
        "character_id": character_id,
        "character_anchors": list(anchors),
        "motions": normalized,
    }


def _load_plan(path: Path) -> dict[str, object]:
    value = _load_json(Path(path))
    if type(value) is not dict:
        raise MediaError("plan_invalid")
    required = {
        "version",
        "mode",
        "set_id",
        "character_id",
        "character_anchors",
        "motions",
        "character_path",
        "character_sha256",
        "prompt_sha256",
        "plan_sha256",
    }
    if set(value) != required:
        raise MediaError("plan_invalid")
    if not _is_hash(value["character_sha256"]) or not _is_hash(value["prompt_sha256"]) or not _is_hash(value["plan_sha256"]):
        raise MediaError("plan_invalid")
    normalized = _validate_plan_model(
        {key: value[key] for key in ("version", "mode", "set_id", "character_id", "character_anchors", "motions")},
        set_id=str(value["set_id"]),
        character_id=str(value["character_id"]),
    )
    payload = dict(normalized)
    for key in ("character_path", "character_sha256", "prompt_sha256"):
        payload[key] = value[key]
    if _sha256_bytes(_canonical(payload)) != value["plan_sha256"]:
        raise MediaError("plan_hash_mismatch")
    return dict(value)


def plan(
    character: Path,
    model_command: str | list[str],
    work_dir: Path,
    set_id: str,
    character_id: str,
) -> dict[str, object]:
    """Ask the model for exactly sixty machine-valid motion records."""
    work_dir = _ensure_directory(Path(work_dir))
    character = Path(character)
    if not _nonempty_text(set_id) or not _nonempty_text(character_id):
        raise MediaError("configuration_error")
    try:
        metadata = character.stat()
    except OSError as exc:
        raise MediaError("character_invalid") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise MediaError("character_invalid")
    character_hash = _sha256_file(character)
    prompt_path = Path(__file__).with_name("creative-prompt.md")
    try:
        prompt = prompt_path.read_bytes()
    except OSError as exc:
        raise MediaError("prompt_missing") from exc
    prompt_hash = _sha256_bytes(prompt)
    argv = _parse_argv(model_command)
    input_hash = _sha256_bytes(
        _canonical(
            {
                "operation": "plan",
                "set_id": set_id,
                "character_id": character_id,
                "character_sha256": character_hash,
                "prompt_sha256": prompt_hash,
                "model_command": argv,
            }
        )
    )
    plan_path, receipt_path = work_dir / "plan.json", work_dir / "plan-receipt.json"
    if plan_path.exists() or receipt_path.exists():
        if not plan_path.is_file():
            raise MediaError("plan_state_incomplete")
        existing = _load_plan(plan_path)
        if existing["character_sha256"] != character_hash or existing["set_id"] != set_id or existing["character_id"] != character_id:
            raise MediaError("plan_conflict")
        if receipt_path.exists():
            receipt = _load_json(receipt_path)
            if type(receipt) is not dict or receipt.get("input_sha256") != input_hash:
                raise MediaError("plan_conflict")
        else:
            repaired = {"version": 1, "operation": "plan", "status": "ready", "effect": 0, "readback": 1, "reason": "repaired", "input_sha256": input_hash, "character_sha256": character_hash, "prompt_sha256": prompt_hash, "plan_sha256": existing["plan_sha256"], "output": plan_path.name}
            repaired["receipt_sha256"] = _sha256_bytes(_canonical(repaired)); _atomic_json(receipt_path, repaired)
        return _public_result(
            "ready",
            "replayed",
            readback=1,
            output=str(plan_path),
            input_sha256=input_hash,
            character_sha256=character_hash,
            prompt_sha256=prompt_hash,
            plan_sha256=str(existing["plan_sha256"]),
        )
    request = {
        "version": 1,
        "mode": "plan",
        "set_id": set_id,
        "character_id": character_id,
        "character_path": str(character.resolve()),
        "character_sha256": character_hash,
        "prompt_sha256": prompt_hash,
        "creative_prompt": prompt.decode("utf-8"),
    }
    response = _run_json_command(argv, request, cwd=work_dir)
    model_plan = _validate_plan_model(response, set_id=set_id, character_id=character_id)
    payload = dict(model_plan)
    payload.update(
        {
            "character_path": str(character.resolve()),
            "character_sha256": character_hash,
            "prompt_sha256": prompt_hash,
        }
    )
    plan_hash = _sha256_bytes(_canonical(payload))
    payload["plan_sha256"] = plan_hash
    _atomic_json(plan_path, payload)
    receipt = {
        "version": 1,
        "operation": "plan",
        "status": "ready",
        "effect": 1,
        "readback": 1,
        "reason": "planned",
        "input_sha256": input_hash,
        "character_sha256": character_hash,
        "prompt_sha256": prompt_hash,
        "plan_sha256": plan_hash,
        "output": plan_path.name,
    }
    receipt["receipt_sha256"] = _sha256_bytes(_canonical(receipt))
    _atomic_json(receipt_path, receipt)
    return _public_result(
        "ready",
        "planned",
        effect=1,
        readback=1,
        output=str(plan_path),
        input_sha256=input_hash,
        character_sha256=character_hash,
        prompt_sha256=prompt_hash,
        plan_sha256=plan_hash,
    )


def _decimal_cost(value: object) -> Decimal:
    if type(value) is not str:
        raise MediaError("cost_invalid")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MediaError("cost_invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise MediaError("cost_invalid")
    return parsed


def _probe_duration(ffprobe: str, source: Path, *, cwd: Path) -> Decimal:
    output, _error = _run_external(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)],
        cwd=cwd,
    )
    try:
        value = json.loads(output.decode("utf-8"))
        duration = value["format"]["duration"]
        parsed = Decimal(str(duration))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, InvalidOperation) as exc:
        raise MediaError("probe_invalid") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise MediaError("probe_invalid")
    return parsed * Decimal(1000)


def _reservation_key(*, set_id: str, plan_hash: str, batch: int, provider: str, model: str, request_id: str, quote_token: str, character_hash: str) -> str:
    return _sha256_bytes(
        _canonical(
            {
                "set_id": set_id,
                "plan_sha256": plan_hash,
                "batch": batch,
                "provider": provider, "model": model, "request_id": request_id, "quote_token": quote_token,
                "character_sha256": character_hash,
            }
        )
    )


def _quote(response: dict[str, object], batch: int) -> dict[str, object]:
    expected = {"request_id", "quote_token", "batch", "provider", "model", "quoted_cost_usd", "expires_at", "regenerable"}
    if set(response) != expected or type(response.get("batch")) is not int or response["batch"] != batch or not all(_nonempty_text(response.get(key)) for key in ("request_id", "quote_token", "provider", "model", "expires_at")) or type(response.get("regenerable")) is not bool:
        raise MediaError("provider_schema_invalid")
    try:
        expiry = datetime.fromisoformat(str(response["expires_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MediaError("quote_expiry_invalid") from exc
    if expiry.tzinfo is None:
        raise MediaError("quote_expiry_invalid")
    if expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise MediaError("quote_expired")
    return {**response, "quoted_cost_usd": format(_decimal_cost(response["quoted_cost_usd"]), "f")}


def _quote_expired(quote: dict[str, object]) -> bool:
    try:
        return datetime.fromisoformat(str(quote["expires_at"]).replace("Z", "+00:00")).astimezone(timezone.utc) <= datetime.now(timezone.utc)
    except (KeyError, ValueError):
        raise MediaError("quote_expiry_invalid")


def _generation(response: dict[str, object], reservation: dict[str, object], motions: list[dict[str, object]]) -> dict[str, object]:
    expected = {"request_id", "quote_token", "batch", "provider", "model", "acknowledged", "video_path", "video_sha256", "segments"}
    expected |= {"regenerable", "actual_cost_usd"}
    if set(response) != expected or any(response.get(key) != reservation.get(key) for key in ("request_id", "quote_token", "batch", "provider", "model")):
        raise MediaError("provider_identity_mismatch")
    acknowledged = response.get("acknowledged")
    if acknowledged is not True:
        if acknowledged not in (False, "unknown", None):
            raise MediaError("acknowledgement_invalid")
        return {**response, "acknowledged": "unknown"}
    if not _nonempty_text(response.get("video_path")) or not _is_hash(response.get("video_sha256")):
        raise MediaError("provider_schema_invalid")
    if type(response.get("regenerable")) is not bool or _decimal_cost(response["actual_cost_usd"]) > _decimal_cost(reservation["quoted_cost_usd"]):
        raise MediaError("provider_schema_invalid")
    segments = response.get("segments")
    if type(segments) is not list or len(segments) != MOTIONS_PER_BATCH:
        raise MediaError("segments_invalid")
    motion_ids = [motion["motion_id"] for motion in motions]
    expected_ids = set(motion_ids)
    seen: set[str] = set()
    previous_end = -1
    normalized_segments: list[dict[str, object]] = []
    for segment in segments:
        if type(segment) is not dict or set(segment) != {"motion_id", "start_ms", "end_ms"}:
            raise MediaError("segments_invalid")
        motion_id, start, end = segment["motion_id"], segment["start_ms"], segment["end_ms"]
        if not _nonempty_text(motion_id) or motion_id not in expected_ids or motion_id in seen:
            raise MediaError("segments_invalid")
        if type(start) is not int or type(end) is not int or start < 0 or end <= start or start < previous_end:
            raise MediaError("segments_invalid")
        seen.add(motion_id)
        previous_end = end
        normalized_segments.append({"motion_id": motion_id, "start_ms": start, "end_ms": end})
    if seen != expected_ids:
        raise MediaError("segments_invalid")
    result = dict(response)
    result["segments"] = normalized_segments
    result["actual_cost_usd"] = format(_decimal_cost(response["actual_cost_usd"]), "f")
    result["video_sha256"] = str(response["video_sha256"]).lower()
    return result


def _candidate_path(record: dict[str, object], *, candidates_root: Path) -> Path:
    value = record.get("path")
    if not _nonempty_text(value):
        raise MediaError("candidate_schema_invalid")
    path = Path(str(value))
    if not path.is_absolute():
        path = candidates_root / path
    return path


def _extract_first_frame(source: Path, destination: Path) -> None:
    """Copy the first APNG frame into a static PNG without another provider call."""
    try:
        chunks = line_sticker._read_chunks(source.read_bytes())  # type: ignore[attr-defined]
    except (OSError, ValueError, AttributeError) as exc:
        raise MediaError("candidate_png_invalid") from exc
    output: list[bytes] = [line_sticker.PNG_SIGNATURE]
    saw_idat = False
    for kind, payload, _digest in chunks:
        if kind in {"acTL", "fcTL", "fdAT"}:
            continue
        if kind == "IEND":
            output.append(_png_chunk("IEND", b""))
            break
        if kind == "IDAT":
            saw_idat = True
        if not saw_idat and kind not in {"IHDR", "PLTE", "tRNS", "gAMA", "cHRM", "sRGB", "pHYs", "iCCP", "sBIT", "bKGD"}:
            continue
        output.append(_png_chunk(kind, payload))
    if not saw_idat or len(output) < 3 or output[-1] != _png_chunk("IEND", b""):
        raise MediaError("candidate_png_invalid")
    _atomic_bytes(destination, b"".join(output))


def _png_chunk(kind: str, payload: bytes) -> bytes:
    import struct
    import zlib

    raw = kind.encode("ascii") + payload
    return struct.pack(">I", len(payload)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)


def _encode_full_frame_apng(raw: bytes, *, width: int, height: int, frames: int, duration_ms: Decimal) -> bytes:
    """Encode decoded RGBA frames with full-size controls for strict validators."""
    import struct
    import zlib

    frame_size = width * height * 4
    if frames < 1 or len(raw) != frame_size * frames:
        raise MediaError("candidate_png_invalid")
    total_ms = int(duration_ms.to_integral_value())
    if total_ms <= 0:
        raise MediaError("candidate_png_invalid")
    numerator, denominator = total_ms, frames * 1000
    divisor = math.gcd(numerator, denominator)
    numerator //= divisor; denominator //= divisor
    if numerator > 65535 or denominator > 65535:
        raise MediaError("candidate_png_invalid")
    output = [line_sticker.PNG_SIGNATURE]
    output.append(_png_chunk("IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    output.append(_png_chunk("acTL", struct.pack(">II", frames, 1)))
    for index in range(frames):
        control_sequence = 0 if index == 0 else index * 2 - 1
        control = struct.pack(">IIIIIHHBB", control_sequence, width, height, 0, 0, numerator, denominator, 0, 0)
        output.append(_png_chunk("fcTL", control))
        frame = raw[index * frame_size : (index + 1) * frame_size]
        scanlines = b"".join(b"\x00" + frame[row * width * 4 : (row + 1) * width * 4] for row in range(height))
        compressed = zlib.compress(scanlines)
        if index == 0:
            output.append(_png_chunk("IDAT", compressed))
        else:
            output.append(_png_chunk("fdAT", struct.pack(">I", index * 2) + compressed))
    output.append(_png_chunk("IEND", b""))
    return b"".join(output)


def _repair_alpha_holes(raw: bytes, width: int, height: int) -> bytes:
    """Fill enclosed zero-alpha components from deterministic opaque seeds."""
    frame_size = width * height * 4
    if width < 1 or height < 1 or len(raw) != frame_size:
        raise MediaError("candidate_png_invalid")
    transparent = bytearray(raw[index * 4 + 3] == 0 for index in range(width * height))
    outside = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if transparent[index] and not outside[index]:
            outside[index] = 1
            queue.append((x, y))

    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)
    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                enqueue(nx, ny)

    def is_green(rgb: tuple[int, int, int]) -> bool:
        return rgb[1] >= 128 and rgb[1] - max(rgb[0], rgb[2]) >= 50

    owners: list[tuple[int, int, int, tuple[int, int, int]] | None] = [None] * (width * height)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if raw[index * 4 + 3] == 255:
                rgb = tuple(raw[index * 4 : index * 4 + 3])
                if not is_green(rgb):
                    owners[index] = (0, y, x, rgb)
                    queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        current = owners[y * width + x]
        if current is None:
            continue
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            index = ny * width + nx
            if (transparent[index] and outside[index]) or owners[index] is not None:
                continue
            owners[index] = (current[0] + 1, current[1], current[2], current[3])
            queue.append((nx, ny))

    visited = bytearray(width * height)
    repaired = bytearray(raw)
    for y in range(height):
        for x in range(width):
            start = y * width + x
            if not transparent[start] or outside[start] or visited[start]:
                continue
            component: list[tuple[int, int]] = []
            queue.append((x, y))
            visited[start] = 1
            while queue:
                cx, cy = queue.popleft()
                component.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        index = ny * width + nx
                        if transparent[index] and not outside[index] and not visited[index]:
                            visited[index] = 1
                            queue.append((nx, ny))
            if any(owners[cy * width + cx] is None for cx, cy in component):
                raise MediaError("alpha_hole_unrepairable")
            for cx, cy in component:
                index = (cy * width + cx) * 4
                repaired[index : index + 3] = bytes(owners[cy * width + cx][3])  # type: ignore[index]
                repaired[index + 3] = 255
    return bytes(repaired)


def _normalize_candidate_apng(
    path: Path,
    *,
    ffmpeg: str,
    duration_ms: Decimal,
    cwd: Path,
    width: int = 320,
    height: int = 270,
    fps: int = 10,
) -> None:
    """Expand a delta-optimized APNG into full-size frames when needed."""
    frame_count = max(5, min(20, int(math.ceil(float(duration_ms) * fps / 1000.0))))
    with tempfile.TemporaryDirectory(prefix="line-sticker-raw-", dir=str(cwd)) as directory:
        raw_path = Path(directory) / "frames.rgba"
        _run_external(
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
                str(raw_path),
            ],
            cwd=cwd,
        )
        expected = width * height * 4 * frame_count
        try:
            raw = raw_path.read_bytes()
        except OSError as exc:
            raise MediaError("candidate_png_invalid") from exc
        if len(raw) != expected:
            raise MediaError("candidate_png_invalid")
        frame_size = width * height * 4
        repaired = b"".join(
            _repair_alpha_holes(raw[offset : offset + frame_size], width, height)
            for offset in range(0, len(raw), frame_size)
        )
        _atomic_bytes(path, _encode_full_frame_apng(repaired, width=width, height=height, frames=frame_count, duration_ms=duration_ms))


def _validate_candidate(path: Path, *, ffmpeg: str) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    try:
        parsed = line_sticker.parse_png(path)
    except Exception as exc:  # parse errors are converted to stable validator codes
        code = getattr(exc, "code", "candidate_png_invalid")
        errors.append(str(code))
        return None, errors
    if not bool(parsed.get("animated")):
        errors.append("animation_required")
    try:
        frames = int(parsed["frames"])
        duration = float(parsed["duration_ms"])
        width, height = int(parsed["width"]), int(parsed["height"])
        color_type = int(parsed["color_type"])
    except (KeyError, TypeError, ValueError):
        errors.append("candidate_png_invalid")
    else:
        if not 5 <= frames <= 20:
            errors.append("frame_count_invalid")
        if duration <= 0 or duration > 4000:
            errors.append("duration_invalid")
        if width > 320 or height > 270 or 270 not in (width, height):
            errors.append("dimensions_invalid")
        if color_type not in (4, 6):
            errors.append("color_type_invalid")
    if not errors:
        try:
            alpha_error = line_sticker._decode_and_check_alpha(path, parsed, ffmpeg, set())  # type: ignore[attr-defined]
        except Exception:
            alpha_error = "decode_failed"
        if alpha_error:
            errors.append(str(alpha_error))
    return parsed, sorted(set(errors))


def _batch_motions(plan_payload: dict[str, object], batch: int) -> list[dict[str, object]]:
    motions = plan_payload.get("motions")
    if type(motions) is not list:
        raise MediaError("plan_invalid")
    selected = [motion for motion in motions if type(motion) is dict and motion.get("batch") == batch]
    if len(selected) != MOTIONS_PER_BATCH:
        raise MediaError("plan_invalid")
    return sorted(selected, key=lambda motion: int(motion["position"]))


def _durable_batch_records(work_dir: Path, motions: list[dict[str, object]], ffmpeg: str) -> list[dict[str, object]]:
    expected = {str(motion["motion_id"]) for motion in motions}
    records: list[dict[str, object]] = []
    for path in sorted((work_dir / "candidates").glob("*.json")):
        try:
            value = _load_json(path)
        except MediaError:
            continue
        if type(value) is dict and value.get("motion_id") in expected:
            records.append(value)
    if {str(value.get("motion_id")) for value in records} != expected or len(records) != MOTIONS_PER_BATCH:
        return []
    for record in records:
        if record.get("validation_errors") != [] or not _is_hash(record.get("candidate_sha256")):
            return []
        try:
            path = _candidate_path(record, candidates_root=work_dir / "candidates")
            metadata = path.lstat()
        except (MediaError, OSError):
            return []
        if not stat.S_ISREG(metadata.st_mode) or _sha256_file(path) != record["candidate_sha256"]:
            return []
        parsed, errors = _validate_candidate(path, ffmpeg=ffmpeg)
        if errors or parsed != record.get("parsed"):
            return []
    return records


def _convert_batch(
    *,
    plan_payload: dict[str, object],
    batch: int,
    provider_receipt: dict[str, object],
    work_dir: Path,
    ffmpeg: str,
    ffprobe: str,
) -> list[dict[str, object]]:
    source = Path(str(provider_receipt["video_path"])).expanduser()
    if not source.is_absolute():
        source = work_dir / source
    try:
        metadata = source.stat()
    except OSError as exc:
        raise MediaError("source_invalid") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise MediaError("source_invalid")
    source_hash = _sha256_file(source)
    if source_hash != provider_receipt["video_sha256"]:
        raise MediaError("source_hash_mismatch")
    duration_ms = _probe_duration(ffprobe, source, cwd=work_dir)
    batch_dir = work_dir / "candidates"
    batch_dir.mkdir(parents=True, exist_ok=True)
    motions = _batch_motions(plan_payload, batch)
    records: list[dict[str, object]] = []
    for segment in provider_receipt["segments"]:
        motion_id = str(segment["motion_id"])
        start_ms, end_ms = int(segment["start_ms"]), int(segment["end_ms"])
        if Decimal(end_ms) > duration_ms:
            raise MediaError("segments_out_of_range")
        duration_seconds = Decimal(end_ms - start_ms) / Decimal(1000)
        # Keep the complete segment while bounding the resulting APNG to 5–20 frames.
        fps = max(5, min(20, (5000 + (end_ms - start_ms) - 1) // (end_ms - start_ms)))
        output = batch_dir / f"{motion_id}.png"
        conversion_argv = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-xerror",
            "-ss",
            format(Decimal(start_ms) / Decimal(1000), "f"),
            "-t",
            format(duration_seconds, "f"),
            "-i",
            str(source),
            "-vf",
            f"chromakey=0x00FF00:0.12:0.08,fps={fps},scale=320:270:force_original_aspect_ratio=decrease,pad=320:270:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            "-plays",
            "1",
            "-f",
            "apng",
            str(output),
        ]
        try:
            _run_external(conversion_argv, cwd=work_dir)
        except MediaError as exc:
            record = {
                "version": 1,
                "motion_id": motion_id,
                "path": str(output),
                "source_sha256": source_hash,
                "segment": dict(segment),
                "conversion_argv_sha256": _sha256_bytes(_canonical(conversion_argv)),
                "candidate_sha256": "",
                "parsed": None,
                "validation_errors": [exc.code],
                "first_frame_path": "",
            }
            _atomic_json(batch_dir / f"{motion_id}.json", record)
            records.append(record)
            continue
        candidate_hash = _sha256_file(output)
        parsed, errors = _validate_candidate(output, ffmpeg=ffmpeg)
        if errors:
            try:
                _normalize_candidate_apng(output, ffmpeg=ffmpeg, duration_ms=duration_seconds * 1000, cwd=work_dir, fps=fps)
                candidate_hash = _sha256_file(output)
                parsed, errors = _validate_candidate(output, ffmpeg=ffmpeg)
            except MediaError as exc:
                errors = sorted(set(errors + [exc.code]))
        first_frame_path = batch_dir / f"{motion_id}.first.png"
        if not errors:
            try:
                _extract_first_frame(output, first_frame_path)
            except MediaError as exc:
                errors.append(exc.code)
                first_frame_path = Path("")
        record = {
            "version": 1,
            "motion_id": motion_id,
            "path": str(output),
            "source_sha256": source_hash,
            "segment": dict(segment),
            "conversion_argv_sha256": _sha256_bytes(_canonical(conversion_argv)),
            "candidate_sha256": candidate_hash,
            "parsed": parsed,
            "validation_errors": sorted(set(errors)),
            "first_frame_path": str(first_frame_path) if str(first_frame_path) else "",
            "provider_request_id": provider_receipt["request_id"],
            "provider": provider_receipt["provider"],
            "model": provider_receipt["model"],
        }
        _atomic_json(batch_dir / f"{motion_id}.json", record)
        records.append(record)
    try:
        removable_source = (
            not source.is_symlink()
            and source.resolve().is_relative_to(work_dir.resolve())
        )
    except OSError:
        removable_source = False
    if len(records) == MOTIONS_PER_BATCH and all(not record["validation_errors"] for record in records) and provider_receipt.get("regenerable") is True and removable_source:
        # The receipt and all ten records are durable before deleting the source.
        try:
            source.unlink()
        except OSError:
            pass
    return records


def _load_convert_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 3, "plan_sha256": "", "character_sha256": "", "batches": {}}
    value = _load_json(path)
    if type(value) is not dict or set(value) != {"version", "plan_sha256", "character_sha256", "batches"} or value.get("version") != 3 or not _is_hash(value.get("plan_sha256")) or not _is_hash(value.get("character_sha256")) or type(value.get("batches")) is not dict:
        raise MediaError("convert_state_invalid")
    return value


def _state_totals(state: dict[str, object]) -> tuple[Decimal, Decimal]:
    reserved, actual = Decimal(0), Decimal(0)
    batches = state.get("batches")
    if type(batches) is not dict:
        raise MediaError("convert_state_invalid")
    for number, record in batches.items():
        if number not in {str(value) for value in range(1, 7)} or type(record) is not dict or type(record.get("quote")) is not dict:
            raise MediaError("convert_state_invalid")
        quote = record["quote"]
        reserved += _decimal_cost(quote.get("quoted_cost_usd"))
        if record.get("status") == "completed":
            receipt = record.get("receipt")
            if type(receipt) is not dict:
                raise MediaError("convert_state_invalid")
            actual += _decimal_cost(receipt.get("actual_cost_usd"))
    return reserved, actual


def _completed_batch(state: dict[str, object], batch: int, motions: list[dict[str, object]], work_dir: Path, plan: dict[str, object], ffmpeg: str) -> dict[str, object]:
    record = state.get("batches", {}).get(str(batch))
    if not isinstance(record, dict) or record.get("status") != "completed" or not isinstance(record.get("quote"), dict) or not isinstance(record.get("receipt"), dict):
        raise MediaError("completed_receipt_invalid")
    quote, receipt = record["quote"], record["receipt"]
    expected_key = _reservation_key(set_id=str(plan["set_id"]), plan_hash=str(plan["plan_sha256"]), batch=batch, provider=str(quote.get("provider", "")), model=str(quote.get("model", "")), request_id=str(quote.get("request_id", "")), quote_token=str(quote.get("quote_token", "")), character_hash=str(plan["character_sha256"]))
    if quote.get("batch") != batch or receipt.get("batch") != batch or quote.get("reservation_key") != expected_key or any(receipt.get(key) != quote.get(key) for key in ("request_id", "quote_token", "batch", "provider", "model")) or receipt.get("acknowledged") is not True or type(receipt.get("regenerable")) is not bool or _decimal_cost(receipt.get("actual_cost_usd")) > _decimal_cost(quote.get("quoted_cost_usd")):
        raise MediaError("completed_receipt_invalid")
    _generation(receipt, quote, motions)
    source = Path(str(receipt.get("video_path", "")))
    if not source.is_absolute(): source = work_dir / source
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise MediaError("completed_receipt_invalid") from exc
    if metadata is not None:
        if not stat.S_ISREG(metadata.st_mode) or _sha256_file(source) != receipt.get("video_sha256"):
            raise MediaError("completed_receipt_invalid")
        return receipt
    records = _durable_batch_records(work_dir, motions, ffmpeg)
    segments = {segment["motion_id"]: segment for segment in receipt["segments"]}
    if not receipt.get("regenerable") or len(records) != MOTIONS_PER_BATCH or any(record.get("provider_request_id") != receipt["request_id"] or record.get("provider") != receipt["provider"] or record.get("model") != receipt["model"] or record.get("source_sha256") != receipt["video_sha256"] or record.get("segment") != segments.get(record.get("motion_id")) for record in records):
        raise MediaError("completed_receipt_invalid")
    return receipt


def convert(
    plan_path: Path,
    animation_command: str | list[str],
    work_dir: Path,
    max_cost_usd: str | Decimal,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    target_batch: int | None = None,
) -> dict[str, object]:
    """One state file fences quote, reservation, generation, and reconciliation."""
    work_dir = _ensure_directory(Path(work_dir)); plan_payload = _load_plan(Path(plan_path)); argv = _parse_argv(animation_command)
    if target_batch is not None and (type(target_batch) is not int or not 1 <= target_batch <= BATCH_COUNT):
        raise MediaError("configuration_error")
    last_batch = BATCH_COUNT if target_batch is None else target_batch
    max_cost = _decimal_cost(max_cost_usd if type(max_cost_usd) is str else format(max_cost_usd, "f"))
    if not Path(str(plan_payload["character_path"])).is_file() or _sha256_file(Path(str(plan_payload["character_path"]))) != plan_payload["character_sha256"]:
        raise MediaError("character_hash_mismatch")
    state_path = work_dir / "convert-state.json"; state = _load_convert_state(state_path)
    if not state["plan_sha256"]:
        state = {"version": 3, "plan_sha256": plan_payload["plan_sha256"], "character_sha256": plan_payload["character_sha256"], "batches": {}}
    if state["plan_sha256"] != plan_payload["plan_sha256"] or state["character_sha256"] != plan_payload["character_sha256"]:
        raise MediaError("convert_state_conflict")
    generated_now = False; all_records: list[dict[str, object]] = []
    for batch in range(1, last_batch + 1):
        motions = _batch_motions(plan_payload, batch); record = state["batches"].get(str(batch))
        if isinstance(record, dict) and record.get("status") == "completed":
            receipt = _completed_batch(state, batch, motions, work_dir, plan_payload, ffmpeg)
            records = _durable_batch_records(work_dir, motions, ffmpeg)
            if not records: records = _convert_batch(plan_payload=plan_payload, batch=batch, provider_receipt=receipt, work_dir=work_dir, ffmpeg=ffmpeg, ffprobe=ffprobe)
            all_records.extend(records); continue
        if isinstance(record, dict) and record.get("status") == "reconcile_required":
            raise MediaError("reconcile_required")
        if isinstance(record, dict):
            quote = record.get("quote")
            if record.get("status") != "reserved" or not isinstance(quote, dict): raise MediaError("convert_state_invalid")
            if _quote_expired(quote):
                refreshed = _quote(_run_json_command(argv, {"version": 1, "operation": "quote", "set_id": plan_payload["set_id"], "character_id": plan_payload["character_id"], "character_sha256": plan_payload["character_sha256"], "plan_sha256": plan_payload["plan_sha256"], "batch": batch, "motions": motions}, cwd=work_dir), batch)
                state["batches"].pop(str(batch)); reserved, _actual = _state_totals(state)
                if reserved + _decimal_cost(refreshed["quoted_cost_usd"]) > max_cost: raise MediaError("cost_exceeded")
                quote = {**refreshed, "reservation_key": _reservation_key(set_id=str(plan_payload["set_id"]), plan_hash=str(plan_payload["plan_sha256"]), batch=batch, provider=str(refreshed["provider"]), model=str(refreshed["model"]), request_id=str(refreshed["request_id"]), quote_token=str(refreshed["quote_token"]), character_hash=str(plan_payload["character_sha256"]))}
                state["batches"][str(batch)] = {"status": "reserved", "quote": quote}; _atomic_json(state_path, state)
        else:
            quote = _quote(_run_json_command(argv, {"version": 1, "operation": "quote", "set_id": plan_payload["set_id"], "character_id": plan_payload["character_id"], "character_sha256": plan_payload["character_sha256"], "plan_sha256": plan_payload["plan_sha256"], "batch": batch, "motions": motions}, cwd=work_dir), batch)
            reserved, _actual = _state_totals(state)
            if reserved + _decimal_cost(quote["quoted_cost_usd"]) > max_cost: raise MediaError("cost_exceeded")
            quote = {**quote, "reservation_key": _reservation_key(set_id=str(plan_payload["set_id"]), plan_hash=str(plan_payload["plan_sha256"]), batch=batch, provider=str(quote["provider"]), model=str(quote["model"]), request_id=str(quote["request_id"]), quote_token=str(quote["quote_token"]), character_hash=str(plan_payload["character_sha256"]))}
            state["batches"][str(batch)] = {"status": "reserved", "quote": quote}; _atomic_json(state_path, state)
        reserved_now, actual_now = _state_totals(state)
        if reserved_now > max_cost or actual_now > max_cost:
            raise MediaError("cost_exceeded")
        # This durable transition is intentionally the last action before provider effect.
        state["batches"][str(batch)] = {"status": "reconcile_required", "quote": quote}; _atomic_json(state_path, state)
        request = {"version": 1, "operation": "generate", "set_id": plan_payload["set_id"], "character_id": plan_payload["character_id"], "character_path": plan_payload["character_path"], "character_sha256": plan_payload["character_sha256"], "plan_sha256": plan_payload["plan_sha256"], "batch": batch, "motions": motions, "remaining_cap_usd": format(max_cost - _state_totals(state)[0] + _decimal_cost(quote["quoted_cost_usd"]), "f"), **{key: quote[key] for key in ("request_id", "quote_token", "provider", "model")}}
        try:
            receipt = _generation(_run_json_command(argv, request, cwd=work_dir), quote, motions)
        except MediaError as exc:
            raise MediaError("reconcile_required") from exc
        if receipt.get("acknowledged") is not True: raise MediaError("reconcile_required")
        if _decimal_cost(receipt["actual_cost_usd"]) > _decimal_cost(quote["quoted_cost_usd"]): raise MediaError("cost_exceeded")
        state["batches"][str(batch)] = {"status": "completed", "quote": quote, "receipt": receipt}; _atomic_json(state_path, state)
        generated_now = True; all_records.extend(_convert_batch(plan_payload=plan_payload, batch=batch, provider_receipt=receipt, work_dir=work_dir, ffmpeg=ffmpeg, ffprobe=ffprobe))
    reserved, actual = _state_totals(state)
    if reserved > max_cost or actual > max_cost: raise MediaError("cost_exceeded")
    payload = {"version": 1, "operation": "convert", "plan_sha256": plan_payload["plan_sha256"], "character_sha256": plan_payload["character_sha256"], "reserved_cost_usd": format(reserved, "f"), "actual_cost_usd": format(actual, "f"), "candidate_count": len(all_records) if all_records else sum(1 for _ in (work_dir / "candidates").glob("*.json")), "candidate_dir": str(work_dir / "candidates")}
    digest = _sha256_bytes(_canonical(payload)); payload["convert_sha256"] = digest; _atomic_json(work_dir / "convert-receipt.json", payload)
    return _public_result("ready", "converted" if generated_now else "replayed", effect=int(generated_now), readback=1, output=str(work_dir / "convert-receipt.json"), plan_sha256=str(plan_payload["plan_sha256"]), character_sha256=str(plan_payload["character_sha256"]), convert_sha256=digest)


def reconcile(convert_state: Path, animation_command: str | list[str], batch: int) -> dict[str, object]:
    """Reconcile only a durably fenced generation; never synthesize provider facts."""
    state_path = Path(convert_state); state = _load_convert_state(state_path)
    record = state.get("batches", {}).get(str(batch)) if type(batch) is int and 1 <= batch <= BATCH_COUNT else None
    if not isinstance(record, dict) or record.get("status") != "reconcile_required" or not isinstance(record.get("quote"), dict):
        raise MediaError("reconcile_required")
    quote = record["quote"]
    response = _run_json_command(_parse_argv(animation_command), {"version": 1, "operation": "reconcile", **{key: quote[key] for key in ("request_id", "quote_token", "batch", "provider", "model")}}, cwd=state_path.parent)
    expected = {"request_id", "quote_token", "batch", "provider", "model", "status", "actual_cost_usd", "regenerable", "video_path", "video_sha256", "segments"}
    if set(response) != expected or any(response.get(key) != quote.get(key) for key in ("request_id", "quote_token", "batch", "provider", "model")) or response.get("status") not in {"completed", "absent", "unknown"} or type(response.get("regenerable")) is not bool:
        raise MediaError("reconcile_schema_invalid")
    cost = _decimal_cost(response.get("actual_cost_usd"))
    if response["status"] == "absent":
        if cost != 0 or response["video_path"] or response["video_sha256"] or response["segments"]: raise MediaError("reconcile_schema_invalid")
        state["batches"][str(batch)] = {"status": "reserved", "quote": quote}; _atomic_json(state_path, state)
        return _public_result("ready", "absent", effect=0, readback=1, output=str(state_path))
    if response["status"] == "unknown":
        state["batches"][str(batch)] = {"status": "reconcile_required", "quote": quote, "reconcile": response}; _atomic_json(state_path, state)
        raise MediaError("reconcile_unknown")
    receipt = _generation({key: value for key, value in response.items() if key != "status"} | {"acknowledged": True}, quote, _batch_motions(_load_plan(state_path.parent / "plan.json"), batch))
    state["batches"][str(batch)] = {"status": "completed", "quote": quote, "receipt": receipt}; _atomic_json(state_path, state)
    return _public_result("ready", "reconciled", effect=0, readback=1, output=str(state_path))


def _load_candidate_records(candidates: Path) -> tuple[list[dict[str, object]], Path]:
    candidates = Path(candidates)
    if candidates.is_file():
        value = _load_json(candidates)
        if type(value) is dict and type(value.get("candidates")) is list:
            records = value["candidates"]
        elif type(value) is list:
            records = value
        else:
            raise MediaError("candidate_schema_invalid")
        root = candidates.parent
    elif candidates.is_dir():
        root = candidates
        records = []
        for path in sorted(candidates.glob("*.json")):
            if path.name in {"selection-input.json", "selection.json"}:
                continue
            try:
                value = _load_json(path)
            except MediaError:
                continue
            if type(value) is dict and "motion_id" in value and "path" in value:
                records.append(value)
    else:
        raise MediaError("candidates_invalid")
    if type(records) is not list or len(records) != MOTION_COUNT:
        raise MediaError("candidate_count_invalid")
    seen: set[str] = set()
    normalized: list[dict[str, object]] = []
    for record in records:
        if type(record) is not dict or not _nonempty_text(record.get("motion_id")):
            raise MediaError("candidate_schema_invalid")
        motion_id = str(record["motion_id"])
        if motion_id in seen:
            raise MediaError("candidate_id_duplicate")
        seen.add(motion_id)
        normalized.append(dict(record))
    return normalized, root


def _selection_model(response: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
    expected = {"version", "mode", "cover_motion_id", "inspected_candidate_hashes", "selections"}
    if set(response) != expected or response.get("version") != 1 or response.get("mode") != "select":
        raise MediaError("selection_schema_invalid")
    cover = response.get("cover_motion_id")
    selections, inspected = response.get("selections"), response.get("inspected_candidate_hashes")
    if not _nonempty_text(cover) or type(selections) is not list or len(selections) != 24:
        raise MediaError("selection_count_invalid")
    if type(inspected) is not list or len(inspected) != MOTION_COUNT or any(not _is_hash(value) for value in inspected):
        raise MediaError("selection_readback_invalid")
    keys = {"position", "motion_id", "reason"}
    positions: set[int] = set()
    ids: set[str] = set()
    output: list[dict[str, object]] = []
    for entry in selections:
        if type(entry) is not dict or set(entry) != keys:
            raise MediaError("selection_schema_invalid")
        if type(entry["position"]) is not int or not 1 <= entry["position"] <= 24:
            raise MediaError("selection_position_invalid")
        if not _nonempty_text(entry["motion_id"]) or not _nonempty_text(entry["reason"]):
            raise MediaError("selection_schema_invalid")
        if entry["position"] in positions or entry["motion_id"] in ids:
            raise MediaError("selection_duplicate")
        positions.add(entry["position"])
        ids.add(entry["motion_id"])
        output.append(dict(entry))
    output = sorted(output, key=lambda entry: int(entry["position"]))
    if positions != set(range(1, 25)) or output[0]["motion_id"] != cover:
        raise MediaError("selection_cover_invalid")
    return str(cover), output


def _selection_input(
    plan_payload: dict[str, object], records: list[dict[str, object]], candidates_root: Path
) -> tuple[dict[str, object], str]:
    motion_map = {str(motion["motion_id"]): motion for motion in plan_payload["motions"] if type(motion) is dict}
    values: list[dict[str, object]] = []
    for record in sorted(records, key=lambda entry: str(entry["motion_id"])):
        path = _candidate_path(record, candidates_root=candidates_root)
        current_hash = ""
        current_errors: list[str] = list(record.get("validation_errors", [])) if type(record.get("validation_errors", [])) is list else ["candidate_schema_invalid"]
        try:
            current_hash = _sha256_file(path)
            if record.get("candidate_sha256") and current_hash != record.get("candidate_sha256"):
                current_errors.append("candidate_changed")
        except MediaError:
            current_errors.append("candidate_missing")
        first_frame = record.get("first_frame_path")
        if not _nonempty_text(first_frame):
            first_frame = ""
        first_frame_path = Path(str(first_frame)) if first_frame else Path("")
        if first_frame_path and not first_frame_path.is_absolute():
            first_frame_path = candidates_root / first_frame_path
        if not first_frame_path or not first_frame_path.is_file():
            if not current_errors and path.is_file():
                first_frame_path = candidates_root / f"{record['motion_id']}.first.png"
                try:
                    _extract_first_frame(path, first_frame_path)
                except MediaError:
                    current_errors.append("first_frame_missing")
        motion = motion_map.get(str(record["motion_id"]))
        if not isinstance(motion, dict):
            current_errors.append("motion_missing")
            motion = {"motion_id": record["motion_id"]}
        values.append(
            {
                "motion_id": record["motion_id"],
                "path": str(path),
                "sha256": current_hash,
                "parsed": record.get("parsed"),
                "errors": sorted(set(str(item) for item in current_errors)),
                "first_frame_path": str(first_frame_path) if first_frame_path else "",
                "motion_preview_path": str(record.get("motion_preview_path") or path),
                "motion": motion,
            }
        )
    payload = {
        "version": 1,
        "mode": "select",
        "plan_sha256": plan_payload["plan_sha256"],
        "character_sha256": plan_payload["character_sha256"],
        "candidates": values,
        "contact_sheet_path": str(candidates_root / "contact-sheet.png"),
    }
    return payload, _sha256_bytes(_canonical(payload))


def select(
    plan_path: Path,
    candidates: Path,
    model_command: str | list[str],
    work_dir: Path,
) -> dict[str, object]:
    """Ask the model to choose and order twenty-four valid candidates."""
    work_dir = _ensure_directory(Path(work_dir))
    plan_payload = _load_plan(Path(plan_path))
    records, candidates_root = _load_candidate_records(Path(candidates))
    selection_input, input_hash = _selection_input(plan_payload, records, candidates_root)
    selection_input_path = work_dir / "selection-input.json"
    _atomic_json(selection_input_path, selection_input)
    selection_path = work_dir / "selection.json"
    receipt_path = work_dir / "selection-receipt.json"
    if selection_path.exists() or receipt_path.exists():
        if not selection_path.is_file():
            raise MediaError("selection_state_incomplete")
        receipt = _load_json(receipt_path) if receipt_path.exists() else None
        if receipt is not None and (type(receipt) is not dict or receipt.get("selection_input_sha256") != input_hash):
            # A changed candidate hash deliberately invalidates the old selection.
            pass
        else:
            selected = _load_selection(selection_path)
            if selected.get("selection_input_sha256") != input_hash:
                raise MediaError("selection_hash_mismatch")
            if receipt is None:
                repaired = {"version": 1, "operation": "select", "status": "ready", "effect": 0, "readback": 1, "reason": "repaired", "selection_input_sha256": input_hash, "selection_sha256": selected.get("selection_sha256", ""), "output": selection_path.name}
                repaired["receipt_sha256"] = _sha256_bytes(_canonical(repaired)); _atomic_json(receipt_path, repaired)
            return _public_result(
                "ready",
                "replayed",
                readback=1,
                output=str(selection_path),
                plan_sha256=str(plan_payload["plan_sha256"]),
                selection_input_sha256=input_hash,
                selection_sha256=str(selected.get("selection_sha256", "")),
            )
    argv = _parse_argv(model_command)
    prompt_path = Path(__file__).with_name("creative-prompt.md")
    try:
        prompt = prompt_path.read_bytes()
    except OSError as exc:
        raise MediaError("prompt_missing") from exc
    request = {
        "version": 1,
        "mode": "select",
        "plan_sha256": plan_payload["plan_sha256"],
        "selection_input_sha256": input_hash,
        "selection_input_path": str(selection_input_path),
        "creative_prompt": prompt.decode("utf-8"),
    }
    response = _run_json_command(argv, request, cwd=work_dir)
    cover, selected_model = _selection_model(response)
    candidate_map = {str(value["motion_id"]): value for value in selection_input["candidates"]}
    if sorted(response["inspected_candidate_hashes"]) != sorted(str(value["sha256"]) for value in selection_input["candidates"]):
        raise MediaError("selection_readback_invalid")
    selected: list[dict[str, object]] = []
    for entry in selected_model:
        candidate = candidate_map.get(str(entry["motion_id"]))
        if not isinstance(candidate, dict):
            raise MediaError("selection_unknown_candidate")
        if candidate.get("errors") or not _nonempty_text(candidate.get("path")) or not Path(str(candidate["path"])).is_file():
            raise MediaError("selection_invalid_candidate")
        selected.append(
            {
                "position": entry["position"],
                "motion_id": entry["motion_id"],
                "reason": entry["reason"],
                "path": candidate["path"],
                "candidate_sha256": candidate["sha256"],
                "source_sha256": next(record.get("source_sha256", "") for record in records if record.get("motion_id") == entry["motion_id"]),
                "segment": next(record.get("segment", {}) for record in records if record.get("motion_id") == entry["motion_id"]),
                "conversion_argv_sha256": next(record.get("conversion_argv_sha256", "") for record in records if record.get("motion_id") == entry["motion_id"]),
                "prompt_sha256": _sha256_bytes(str(candidate["motion"].get("provider_prompt", "")).encode("utf-8")),
            }
        )
    payload = {
        "version": 1,
        "mode": "select",
        "plan_sha256": plan_payload["plan_sha256"],
        "character_sha256": plan_payload["character_sha256"],
        "selection_input_sha256": input_hash,
        "cover_motion_id": cover,
        "inspected_candidate_hashes": response["inspected_candidate_hashes"],
        "selections": selected,
    }
    selection_hash = _sha256_bytes(_canonical(payload))
    payload["selection_sha256"] = selection_hash
    _atomic_json(selection_path, payload)
    receipt = {
        "version": 1,
        "operation": "select",
        "status": "ready",
        "effect": 1,
        "readback": 1,
        "reason": "selected",
        "selection_input_sha256": input_hash,
        "selection_sha256": selection_hash,
        "output": selection_path.name,
    }
    receipt["receipt_sha256"] = _sha256_bytes(_canonical(receipt))
    _atomic_json(receipt_path, receipt)
    return _public_result(
        "ready",
        "selected",
        effect=1,
        readback=1,
        output=str(selection_path),
        plan_sha256=str(plan_payload["plan_sha256"]),
        selection_input_sha256=input_hash,
        selection_sha256=selection_hash,
    )


def _load_selection(path: Path) -> dict[str, object]:
    value = _load_json(path)
    if type(value) is not dict:
        raise MediaError("selection_invalid")
    required = {
        "version",
        "mode",
        "plan_sha256",
        "character_sha256",
        "selection_input_sha256",
        "cover_motion_id",
        "inspected_candidate_hashes",
        "selections",
        "selection_sha256",
    }
    if set(value) != required or value.get("version") != 1 or value.get("mode") != "select":
        raise MediaError("selection_invalid")
    if not _is_hash(value["plan_sha256"]) or not _is_hash(value["character_sha256"]) or not _is_hash(value["selection_input_sha256"]) or not _is_hash(value["selection_sha256"]):
        raise MediaError("selection_invalid")
    if type(value["selections"]) is not list:
        raise MediaError("selection_invalid")
    try:
        model_selections = [
            {key: entry[key] for key in ("position", "motion_id", "reason")}
            for entry in value["selections"]
            if type(entry) is dict and set(entry) >= {"position", "motion_id", "reason"}
        ]
        cover, selections = _selection_model(
            {
                "version": 1,
                "mode": "select",
                "cover_motion_id": value["cover_motion_id"],
                "inspected_candidate_hashes": value["inspected_candidate_hashes"],
                "selections": model_selections,
            }
        )
    except (KeyError, TypeError, MediaError) as exc:
        if isinstance(exc, MediaError):
            raise
        raise MediaError("selection_invalid") from exc
    if cover != value["cover_motion_id"] or len(selections) != 24:
        raise MediaError("selection_invalid")
    payload = dict(value)
    payload.pop("selection_sha256")
    if _sha256_bytes(_canonical(payload)) != value["selection_sha256"]:
        raise MediaError("selection_hash_mismatch")
    return dict(value)


def _write_png_zip(root: Path) -> bytes:
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in PNG_NAMES:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                archive.writestr(info, (root / name).read_bytes())
        stream.seek(0)
        return stream.read()


def _ffmpeg_make_main(ffmpeg: str, cover: Path, output: Path, *, cwd: Path) -> None:
    _run_external(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(cover),
            "-vf",
            "scale=240:240:force_original_aspect_ratio=decrease,pad=240:240:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            "-plays",
            "1",
            "-f",
            "apng",
            str(output),
        ],
        cwd=cwd,
    )


def _ffmpeg_make_tab(ffmpeg: str, first_frame: Path, output: Path, *, cwd: Path) -> None:
    _run_external(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(first_frame),
            "-vf",
            "scale=96:74:force_original_aspect_ratio=decrease,pad=96:74:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            "-frames:v",
            "1",
            "-f",
            "image2",
            str(output),
        ],
        cwd=cwd,
    )


def _package_provenance(
    root: Path,
    plan_payload: dict[str, object],
    selection: dict[str, object],
    work_dir: Path,
    rights_evidence: dict[str, object],
    ffmpeg: str,
) -> dict[str, object]:
    prompt_hashes: dict[str, str] = {}
    assets: dict[str, object] = {}
    selected = {str(entry["position"]): entry for entry in selection["selections"] if type(entry) is dict}
    cover_prompt = str(selected["1"].get("prompt_sha256", plan_payload["prompt_sha256"]))
    for name in PNG_NAMES:
        if name == "main.png" or name == "tab.png":
            prompt_hashes[name] = cover_prompt
        else:
            prompt_hashes[name] = str(selected[str(int(name[:2]))].get("prompt_sha256", cover_prompt))
        prompt_hashes[name] = prompt_hashes[name] if _is_hash(prompt_hashes[name]) else _sha256_bytes(prompt_hashes[name].encode())
        assets[name] = {"sha256": _sha256_file(root / name), "intentional_alpha_holes": []}
    state = _load_convert_state(work_dir / "convert-state.json")
    batches: dict[str, object] = {}
    providers: set[str] = set()
    models: set[str] = set()
    for batch in range(1, 7):
        generation = _completed_batch(state, batch, _batch_motions(plan_payload, batch), work_dir, plan_payload, ffmpeg)
        value = state["batches"][str(batch)]; reservation = value["quote"]
        providers.add(str(reservation.get("provider", ""))); models.add(str(reservation.get("model", "")))
        if not all(_nonempty_text(reservation.get(key)) for key in ("request_id", "quote_token", "provider", "model", "quoted_cost_usd")) or not _nonempty_text(generation.get("request_id")) or not _is_hash(generation.get("video_sha256")) or generation.get("request_id") != reservation.get("request_id"):
            raise MediaError("receipt_invalid")
        batches[str(batch)] = {"quote_request_id": reservation["request_id"], "generation_request_id": generation["request_id"], "quote_token": reservation["quote_token"], "provider": reservation["provider"], "model": reservation["model"], "reserved_cost_usd": reservation["quoted_cost_usd"], "actual_cost_usd": generation["actual_cost_usd"], "source_sha256": generation["video_sha256"], "regenerable": generation["regenerable"]}
    if len(providers) != 1 or len(models) != 1 or not all(providers) or not all(models):
        raise MediaError("receipt_invalid")
    bindings: dict[str, object] = {}
    for position in range(1, 25):
        entry = selected[str(position)]
        for key in ("motion_id", "source_sha256", "candidate_sha256", "conversion_argv_sha256"):
            if not _nonempty_text(entry.get(key)) if key == "motion_id" else not _is_hash(entry.get(key)):
                raise MediaError("selection_invalid")
        segment = entry.get("segment")
        if not isinstance(segment, dict):
            raise MediaError("selection_invalid")
        name = f"{position:02d}.png"
        bindings[name] = {"motion_id": entry["motion_id"], "source_sha256": entry["source_sha256"], "segment": segment, "candidate_sha256": entry["candidate_sha256"], "conversion_argv_sha256": entry["conversion_argv_sha256"], "asset_sha256": _sha256_file(root / name)}
    reserved, actual = _state_totals(state)
    generation = {"rights_evidence": rights_evidence, "character_sha256": plan_payload["character_sha256"], "plan_sha256": plan_payload["plan_sha256"], "selection_sha256": selection["selection_sha256"], "prompt_sha256": plan_payload["prompt_sha256"], "model": next(iter(models)), "provider": next(iter(providers)), "reserved_cost_usd": format(reserved, "f"), "actual_cost_usd": format(actual, "f"), "batches": batches, "candidate_bindings": bindings}
    generation["generation_sha256"] = _sha256_bytes(_canonical(generation))
    return {
        "set_id": plan_payload["set_id"],
        "character_id": plan_payload["character_id"],
        "rights": "original_ai_generated",
        "providers": {"image": str(rights_evidence["creation_source"]), "animation": next(iter(providers))},
        "prompt_hashes": prompt_hashes,
        "assets": assets,
        "generation": generation,
    }


def _rights_receipt(path: Path, plan: dict[str, object]) -> dict[str, object]:
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MediaError("rights_receipt_invalid") from exc
    expected = {"version", "set_id", "character_id", "character_sha256", "creation_source", "rights"}
    if type(value) is not dict or set(value) != expected or value.get("version") != 1 or value.get("set_id") != plan["set_id"] or value.get("character_id") != plan["character_id"] or value.get("character_sha256") != plan["character_sha256"] or value.get("rights") != "original_ai_generated" or not _nonempty_text(value.get("creation_source")):
        raise MediaError("rights_receipt_invalid")
    body = {key: value[key] for key in ("set_id", "character_id", "character_sha256", "creation_source", "rights")}
    return {"receipt_sha256": _sha256_bytes(_canonical(body)), **body}


def package(
    selection: Path,
    work_dir: Path,
    output: Path,
    policy: Path,
    rights_receipt: Path,
    ffmpeg: str = "ffmpeg",
) -> dict[str, object]:
    """Build, validate, and atomically promote the official 26-PNG package."""
    work_dir = _ensure_directory(Path(work_dir))
    selected_payload = _load_selection(Path(selection))
    plan_path = work_dir / "plan.json"
    plan_payload = _load_plan(plan_path)
    if selected_payload["plan_sha256"] != plan_payload["plan_sha256"] or selected_payload["character_sha256"] != plan_payload["character_sha256"]:
        raise MediaError("selection_plan_mismatch")
    rights_evidence = _rights_receipt(rights_receipt, plan_payload)
    output = Path(output)
    if output.exists() or output.is_symlink():
        if output.is_dir() and not output.is_symlink():
            validation = line_sticker.validate_package(output, Path(policy), ffmpeg=ffmpeg)
            try:
                provenance = _load_json(output / "provenance.json")
            except MediaError:
                provenance = None
            generation = provenance.get("generation") if isinstance(provenance, dict) else None
            if validation.get("status") == "ready" and isinstance(generation, dict) and generation.get("plan_sha256") == plan_payload["plan_sha256"] and generation.get("selection_sha256") == selected_payload["selection_sha256"] and generation.get("rights_evidence") == rights_evidence:
                return _public_result("ready", "replayed", effect=0, readback=1, output=str(output), plan_sha256=str(plan_payload["plan_sha256"]), selection_sha256=str(selected_payload["selection_sha256"]), artifact_sha256=str(validation.get("artifact_sha256", "")), package_sha256=str(validation.get("package_sha256", "")))
        raise MediaError("output_conflict")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix="line-sticker-package-", dir=str(output.parent)))
        selected = selected_payload["selections"]
        if type(selected) is not list or len(selected) != 24:
            raise MediaError("selection_count_invalid")
        cover_path: Path | None = None
        first_frame_path: Path | None = None
        for entry in sorted(selected, key=lambda value: int(value["position"])):
            if type(entry) is not dict:
                raise MediaError("selection_invalid")
            position = int(entry["position"])
            path = Path(str(entry["path"]))
            if not path.is_file() or _sha256_file(path) != entry["candidate_sha256"]:
                raise MediaError("candidate_changed_after_selection")
            destination = staging / f"{position:02d}.png"
            _atomic_bytes(destination, path.read_bytes())
            if position == 1:
                cover_path = path
                candidate_first = path.parent / f"{entry['motion_id']}.first.png"
                if candidate_first.is_file():
                    first_frame_path = candidate_first
                else:
                    first_frame_path = staging / "cover.first.png"
                    _extract_first_frame(path, first_frame_path)
        if cover_path is None or first_frame_path is None:
            raise MediaError("selection_cover_invalid")
        try:
            cover_facts = line_sticker.parse_png(cover_path)
        except Exception as exc:
            raise MediaError("candidate_png_invalid") from exc
        _ffmpeg_make_main(ffmpeg, cover_path, staging / "main.png", cwd=work_dir)
        try:
            line_sticker.parse_png(staging / "main.png")
        except Exception:
            _normalize_candidate_apng(
                staging / "main.png",
                ffmpeg=ffmpeg,
                duration_ms=Decimal(str(cover_facts["duration_ms"])),
                cwd=work_dir,
                width=240,
                height=240,
            )
        _ffmpeg_make_tab(ffmpeg, first_frame_path, staging / "tab.png", cwd=work_dir)
        provenance = _package_provenance(staging, plan_payload, selected_payload, work_dir, rights_evidence, ffmpeg)
        _atomic_json(staging / "provenance.json", provenance)
        _atomic_bytes(staging / "submission.zip", _write_png_zip(staging))
        validation = line_sticker.validate_package(staging, Path(policy), ffmpeg=ffmpeg)
        if validation.get("status") != "ready":
            raise MediaError("validator_invalid")
        os.replace(staging, output)
        staging = None
        return _public_result(
            "ready",
            "packaged",
            effect=1,
            readback=1,
            output=str(output),
            plan_sha256=str(plan_payload["plan_sha256"]),
            selection_sha256=str(selected_payload["selection_sha256"]),
            artifact_sha256=str(validation.get("artifact_sha256", "")),
            package_sha256=str(validation.get("package_sha256", "")),
        )
    except OSError as exc:
        if getattr(exc, "errno", None) == 28:
            raise MediaError("disk_full") from exc
        raise
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise MediaError("configuration_error")


def _cli_result(exc: Exception) -> dict[str, object]:
    code = exc.code if isinstance(exc, MediaError) else "configuration_error"
    return _public_result("error", code)


def main(argv: list[str] | None = None) -> int:
    parser = _JsonArgumentParser(prog="line_sticker_media.py", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_JsonArgumentParser)
    plan_parser = subparsers.add_parser("plan", add_help=False)
    plan_parser.add_argument("--character", required=True, type=Path)
    plan_parser.add_argument("--model-command", required=True)
    plan_parser.add_argument("--work-dir", required=True, type=Path)
    plan_parser.add_argument("--set-id", required=True)
    plan_parser.add_argument("--character-id", required=True)
    convert_parser = subparsers.add_parser("convert", add_help=False)
    convert_parser.add_argument("--plan", required=True, type=Path)
    convert_parser.add_argument("--animation-command", required=True)
    convert_parser.add_argument("--work-dir", required=True, type=Path)
    convert_parser.add_argument("--max-cost-usd", required=True)
    convert_parser.add_argument("--ffmpeg", required=True)
    convert_parser.add_argument("--ffprobe", required=True)
    convert_parser.add_argument("--batch", type=int)
    reconcile_parser = subparsers.add_parser("reconcile", add_help=False)
    reconcile_parser.add_argument("--convert-state", required=True, type=Path)
    reconcile_parser.add_argument("--animation-command", required=True)
    reconcile_parser.add_argument("--batch", required=True, type=int)
    select_parser = subparsers.add_parser("select", add_help=False)
    select_parser.add_argument("--plan", required=True, type=Path)
    select_parser.add_argument("--candidates", required=True, type=Path)
    select_parser.add_argument("--model-command", required=True)
    select_parser.add_argument("--work-dir", required=True, type=Path)
    package_parser = subparsers.add_parser("package", add_help=False)
    package_parser.add_argument("--selection", required=True, type=Path)
    package_parser.add_argument("--work-dir", required=True, type=Path)
    package_parser.add_argument("--output", required=True, type=Path)
    package_parser.add_argument("--policy", required=True, type=Path)
    package_parser.add_argument("--rights-receipt", required=True, type=Path)
    package_parser.add_argument("--ffmpeg", required=True)
    try:
        args = parser.parse_args(argv)
    except Exception as exc:
        result = _cli_result(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    try:
        if args.command == "plan":
            result = plan(args.character, args.model_command, args.work_dir, args.set_id, args.character_id)
        elif args.command == "convert":
            result = convert(args.plan, args.animation_command, args.work_dir, args.max_cost_usd, args.ffmpeg, args.ffprobe, args.batch)
        elif args.command == "reconcile":
            result = reconcile(args.convert_state, args.animation_command, args.batch)
        elif args.command == "select":
            result = select(args.plan, args.candidates, args.model_command, args.work_dir)
        elif args.command == "package":
            result = package(args.selection, args.work_dir, args.output, args.policy, args.rights_receipt, args.ffmpeg)
        else:
            raise MediaError("configuration_error")
    except Exception as exc:
        result = _cli_result(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
