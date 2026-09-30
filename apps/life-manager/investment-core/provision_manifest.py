"""Provision the safe owner-input boundary during a Life Manager release handoff."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from cross_venue_run import read_manifest


class ManifestProvisionError(ValueError):
    """The deployment cannot safely provision or retain the owner manifest."""


def _is_zero(value: Any) -> bool:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return parsed.is_finite() and parsed == 0


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def provision_manifest(
    path: str | Path,
    alpaca_state_dir: str,
    *,
    available_capital_usd: Any = "0",
) -> dict[str, str]:
    """Create only the safe zero-capital default; never overwrite owner input."""
    if not isinstance(alpaca_state_dir, str) or not alpaca_state_dir:
        raise ManifestProvisionError("alpaca_state_dir_required")
    if not _is_zero(available_capital_usd):
        raise ManifestProvisionError("capital_must_be_zero")

    manifest_path = Path(path).expanduser()
    if manifest_path.is_symlink():
        raise ManifestProvisionError("manifest_symlink_refused")
    if manifest_path.exists():
        current = read_manifest(manifest_path)
        if current.get("status") != "configured":
            raise ManifestProvisionError("existing_manifest_invalid")
        return {"status": "existing", "path": str(manifest_path)}

    manifest_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path.parent.chmod(0o700)
    payload = json.dumps({
        "alpaca_state_dir": alpaca_state_dir,
        "available_capital_usd": "0",
        "snapshot_specs": [],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _atomic_write(manifest_path, (payload + "\n").encode("utf-8"))
    return {"status": "created", "path": str(manifest_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--alpaca-state-dir", required=True)
    parser.add_argument("--available-capital-usd", default="0")
    args = parser.parse_args(argv)
    try:
        result = provision_manifest(
            args.path,
            args.alpaca_state_dir,
            available_capital_usd=args.available_capital_usd,
        )
    except ManifestProvisionError as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ManifestProvisionError", "main", "provision_manifest"]
