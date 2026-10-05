"""Deterministic, no-cost local animation provider for the LINE media loop."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROVIDER = "native-ffmpeg"
MODEL = "whole-character-transforms-v2"
SEGMENT_MS = 1_000
MOTION_COUNT = 10
BATCH_COUNT = 6
QUOTE_EXPIRY = "2099-01-01T00:00:00Z"
MAX_OUTPUT = 1_048_576
COMMAND_TIMEOUT = 600
COMMON_KEYS = frozenset({
    "version", "operation", "set_id", "character_id", "character_sha256", "plan_sha256", "batch", "motions",
})
GENERATE_KEYS = COMMON_KEYS | frozenset({
    "character_path", "remaining_cap_usd", "request_id", "quote_token", "provider", "model",
})
RECONCILE_KEYS = frozenset({"version", "operation", "request_id", "quote_token", "batch", "provider", "model"})


class NativeError(ValueError):
    """A safe adapter error that contains no request or filesystem data."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _hash_ok(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path, error: str = "file_invalid") -> str:
    try:
        if not path.is_file():
            raise NativeError(error)
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except NativeError:
        raise
    except (OSError, ValueError):
        raise NativeError(error) from None


def _cost(value: object) -> Decimal:
    if value is None or type(value) is bool:
        raise NativeError("cost_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise NativeError("cost_invalid") from None
    if not parsed.is_finite() or parsed < 0:
        raise NativeError("cost_invalid")
    return parsed


def _validate_request(request: dict[str, object], operation: str, keys: frozenset[str]) -> int:
    if set(request) != keys or request.get("version") != 1 or request.get("operation") != operation:
        raise NativeError("request_invalid")
    if not _text(request.get("set_id")) or not _text(request.get("character_id")):
        raise NativeError("request_invalid")
    if not _hash_ok(request.get("character_sha256")) or not _hash_ok(request.get("plan_sha256")):
        raise NativeError("request_invalid")
    batch = request.get("batch")
    if type(batch) is not int or not 1 <= batch <= BATCH_COUNT:
        raise NativeError("batch_invalid")
    return batch


def _motions(value: object, batch: int) -> list[str]:
    if type(value) is not list or len(value) != MOTION_COUNT:
        raise NativeError("motions_invalid")
    ids: list[str] = []
    for position, motion in enumerate(value, 1):
        expected_keys = {"motion_id", "batch", "position", "intent", "action", "provider_prompt", "duration_ms"}
        if type(motion) is not dict or set(motion) != expected_keys:
            raise NativeError("motions_invalid")
        expected_id = f"motion-{(batch - 1) * MOTION_COUNT + position:02d}"
        if motion.get("motion_id") != expected_id or motion.get("batch") != batch or motion.get("position") != position or motion.get("duration_ms") != SEGMENT_MS:
            raise NativeError("motions_invalid")
        if any(type(motion[field]) is not str or not motion[field].strip() for field in ("intent", "action", "provider_prompt")):
            raise NativeError("motions_invalid")
        ids.append(expected_id)
    return ids


def _identity(request: dict[str, object]) -> dict[str, object]:
    return {key: request[key] for key in ("version", "set_id", "character_id", "character_sha256", "plan_sha256", "batch", "motions")} | {"provider": PROVIDER, "model": MODEL}


def _request_id(request: dict[str, object]) -> str:
    return _sha256(_canonical(_identity(request)))


def _quote_token(request: dict[str, object], request_id: str) -> str:
    return _sha256(_canonical({"kind": "native-quote", "identity": _identity(request), "request_id": request_id, "expires_at": QUOTE_EXPIRY}))


def _segments(ids: list[str]) -> list[dict[str, object]]:
    return [{"motion_id": motion_id, "start_ms": i * SEGMENT_MS, "end_ms": (i + 1) * SEGMENT_MS} for i, motion_id in enumerate(ids)]


def _run(argv: list[str], cwd: Path) -> None:
    try:
        process = subprocess.run(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 shell=False, timeout=COMMAND_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise NativeError("ffmpeg_failed") from None
    if process.returncode != 0 or len(process.stdout) > MAX_OUTPUT or len(process.stderr) > MAX_OUTPUT:
        raise NativeError("ffmpeg_failed")


def _png_size(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n" or stream.read(4) != b"\x00\x00\x00\r" or stream.read(4) != b"IHDR":
                raise NativeError("character_invalid")
            width, height = int.from_bytes(stream.read(4), "big"), int.from_bytes(stream.read(4), "big")
            if not 1 <= width <= 4096 or not 1 <= height <= 4096:
                raise NativeError("character_invalid")
            return width, height
    except NativeError:
        raise
    except (OSError, ValueError):
        raise NativeError("character_invalid") from None


def _render(request: dict[str, object], source: Path, output: Path, cwd: Path, width: int, height: int) -> None:
    rhythms = ((-18, -12, -8), (-10, -8, 8), (0, 0, -10), (10, 8, 8), (18, 12, -8), (-14, -10, 8), (14, 10, -8), (-6, -6, 6), (6, 6, -6), (0, 0, 10))
    batch = int(request["batch"])
    frequency = 1 + batch / 10
    amplitude = 0.8 + batch / 20
    segments = [cwd / f".native-{int(request['batch'])}-{i}.mp4" for i in range(MOTION_COUNT)]
    concat = cwd / f".native-{int(request['batch'])}.concat.txt"
    try:
        for index, (segment, (angle, dx, dy)) in enumerate(zip(segments, rhythms)):
            phase = batch * 0.37 + index * 0.17
            wave = f"sin(2*PI*{frequency}*t+{phase})"
            vf = f"rotate={angle * amplitude}*PI/180*{wave}:ow=iw:oh=ih:fillcolor=0x00FF00,scale={width}:{height},pad={width + 64}:{height + 64}:32:32:color=0x00FF00,crop={width}:{height}:32+{dx * amplitude}*{wave}:32+{dy * amplitude}*{wave},format=yuv420p"
            _run(["ffmpeg", "-y", "-v", "error", "-xerror", "-loop", "1", "-framerate", "24", "-i", str(source), "-t", "1", "-vf", vf,
                  "-r", "24", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(segment)], cwd)
        concat.write_text("".join(f"file '{path.name}'\n" for path in segments), encoding="utf-8")
        _run(["ffmpeg", "-y", "-v", "error", "-xerror", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)], cwd)
    except OSError:
        raise NativeError("video_write_failed") from None
    finally:
        for path in segments + [concat]:
            try:
                path.unlink()
            except OSError:
                pass


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", mode="w", encoding="utf-8", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    except OSError:
        raise NativeError("receipt_write_failed") from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _receipt_path(video: Path) -> Path:
    return video.with_suffix(video.suffix + ".receipt.json")


def _commit_path(video: Path) -> Path:
    return video.with_suffix(video.suffix + ".commit.json")


RECEIPT_KEYS = frozenset({
    "request_id", "quote_token", "batch", "provider", "model", "video_path", "video_sha256", "segments", "regenerable",
})


def _fsync_file(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _generation_result(request: dict[str, object], receipt: dict[str, object]) -> dict[str, object]:
    return {"request_id": request["request_id"], "quote_token": request["quote_token"], "batch": request["batch"],
            "provider": PROVIDER, "model": MODEL, "acknowledged": True, "video_path": receipt["video_path"],
            "video_sha256": receipt["video_sha256"], "segments": receipt["segments"], "regenerable": False, "actual_cost_usd": "0"}


def _lock(path: Path) -> int:
    try:
        descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except BlockingIOError:
        try:
            os.close(descriptor)
        except UnboundLocalError:
            pass
        raise NativeError("generation_conflict") from None
    except OSError:
        raise NativeError("video_write_failed") from None


def _read_receipt(request: dict[str, object], target: Path, receipt_path: Path, batch: int, *, verify_source: bool = True) -> dict[str, object]:
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise NativeError("generation_conflict")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise NativeError("generation_conflict") from None
    if type(receipt) is not dict or set(receipt) != RECEIPT_KEYS:
        raise NativeError("generation_conflict")
    if any(receipt.get(key) != request.get(key) for key in ("request_id", "quote_token", "batch", "provider", "model")) or receipt.get("regenerable") is not False:
        raise NativeError("generation_conflict")
    try:
        path_matches = Path(str(receipt["video_path"])).resolve() == target.resolve()
    except (OSError, ValueError):
        path_matches = False
    if not path_matches or not _hash_ok(receipt.get("video_sha256")) or (verify_source and _hash_file(target, "generation_conflict") != receipt["video_sha256"]) or not _valid_segments(receipt.get("segments"), batch):
        raise NativeError("generation_conflict")
    return receipt


def _matching_receipt(request: dict[str, object], target: Path, receipt_path: Path, commit_path: Path, batch: int) -> dict[str, object] | None:
    source_exists = target.exists() or target.is_symlink()
    receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
    commit_exists = commit_path.exists() or commit_path.is_symlink()
    if not source_exists and not receipt_exists and not commit_exists:
        return None
    if not source_exists and not receipt_exists and commit_exists:
        _read_receipt(request, target, commit_path, batch, verify_source=False)
        try:
            commit_path.unlink()
        except OSError:
            raise NativeError("generation_conflict") from None
        return None
    if target.is_symlink() or receipt_path.is_symlink() or commit_path.is_symlink() or not target.is_file():
        raise NativeError("generation_conflict")
    if receipt_exists:
        receipt = _read_receipt(request, target, receipt_path, batch)
        if commit_exists:
            try:
                commit_path.unlink()
            except OSError:
                pass
        return _generation_result(request, receipt)
    if not commit_exists:
        raise NativeError("generation_conflict")
    receipt = _read_receipt(request, target, commit_path, batch)
    _atomic_json(receipt_path, receipt)
    try:
        commit_path.unlink()
    except OSError:
        pass
    return _generation_result(request, receipt)


def _generate(request: dict[str, object]) -> dict[str, object]:
    batch = _validate_request(request, "generate", GENERATE_KEYS)
    if request.get("provider") != PROVIDER or request.get("model") != MODEL:
        raise NativeError("provider_identity_mismatch")
    _cost(request.get("remaining_cap_usd"))
    try:
        character = Path(str(request["character_path"])).expanduser()
    except (KeyError, TypeError, ValueError):
        raise NativeError("character_invalid") from None
    if _hash_file(character, "character_invalid") != str(request["character_sha256"]).lower():
        raise NativeError("character_hash_mismatch")
    ids = _motions(request["motions"], batch)
    request_id = _request_id(request)
    if request.get("request_id") != request_id or request.get("quote_token") != _quote_token(request, request_id):
        raise NativeError("request_identity_mismatch")
    width, height = _png_size(character)
    cwd = Path.cwd()
    target = cwd / f"native-source-batch-{batch}.mp4"
    receipt_path = _receipt_path(target)
    commit_path = _commit_path(target)
    lock_path = cwd / f".native-source-batch-{batch}.lock"
    lock_fd = _lock(lock_path)
    temp_dir: Path | None = None
    try:
        replay = _matching_receipt(request, target, receipt_path, commit_path, batch)
        if replay is not None:
            return replay
        temp_dir = Path(tempfile.mkdtemp(prefix=f".native-batch-{batch}-", dir=str(cwd)))
        rendered = temp_dir / "source.mp4"
        _render(request, character, rendered, temp_dir, width, height)
        digest = _hash_file(rendered, "video_invalid")
        _fsync_file(rendered)
        receipt = {"request_id": request_id, "quote_token": request["quote_token"], "batch": batch, "provider": PROVIDER, "model": MODEL,
                   "video_path": str(target.resolve()), "video_sha256": digest, "segments": _segments(ids), "regenerable": False}
        _atomic_json(commit_path, receipt)
        if target.exists() or target.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
            raise NativeError("generation_conflict")
        os.replace(rendered, target)
        _fsync_directory(cwd)
        _atomic_json(receipt_path, receipt)
        try:
            commit_path.unlink()
        except OSError:
            pass
        return _generation_result(request, receipt)
    except OSError:
        raise NativeError("video_write_failed") from None
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
def _absent(request: dict[str, object]) -> dict[str, object]:
    return {"request_id": request["request_id"], "quote_token": request["quote_token"], "batch": request["batch"], "provider": PROVIDER,
            "model": MODEL, "status": "absent", "actual_cost_usd": "0", "regenerable": False, "video_path": "", "video_sha256": "", "segments": []}


def _valid_segments(value: object, batch: int) -> bool:
    if type(value) is not list or len(value) != MOTION_COUNT:
        return False
    previous = 0
    ids: set[str] = set()
    for index, segment in enumerate(value, 1):
        if type(segment) is not dict or set(segment) != {"motion_id", "start_ms", "end_ms"}:
            return False
        expected_id = f"motion-{(batch - 1) * MOTION_COUNT + index:02d}"
        if segment.get("motion_id") != expected_id or segment["motion_id"] in ids or segment["start_ms"] != previous or segment["end_ms"] != previous + SEGMENT_MS:
            return False
        ids.add(segment["motion_id"])
        previous += SEGMENT_MS
    return True


def _reconcile(request: dict[str, object]) -> dict[str, object]:
    if set(request) != RECONCILE_KEYS or request.get("version") != 1 or request.get("operation") != "reconcile":
        raise NativeError("request_invalid")
    batch = request.get("batch")
    if type(batch) is not int or not 1 <= batch <= BATCH_COUNT:
        raise NativeError("batch_invalid")
    if request.get("provider") != PROVIDER or request.get("model") != MODEL or not _text(request.get("request_id")) or not _text(request.get("quote_token")):
        raise NativeError("provider_identity_mismatch")
    target = Path.cwd() / f"native-source-batch-{batch}.mp4"
    receipt_path = _receipt_path(target)
    try:
        if target.is_symlink() or receipt_path.is_symlink() or not target.is_file() or not receipt_path.is_file():
            return _absent(request)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if type(receipt) is not dict or set(receipt) != {"request_id", "quote_token", "batch", "provider", "model", "video_path", "video_sha256", "segments", "regenerable"}:
            return _absent(request)
        if any(receipt.get(key) != request.get(key) for key in ("request_id", "quote_token", "batch", "provider", "model")) or receipt.get("regenerable") is not False:
            return _absent(request)
        if Path(str(receipt["video_path"])).resolve() != target.resolve() or not _hash_ok(receipt.get("video_sha256")) or _hash_file(target, "video_invalid") != receipt["video_sha256"] or not _valid_segments(receipt.get("segments"), batch):
            return _absent(request)
        return {"request_id": request["request_id"], "quote_token": request["quote_token"], "batch": batch, "provider": PROVIDER, "model": MODEL,
                "status": "completed", "actual_cost_usd": "0", "regenerable": False, "video_path": str(target.resolve()),
                "video_sha256": receipt["video_sha256"], "segments": receipt["segments"]}
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, NativeError):
        return _absent(request)


def _handle(request: object) -> dict[str, object]:
    if type(request) is not dict:
        raise NativeError("request_invalid")
    operation = request.get("operation")
    if operation == "quote":
        batch = _validate_request(request, "quote", COMMON_KEYS)
        _motions(request["motions"], batch)
        request_id = _request_id(request)
        return {"request_id": request_id, "quote_token": _quote_token(request, request_id), "batch": batch, "provider": PROVIDER,
                "model": MODEL, "quoted_cost_usd": "0", "expires_at": QUOTE_EXPIRY, "regenerable": False}
    if operation == "generate":
        return _generate(request)
    if operation == "reconcile":
        return _reconcile(request)
    raise NativeError("operation_invalid")


def main() -> int:
    try:
        result = _handle(json.loads(sys.stdin.read()))
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0
    except NativeError as exc:
        sys.stdout.write(json.dumps({"error": exc.code}, separators=(",", ":")) + "\n")
        return 1
    except (json.JSONDecodeError, UnicodeDecodeError):
        sys.stdout.write('{"error":"request_invalid"}\n')
        return 1
    except Exception:
        sys.stdout.write('{"error":"internal_error"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
