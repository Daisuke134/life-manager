"""Subprocess contract tests for the deterministic native animation provider."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib


MODULE_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = MODULE_ROOT / "native_animation.py"
SPEC = importlib.util.spec_from_file_location("native_animation", ADAPTER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _character_png() -> bytes:
    rows = []
    for y in range(512):
        row = bytearray(b"\x00")
        for x in range(512):
            row.extend((220, 30, 90, 255) if 180 <= x < 332 and 160 <= y < 352 else (0, 255, 0, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


MODEL_V2 = "whole-character-transforms-v2"


class NativeAnimationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="native-animation-test-")
        self.root = Path(self.temp.name)
        self.character = self.root / "character.png"
        self.character.write_bytes(_character_png())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, request: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ADAPTER)],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            cwd=self.root,
        )

    def _motions(self, batch: int = 1) -> list[dict[str, object]]:
        return [
            {
                "motion_id": f"motion-{(batch - 1) * 10 + index:02d}",
                "batch": batch,
                "position": index,
                "intent": f"intent {index}",
                "action": f"action {index}",
                "provider_prompt": f"ignored native prompt {index}",
                "duration_ms": 1000,
            }
            for index in range(1, 11)
        ]

    def _quote_request(self, batch: int = 1) -> dict[str, object]:
        return {
            "version": 1,
            "operation": "quote",
            "set_id": "set-1",
            "character_id": "char-1",
            "character_sha256": hashlib.sha256(self.character.read_bytes()).hexdigest(),
            "plan_sha256": "a" * 64,
            "batch": batch,
            "motions": self._motions(batch),
        }

    def _generate_request(self, quote: dict[str, object]) -> dict[str, object]:
        request = self._quote_request(int(quote["batch"]))
        request.update(
            {
                "operation": "generate",
                "character_path": str(self.character),
                "remaining_cap_usd": "0",
                "request_id": quote["request_id"],
                "quote_token": quote["quote_token"],
                "provider": quote["provider"],
                "model": quote["model"],
            }
        )
        return request

    def _reconcile_request(self, quote: dict[str, object]) -> dict[str, object]:
        return {
            "version": 1,
            "operation": "reconcile",
            "request_id": quote["request_id"],
            "quote_token": quote["quote_token"],
            "batch": quote["batch"],
            "provider": quote["provider"],
            "model": quote["model"],
        }

    def _json(self, process: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(process.stdout.count("\n"), 1, process.stdout)
        value = json.loads(process.stdout)
        self.assertIsInstance(value, dict)
        return value

    def test_quote_is_free_deterministic_and_does_not_create_source(self) -> None:
        request = self._quote_request()
        first_process = self._run(request)
        second_process = self._run(request)
        self.assertEqual(first_process.returncode, 0, first_process.stderr)
        self.assertEqual(second_process.returncode, 0, second_process.stderr)
        first = self._json(first_process)
        second = self._json(second_process)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {"request_id", "quote_token", "batch", "provider", "model", "quoted_cost_usd", "expires_at", "regenerable"},
        )
        self.assertEqual(first["provider"], "native-ffmpeg")
        self.assertEqual(first["model"], MODEL_V2)
        self.assertEqual(first["quoted_cost_usd"], "0")
        self.assertFalse(first["regenerable"])
        self.assertTrue(str(first["expires_at"]).endswith("Z"))
        self.assertFalse((self.root / "native-source-batch-1.mp4").exists())

    def test_generate_rejects_changed_character_hash_before_render(self) -> None:
        quote_process = self._run(self._quote_request())
        quote = self._json(quote_process)
        request = self._generate_request(quote)
        request["character_sha256"] = "0" * 64
        process = self._run(request)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self._json(process)["error"], "character_hash_mismatch")
        self.assertFalse((self.root / "native-source-batch-1.mp4").exists())

    def test_generate_returns_hashed_ten_segments_with_distinct_frames(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        process = self._run(self._generate_request(quote))
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self._json(process)
        self.assertEqual(result["provider"], "native-ffmpeg")
        self.assertEqual(result["model"], MODEL_V2)
        self.assertTrue(result["acknowledged"])
        self.assertFalse(result["regenerable"])
        self.assertEqual(result["actual_cost_usd"], "0")
        video = Path(str(result["video_path"]))
        self.assertTrue(video.is_absolute())
        self.assertEqual(video, (self.root / "native-source-batch-1.mp4").resolve())
        self.assertEqual(result["video_sha256"], hashlib.sha256(video.read_bytes()).hexdigest())
        self.assertEqual(
            result["segments"],
            [
                {"motion_id": f"motion-{index:02d}", "start_ms": (index - 1) * 1000, "end_ms": index * 1000}
                for index in range(1, 11)
            ],
        )
        frame_hashes = []
        for index in range(10):
            segment_hashes = []
            for offset in (0.1, 0.5, 0.9):
                frame = self.root / f"frame-{index}-{offset}.png"
                extracted = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ss", str(index + offset), "-frames:v", "1", str(frame)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(extracted.returncode, 0, extracted.stderr)
                segment_hashes.append(hashlib.sha256(frame.read_bytes()).hexdigest())
            frame_hashes.extend(segment_hashes)
            self.assertGreater(len(set(segment_hashes)), 1, f"segment {index} is static")
        self.assertGreater(len(set(frame_hashes)), 10)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_entries", "format=duration:stream=r_frame_rate,nb_frames,nb_read_frames", "-of", "json", str(video)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        metadata = json.loads(probe.stdout)
        self.assertAlmostEqual(float(metadata["format"]["duration"]), 10.0, places=1)
        stream = metadata["streams"][0]
        self.assertEqual(stream["r_frame_rate"], "24/1")
        self.assertEqual(int(stream.get("nb_frames") or stream["nb_read_frames"]), 240)
        for timestamp in (0.1, 0.5, 0.9, 3.5, 7.5, 9.5):
            chroma = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                capture_output=True,
            )
            self.assertEqual(chroma.returncode, 0, chroma.stderr.decode(errors="replace"))
            self.assertGreaterEqual(len(chroma.stdout), 512 * 512 * 3)
            for x, y in ((0, 0), (511, 0), (0, 511), (511, 511)):
                red, green, blue = chroma.stdout[(y * 512 + x) * 3:(y * 512 + x + 1) * 3]
                self.assertLess(red, 100, (timestamp, x, y))
                self.assertGreater(green, 170, (timestamp, x, y))
                self.assertLess(blue, 100, (timestamp, x, y))

    def test_batches_have_distinct_source_and_representative_frame_hashes(self) -> None:
        outputs = []
        for batch in (1, 2):
            quote = self._json(self._run(self._quote_request(batch)))
            process = self._run(self._generate_request(quote))
            self.assertEqual(process.returncode, 0, process.stderr)
            result = self._json(process)
            video = Path(str(result["video_path"]))
            representative = []
            for index in range(10):
                frame = self.root / f"representative-{batch}-{index}.png"
                extracted = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ss", str(index + 0.5), "-frames:v", "1", str(frame)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(extracted.returncode, 0, extracted.stderr)
                representative.append(hashlib.sha256(frame.read_bytes()).hexdigest())
            temporal = []
            for offset in (0.1, 0.5, 0.9):
                frame = self.root / f"temporal-{batch}-{offset}.png"
                extracted = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ss", str(offset), "-frames:v", "1", str(frame)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(extracted.returncode, 0, extracted.stderr)
                temporal.append(hashlib.sha256(frame.read_bytes()).hexdigest())
            self.assertGreater(len(set(temporal)), 1, batch)
            outputs.append((result["video_sha256"], set(representative)))
        self.assertNotEqual(outputs[0][0], outputs[1][0])
        self.assertTrue(outputs[0][1].isdisjoint(outputs[1][1]))

    def test_reconcile_requires_matching_source_and_sidecar(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        generated = self._json(self._run(self._generate_request(quote)))
        reconciled = self._run(self._reconcile_request(quote))
        self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
        result = self._json(reconciled)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["video_sha256"], generated["video_sha256"])

        video = Path(str(generated["video_path"]))
        original_video = video.read_bytes()
        video.write_bytes(video.read_bytes() + b"tampered")
        absent = self._run(self._reconcile_request(quote))
        self.assertEqual(absent.returncode, 0, absent.stderr)
        self.assertEqual(self._json(absent)["status"], "absent")

        video.write_bytes(original_video)
        real_video = self.root / "real-video.mp4"
        video.rename(real_video)
        video.symlink_to(real_video)
        source_link = self._run(self._reconcile_request(quote))
        self.assertEqual(source_link.returncode, 0, source_link.stderr)
        self.assertEqual(self._json(source_link)["status"], "absent")
        video.unlink()
        real_video.rename(video)
        receipt = Path(str(video) + ".receipt.json")
        real_receipt = self.root / "real-receipt.json"
        receipt.rename(real_receipt)
        receipt.symlink_to(real_receipt)
        receipt_link = self._run(self._reconcile_request(quote))
        self.assertEqual(receipt_link.returncode, 0, receipt_link.stderr)
        self.assertEqual(self._json(receipt_link)["status"], "absent")
        receipt.unlink()
        real_receipt.rename(receipt)

    def test_motion_schema_and_reconcile_segment_ids_are_exact(self) -> None:
        quote_request = self._quote_request()
        for mutation in ("missing", "extra"):
            request = json.loads(json.dumps(quote_request))
            if mutation == "missing":
                del request["motions"][0]["intent"]
            else:
                request["motions"][0]["unexpected"] = "not-authority"
            process = self._run(request)
            self.assertNotEqual(process.returncode, 0, mutation)
        quote = self._json(self._run(quote_request))
        generated = self._json(self._run(self._generate_request(quote)))
        sidecar = Path(str(generated["video_path"]) + ".receipt.json")
        receipt = json.loads(sidecar.read_text(encoding="utf-8"))
        receipt["segments"][0]["motion_id"] = "motion-02"
        sidecar.write_text(json.dumps(receipt), encoding="utf-8")
        reconciled = self._run(self._reconcile_request(quote))
        self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
        self.assertEqual(self._json(reconciled)["status"], "absent")

    def test_generate_refuses_conflicting_source_and_replays_matching_receipt(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        target = self.root / "native-source-batch-1.mp4"
        sentinel = self.root / "sentinel.mp4"
        sentinel.write_bytes(b"sentinel")
        target.symlink_to(sentinel)
        symlink_conflict = self._run(self._generate_request(quote))
        self.assertNotEqual(symlink_conflict.returncode, 0)
        self.assertTrue(target.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b"sentinel")
        target.unlink()
        target.write_bytes(b"conflicting-source")
        conflict = self._run(self._generate_request(quote))
        self.assertNotEqual(conflict.returncode, 0)
        self.assertEqual(target.read_bytes(), b"conflicting-source")
        target.unlink()
        generated = self._run(self._generate_request(quote))
        self.assertEqual(generated.returncode, 0, generated.stderr)
        result = self._json(generated)
        mtime = target.stat().st_mtime_ns
        replay = self._run(self._generate_request(quote))
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual(self._json(replay), result)
        self.assertEqual(target.stat().st_mtime_ns, mtime)

    def test_receipt_write_failure_recovers_same_request_without_overwrite(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        request = self._generate_request(quote)
        original = MODULE._atomic_json
        calls = 0

        def fail_receipt_after_journal(path: Path, value: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if path.name.endswith(".receipt.json"):
                raise MODULE.NativeError("receipt_write_failed")
            original(path, value)

        previous = Path.cwd()
        os.chdir(self.root)
        try:
            with mock.patch.object(MODULE, "_atomic_json", side_effect=fail_receipt_after_journal):
                with self.assertRaisesRegex(MODULE.NativeError, "receipt_write_failed"):
                    MODULE._generate(request)
        finally:
            os.chdir(previous)
        target = self.root / "native-source-batch-1.mp4"
        self.assertTrue(target.is_file())
        self.assertFalse(Path(str(target) + ".receipt.json").exists())
        retry = self._run(request)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(Path(str(target) + ".receipt.json").is_file())

    def test_stale_lock_recovers_but_live_lock_blocks_generation(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        request = self._generate_request(quote)
        lock = self.root / ".native-source-batch-1.lock"
        lock.write_bytes(b"stale")
        stale = self._run(request)
        self.assertEqual(stale.returncode, 0, stale.stderr)
        target = self.root / "native-source-batch-1.mp4"
        receipt = Path(str(target) + ".receipt.json")
        target.unlink()
        receipt.unlink()
        lock_fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            blocked = self._run(request)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        self.assertNotEqual(blocked.returncode, 0)
        recovered = self._run(request)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_generate_fsyncs_source_and_directories_before_ack(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        request = self._generate_request(quote)
        events: list[tuple[str, str]] = []
        real_replace = os.replace

        def fake_render(_request: dict[str, object], _source: Path, output: Path, _cwd: Path, _width: int, _height: int) -> None:
            output.write_bytes(b"rendered-source")

        def record_file(path: Path) -> None:
            events.append(("file_fsync", Path(path).name))

        def record_directory(path: Path) -> None:
            events.append(("dir_fsync", Path(path).name))

        def record_replace(source: str, target: str) -> None:
            events.append(("replace", Path(target).name))
            real_replace(source, target)

        previous = Path.cwd()
        os.chdir(self.root)
        try:
            with mock.patch.object(MODULE, "_render", side_effect=fake_render), \
                    mock.patch.object(MODULE, "_fsync_file", side_effect=record_file, create=True), \
                    mock.patch.object(MODULE, "_fsync_directory", side_effect=record_directory, create=True), \
                    mock.patch.object(MODULE.os, "replace", side_effect=record_replace):
                result = MODULE._generate(request)
        finally:
            os.chdir(previous)
        self.assertTrue(result["acknowledged"])
        source_replace = events.index(("replace", "native-source-batch-1.mp4"))
        receipt_replace = next(index for index, event in enumerate(events) if event[0] == "replace" and event[1].endswith(".receipt.json"))
        self.assertLess(events.index(("file_fsync", "source.mp4")), source_replace)
        self.assertLess(source_replace, next(index for index in range(source_replace + 1, receipt_replace) if events[index][0] == "dir_fsync"))
        commit_replace = next(index for index, event in enumerate(events) if event[0] == "replace" and event[1].endswith(".commit.json"))
        self.assertLess(commit_replace, source_replace)
        self.assertLess(commit_replace, next(index for index in range(commit_replace + 1, source_replace) if events[index][0] == "dir_fsync"))
        self.assertLess(receipt_replace, next(index for index in range(receipt_replace + 1, len(events)) if events[index][0] == "dir_fsync"))

    def test_orphan_valid_commit_journal_is_discarded_and_rerendered(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        request = self._generate_request(quote)
        target = self.root / "native-source-batch-1.mp4"
        commit = Path(str(target) + ".commit.json")
        journal = {
            "request_id": quote["request_id"],
            "quote_token": quote["quote_token"],
            "batch": 1,
            "provider": "native-ffmpeg",
            "model": MODEL_V2,
            "video_path": str(target.resolve()),
            "video_sha256": "b" * 64,
            "segments": [
                {"motion_id": f"motion-{index:02d}", "start_ms": (index - 1) * 1000, "end_ms": index * 1000}
                for index in range(1, 11)
            ],
            "regenerable": False,
        }
        commit.write_text(json.dumps(journal), encoding="utf-8")
        process = self._run(request)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(target.is_file())
        self.assertTrue(Path(str(target) + ".receipt.json").is_file())
        self.assertFalse(commit.exists())

    def test_orphan_commit_journal_with_wrong_identity_or_hash_fails_closed(self) -> None:
        quote = self._json(self._run(self._quote_request()))
        request = self._generate_request(quote)
        target = self.root / "native-source-batch-1.mp4"
        commit = Path(str(target) + ".commit.json")
        valid = {
            "request_id": quote["request_id"], "quote_token": quote["quote_token"], "batch": 1,
            "provider": "native-ffmpeg", "model": MODEL_V2, "video_path": str(target.resolve()),
            "video_sha256": "b" * 64,
            "segments": [
                {"motion_id": f"motion-{index:02d}", "start_ms": (index - 1) * 1000, "end_ms": index * 1000}
                for index in range(1, 11)
            ],
            "regenerable": False,
        }
        for field, value in (("request_id", "wrong"), ("quote_token", "wrong"), ("video_sha256", "not-a-hash")):
            journal = dict(valid)
            journal[field] = value
            commit.write_text(json.dumps(journal), encoding="utf-8")
            process = self._run(request)
            self.assertNotEqual(process.returncode, 0, field)
            self.assertTrue(commit.exists(), field)
            self.assertFalse(target.exists(), field)
            commit.unlink()


if __name__ == "__main__":
    unittest.main()
