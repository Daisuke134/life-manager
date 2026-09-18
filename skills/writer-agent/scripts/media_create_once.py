#!/usr/bin/env python3
"""Atomically promote one valid generated image into an immutable run path."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

class MediaCreateRefused(ValueError):
    """The immutable destination already belongs to another candidate."""


REQUIRED_ASSETS: list[dict[str, str]] = [
    {
        "kind": "headline",
        "destination": "headline-image.png",
        "receipt": "gates/headline-image-create.json",
    },
    {
        "kind": "body",
        "destination": "body-diagram.png",
        "receipt": "gates/body-diagram-create.json",
    },
]
X_RENDER_WIDTH = 587
X_BODY_MIN_HEIGHT = 110
X_BODY_MAX_HEIGHT = 650
HEADLINE_API_CANDIDATE = "gates/media-candidates/headline-gpt-image-2.png"
HEADLINE_API_RECEIPT = "gates/headline-image-api-receipt.json"


def _marker(version: int = 2) -> dict[str, object]:
    value: dict[str, object] = {
        "version": version,
        "status": "required",
        "assets": REQUIRED_ASSETS,
    }
    if version == 2:
        value["headline_api"] = {
            "candidate": HEADLINE_API_CANDIDATE,
            "receipt": HEADLINE_API_RECEIPT,
            "request_model": "gpt-image-2-2026-04-21",
        }
    return value


def _body_projection(descriptor: dict[str, object]) -> float:
    width = int(descriptor.get("width", 0) or 0)
    height = int(descriptor.get("height", 0) or 0)
    return round(X_RENDER_WIDTH * height / width, 2) if width else 0


def _descriptor_from_file(path: Path) -> dict[str, object]:
    # Arming happens before generation and must not require Pillow. Image decoding
    # is imported only for commit/verify, where valid pixel evidence is mandatory.
    from media_integrity import descriptor_from_file

    return descriptor_from_file(path)


def _pad_tall_body_candidate(path: Path) -> None:
    """Add transparent side margins so a readable diagram fits X's column.

    Mermaid's vertical layout can be narrow and tall even when its text is
    readable. Padding never enlarges or re-encodes the diagram content; it only
    gives the fixed 587px X column enough canvas width for the existing pixels.
    Too-flat candidates remain refused because padding cannot make their text
    readable.
    """
    descriptor = _descriptor_from_file(path)
    width = int(descriptor.get("width", 0) or 0)
    height = int(descriptor.get("height", 0) or 0)
    projected = _body_projection(descriptor)
    if projected <= X_BODY_MAX_HEIGHT or not width or not height:
        return
    from PIL import Image

    target_width = max(width, math.ceil(X_RENDER_WIDTH * height / X_BODY_MAX_HEIGHT))
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", (target_width, height), (255, 255, 255, 0))
    canvas.paste(image, ((target_width - width) // 2, 0), image)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pad")
    canvas.save(temporary, format="PNG")
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _install_independent_copy_once(source: Path, target: Path) -> None:
    """Atomically install bytes without leaving a mutable hard-link alias."""
    temporary = target.with_name(f".{target.name}.{os.getpid()}.media-tmp")
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.link(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def arm(run_dir: Path) -> dict[str, object]:
    run = run_dir.resolve(strict=True)
    gates = (run / "gates").resolve(strict=True)
    marker = gates / "media-create-required.json"
    payload = _marker()
    if marker.exists():
        try:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise MediaCreateRefused("media-create-marker-invalid") from error
        if recorded != payload:
            raise MediaCreateRefused("media-create-marker-mismatch")
        return payload
    _atomic_json(marker, payload)
    return payload


def _read_json(path: Path, reason: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise MediaCreateRefused(reason) from error
    if not isinstance(payload, dict):
        raise MediaCreateRefused(reason)
    return payload


def verify(run_dir: Path) -> dict[str, object]:
    run = run_dir.resolve(strict=True)
    marker = _read_json(
        run / "gates/media-create-required.json",
        "media-create-marker-invalid",
    )
    legacy = marker == _marker(1)
    if marker != _marker() and not legacy:
        raise MediaCreateRefused("media-create-marker-mismatch")
    headline_descriptor: dict[str, object] | None = None
    for asset in REQUIRED_ASSETS:
        destination = run / asset["destination"]
        receipt = _read_json(run / asset["receipt"], "media-create-receipt-invalid")
        descriptor = _descriptor_from_file(destination)
        if not all(
            isinstance(descriptor.get(field), int) and int(descriptor[field]) > 0
            for field in ("byte_length", "width", "height")
        ):
            raise MediaCreateRefused(f"media-create-asset-invalid:{asset['kind']}")
        if asset["kind"] == "body":
            projected = _body_projection(descriptor)
            if not X_BODY_MIN_HEIGHT <= projected <= X_BODY_MAX_HEIGHT:
                # A run that already has publication-state.json predates this
                # X readability contract. Keep its immutable boundary readable
                # so the X repair worker can persist a receipt and quarantine
                # the exact unpublished pair; new runs fail at commit above.
                if not (run / "gates" / "publication-state.json").is_file():
                    raise MediaCreateRefused(
                        "media-create-body-outside-x-render-range"
                    )
        expected_receipt: dict[str, object] = {
            "version": 1,
            "status": "committed",
            "kind": asset["kind"],
            "destination": str(destination),
            "sha256": str(descriptor["sha256"]),
            "byte_length": int(descriptor["byte_length"]),
            "width": int(descriptor["width"]),
            "height": int(descriptor["height"]),
        }
        if receipt != expected_receipt:
            raise MediaCreateRefused(f"media-create-receipt-mismatch:{asset['kind']}")
        if asset["kind"] == "headline":
            headline_descriptor = descriptor
    if not legacy:
        candidate = run / HEADLINE_API_CANDIDATE
        api_receipt = _read_json(run / HEADLINE_API_RECEIPT, "headline-api-receipt-invalid")
        candidate_descriptor = _descriptor_from_file(candidate)
        required = {
            "schema": "writer.gpt-image-headline-receipt",
            "version": 1,
            "status": "committed",
            "candidate": str(candidate),
            "request_model": "gpt-image-2-2026-04-21",
            "file_sha256": candidate_descriptor.get("sha256"),
            "byte_length": candidate_descriptor.get("byte_length"),
            "width": candidate_descriptor.get("width"),
            "height": candidate_descriptor.get("height"),
        }
        if any(api_receipt.get(key) != value for key, value in required.items()):
            raise MediaCreateRefused("headline-api-receipt-mismatch")
        for key in ("x_request_id", "prompt_sha256", "response_sha256", "alt", "rights_provenance"):
            if not isinstance(api_receipt.get(key), str) or not str(api_receipt[key]).strip():
                raise MediaCreateRefused(f"headline-api-receipt-missing:{key}")
        if headline_descriptor is None or candidate_descriptor.get("sha256") != headline_descriptor.get("sha256"):
            raise MediaCreateRefused("headline-api-canonical-sha-mismatch")
    return {"version": 1, "status": "verified", "assets_verified": 2,
            "headline_api_verified": not legacy}


def commit(candidate: Path, destination: Path, receipt: Path, kind: str) -> dict[str, object]:
    source = candidate.resolve(strict=True)
    target = destination.parent.resolve(strict=True) / destination.name
    if kind == "body":
        _pad_tall_body_candidate(source)
    descriptor = _descriptor_from_file(source)
    if not all(
        isinstance(descriptor.get(field), int) and int(descriptor[field]) > 0
        for field in ("byte_length", "width", "height")
    ):
        raise MediaCreateRefused("candidate-not-decodable-image")
    if kind == "body":
        projected = _body_projection(descriptor)
        if not X_BODY_MIN_HEIGHT <= projected <= X_BODY_MAX_HEIGHT:
            raise MediaCreateRefused("candidate-body-outside-x-render-range")
    payload: dict[str, object] = {
        "version": 1,
        "status": "committed",
        "kind": kind,
        "destination": str(target),
        "sha256": str(descriptor["sha256"]),
        "byte_length": int(descriptor["byte_length"]),
        "width": int(descriptor["width"]),
        "height": int(descriptor["height"]),
    }
    try:
        _install_independent_copy_once(source, target)
    except FileExistsError as error:
        target_descriptor = _descriptor_from_file(target)
        if target_descriptor.get("sha256") != descriptor.get("sha256"):
            raise MediaCreateRefused("canonical-media-already-committed") from error
        if receipt.exists():
            try:
                recorded = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as receipt_error:
                raise MediaCreateRefused("canonical-media-receipt-invalid") from receipt_error
            if recorded != payload:
                raise MediaCreateRefused("canonical-media-receipt-mismatch")
    _atomic_json(receipt, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    arm_parser = subparsers.add_parser("arm")
    arm_parser.add_argument("--run-dir", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-dir", required=True, type=Path)
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--candidate", required=True, type=Path)
    commit_parser.add_argument("--destination", required=True, type=Path)
    commit_parser.add_argument("--receipt", required=True, type=Path)
    commit_parser.add_argument("--kind", required=True, choices=("headline", "body"))
    args = parser.parse_args()
    try:
        if args.command == "arm":
            payload = arm(args.run_dir)
        elif args.command == "verify":
            payload = verify(args.run_dir)
        else:
            payload = commit(args.candidate, args.destination, args.receipt, args.kind)
    except MediaCreateRefused as error:
        print(
            json.dumps(
                {"status": "refused", "reason": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
