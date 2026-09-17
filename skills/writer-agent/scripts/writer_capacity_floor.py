#!/usr/bin/env python3
"""Resolve a host-measured Writer capacity floor with no publisher dependencies."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

CANONICAL_DISK_HEADROOM_KIB = 524_288
CANONICAL_DISK_HEADROOM_BYTES = CANONICAL_DISK_HEADROOM_KIB * 1024


class CapacityFloorError(ValueError):
    pass


def resolve_disk_floor_bytes(state_dir: Path) -> int:
    try:
        configured_kib = int(os.environ.get(
            "GIG_DISK_HEADROOM_KIB", str(CANONICAL_DISK_HEADROOM_KIB)
        ))
        configured_bytes = int(os.environ.get(
            "ARTICLE_DISK_MIN_FREE_BYTES", str(configured_kib * 1024)
        ))
    except ValueError as error:
        raise CapacityFloorError("disk_headroom_configuration_invalid") from error
    if (
        configured_kib < CANONICAL_DISK_HEADROOM_KIB
        or configured_bytes < configured_kib * 1024
    ):
        raise CapacityFloorError("disk_headroom_configuration_invalid")

    receipt_path = Path(os.environ.get(
        "ARTICLE_CAPACITY_RECEIPT",
        str(state_dir / "capacity" / "article-run-floor.json"),
    ))
    if not receipt_path.exists():
        return configured_bytes
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise TypeError("capacity receipt must be an object")
        observed = receipt["observed_consumption_kib"]
        reserve = receipt["atomic_reserve_kib"]
        required = receipt["required_free_kib"]
        if any(type(value) is not int for value in (observed, reserve, required)):
            raise TypeError("capacity receipt counters must be integers")
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        raise CapacityFloorError("capacity_receipt_invalid") from error
    if (
        receipt.get("schema") != "writer.capacity-receipt"
        or type(receipt.get("version")) is not int
        or receipt.get("version") != 1
        or observed < 0
        or reserve < CANONICAL_DISK_HEADROOM_KIB
        or required != observed + reserve
    ):
        raise CapacityFloorError("capacity_receipt_invalid")
    return max(configured_bytes, required * 1024)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    print(resolve_disk_floor_bytes(Path(args.state_dir)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CapacityFloorError as error:
        print(f"REFUSED: {error}", file=__import__("sys").stderr)
        raise SystemExit(2)
