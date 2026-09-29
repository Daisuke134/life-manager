"""Provider-neutral contract for restoring buyer-supplied client assets.

The marketplace adapter owns browser/FTPS/API mutation.  This module owns the
part that must be identical on every platform: ordered buyer assets, the
animation-preservation fence, management-editor coverage, official readback,
and replay-zero.  A paid lane may not call an artifact complete until this
contract validates.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    """The client restore manifest cannot safely authorize a restore."""


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(manifest)).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field}_required")
    return value.strip()


def build_restore_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest_object_required")
    if manifest.get("version") != 1:
        raise ManifestError("version_unsupported")
    if manifest.get("kind") != "client_artifact_restore":
        raise ManifestError("kind_invalid")
    _text(manifest.get("platform"), "platform")
    _text(manifest.get("project_id"), "project_id")
    assets = manifest.get("ordered_assets")
    if not isinstance(assets, list) or not assets:
        raise ManifestError("ordered_assets_required")
    labels: list[str] = []
    public_paths: list[str] = []
    hashes: list[str] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise ManifestError(f"asset_{index}_object_required")
        label = _text(asset.get("label"), f"asset_{index}_label")
        path = _text(asset.get("public_path"), f"asset_{index}_public_path")
        if path.startswith("/") or ".." in Path(path).parts:
            raise ManifestError(f"asset_{index}_public_path_unsafe")
        digest = _text(asset.get("sha256"), f"asset_{index}_sha256").lower()
        if not _HEX64.fullmatch(digest):
            raise ManifestError(f"asset_{index}_sha256_invalid")
        labels.append(label)
        public_paths.append(path)
        hashes.append(digest)
    if len(set(labels)) != len(labels):
        raise ManifestError("labels_unique")
    animation = manifest.get("animation")
    if not isinstance(animation, dict):
        raise ManifestError("animation_required")
    preserve = animation.get("preserve")
    if preserve is not True:
        raise ManifestError("animation_preserve_required")
    baseline = _text(animation.get("baseline_sha256"), "animation_baseline_sha256").lower()
    if not _HEX64.fullmatch(baseline):
        raise ManifestError("animation_baseline_sha256_invalid")
    management = manifest.get("management")
    if not isinstance(management, dict):
        raise ManifestError("management_required")
    fields = management.get("editable_fields")
    controls = management.get("restore_controls")
    if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x.strip() for x in fields):
        raise ManifestError("management_editable_fields_required")
    if not isinstance(controls, int) or isinstance(controls, bool) or controls != len(assets):
        raise ManifestError("management_restore_controls_mismatch")
    return {
        "platform": str(manifest["platform"]).strip(),
        "project_id": str(manifest["project_id"]).strip(),
        "labels": labels,
        "public_paths": public_paths,
        "asset_sha256": hashes,
        "animation": {"preserve": True, "baseline_sha256": baseline},
        "management": {"editable_fields": list(fields), "restore_controls": controls},
    }


def merge_content_document(document: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a content document with only the ordered asset fields restored."""
    plan = build_restore_plan(manifest)
    if not isinstance(document, dict):
        raise ManifestError("content_document_object_required")
    slides = document.get("genreSlides")
    if not isinstance(slides, list) or len(slides) != len(plan["labels"]):
        raise ManifestError("content_genre_slides_count_mismatch")
    output = copy.deepcopy(document)
    for index, (slide, label, path) in enumerate(zip(output["genreSlides"], plan["labels"], plan["public_paths"])):
        if not isinstance(slide, dict) or str(slide.get("label") or "") != label:
            raise ManifestError(f"content_genre_slide_{index}_label_mismatch")
        slide["image"] = path
    return output


def validate_readback(manifest: dict[str, Any], readback: dict[str, Any]) -> list[str]:
    """Return typed failures; an empty list is the only completion result."""
    plan = build_restore_plan(manifest)
    if not isinstance(readback, dict):
        return ["readback_object_required"]
    errors: list[str] = []
    if readback.get("status") != "ok":
        errors.append("status_not_ok")
    if readback.get("manifest_sha256") != manifest_sha256(manifest):
        errors.append("manifest_sha256_mismatch")
    slides = readback.get("genre_slides")
    if not isinstance(slides, list):
        errors.append("genre_slides_missing")
    else:
        observed = [(item.get("label"), item.get("image")) for item in slides if isinstance(item, dict)]
        expected = list(zip(plan["labels"], plan["public_paths"]))
        if observed != expected:
            errors.append("genre_slides_mismatch")
    if plan["animation"]["preserve"] and readback.get("animation_sha256") != plan["animation"]["baseline_sha256"]:
        errors.append("animation_changed")
    if readback.get("management_restore_controls") != plan["management"]["restore_controls"]:
        errors.append("management_restore_controls_mismatch")
    if not isinstance(readback.get("official_receipt_id"), str) or not readback["official_receipt_id"].strip():
        errors.append("official_receipt_missing")
    if readback.get("replay_zero") is not True:
        errors.append("replay_zero_missing")
    return errors


def validate_project_readback(project_root: str | Path) -> list[str]:
    """Validate the optional project contract used by the Paid delivery gate."""
    root = Path(project_root).expanduser().resolve()
    manifest_path = root / "requirements" / "client-artifact-restore.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return []
    readback_path = root / "delivery" / "client-artifact-restore-readback.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        readback = json.loads(readback_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["client_artifact_restore_readback_missing"]
    return validate_readback(manifest, readback)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--readback", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    readback = json.loads(args.readback.read_text(encoding="utf-8"))
    errors = validate_readback(manifest, readback)
    print(json.dumps({"status": "ok" if not errors else "failed", "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
