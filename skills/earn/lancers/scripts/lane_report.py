#!/usr/bin/env python3
"""Project one canonical Lancers sales snapshot into one owner-visible lane."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
DEFAULT_STATE = Path.home() / ".local/state/anicca/lancers/contracts.json"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("reporter_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_snapshot(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("source_complete") is not True:
        raise ValueError("sales_source_incomplete")
    return dict(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--lane", required=True, choices=("negotiate", "paid"))
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)
    try:
        snapshot = read_snapshot(args.state_path)
        reporter = _load("_anicca_lancers_lane_reporter", HERE / "telegram_report.py")
        notify = reporter.notify_negotiate_wake if args.lane == "negotiate" else reporter.notify_paid_wake
        delivery = notify(snapshot)
        result = {
            "ok": delivery.delivery_uncertain == 0 and delivery.pre_send_failed == 0
            and delivery.provider_rejected == 0,
            "lane": args.lane,
            "attempted": delivery.attempted,
            "delivered": delivery.delivered,
            "delivery_uncertain": delivery.delivery_uncertain,
            "pre_send_failed": delivery.pre_send_failed,
            "provider_rejected": delivery.provider_rejected,
        }
    except Exception as error:
        result = {"ok": False, "lane": args.lane, "error": type(error).__name__.lower()}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
