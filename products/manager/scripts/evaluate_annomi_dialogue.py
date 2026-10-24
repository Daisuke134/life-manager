#!/usr/bin/env python3
"""Run the pinned AnnoMI label-quality baseline and emit aggregate JSON only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MANAGER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGER_ROOT / "manager_core"))

from annomi_dialogue_eval import AnnoMIEvaluationError, evaluate_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_csv(args.input)
    except AnnoMIEvaluationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("ERROR EVALUATION_FAILED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
