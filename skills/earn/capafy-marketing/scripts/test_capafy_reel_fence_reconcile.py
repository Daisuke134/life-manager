#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_fence_reconcile import OWNER_ID, build_proof

OCC = f"{OWNER_ID}:20261022T004100-abc"


def _run_dir(tmp_path, markers=()):
    d = tmp_path / "runs" / "20261022T004100-abc"
    d.mkdir(parents=True)
    (d / "occurrence.json").write_text(json.dumps({"owner_id": OWNER_ID, "occurrence_id": OCC,
                                                   "target_date": "2026-10-29"}))
    for net in markers:
        (d / f"dispatch-{net}.json").write_text("{}")
    return d


def test_both_posts_read_back_proves_the_effect_with_provider_ids(tmp_path):
    d = _run_dir(tmp_path, ("ig", "x"))
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: f"{net}-post-1")
    assert proof["verified"] is True and proof["outcome"] == "effected"
    assert proof["provider_receipt_id"] == "ig:ig-post-1,x:x-post-1"
    assert proof["owner_id"] == OWNER_ID and proof["occurrence_id"] == OCC


def test_no_dispatch_marker_is_a_pre_effect_proof(tmp_path):
    d = _run_dir(tmp_path)
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: None)
    assert proof["verified"] is True and proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].endswith("occurrence.json")
    assert "provider_receipt_id" not in proof


def test_marker_without_readback_stays_held(tmp_path):
    d = _run_dir(tmp_path, ("ig",))
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: None)
    assert proof["verified"] is False


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ValueError):
        build_proof(OCC, tmp_path / "runs" / "nope", posts_fn=lambda net, slot: None)


def test_second_slot_marker_reads_back_at_second_slot_time(tmp_path):
    d = _run_dir(tmp_path, ("x",))
    (d / "dispatch-ig-s2.json").write_text("{}")
    seen = []
    proof = build_proof(OCC, d, posts_fn=lambda net, slot: seen.append((net, slot)) or f"{net}-1")
    assert ("ig", "2026-10-29T23:00:00.000Z") in seen and ("x", "2026-10-29T17:00:00.000Z") in seen
    assert proof["verified"] is True
