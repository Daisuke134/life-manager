"""The final exact readback after a commit must not erase what the workers already sent.

Run 18df847a6a6c0b68-50470 sent four applications, then the parent's final applied-history
readback got HTTP 500 on the CDP websocket upgrade (websockets InvalidStatus) for every
connect retry. Only ConnectionClosedError recycled the target, so the parent died with rc 1
before writing parent-commit.json, and the wake summary reported effect 0 instead of 4.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import websockets

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_SPEC = importlib.util.spec_from_file_location(
    "application_parent_finalize_test", SCRIPTS / "application_parent.py")
parent = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(parent)
_DIRECT_SPEC = importlib.util.spec_from_file_location(
    "application_direct_finalize_test", SCRIPTS / "application_direct.py")
direct = importlib.util.module_from_spec(_DIRECT_SPEC)
_DIRECT_SPEC.loader.exec_module(direct)

REFUSED = websockets.exceptions.InvalidStatus.__new__(websockets.exceptions.InvalidStatus)


def _effects(tmp_path, monkeypatch, outcomes):
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(tmp_path / "vault" / "leases.json"))
    effects = parent.CdpParentEffects(
        ws_url="ws://127.0.0.1:9222/devtools/page/OLD", evidence_dir=tmp_path / "evidence",
        ledger_path=tmp_path / "applied.jsonl", pass_id="pass-1")
    recycled, reads = [], []
    effects.ws_recycler = lambda: recycled.append(1) or "ws://127.0.0.1:9222/devtools/page/NEW"
    queue = list(outcomes)

    def fake_readback(expected_ids, path, *args, **kwargs):
        reads.append(effects.ws_url)
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"source": "code_owned_cdp_readback",
                                    "request_ids": sorted(expected_ids)}))
        return set(expected_ids)

    monkeypatch.setattr(effects, "_official_readback", fake_readback)
    return effects, recycled, reads


def test_refused_upgrade_recycles_the_target_and_reads_back_once_more(tmp_path, monkeypatch):
    effects, recycled, reads = _effects(tmp_path, monkeypatch, [REFUSED, "ok"])
    effects.finalize_exact_readback({"5330001", "5330002"})
    assert recycled == [1]
    assert reads == ["ws://127.0.0.1:9222/devtools/page/OLD", "ws://127.0.0.1:9222/devtools/page/NEW"]
    payload = json.loads((tmp_path / "evidence" / "code-applied-readback.json").read_text())
    assert payload["request_ids"] == ["5330001", "5330002"]


def test_a_second_refusal_still_fails_the_finalize(tmp_path, monkeypatch):
    effects, recycled, reads = _effects(tmp_path, monkeypatch, [REFUSED, REFUSED])
    with pytest.raises(websockets.exceptions.InvalidStatus):
        effects.finalize_exact_readback({"5330001"})
    assert recycled == [1] and len(reads) == 2      # one recycle, one retry, never a third


def test_worker_results_are_durable_before_finalize_and_summary_counts_them(tmp_path, monkeypatch):
    effects, _recycled, _reads = _effects(tmp_path, monkeypatch, [REFUSED, REFUSED])
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True)
    results = [{"request_id": rid, "status": "confirmed",
                "application": {"request_id": rid, "title": f"t{rid}", "price_jpy": 5000}}
               for rid in ("5330001", "5330002", "5330003", "5330004")]
    results.append({"request_id": "5331065", "status": "submission_failed:cdp_timeout"})
    with pytest.raises(websockets.exceptions.InvalidStatus):
        parent._commit_then_finalize(
            effects, evidence_dir=evidence, snapshot={"snapshot_sha256": "a" * 64},
            planner_missing_request_ids=[], results=results)
    commit = json.loads((evidence / "parent-commit.json").read_text())
    assert [row["request_id"] for row in commit["results"]][:4] == [
        "5330001", "5330002", "5330003", "5330004"]
    assert not (evidence / "summary.json").exists()   # never business success
    summary = direct.summarize(evidence, 1)
    assert summary["effect"] == 4 and summary["failed"] >= 1
