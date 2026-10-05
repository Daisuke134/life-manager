"""Contract tests for the deterministic LINE animated-sticker package validator."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile
import zlib


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import line_sticker as MODULE  # noqa: E402  # RED: module is created by the implementation step


POLICY = MODULE_ROOT / "official-policy.json"
PNG_NAMES = ["main.png", "tab.png"] + [f"{n:02d}.png" for n in range(1, 25)]


def _chunk(kind: str, payload: bytes) -> bytes:
    raw_kind = kind.encode("ascii")
    body = raw_kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _png(
    width: int,
    height: int,
    *,
    animated: bool,
    frames: int = 5,
    plays: int = 1,
    color_type: int = 6,
    delay_num: int = 20,
    delay_den: int = 100,
    marker: str = "",
    extra_chunks: list[tuple[str, bytes]] | None = None,
    after_idat_chunks: list[tuple[str, bytes]] | None = None,
    frame_dimensions: list[tuple[int, int]] | None = None,
    actl_after_idat: bool = False,
) -> bytes:
    chunks = [b"\x89PNG\r\n\x1a\n"]
    chunks.append(_chunk("IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)))
    for kind, payload in extra_chunks or []:
        chunks.append(_chunk(kind, payload))
    if animated and not actl_after_idat:
        chunks.append(_chunk("acTL", struct.pack(">II", frames, plays)))
        sequence = 0
        for frame in range(frames):
            frame_width, frame_height = (
                frame_dimensions[frame] if frame_dimensions is not None else (width, height)
            )
            chunks.append(
                _chunk(
                    "fcTL",
                    struct.pack(">IIIIIHHBB", sequence, frame_width, frame_height, 0, 0, delay_num, delay_den, 0, 0),
                )
            )
            sequence += 1
            if frame == 0:
                chunks.append(_chunk("IDAT", zlib.compress(b"\x00\x00\x00\x00")))
            else:
                chunks.append(_chunk("fdAT", struct.pack(">I", sequence) + zlib.compress(b"\x00\x00\x00\x00")))
                sequence += 1
    else:
        chunks.append(_chunk("IDAT", zlib.compress(b"\x00\x00\x00\x00")))
    if animated and actl_after_idat:
        chunks.append(_chunk("acTL", struct.pack(">II", frames, plays)))
    for kind, payload in after_idat_chunks or []:
        chunks.append(_chunk(kind, payload))
    if marker:
        chunks.append(_chunk("tEXt", b"asset=" + marker.encode("ascii")))
    chunks.append(_chunk("IEND", b""))
    return b"".join(chunks)


def _write_fake_ffmpeg(
    path: Path,
    *,
    enclosed_hole: bool = False,
    opaque_background: bool = False,
    opaque_background_name: str | None = None,
    later_hole: bool = False,
    identical_frames: bool = False,
    identical_frames_name: str | None = None,
    extra_frame: bool = False,
) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import struct, sys\n"
        "input_path = Path(sys.argv[sys.argv.index('-i') + 1])\n"
        "data = input_path.read_bytes()\n"
        "width, height = struct.unpack('>II', data[16:24])\n"
        "frame_count = int(sys.argv[sys.argv.index('-frames:v') + 1])\n"
        "output_path = Path(sys.argv[-1])\n"
        "frames = []\n"
        "for frame in range(frame_count):\n"
        "    pixels = bytearray(b'\\xff' * (width * height * 4))\n"
        + (
            "    if not (" + repr(opaque_background) + " or input_path.name == " + repr(opaque_background_name) + "):\n"
            "        for x in range(width):\n"
            "            pixels[(x * 4) + 3] = 0\n"
            "            pixels[((height - 1) * width + x) * 4 + 3] = 0\n"
            "        for y in range(height):\n"
            "            pixels[(y * width) * 4 + 3] = 0\n"
            "            pixels[(y * width + width - 1) * 4 + 3] = 0\n"
            if True
            else ""
        )
        + (
            "    if not (" + repr(identical_frames) + " or input_path.name == " + repr(identical_frames_name) + "):\n"
            "        center = ((height // 2) * width + (width // 2)) * 4\n"
            "        pixels[center] = frame % 255\n"
            if True
            else ""
        )
        + (
            "    if input_path.name == '01.png' and " + repr(enclosed_hole) + " and frame == 0:\n"
            "        pixels[((height // 2) * width + (width // 2)) * 4 + 3] = 0\n"
            if enclosed_hole
            else ""
        )
        + (
            "    if input_path.name == '01.png' and " + repr(later_hole) + " and frame == 1:\n"
            "        pixels[((height // 2) * width + (width // 2)) * 4 + 3] = 0\n"
            if later_hole
            else ""
        )
        + "    frames.append(bytes(pixels))\n"
        + "output = b''.join(frames)\n"
        + ("output += frames[-1]\n" if extra_frame else "")
        + "(sys.stdout.buffer.write(output) if str(output_path) == '-' else output_path.write_bytes(output))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_zip(root: Path, names: list[str] | None = None) -> None:
    names = names or PNG_NAMES
    with zipfile.ZipFile(root / "submission.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, (root / name).read_bytes())


def _write_provenance(root: Path) -> None:
    assets = {}
    prompt_hashes = {}
    for name in PNG_NAMES:
        contents = (root / name).read_bytes()
        assets[name] = {
            "sha256": _sha256(contents),
            "intentional_alpha_holes": [],
        }
        prompt_hashes[name] = _sha256(("prompt:" + name).encode("ascii"))
    digest = "a" * 64
    generation = {
        "rights_evidence": {"receipt_sha256": "", "set_id": "set-20260828-001", "character_id": "char-001", "character_sha256": digest, "creation_source": "fixture", "rights": "original_ai_generated"},
        "character_sha256": digest,
        "plan_sha256": digest,
        "selection_sha256": digest,
        "prompt_sha256": digest,
        "model": "fixture-model",
        "provider": "fixture-provider",
        "reserved_cost_usd": "0.06",
        "actual_cost_usd": "0.06",
        "batches": {
            str(batch): {"quote_request_id": f"quote-{batch}", "generation_request_id": f"quote-{batch}", "quote_token": f"token-{batch}", "provider": "fixture-provider", "model": "fixture-model", "reserved_cost_usd": "0.01", "actual_cost_usd": "0.01", "source_sha256": digest, "regenerable": True}
            for batch in range(1, 7)
        },
        "candidate_bindings": {
            f"{index:02d}.png": {"motion_id": f"motion-{index:02d}", "source_sha256": digest, "segment": {"motion_id": f"motion-{index:02d}", "start_ms": 0, "end_ms": 500}, "candidate_sha256": assets[f"{index:02d}.png"]["sha256"], "conversion_argv_sha256": digest, "asset_sha256": assets[f"{index:02d}.png"]["sha256"]}
            for index in range(1, 25)
        },
    }
    generation["rights_evidence"]["receipt_sha256"] = _sha256(json.dumps({key: generation["rights_evidence"][key] for key in ("set_id", "character_id", "character_sha256", "creation_source", "rights")}, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    generation["generation_sha256"] = _sha256(json.dumps(generation, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    (root / "provenance.json").write_text(
        json.dumps(
            {
                "set_id": "set-20260828-001",
                "character_id": "char-001",
                "rights": "original_ai_generated",
                "providers": {"image": "openai", "animation": "fixture-provider"},
                "prompt_hashes": prompt_hashes,
                "assets": assets,
                "generation": generation,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _refresh_package(root: Path) -> None:
    _write_provenance(root)
    _write_zip(root)


def _rehash_generation(root: Path) -> dict[str, object]:
    provenance = json.loads((root / "provenance.json").read_text())
    generation = provenance["generation"]
    generation.pop("generation_sha256")
    generation["generation_sha256"] = _sha256(json.dumps(generation, sort_keys=True, separators=(",", ":")).encode())
    (root / "provenance.json").write_text(json.dumps(provenance, sort_keys=True) + "\n")
    return provenance


def _make_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.png").write_bytes(_png(240, 240, animated=True, marker="main"))
    (root / "tab.png").write_bytes(_png(96, 74, animated=False, marker="tab"))
    for number in range(1, 25):
        name = f"{number:02d}.png"
        (root / name).write_bytes(_png(270, 270, animated=True, marker=name))
    _refresh_package(root)
    return root


def _copy_policy(root: Path, *, observed_at: str) -> Path:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["observed_at"] = observed_at
    path = root.parent / "policy.json"
    path.write_text(json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _replace_asset(root: Path, name: str, contents: bytes, *, refresh: bool = True) -> None:
    (root / name).write_bytes(contents)
    if refresh:
        _refresh_package(root)


def _corrupt_crc(contents: bytes) -> bytes:
    data = bytearray(contents)
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = bytes(data[offset + 4 : offset + 8])
        crc_offset = offset + 8 + length
        if kind == b"IDAT":
            data[crc_offset + 3] ^= 0x01
            return bytes(data)
        offset = crc_offset + 4
    raise AssertionError("fixture has no IDAT chunk")


def _with_zip_entries(root: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(root / "submission.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for name, contents in entries.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, contents)


def _generate_real_apng(path: Path, width: int, height: int, seed: int = 1) -> None:
    generated = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"nullsrc=size={width}x{height}:rate=5,format=rgba,geq=r='mod(X+Y+{seed}+N*17,256)':g='mod(X*2+Y+{seed}+N*29,256)':b='mod(X+Y*2+{seed}+N*43,256)':a='if(eq(X,0)+eq(X,W-1)+eq(Y,0)+eq(Y,H-1),0,255)'",
            "-frames:v",
            "5",
            "-plays",
            "1",
            "-f",
            "apng",
            str(path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if generated.returncode:
        raise AssertionError(generated.stderr.decode(errors="replace"))


def _generate_real_png(path: Path, width: int, height: int) -> None:
    generated = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black@0.0:s={width}x{height},format=rgba",
            "-frames:v",
            "1",
            "-f",
            "image2",
            str(path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if generated.returncode:
        raise AssertionError(generated.stderr.decode(errors="replace"))


def _corrupt_fdat_payload(contents: bytes) -> bytes:
    data = bytearray(contents)
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = bytes(data[offset + 4 : offset + 8])
        if kind == b"fdAT" and length > 5:
            payload_start = offset + 8
            data[payload_start + 4 : payload_start + length] = b"\x00" * (length - 4)
            crc_body = bytes(data[offset + 4 : payload_start + length])
            data[payload_start + length : payload_start + length + 4] = struct.pack(
                ">I", zlib.crc32(crc_body) & 0xFFFFFFFF
            )
            return bytes(data)
        offset += length + 12
    raise AssertionError("fixture has no fdAT chunk")


class LineStickerValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        previous = getattr(self, "tempdir", None)
        if previous is not None:
            previous.cleanup()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = _make_package(Path(self.tempdir.name) / "package")
        self.ffmpeg = _write_fake_ffmpeg(Path(self.tempdir.name) / "ffmpeg")

    def tearDown(self) -> None:
        current = getattr(self, "tempdir", None)
        if current is not None:
            current.cleanup()
            self.tempdir = None

    def _validate(self, *, policy: Path = POLICY, ffmpeg: Path | None = None) -> dict[str, object]:
        return MODULE.validate_package(self.root, policy, ffmpeg=str(ffmpeg or self.ffmpeg))

    def test_official_policy_is_exact_snapshot(self) -> None:
        self.assertEqual(
            json.loads(POLICY.read_text(encoding="utf-8")),
            {
                "version": 1,
                "source_url": "https://creator.line.me/en/guideline/animationsticker/",
                "observed_at": "2026-08-28",
                "max_policy_age_days": 30,
                "sticker_count": 24,
                "main": {"width": 240, "height": 240, "animated": True},
                "tab": {"width": 96, "height": 74, "animated": False},
                "sticker": {"max_width": 320, "max_height": 270, "required_side": 270},
                "apng": {
                    "min_frames": 5,
                    "max_frames": 20,
                    "min_plays": 1,
                    "max_plays": 4,
                    "max_duration_ms": 4000,
                },
                "max_file_bytes": 1000000,
                "max_zip_bytes": 60000000,
                "required_color_types": [4, 6],
            },
        )

    def test_valid_package_is_ready_and_identity_is_stable(self) -> None:
        first = self._validate()
        second = self._validate()
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["effect"], 0)
        self.assertEqual(first["readback"], 0)
        self.assertEqual(len(first["files"]), 26)
        self.assertRegex(first["package_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first, second)
        self.assertEqual([entry["name"] for entry in first["files"]], sorted(PNG_NAMES))

    def test_generation_batch_contract_rejects_cost_identity_and_source_mismatches(self) -> None:
        variants = {
            "negative": lambda g: g["batches"]["1"].update({"actual_cost_usd": "-1"}),
            "overrun": lambda g: g["batches"]["1"].update({"actual_cost_usd": "0.02"}),
            "request": lambda g: g["batches"]["1"].update({"generation_request_id": "other"}),
            "provider": lambda g: g["batches"]["1"].update({"provider": "other"}),
            "top_provider": lambda g: g.update({"provider": "other"}),
            "wrong_batch_source": lambda g: (g["batches"]["2"].update({"source_sha256": "b" * 64}), g["candidate_bindings"]["01.png"].update({"source_sha256": "b" * 64})),
            "batch_list": lambda g: g["batches"].update({"1": []}),
            "batch_null": lambda g: g["batches"].update({"1": None}),
            "batch_string": lambda g: g["batches"].update({"1": "invalid"}),
            "unsafe_motion_id": lambda g: g["candidate_bindings"]["01.png"].update({"motion_id": "junk-01", "segment": {"motion_id": "junk-01", "start_ms": 0, "end_ms": 500}}),
            "unpadded_motion_id": lambda g: g["candidate_bindings"]["01.png"].update({"motion_id": "motion-1", "segment": {"motion_id": "motion-1", "start_ms": 0, "end_ms": 500}}),
        }
        for label, mutate in variants.items():
            with self.subTest(label=label):
                _refresh_package(self.root)
                provenance = json.loads((self.root / "provenance.json").read_text())
                mutate(provenance["generation"])
                generation = provenance["generation"]; generation.pop("generation_sha256")
                generation["generation_sha256"] = _sha256(json.dumps(generation, sort_keys=True, separators=(",", ":")).encode())
                (self.root / "provenance.json").write_text(json.dumps(provenance, sort_keys=True) + "\n")
                self.assertIn("provenance_invalid", self._validate()["errors"])

    def test_non_mapping_providers_are_validation_errors(self) -> None:
        for providers in (None, [], "provider", 1):
            with self.subTest(providers=providers):
                provenance_path = self.root / "provenance.json"
                provenance = json.loads(provenance_path.read_text())
                provenance["providers"] = providers
                provenance_path.write_text(json.dumps(provenance) + "\n")
                self.assertIn("provenance_invalid", self._validate()["errors"])
                self.tearDown()
                self.setUp()

    def test_parse_png_reports_apng_fields_and_chunk_hashes(self) -> None:
        parsed = MODULE.parse_png(self.root / "01.png")
        self.assertEqual(parsed["width"], 270)
        self.assertEqual(parsed["height"], 270)
        self.assertEqual(parsed["color_type"], 6)
        self.assertTrue(parsed["animated"])
        self.assertEqual(parsed["frames"], 5)
        self.assertEqual(parsed["plays"], 1)
        self.assertEqual(parsed["duration_ms"], 1000)
        self.assertTrue(parsed["chunk_hashes"])

    def test_policy_schema_values_and_dates_are_fail_closed(self) -> None:
        variants = {
            "wrong value": lambda policy: policy["main"].update({"width": 1}),
            "wrong type": lambda policy: policy.update({"max_file_bytes": "1000000"}),
            "extra key": lambda policy: policy.update({"untrusted": True}),
            "missing key": lambda policy: policy.pop("required_color_types"),
        }
        for label, mutate in variants.items():
            with self.subTest(label=label):
                policy_path = self.root.parent / f"policy-{label.replace(' ', '-')}.json"
                policy = json.loads(POLICY.read_text(encoding="utf-8"))
                mutate(policy)
                policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "^policy_hash_mismatch$"):
                    MODULE.validate_package(self.root, policy_path, ffmpeg=str(self.ffmpeg))
        self.assertTrue(MODULE._policy_is_stale({"observed_at": "2999-01-01", "max_policy_age_days": 30}))

    def test_policy_uses_versioned_file_hash_trust_anchor(self) -> None:
        self.assertFalse(hasattr(MODULE, "OFFICIAL_POLICY"))
        self.assertEqual(MODULE.POLICY_SHA256_V1, _sha256(POLICY.read_bytes()))
        tampered = self.root.parent / "tampered-policy.json"
        tampered.write_bytes(POLICY.read_bytes().replace(b'"version": 1', b'"version": 2'))
        with self.assertRaisesRegex(ValueError, "^policy_hash_mismatch$"):
            MODULE.validate_package(self.root, tampered, ffmpeg=str(self.ffmpeg))

    def test_invalid_png_type_or_size_is_rejected_before_parse_and_ffmpeg(self) -> None:
        target = self.root / "01.png"
        target.unlink()
        target.symlink_to(self.root / "02.png")
        original_parse = MODULE.parse_png
        original_run = MODULE.subprocess.run

        def parse(path: Path) -> dict[str, object]:
            if Path(path).name == "01.png":
                raise AssertionError("non-regular PNG was parsed")
            return original_parse(path)

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if "-i" in command and Path(command[command.index("-i") + 1]).name == "01.png":
                raise AssertionError("non-regular PNG reached ffmpeg")
            return original_run(command, **kwargs)

        with mock.patch.object(MODULE, "parse_png", side_effect=parse), mock.patch.object(MODULE.subprocess, "run", side_effect=run):
            self.assertEqual(self._validate()["errors"], ["file_not_regular:01.png"])

    def test_oversized_png_skips_parse_and_ffmpeg(self) -> None:
        self._make_large_asset()
        original_parse = MODULE.parse_png
        original_run = MODULE.subprocess.run

        def parse(path: Path) -> dict[str, object]:
            if Path(path).name == "01.png":
                raise AssertionError("oversized PNG was parsed")
            return original_parse(path)

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if "-i" in command and Path(command[command.index("-i") + 1]).name == "01.png":
                raise AssertionError("oversized PNG reached ffmpeg")
            return original_run(command, **kwargs)

        with mock.patch.object(MODULE, "parse_png", side_effect=parse), mock.patch.object(MODULE.subprocess, "run", side_effect=run):
            self.assertEqual(self._validate()["errors"], ["file_too_large:01.png"])

    def test_invalid_dimensions_skip_ffmpeg(self) -> None:
        self._make_bad_dimensions()
        original_run = MODULE.subprocess.run

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if "-i" in command and Path(command[command.index("-i") + 1]).name == "01.png":
                raise AssertionError("invalid-dimension PNG reached ffmpeg")
            return original_run(command, **kwargs)

        with mock.patch.object(MODULE.subprocess, "run", side_effect=run):
            self.assertEqual(self._validate()["errors"], ["dimensions_invalid:01.png"])

    def test_acTL_must_precede_IDAT(self) -> None:
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, actl_after_idat=True, marker="01-actl-after"))
        self.assertEqual(self._validate()["errors"], ["png_apng_order_invalid:01.png"])

    def test_opaque_background_is_rejected(self) -> None:
        ffmpeg = _write_fake_ffmpeg(Path(self.tempdir.name) / "opaque-ffmpeg", opaque_background_name="01.png")
        self.assertEqual(self._validate(ffmpeg=ffmpeg)["errors"], ["alpha_background_missing:01.png"])

    def test_later_frame_unexpected_hole_is_rejected(self) -> None:
        ffmpeg = _write_fake_ffmpeg(Path(self.tempdir.name) / "later-hole-ffmpeg", later_hole=True)
        self.assertEqual(self._validate(ffmpeg=ffmpeg)["errors"], ["alpha_hole_unexpected:01.png"])

    def test_identical_decoded_frames_are_rejected(self) -> None:
        ffmpeg = _write_fake_ffmpeg(Path(self.tempdir.name) / "identical-ffmpeg", identical_frames_name="01.png")
        self.assertEqual(self._validate(ffmpeg=ffmpeg)["errors"], ["animation_static:01.png"])

    def test_later_frame_corrupt_payload_fails_real_decode(self) -> None:
        real_apng = Path(self.tempdir.name) / "corrupt-source.png"
        corrupt_apng = Path(self.tempdir.name) / "corrupt-later-frame.png"
        _generate_real_apng(real_apng, 270, 270, seed=81)
        corrupt_apng.write_bytes(_corrupt_fdat_payload(real_apng.read_bytes()))
        parsed = MODULE.parse_png(corrupt_apng)
        self.assertEqual(MODULE._decode_and_check_alpha(corrupt_apng, parsed, "ffmpeg", set()), "decode_failed")

    def test_complete_real_ffmpeg_package_is_ready(self) -> None:
        package = Path(self.tempdir.name) / "real-package"
        package.mkdir()
        _generate_real_apng(package / "main.png", 240, 240, seed=100)
        _generate_real_png(package / "tab.png", 96, 74)
        for number in range(1, 25):
            _generate_real_apng(package / f"{number:02d}.png", 270, 270, seed=100 + number * 3)
        _refresh_package(package)
        result = MODULE.validate_package(package, POLICY, ffmpeg="ffmpeg")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["errors"], [])

    def test_exact_file_limit_is_rejected(self) -> None:
        self._make_asset_at_limit()
        self.assertEqual(self._validate()["errors"], ["file_too_large:01.png"])

    def test_exact_zip_limit_is_rejected(self) -> None:
        with (self.root / "submission.zip").open("r+b") as stream:
            stream.truncate(60_000_000)
        self.assertEqual(self._validate()["errors"], ["zip_too_large"])

    def test_provenance_schema_and_hole_declarations_are_exact(self) -> None:
        variants = {
            "top-level unknown": lambda provenance: provenance.update({"unknown": True}),
            "asset unknown": lambda provenance: provenance["assets"]["01.png"].update({"unknown": True}),
            "hole missing": lambda provenance: provenance["assets"]["01.png"].pop("intentional_alpha_holes"),
            "hole malformed": lambda provenance: provenance["assets"]["01.png"].update({"intentional_alpha_holes": [{"x": "135", "y": 135}]}),
            "hole out of range": lambda provenance: provenance["assets"]["01.png"].update({"intentional_alpha_holes": [{"x": 270, "y": 135}]}),
            "hole unknown field": lambda provenance: provenance["assets"]["01.png"].update({"intentional_alpha_holes": [{"x": 135, "y": 135, "extra": 1}]}),
        }
        for label, mutate in variants.items():
            with self.subTest(label=label):
                provenance_path = self.root / "provenance.json"
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
                mutate(provenance)
                provenance_path.write_text(json.dumps(provenance) + "\n", encoding="utf-8")
                self.assertEqual(self._validate()["errors"], ["provenance_invalid"])
                self.tearDown()
                self.setUp()

    def test_rgba_palette_chunk_is_legal(self) -> None:
        _replace_asset(
            self.root,
            "01.png",
            _png(270, 270, animated=True, marker="01-plte", extra_chunks=[("PLTE", b"\x00\x00\x00")]),
        )
        self.assertEqual(self._validate()["status"], "ready")

    def test_rgba_trns_chunk_is_rejected(self) -> None:
        _replace_asset(
            self.root,
            "01.png",
            _png(270, 270, animated=True, marker="01-trns", extra_chunks=[("tRNS", b"\x00\x00")]),
        )
        self.assertEqual(self._validate()["errors"], ["png_trns_invalid:01.png"])

    def test_zip_declared_expansion_is_rejected_before_read(self) -> None:
        entries = {name: (self.root / name).read_bytes() for name in PNG_NAMES}
        entries["01.png"] = b"\x00" * 1_000_001
        _with_zip_entries(self.root, entries)
        self.assertEqual(self._validate()["errors"], ["zip_file_too_large:01.png"])

    def test_ffmpeg_timeout_is_a_stable_error(self) -> None:
        original_run = MODULE.subprocess.run

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            self.assertGreater(float(kwargs["timeout"]), 0)
            path = Path(command[command.index("-i") + 1])
            if path.name == "01.png":
                raise subprocess.TimeoutExpired(command, float(kwargs["timeout"]))
            return original_run(command, **kwargs)

        with mock.patch.object(MODULE.subprocess, "run", side_effect=run):
            self.assertEqual(self._validate()["errors"], ["decode_timeout:01.png"])

    def test_real_ffmpeg_generated_apng_decodes(self) -> None:
        real_apng = Path(self.tempdir.name) / "real.png"
        generated = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "nullsrc=size=270x270:rate=5,format=rgba,geq=r='random(1)*255':g='random(2)*255':b='random(3)*255':a='if(eq(X,0)+eq(X,W-1)+eq(Y,0)+eq(Y,H-1),0,255)'",
                "-frames:v",
                "5",
                "-plays",
                "1",
                "-f",
                "apng",
                str(real_apng),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr.decode(errors="replace"))
        parsed = MODULE.parse_png(real_apng)
        self.assertTrue(parsed["animated"])
        self.assertEqual(MODULE._decode_and_check_alpha(real_apng, parsed, "ffmpeg", set()), None)

    def test_fcTL_frame_dimensions_must_match(self) -> None:
        dimensions = [(270, 270), (269, 270), (269, 270), (269, 270), (269, 270)]
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, frame_dimensions=dimensions, marker="01-dimension-mismatch"))
        self.assertEqual(self._validate()["errors"], ["dimensions_invalid:01.png"])

    def test_plte_legality_is_exact(self) -> None:
        variants = {
            "gray-alpha": _png(270, 270, animated=True, color_type=4, extra_chunks=[("PLTE", b"\x00\x00\x00")], marker="01-plte-gray-alpha"),
            "zero-length": _png(270, 270, animated=True, extra_chunks=[("PLTE", b"")], marker="01-plte-zero"),
            "not-divisible": _png(270, 270, animated=True, extra_chunks=[("PLTE", b"\x00\x00\x00\x00")], marker="01-plte-four"),
            "too-many": _png(270, 270, animated=True, extra_chunks=[("PLTE", b"\x00" * 769)], marker="01-plte-large"),
            "after-idat": _png(270, 270, animated=True, after_idat_chunks=[("PLTE", b"\x00\x00\x00")], marker="01-plte-after"),
        }
        for label, contents in variants.items():
            with self.subTest(label=label):
                try:
                    _replace_asset(self.root, "01.png", contents)
                    self.assertEqual(self._validate()["errors"], ["png_palette_invalid:01.png"])
                finally:
                    self.tearDown()
                    self.setUp()

    def test_unknown_zip_bomb_is_bounded_before_read(self) -> None:
        entries = {name: (self.root / name).read_bytes() for name in PNG_NAMES}
        entries["unknown.bin"] = b"\x00" * 1_000_001
        _with_zip_entries(self.root, entries)
        original_read = MODULE.zipfile.ZipFile.read

        def read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, *args: object, **kwargs: object) -> bytes:
            if info.filename == "unknown.bin":
                raise AssertionError("unknown entry was decompressed before preflight")
            return original_read(archive, info, *args, **kwargs)

        with mock.patch.object(MODULE.zipfile.ZipFile, "read", autospec=True, side_effect=read):
            self.assertEqual(
                self._validate()["errors"],
                ["zip_file_too_large:unknown.bin", "zip_membership_mismatch"],
            )

    def test_cli_prints_one_json_object_and_returns_ready_exit_code(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_ROOT / "line_sticker.py"),
                "validate",
                "--package",
                str(self.root),
                "--policy",
                str(POLICY),
                "--ffmpeg",
                str(self.ffmpeg),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(set(("status", "effect", "readback", "set_id", "character_id", "artifact_sha256", "package_sha256", "files", "errors")), set(payload))
        self.assertNotIn("prompt:", completed.stdout)

    def test_every_cli_parse_error_is_one_stable_json_object(self) -> None:
        for arguments in ([], ["--help"], ["unknown"], ["validate"], ["validate", "--package"]):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(MODULE_ROOT / "line_sticker.py"), *arguments],
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(len(completed.stdout.splitlines()), 1)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["errors"], ["configuration_error"])
                self.assertNotIn(str(self.root), completed.stdout)
                self.assertNotIn("prompt:", completed.stdout)

    def test_cli_invalid_policy_is_stable_json_exit_two(self) -> None:
        invalid_policy = self.root.parent / "invalid-policy.json"
        invalid_policy.write_text('{"prompt": "do not leak"}\n', encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_ROOT / "line_sticker.py"),
                "validate",
                "--package",
                str(self.root),
                "--policy",
                str(invalid_policy),
                "--ffmpeg",
                str(self.ffmpeg),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        self.assertEqual(json.loads(completed.stdout)["errors"], ["policy_hash_mismatch"])
        self.assertNotIn("do not leak", completed.stdout)

    def test_fail_closed_mutations(self) -> None:
        mutations = {
            "policy_hash_mismatch": lambda: self._validate(policy=_copy_policy(self.root, observed_at="2026-01-01")),
            "package_membership_mismatch": lambda: self._add_extra_file(),
            "zip_membership_mismatch": lambda: self._add_zip_extra(),
            "zip_content_mismatch:01.png": lambda: self._add_zip_content_mismatch(),
            "provenance_missing": lambda: self._remove_provenance(),
            "provenance_hash_mismatch:01.png": lambda: self._change_provenance_hash(),
            "duplicate_asset:01.png:02.png": lambda: self._duplicate_asset(),
            "png_crc_invalid:01.png": lambda: self._corrupt_asset_crc(),
            "animation_required:01.png": lambda: self._make_static_asset(),
            "frame_count_invalid:01.png": lambda: self._make_short_animation(),
            "play_count_invalid:01.png": lambda: self._make_excessive_play_count(),
            "duration_invalid:01.png": lambda: self._make_long_animation(),
            "dimensions_invalid:01.png": lambda: self._make_bad_dimensions(),
            "color_type_invalid:01.png": lambda: self._make_bad_color_type(),
            "alpha_hole_unexpected:01.png": lambda: self._validate(ffmpeg=_write_fake_ffmpeg(Path(self.tempdir.name) / "hole-ffmpeg", enclosed_hole=True)),
            "file_too_large:01.png": lambda: self._make_large_asset(),
            "zip_too_large": lambda: self._make_large_zip(),
        }
        for expected, mutate in mutations.items():
            with self.subTest(expected=expected):
                try:
                    try:
                        result = mutate()
                    except ValueError as exc:
                        result = {"status": "error", "errors": [str(exc)]}
                    if result is None:
                        result = self._validate()
                    self.assertNotEqual(result["status"], "ready")
                    self.assertEqual(result["errors"], [expected])
                finally:
                    self.tearDown()
                    self.setUp()

    def test_declared_alpha_hole_is_allowed(self) -> None:
        provenance_path = self.root / "provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["assets"]["01.png"]["intentional_alpha_holes"] = [{"x": 135, "y": 135}]
        provenance_path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")
        self.assertEqual(self._validate(ffmpeg=_write_fake_ffmpeg(Path(self.tempdir.name) / "hole-ffmpeg", enclosed_hole=True))["status"], "ready")

    def _add_extra_file(self) -> None:
        (self.root / "extra.txt").write_text("unexpected", encoding="utf-8")

    def _add_zip_extra(self) -> None:
        entries = {name: (self.root / name).read_bytes() for name in PNG_NAMES}
        entries["extra.txt"] = b"unexpected"
        _with_zip_entries(self.root, entries)

    def _add_zip_content_mismatch(self) -> None:
        entries = {name: (self.root / name).read_bytes() for name in PNG_NAMES}
        entries["01.png"] = b"different zip bytes"
        _with_zip_entries(self.root, entries)

    def _remove_provenance(self) -> None:
        path = self.root / "provenance.json"
        provenance = json.loads(path.read_text(encoding="utf-8"))
        del provenance["prompt_hashes"]["01.png"]
        path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")

    def _change_provenance_hash(self) -> None:
        path = self.root / "provenance.json"
        provenance = json.loads(path.read_text(encoding="utf-8"))
        provenance["assets"]["01.png"]["sha256"] = "0" * 64
        path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")

    def _duplicate_asset(self) -> None:
        _replace_asset(self.root, "02.png", (self.root / "01.png").read_bytes())

    def _corrupt_asset_crc(self) -> None:
        _replace_asset(self.root, "01.png", _corrupt_crc((self.root / "01.png").read_bytes()))

    def _make_static_asset(self) -> None:
        _replace_asset(self.root, "01.png", _png(270, 270, animated=False, marker="01-static"))

    def _make_short_animation(self) -> None:
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, frames=4, marker="01-short"))

    def _make_excessive_play_count(self) -> None:
        _replace_asset(
            self.root,
            "01.png",
            _png(270, 270, animated=True, plays=5, delay_num=1, delay_den=100, marker="01-plays"),
        )

    def _make_long_animation(self) -> None:
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, delay_num=1000, delay_den=1000, marker="01-long"))

    def _make_bad_dimensions(self) -> None:
        _replace_asset(self.root, "01.png", _png(321, 270, animated=True, marker="01-wide"))

    def _make_bad_color_type(self) -> None:
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, color_type=2, marker="01-rgb"))

    def _make_large_asset(self) -> None:
        contents = bytearray((self.root / "01.png").read_bytes())
        iend = contents.rfind(b"IEND") - 4
        contents[iend:iend] = _chunk("tEXt", b"x" * 1_000_001)
        _replace_asset(self.root, "01.png", bytes(contents))

    def _make_asset_at_limit(self) -> None:
        contents = bytearray((self.root / "01.png").read_bytes())
        iend = contents.rfind(b"IEND") - 4
        payload_size = 1_000_000 - len(contents) - 12
        self.assertGreater(payload_size, 0)
        contents[iend:iend] = _chunk("tEXt", b"x" * payload_size)
        self.assertEqual(len(contents), 1_000_000)
        _replace_asset(self.root, "01.png", bytes(contents))

    def _make_large_zip(self) -> None:
        with (self.root / "submission.zip").open("r+b") as stream:
            stream.truncate(60_000_001)


class FakeProvider:
    """Small official inventory used by the durable owner contract tests."""

    def __init__(self, inventory: dict[str, object] | None = None) -> None:
        self.inventory = inventory if inventory is not None else {
            "status": "absent",
            "account_id": None,
            "set_id": None,
            "revision": None,
            "artifact_sha256": None,
            "product_id": None,
            "public_url": None,
        }
        self.submit_calls = 0
        self.release_calls = 0
        self.status = "absent"
        self.raise_on_submit = False
        self.raise_on_release = False

    def observe(self, identity: dict[str, object]) -> dict[str, object]:
        status = str(self.inventory.get("status", self.status))
        if status == "absent":
            return {
                "account_id": identity["account_id"],
                "set_id": identity["set_id"],
                "revision": identity["revision"],
                "artifact_sha256": identity["artifact_sha256"],
                "product_id": None,
                "status": "absent",
                "public_url": None,
            }
        return {
            "account_id": self.inventory.get("account_id", identity["account_id"]),
            "set_id": self.inventory.get("set_id", identity["set_id"]),
            "revision": self.inventory.get("revision", identity["revision"]),
            "artifact_sha256": self.inventory.get("artifact_sha256", identity["artifact_sha256"]),
            "product_id": self.inventory.get("product_id"),
            "status": status,
            "public_url": self.inventory.get("public_url"),
        }

    def submit(self, intent: dict[str, object]) -> dict[str, object]:
        self.submit_calls += 1
        self.status = "submitted"
        self.inventory.update(
            {
                "account_id": intent["account_id"],
                "set_id": intent["set_id"],
                "revision": intent["revision"],
                "artifact_sha256": intent["artifact_sha256"],
                "product_id": "123",
                "status": "submitted",
                "public_url": None,
            }
        )
        if self.raise_on_submit:
            raise RuntimeError("submit transport lost")
        return self.observe(intent)

    def release(self, intent: dict[str, object]) -> dict[str, object]:
        self.release_calls += 1
        self.status = "released"
        self.inventory.update(
            {
                "account_id": intent["account_id"],
                "set_id": intent["set_id"],
                "revision": intent["revision"],
                "artifact_sha256": intent["artifact_sha256"],
                "product_id": "123",
                "status": "released",
                "public_url": "https://store.line.me/stickershop/product/123/en",
            }
        )
        if self.raise_on_release:
            raise RuntimeError("release transport lost")
        return self.observe(intent)


class LineStickerOwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        previous = getattr(self, "tempdir", None)
        if previous is not None:
            previous.cleanup()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = _make_package(Path(self.tempdir.name) / "package")
        self.state = Path(self.tempdir.name) / "state"
        self.state.mkdir()
        self.ffmpeg = _write_fake_ffmpeg(Path(self.tempdir.name) / "ffmpeg")
        self.provider = FakeProvider()
        self.lock_root = Path(self.tempdir.name) / "locks"
        self.lock_patch = mock.patch.object(MODULE, "_canonical_lock_root", return_value=self.lock_root)
        self.lock_patch.start()

    def tearDown(self) -> None:
        patch = getattr(self, "lock_patch", None)
        if patch is not None:
            patch.stop()
        current = getattr(self, "tempdir", None)
        if current is not None:
            current.cleanup()
            self.tempdir = None

    def _wake(self, provider: FakeProvider | None = None, **kwargs: object) -> dict[str, object]:
        policy = kwargs.pop("policy", POLICY)
        return MODULE.wake_owner(
            self.state,
            self.root,
            policy,
            provider or self.provider,
            kwargs.pop("account_id", "acct-1"),
            kwargs.pop("revision", 1),
            ffmpeg=str(self.ffmpeg),
            **kwargs,
        )

    def test_submit_release_and_observe_only_replay_are_fenced(self) -> None:
        first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"]), ("WAITING_REVIEW", 1, 1))
        self.assertEqual(self.provider.submit_calls, 1)

        self.provider.inventory["status"] = "approved"
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("RELEASED", 1, 1))
        self.assertEqual(self.provider.release_calls, 1)

        third = self._wake()
        self.assertEqual(third["state"], "TERMINAL_PENDING_REPLAY")
        self.assertEqual(third["public_url"], "https://store.line.me/stickershop/product/123/en")

        fourth = self._wake()
        self.assertEqual((fourth["state"], fourth["effect"], fourth["duplicate_effect"]), ("CLOSED", 0, 0))
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (1, 1))

    def test_two_concurrent_wakes_have_one_submit_and_one_intent(self) -> None:
        shared_inventory: dict[str, object] = {
            "status": "absent",
            "account_id": None,
            "set_id": None,
            "revision": None,
            "artifact_sha256": None,
            "product_id": None,
            "public_url": None,
        }
        counters = {"submit": 0}
        counter_lock = threading.Lock()

        class SlowProvider(FakeProvider):
            def submit(self, intent: dict[str, object]) -> dict[str, object]:
                with counter_lock:
                    counters["submit"] += 1
                time.sleep(0.1)
                return super().submit(intent)

        providers = [SlowProvider(shared_inventory), SlowProvider(shared_inventory)]
        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []

        def wake(provider: FakeProvider) -> None:
            barrier.wait(timeout=5)
            results.append(self._wake(provider))

        threads = [threading.Thread(target=wake, args=(provider,)) for provider in providers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(counters["submit"], 1)
        self.assertEqual(sum(provider.submit_calls for provider in providers), 1)
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows].count("intent"), 1)
        self.assertEqual([row["outcome"] for row in rows].count("acknowledged"), 1)

    def test_provider_identity_and_shape_mismatches_fail_closed(self) -> None:
        self._wake()
        cases = {
            "account_id": "identity_mismatch:account_id",
            "set_id": "identity_mismatch:set_id",
            "revision": "identity_mismatch:revision",
            "artifact_sha256": "identity_mismatch:artifact_sha256",
            "product_id": "provider_mismatch:product_id",
            "status": "provider_status_invalid",
            "public_url": "provider_url_invalid",
        }
        for field, expected in cases.items():
            with self.subTest(field=field):
                provider = FakeProvider(self.provider.inventory.copy())
                if field in {"account_id", "set_id", "artifact_sha256", "product_id", "public_url"}:
                    provider.inventory[field] = "wrong"
                elif field == "revision":
                    provider.inventory[field] = 99
                else:
                    provider.inventory[field] = "invalid"
                result = self._wake(provider)
                self.assertEqual(result["reason"], expected)
                self.assertEqual(result["effect"], 0)

    def test_lost_submit_ack_reconciles_without_retry_after_restart(self) -> None:
        self.provider.raise_on_submit = True
        first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"]), ("RECONCILE_UNKNOWN", None, 0))
        self.assertIsNone(first["duplicate_effect"])
        self.assertEqual(self.provider.submit_calls, 1)

        restarted = FakeProvider(self.provider.inventory)
        second = self._wake(restarted)
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("WAITING_REVIEW", 0, 1))
        self.assertEqual(restarted.submit_calls, 0)
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "unknown", "acknowledged"])
        self.assertIsNone(rows[-1]["effect"])
        self.assertEqual(rows[-1]["readback"], 1)
        self.assertIsNone(rows[-1]["duplicate_effect"])
        ledger_before = (self.state / "effects.jsonl").read_bytes()
        third = self._wake(restarted)
        self.assertEqual((third["state"], third["effect"], third["readback"]), ("WAITING_REVIEW", 0, 0))
        self.assertEqual((self.state / "effects.jsonl").read_bytes(), ledger_before)

    def test_known_submit_unknown_product_reconciles_only_with_same_product(self) -> None:
        class PostObserveFails(FakeProvider):
            def submit(self, intent: dict[str, object]) -> dict[str, object]:
                self.submit_calls += 1
                self.inventory.update(
                    {
                        "account_id": intent["account_id"],
                        "set_id": intent["set_id"],
                        "revision": intent["revision"],
                        "artifact_sha256": intent["artifact_sha256"],
                        "product_id": "123",
                        "status": "submitted",
                        "public_url": None,
                    }
                )
                return FakeProvider.observe(self, intent)

            def observe(self, identity: dict[str, object]) -> dict[str, object]:
                if self.inventory["status"] == "absent":
                    return FakeProvider.observe(self, identity)
                raise RuntimeError("post-submit observe lost")

        provider = PostObserveFails()
        first = self._wake(provider)
        self.assertEqual((first["state"], first["effect"]), ("RECONCILE_UNKNOWN", None))
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["product_id"], "123")

        restarted = FakeProvider(provider.inventory)
        owner_before = (self.state / "owner.json").read_bytes()
        ledger_before = (self.state / "effects.jsonl").read_bytes()
        for status in ("absent", "draft"):
            with self.subTest(status=status):
                restarted.inventory["status"] = status
                if status == "absent":
                    restarted.inventory["product_id"] = None
                    restarted.inventory["public_url"] = None
                else:
                    restarted.inventory["product_id"] = "123"
                stayed = self._wake(restarted)
                self.assertEqual((stayed["state"], stayed["effect"], stayed["readback"]), ("RECONCILE_UNKNOWN", None, 0))
                self.assertEqual((provider.submit_calls, restarted.submit_calls), (1, 0))
                self.assertEqual(((self.state / "owner.json").read_bytes(), (self.state / "effects.jsonl").read_bytes()), (owner_before, ledger_before))
        restarted.inventory["status"] = "submitted"
        restarted.inventory["product_id"] = "123"
        second = self._wake(restarted)
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("WAITING_REVIEW", 0, 1))
        self.assertEqual(restarted.submit_calls, 0)
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["product_id"], "123")

        self.tearDown()
        self.setUp()
        provider = PostObserveFails()
        self._wake(provider)
        mismatched = FakeProvider(provider.inventory.copy())
        mismatched.inventory["product_id"] = "999"
        failed = self._wake(mismatched)
        self.assertEqual((failed["reason"], failed["effect"]), ("ledger_conflict", 0))

    def test_identity_uses_validator_provenance_snapshot_not_replaced_path(self) -> None:
        original_validate = MODULE.validate_package

        def replace_provenance(*args: object, **kwargs: object) -> dict[str, object]:
            result = original_validate(*args, **kwargs)
            provenance = json.loads((self.root / "provenance.json").read_text(encoding="utf-8"))
            provenance.update({"set_id": "replacement-set", "character_id": "replacement-character"})
            (self.root / "provenance.json").write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")
            return result

        with mock.patch.object(MODULE, "validate_package", side_effect=replace_provenance):
            result = self._wake()
        self.assertEqual(result["state"], "WAITING_REVIEW")
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual((owner["identity"]["set_id"], owner["identity"]["character_id"]), ("set-20260828-001", "char-001"))

    def test_submit_ack_requires_exact_owner_product_for_state_and_wake(self) -> None:
        self._wake()
        owner_path = self.state / "owner.json"
        ledger_path = self.state / "effects.jsonl"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["product_id"] = None
        owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
        owner_before = owner_path.read_bytes()
        ledger_before = ledger_path.read_bytes()
        completed = subprocess.run(
            [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual((completed.returncode, json.loads(completed.stdout)), (2, {"reason": "owner_state_conflict", "status": "error"}))
        wake = self._wake()
        self.assertEqual((wake["reason"], wake["effect"]), ("owner_state_conflict", 0))
        self.assertEqual((owner_path.read_bytes(), ledger_path.read_bytes()), (owner_before, ledger_before))

    def test_unknown_submit_resolution_ack_append_failure_recovers_without_retry(self) -> None:
        self.provider.raise_on_submit = True
        self._wake()
        original_append = MODULE._append_receipt
        failed = False

        def fail_resolution_ack(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "submit" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        self.provider.raise_on_submit = False
        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_resolution_ack):
            first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["reason"]), ("WAITING_REVIEW", 0, 1, "receipt_pending"))
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "WAITING_REVIEW")
        rows_before = (self.state / "effects.jsonl").read_bytes()
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("WAITING_REVIEW", 0, 1))
        self.assertEqual(self.provider.submit_calls, 1)
        self.assertNotEqual((self.state / "effects.jsonl").read_bytes(), rows_before)

    def test_unknown_release_resolution_ack_append_failure_recovers_without_retry(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self.provider.raise_on_release = True
        self._wake()
        original_append = MODULE._append_receipt
        failed = False

        def fail_resolution_ack(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "release" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        self.provider.raise_on_release = False
        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_resolution_ack):
            first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["reason"]), ("RELEASED", 0, 1, "receipt_pending"))
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "RELEASED")
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("RELEASED", 0, 1))
        self.assertEqual(self.provider.release_calls, 1)

    def test_lost_submit_ack_still_absent_never_retries(self) -> None:
        class StillAbsent(FakeProvider):
            def submit(self, intent: dict[str, object]) -> dict[str, object]:
                self.submit_calls += 1
                raise RuntimeError("submit transport lost before effect")

        provider = StillAbsent()
        first = self._wake(provider)
        second = self._wake(provider)
        self.assertEqual(first["state"], "RECONCILE_UNKNOWN")
        self.assertEqual(second["state"], "RECONCILE_UNKNOWN")
        self.assertIsNone(second["effect"])
        self.assertEqual(provider.submit_calls, 1)

    def test_missing_submit_unknown_receipt_is_restored_before_reconcile(self) -> None:
        original_append = MODULE._append_receipt
        failed = False

        def fail_unknown(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "submit" and value.get("outcome") == "unknown" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        self.provider.raise_on_submit = True
        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_unknown):
            first = self._wake()
        self.assertEqual(first["state"], "NEW")
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "RECONCILE_UNKNOWN")
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent"])
        self.provider.raise_on_submit = False
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("WAITING_REVIEW", 0, 1))
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "unknown", "acknowledged"])
        self.assertEqual(self.provider.submit_calls, 1)

    def test_missing_release_unknown_receipt_is_restored_before_reconcile(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self.provider.raise_on_release = True
        original_append = MODULE._append_receipt
        failed = False

        def fail_unknown(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "release" and value.get("outcome") == "unknown" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_unknown):
            first = self._wake()
        self.assertEqual(first["state"], "APPROVED")
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "RECONCILE_UNKNOWN")
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "acknowledged", "intent"])
        self.provider.raise_on_release = False
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("RELEASED", 0, 1))
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "acknowledged", "intent", "unknown", "acknowledged"])
        self.assertEqual(self.provider.release_calls, 1)

    def test_owner_and_receipts_have_stable_exact_shapes(self) -> None:
        first = self._wake()
        self.assertEqual(
            set(first),
            {"status", "state", "effect", "readback", "duplicate_effect", "effect_key", "product_id", "public_url", "reason"},
        )
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(set(owner), {"version", "identity", "state", "product_id", "public_url"})
        self.assertEqual(owner["version"], 1)
        self.assertEqual(owner["state"], "WAITING_REVIEW")
        self.assertEqual(set(owner["identity"]), {"account_id", "set_id", "character_id", "revision", "artifact_sha256", "package_sha256"})
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        expected_keys = {
            "receipt_id", "effect_key", "action", "account_id", "set_id", "revision", "artifact_sha256",
            "product_id", "before_status", "after_status", "effect", "readback", "duplicate_effect", "outcome",
        }
        self.assertTrue(all(set(row) == expected_keys for row in rows))
        self.assertEqual([row["outcome"] for row in rows], ["intent", "acknowledged"])
        expected_effect_key = _sha256(json.dumps({"account_id": "acct-1", "action": "submit", "revision": 1, "set_id": owner["identity"]["set_id"]}, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(first["effect_key"], expected_effect_key)

    def test_release_lost_ack_is_reconciled_without_release_retry(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self.provider.raise_on_release = True
        first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["duplicate_effect"]), ("RECONCILE_UNKNOWN", None, 0, None))
        self.assertEqual(self.provider.release_calls, 1)
        restarted = FakeProvider(self.provider.inventory)
        second = self._wake(restarted)
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("RELEASED", 0, 1))
        self.assertEqual(restarted.release_calls, 0)

    def test_closed_wakes_do_not_write_owner_or_ledger(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        owner_before = (self.state / "owner.json").read_bytes()
        ledger_before = (self.state / "effects.jsonl").read_bytes()
        fifth = self._wake()
        self.assertEqual((fifth["state"], fifth["effect"], fifth["duplicate_effect"]), ("CLOSED", 0, 0))
        self.assertEqual((self.state / "owner.json").read_bytes(), owner_before)
        self.assertEqual((self.state / "effects.jsonl").read_bytes(), ledger_before)
        sixth = self._wake()
        seventh = self._wake()
        self.assertEqual((sixth["state"], sixth["effect"], sixth["duplicate_effect"]), ("CLOSED", 0, 0))
        self.assertEqual((seventh["state"], seventh["effect"], seventh["duplicate_effect"]), ("CLOSED", 0, 0))
        self.assertEqual((self.state / "owner.json").read_bytes(), owner_before)
        self.assertEqual((self.state / "effects.jsonl").read_bytes(), ledger_before)

    def test_owner_identity_and_state_path_fail_closed(self) -> None:
        self._wake()
        wrong_account = self._wake(account_id="acct-2")
        self.assertEqual((wrong_account["reason"], wrong_account["effect"]), ("identity_mismatch:account_id", 0))
        owner_path = self.state / "owner.json"
        owner_path.unlink()
        owner_path.write_text("{", encoding="utf-8")
        malformed = self._wake()
        self.assertEqual((malformed["reason"], malformed["effect"]), ("owner_malformed", 0))

    def test_lock_symlink_fails_before_provider(self) -> None:
        target = Path(self.tempdir.name) / "outside-lock"
        target.write_text("", encoding="utf-8")
        identity = MODULE._identity_from_package(self.root, POLICY, "acct-1", 1, str(self.ffmpeg))
        lock_path = MODULE._canonical_lock_path(identity)
        lock_path.parent.mkdir(parents=True)
        lock_path.symlink_to(target)
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("lock_symlink", 0))
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (0, 0))

    def test_lock_nonregular_path_fails_before_provider(self) -> None:
        identity = MODULE._identity_from_package(self.root, POLICY, "acct-1", 1, str(self.ffmpeg))
        lock_path = MODULE._canonical_lock_path(identity)
        lock_path.parent.mkdir(parents=True)
        lock_path.mkdir()
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("lock_not_regular", 0))
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (0, 0))

    def test_canonical_lock_binds_identity_to_one_state_dir_and_rejects_replacement(self) -> None:
        self._wake()
        other_state = Path(self.tempdir.name) / "other-state"
        other_state.mkdir()
        other = MODULE.wake_owner(other_state, self.root, POLICY, self.provider, "acct-1", 1, ffmpeg=str(self.ffmpeg))
        self.assertEqual((other["reason"], other["effect"]), ("lock_state_dir_conflict", 0))
        self.assertEqual(self.provider.submit_calls, 1)

        identity = MODULE._identity_from_package(self.root, POLICY, "acct-1", 1, str(self.ffmpeg))
        lock_path = MODULE._canonical_lock_path(identity)
        lock_path.unlink()
        lock_path.write_text("{}\n", encoding="utf-8")
        replaced = self._wake()
        self.assertEqual((replaced["reason"], replaced["effect"]), ("lock_state_dir_conflict", 0))
        self.assertEqual(self.provider.submit_calls, 1)

    def test_submit_rehashes_zip_after_lock_before_effect(self) -> None:
        original_lock = MODULE._state_lock

        @contextmanager
        def replace_zip(state_dir: Path, identity: dict[str, object]):
            with original_lock(state_dir, identity):
                zip_path = self.root / "submission.zip"
                zip_path.write_bytes(zip_path.read_bytes() + b"changed-after-validation")
                yield

        with mock.patch.object(MODULE, "_state_lock", replace_zip):
            result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("artifact_changed", 0))
        self.assertEqual(self.provider.submit_calls, 0)

    def test_absent_after_submit_is_fail_closed_without_retry(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "absent"
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"], result["state"]), ("provider_absent_after_submit", 0, "WAITING_REVIEW"))
        self.assertEqual(self.provider.submit_calls, 1)

    def test_absent_after_release_unknown_is_fail_closed_without_retry(self) -> None:
        class NoEffectRelease(FakeProvider):
            def release(self, intent: dict[str, object]) -> dict[str, object]:
                self.release_calls += 1
                raise RuntimeError("release failed before effect")

        self._wake()
        self.provider.inventory["status"] = "approved"
        provider = NoEffectRelease(self.provider.inventory)
        unknown = self._wake(provider)
        self.assertEqual(unknown["state"], "RECONCILE_UNKNOWN")
        provider.inventory["status"] = "absent"
        result = self._wake(provider)
        self.assertEqual((result["reason"], result["effect"]), ("provider_absent_after_submit", 0))
        self.assertEqual(provider.release_calls, 1)

    def test_submit_ack_append_failure_leaves_state_ahead_and_recovers(self) -> None:
        original_append = MODULE._append_receipt
        failed = False

        def fail_submit_ack(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "submit" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_submit_ack):
            first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["reason"]), ("WAITING_REVIEW", 1, 1, "receipt_pending"))
        self.assertEqual(self.provider.submit_calls, 1)
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "WAITING_REVIEW")
        rows_before = (self.state / "effects.jsonl").read_bytes()
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("WAITING_REVIEW", 0, 1))
        self.assertEqual(self.provider.submit_calls, 1)
        self.assertNotEqual((self.state / "effects.jsonl").read_bytes(), rows_before)
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "acknowledged"])

    def test_release_ack_append_failure_leaves_state_ahead_and_recovers(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        original_append = MODULE._append_receipt
        failed = False

        def fail_release_ack(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "release" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_release_ack):
            first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["reason"]), ("RELEASED", 1, 1, "receipt_pending"))
        self.assertEqual(self.provider.release_calls, 1)
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "RELEASED")
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("RELEASED", 0, 1))
        self.assertEqual(self.provider.release_calls, 1)
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["intent", "acknowledged", "intent", "acknowledged"])

    def test_replay_receipt_append_failure_leaves_closed_state_and_recovers(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        original_append = MODULE._append_receipt
        failed = False

        def fail_replay(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "replay" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_replay):
            first = self._wake()
        self.assertEqual((first["state"], first["effect"], first["readback"], first["reason"]), ("TERMINAL_PENDING_REPLAY", 0, 1, "receipt_pending"))
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["state"], "TERMINAL_PENDING_REPLAY")
        rows = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        replay_rows = [row for row in rows if row["action"] == "replay"]
        self.assertEqual(len(replay_rows), 0)
        second = self._wake()
        self.assertEqual((second["state"], second["effect"], second["readback"]), ("CLOSED", 0, 1))
        rows_after = [json.loads(line) for line in (self.state / "effects.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len([row for row in rows_after if row["action"] == "replay"]), 1)
        owner_before = (self.state / "owner.json").read_bytes()
        ledger_before = (self.state / "effects.jsonl").read_bytes()
        third = self._wake()
        fourth = self._wake()
        self.assertEqual((third["state"], fourth["state"]), ("CLOSED", "CLOSED"))
        self.assertEqual((self.state / "owner.json").read_bytes(), owner_before)
        self.assertEqual((self.state / "effects.jsonl").read_bytes(), ledger_before)

    def test_ledger_ahead_owner_below_acknowledgement_is_conflict(self) -> None:
        self._wake()
        owner_path = self.state / "owner.json"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["state"] = "NEW"
        owner["product_id"] = None
        owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
        before = owner_path.read_bytes()
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("owner_state_conflict", 0))
        self.assertEqual(owner_path.read_bytes(), before)
        self.assertEqual(self.provider.submit_calls, 1)

    def test_submit_state_ahead_reconciles_review_progress_without_resubmit(self) -> None:
        for status, expected_state in (("submitted", "WAITING_REVIEW"), ("rejected", "REJECTED"), ("approved", "APPROVED")):
            with self.subTest(status=status):
                if status != "submitted":
                    self.tearDown()
                    self.setUp()
                original_append = MODULE._append_receipt
                failed = False

                def fail_submit_ack(path: Path, value: dict[str, object]) -> None:
                    nonlocal failed
                    if value.get("action") == "submit" and value.get("outcome") == "acknowledged" and not failed:
                        failed = True
                        raise MODULE.OwnerStateError("injected_receipt_write_failure")
                    original_append(path, value)

                with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_submit_ack):
                    first = self._wake()
                self.assertEqual(first["state"], "WAITING_REVIEW")
                self.provider.inventory["status"] = status
                self.provider.inventory["public_url"] = None
                second = self._wake()
                self.assertEqual((second["state"], second["effect"], second["readback"]), (expected_state, 0, 1))
                self.assertEqual(self.provider.submit_calls, 1)

    def test_submit_state_ahead_released_without_release_intent_is_conflict(self) -> None:
        original_append = MODULE._append_receipt
        failed = False

        def fail_submit_ack(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if value.get("action") == "submit" and value.get("outcome") == "acknowledged" and not failed:
                failed = True
                raise MODULE.OwnerStateError("injected_receipt_write_failure")
            original_append(path, value)

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_submit_ack):
            self._wake()
        self.provider.inventory.update(
            {
                "status": "released",
                "public_url": "https://store.line.me/stickershop/product/123/en",
            }
        )
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("provider_state_conflict", 0))
        self.assertEqual(self.provider.submit_calls, 1)

    def test_unknown_submit_reconciles_review_states_but_rejects_released_before_ack(self) -> None:
        for status, expected_state in (("submitted", "WAITING_REVIEW"), ("rejected", "REJECTED"), ("approved", "APPROVED")):
            with self.subTest(status=status):
                self.provider.raise_on_submit = True
                self._wake()
                self.provider.raise_on_submit = False
                self.provider.inventory.update({"status": status, "public_url": None})
                result = self._wake()
                self.assertEqual((result["state"], result["effect"], result["readback"]), (expected_state, 0, 1))
                self.assertEqual(self.provider.submit_calls, 1)
                self.tearDown()
                self.setUp()

        self.provider.raise_on_submit = True
        self._wake()
        self.provider.inventory.update(
            {
                "status": "released",
                "public_url": "https://store.line.me/stickershop/product/123/en",
            }
        )
        owner_path = self.state / "owner.json"
        ledger_path = self.state / "effects.jsonl"
        owner_before = owner_path.read_bytes()
        ledger_before = ledger_path.read_bytes()
        append_calls = 0

        def fail_if_ack_appended(path: Path, value: dict[str, object]) -> None:
            nonlocal append_calls
            append_calls += 1
            raise MODULE.OwnerStateError("ack_append_reached")

        with mock.patch.object(MODULE, "_append_receipt", side_effect=fail_if_ack_appended):
            result = self._wake()
        self.assertEqual((result["reason"], result["effect"], result["state"]), ("provider_state_conflict", 0, "RECONCILE_UNKNOWN"))
        self.assertEqual(append_calls, 0)
        self.assertEqual((owner_path.read_bytes(), ledger_path.read_bytes()), (owner_before, ledger_before))
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (1, 0))

    def test_waiting_review_released_is_provider_state_conflict(self) -> None:
        self._wake()
        self.provider.inventory.update(
            {
                "status": "released",
                "public_url": "https://store.line.me/stickershop/product/123/en",
            }
        )
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"], result["state"]), ("provider_state_conflict", 0, "WAITING_REVIEW"))
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (1, 0))

    def test_acknowledged_without_intent_is_ledger_conflict(self) -> None:
        self._wake()
        ledger = self.state / "effects.jsonl"
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        ledger.write_text(json.dumps(rows[1], sort_keys=True) + "\n", encoding="utf-8")
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("ledger_conflict", 0))

    def test_acknowledged_before_unknown_is_ledger_conflict(self) -> None:
        self.provider.raise_on_submit = True
        self._wake()
        ledger = self.state / "effects.jsonl"
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        unknown = rows.pop()
        acknowledged = dict(rows[0])
        acknowledged["outcome"] = "acknowledged"
        acknowledged["effect"] = 1
        acknowledged["readback"] = 1
        acknowledged["duplicate_effect"] = 0
        acknowledged["receipt_id"] = "conflicting-ack"
        rows.append(acknowledged)
        rows.append(unknown)
        ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("ledger_conflict", 0))

    def test_released_url_must_bind_exact_product_path(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self.provider.inventory["public_url"] = "https://store.line.me/stickershop/product/999/en"
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("provider_url_invalid", 0))
        self.assertEqual(self.provider.release_calls, 1)

        self.provider.inventory["public_url"] = "https://store.line.me/stickershop/product/123/ja"
        replay_result = self._wake()
        self.assertEqual((replay_result["reason"], replay_result["effect"]), ("provider_url_mismatch", 0))
        self.assertEqual(self.provider.release_calls, 1)

    def test_owner_rollback_below_acknowledged_minimum_is_rejected(self) -> None:
        self._wake()
        owner_path = self.state / "owner.json"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["state"] = "NEW"
        owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
        before = owner_path.read_bytes()
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("owner_state_conflict", 0))
        self.assertEqual(owner_path.read_bytes(), before)
        self.assertEqual(self.provider.submit_calls, 1)

    def test_ledger_symlink_truncated_and_conflicting_rows_fail_closed(self) -> None:
        self._wake()
        ledger = self.state / "effects.jsonl"
        ledger_bytes = ledger.read_bytes()
        ledger.unlink()
        outside = Path(self.tempdir.name) / "outside-ledger"
        outside.write_bytes(ledger_bytes)
        ledger.symlink_to(outside)
        symlink_result = self._wake()
        self.assertEqual((symlink_result["reason"], symlink_result["effect"]), ("ledger_symlink", 0))

        ledger.unlink()
        ledger.write_bytes(b'{"truncated"')
        truncated_result = self._wake()
        self.assertEqual((truncated_result["reason"], truncated_result["effect"]), ("ledger_malformed", 0))

        ledger.write_bytes(ledger_bytes + ledger_bytes.splitlines(keepends=True)[1])
        conflict_result = self._wake()
        self.assertEqual((conflict_result["reason"], conflict_result["effect"]), ("ledger_duplicate", 0))

    def test_provider_observe_failure_is_fail_closed(self) -> None:
        class BrokenObserve(FakeProvider):
            def observe(self, identity: dict[str, object]) -> dict[str, object]:
                raise RuntimeError("provider unavailable")

        broken = BrokenObserve()
        result = self._wake(broken)
        self.assertEqual((result["reason"], result["effect"], result["state"]), ("provider_observe_failed", 0, "NEW"))
        self.assertEqual(broken.submit_calls, 0)

    def test_terminal_state_never_calls_provider_mutation(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        result = self._wake()
        self.assertEqual(result["state"], "CLOSED")
        self.assertEqual((self.provider.submit_calls, self.provider.release_calls), (1, 1))

    def test_closed_rollback_to_released_or_waiting_is_rejected_and_not_rewritten(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        for rollback in ("RELEASED", "WAITING_REVIEW"):
            with self.subTest(rollback=rollback):
                owner_path = self.state / "owner.json"
                ledger_path = self.state / "effects.jsonl"
                owner = json.loads(owner_path.read_text(encoding="utf-8"))
                owner["state"] = rollback
                owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
                owner_before = owner_path.read_bytes()
                ledger_before = ledger_path.read_bytes()
                result = self._wake()
                self.assertEqual((result["reason"], result["effect"]), ("owner_state_conflict", 0))
                self.assertEqual((owner_path.read_bytes(), ledger_path.read_bytes()), (owner_before, ledger_before))
                owner["state"] = "CLOSED"
                owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")

    def test_replay_ack_requires_closed_before_provider_observe(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        owner_path = self.state / "owner.json"
        for rollback in ("NEEDS_OWNER_CEREMONY", "NEEDS_POLICY_REVIEW", "RELEASED"):
            with self.subTest(rollback=rollback):
                owner = json.loads(owner_path.read_text(encoding="utf-8"))
                owner["state"] = rollback
                owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
                with mock.patch.object(self.provider, "observe", side_effect=AssertionError("provider observation reached")):
                    result = self._wake()
                self.assertEqual((result["reason"], result["effect"]), ("owner_state_conflict", 0))
                owner["state"] = "CLOSED"
                owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")

    def test_replay_receipt_terminal_crash_recovers_without_provider_mutation(self) -> None:
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        owner_path = self.state / "owner.json"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["state"] = "TERMINAL_PENDING_REPLAY"
        owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
        with mock.patch.object(self.provider, "observe", side_effect=AssertionError("provider observation reached")):
            result = self._wake()
        self.assertEqual((result["state"], result["effect"], result["readback"]), ("CLOSED", 0, 1))
        self.assertEqual(json.loads(owner_path.read_text(encoding="utf-8"))["state"], "CLOSED")

    def test_state_cli_returns_valid_summary_and_rejects_symlink(self) -> None:
        self._wake()
        completed = subprocess.run(
            [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0)
        summary = json.loads(completed.stdout)
        self.assertEqual((summary["status"], summary["state"], summary["outcome"]), ("ok", "WAITING_REVIEW", "acknowledged"))
        self.assertNotIn(str(self.state), completed.stdout)
        self.tearDown()
        self.setUp()
        self._wake()
        owner_path = self.state / "owner.json"
        replacement = self.state / "owner-copy.json"
        replacement.write_bytes(owner_path.read_bytes())
        owner_path.unlink()
        owner_path.symlink_to(replacement)
        bad = subprocess.run(
            [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout), {"reason": "owner_symlink", "status": "error"})

    def test_state_cli_rejects_action_mismatched_acknowledged_receipts(self) -> None:
        def state_cli() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        for state in ("RELEASED", "TERMINAL_PENDING_REPLAY", "CLOSED"):
            with self.subTest(receipt="submit", state=state):
                self._wake()
                owner_path = self.state / "owner.json"
                ledger_path = self.state / "effects.jsonl"
                owner = json.loads(owner_path.read_text(encoding="utf-8"))
                owner.update(
                    {
                        "state": state,
                        "public_url": "https://store.line.me/stickershop/product/123/en",
                    }
                )
                rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
                rows[-1] = MODULE._receipt(
                    owner["identity"],
                    action="submit",
                    product_id="123",
                    before_status="absent",
                    after_status="released",
                    outcome="acknowledged",
                )
                owner_path.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
                ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
                owner_before = owner_path.read_bytes()
                ledger_before = ledger_path.read_bytes()
                completed = state_cli()
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(json.loads(completed.stdout), {"reason": "ledger_conflict", "status": "error"})
                self.assertEqual((owner_path.read_bytes(), ledger_path.read_bytes()), (owner_before, ledger_before))
                self.tearDown()
                self.setUp()

        self.tearDown()
        self.setUp()
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        ledger_path = self.state / "effects.jsonl"
        rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        owner = json.loads((self.state / "owner.json").read_text(encoding="utf-8"))
        rows[-1] = MODULE._receipt(
            owner["identity"],
            action="release",
            product_id="123",
            before_status="approved",
            after_status="approved",
            outcome="acknowledged",
        )
        ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        release_completed = state_cli()
        self.assertEqual(release_completed.returncode, 2)
        self.assertEqual(json.loads(release_completed.stdout), {"reason": "ledger_conflict", "status": "error"})

    def test_state_cli_rejects_replay_acknowledgement_with_nonzero_effect(self) -> None:
        def state_cli() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.tearDown()
        self.setUp()
        self._wake()
        self.provider.inventory["status"] = "approved"
        self._wake()
        self._wake()
        self._wake()
        ledger_path = self.state / "effects.jsonl"
        rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        rows[-1]["effect"] = 1
        ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        replay_completed = state_cli()
        self.assertEqual(replay_completed.returncode, 2)
        self.assertEqual(json.loads(replay_completed.stdout), {"reason": "ledger_conflict", "status": "error"})

    def test_state_cli_binds_acknowledgement_before_status_to_action_history(self) -> None:
        def state_cli() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(self.state)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        for action, forged_before in (("submit", "approved"), ("release", "absent"), ("replay", "approved")):
            with self.subTest(action=action):
                self.tearDown()
                self.setUp()
                if action == "submit":
                    self._wake()
                elif action == "release":
                    self._wake()
                    self.provider.inventory["status"] = "approved"
                    self._wake()
                else:
                    self._wake()
                    self.provider.inventory["status"] = "approved"
                    self._wake()
                    self._wake()
                    self._wake()
                self.assertEqual(state_cli().returncode, 0)
                ledger_path = self.state / "effects.jsonl"
                rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
                acknowledged = rows[-1]
                rows[-1] = MODULE._receipt(
                    json.loads((self.state / "owner.json").read_text(encoding="utf-8"))["identity"],
                    action=action,
                    product_id=acknowledged["product_id"],
                    before_status=forged_before,
                    after_status=acknowledged["after_status"],
                    outcome="acknowledged",
                )
                ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
                completed = state_cli()
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(json.loads(completed.stdout), {"reason": "ledger_conflict", "status": "error"})

        self.tearDown()
        self.setUp()
        self.provider.raise_on_submit = True
        self._wake()
        self.provider.raise_on_submit = False
        resolved = self._wake()
        self.assertEqual((resolved["state"], resolved["effect"], resolved["readback"]), ("WAITING_REVIEW", 0, 1))
        self.assertEqual(state_cli().returncode, 0)

    def test_valid_package_bytes_changed_after_creation_are_rejected(self) -> None:
        self._wake()
        _replace_asset(self.root, "01.png", _png(270, 270, animated=True, marker="changed"))
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("artifact_changed", 0))
        self.assertEqual(self.provider.submit_calls, 1)

    def test_duplicate_ledger_row_is_rejected_without_provider_observe(self) -> None:
        self._wake()
        ledger = self.state / "effects.jsonl"
        original = ledger.read_bytes()
        ledger.write_bytes(original + original.splitlines(keepends=True)[0])
        observed = 0
        original_observe = self.provider.observe

        def observe(identity: dict[str, object]) -> dict[str, object]:
            nonlocal observed
            observed += 1
            return original_observe(identity)

        self.provider.observe = observe  # type: ignore[method-assign]
        result = self._wake()
        self.assertEqual((result["reason"], result["effect"]), ("ledger_duplicate", 0))
        self.assertEqual(observed, 0)

    def test_invalid_policy_is_a_stable_owner_error(self) -> None:
        invalid_policy = self.root.parent / "invalid-policy.json"
        invalid_policy.write_text('{"prompt":"do not leak"}\n', encoding="utf-8")
        result = self._wake(policy=invalid_policy)
        self.assertEqual((result["status"], result["state"], result["effect"], result["reason"]), ("error", "NEW", 0, "policy_hash_mismatch"))

    def test_state_cli_reports_uninitialized_without_creating_state(self) -> None:
        missing = Path(self.tempdir.name) / "missing"
        completed = subprocess.run(
            [sys.executable, str(MODULE_ROOT / "line_sticker.py"), "state", "--state-dir", str(missing)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout), {"status": "uninitialized", "effect": 0, "readback": 0})
        self.assertEqual(completed.stderr, "")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
