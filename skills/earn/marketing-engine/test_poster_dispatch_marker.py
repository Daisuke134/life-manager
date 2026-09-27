#!/usr/bin/env python3
"""TDD for poster.py's durable pre-publish dispatch marker (T5-G-4).

A future fence reconciler needs to tell "this run never reached the publish
call" from "this run attempted or completed a publish". write_dispatch_marker
is the minimal primitive: it must be a no-op when unconfigured (so every other
marketing loop sharing this poster is unaffected) and otherwise persist an
atomic, readable JSON marker.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().with_name("poster.py")
_spec = importlib.util.spec_from_file_location("capafy_poster_under_test", MODULE_PATH)
assert _spec and _spec.loader
poster = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = poster
_spec.loader.exec_module(poster)


def test_no_op_when_marker_path_absent():
    # Must not raise and must not touch the filesystem when unconfigured.
    poster.write_dispatch_marker(None, "some-occurrence")


def test_writes_pre_effect_before_publish(tmp_path):
    marker = tmp_path / "dispatch-marker.json"
    poster.write_dispatch_marker(str(marker), "capafy-ig-marketing-daily:abc-1")
    row = json.loads(marker.read_text(encoding="utf-8"))
    assert row["version"] == 1
    assert row["status"] == "pre_effect"
    assert row["occurrence_id"] == "capafy-ig-marketing-daily:abc-1"
    assert row["effect"] is None
    assert row["ts"]


def test_overwrites_to_completed_after_publish(tmp_path):
    marker = tmp_path / "dispatch-marker.json"
    poster.write_dispatch_marker(str(marker), "occ-2")
    poster.write_dispatch_marker(str(marker), "occ-2", status="completed", effect=1)
    row = json.loads(marker.read_text(encoding="utf-8"))
    assert row["status"] == "completed"
    assert row["effect"] == 1
    assert row["occurrence_id"] == "occ-2"


def test_write_is_atomic_no_leftover_tmp(tmp_path):
    marker = tmp_path / "nested" / "dispatch-marker.json"
    poster.write_dispatch_marker(str(marker), "occ-3")
    leftovers = list(marker.parent.glob("*.tmp-*"))
    assert leftovers == []
    assert marker.is_file()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
