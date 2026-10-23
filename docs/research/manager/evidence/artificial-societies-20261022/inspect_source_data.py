#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical public aggregate inspector."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPOSITORY_ROOT / "products/manager/scripts"))

from inspect_external_behavior_benchmark import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
