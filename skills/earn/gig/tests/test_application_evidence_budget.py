from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills/earn/gig/scripts"
SPEC = importlib.util.spec_from_file_location("scheduled_evidence_gc", SCRIPTS / "evidence_gc.py")
assert SPEC and SPEC.loader
evidence_gc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evidence_gc
SPEC.loader.exec_module(evidence_gc)


def test_apply_evidence_budget_runs_outside_the_revenue_lane() -> None:
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())
    loop = registry["loops"]["hf-gig-apply-evidence-gc"]
    assert loop["entrypoint"] == "skills/earn/gig/scripts/evidence_gc.py"
    assert loop["provider_route"] == "deterministic"
    assert loop["runtime_timeout_seconds"] == 3600
    assert loop["command"] == [
        "--state-dir", "~/gig",
        "--evidence-root", "~/gig/apply-direct",
        "--high-water-bytes", str(400 * 1024 * 1024),
        "--low-water-bytes", str(250 * 1024 * 1024),
        "--quiet",
    ]
    application = (ROOT / "skills/earn/gig/scripts/application_direct.py").read_text()
    assert "evidence_gc.main" not in application


def test_scheduled_gc_expands_home_paths(monkeypatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(evidence_gc, "collect", lambda **kwargs: calls.append(kwargs) or evidence_gc.GcResult())
    monkeypatch.setattr(evidence_gc, "_record", lambda *_args: None)

    assert evidence_gc.main([
        "--state-dir", "~/gig",
        "--evidence-root", "~/gig/apply-direct",
        "--quiet",
    ]) == 0
    assert calls[0]["state_dir"] == tmp_path / "gig"
    assert calls[0]["evidence_root"] == tmp_path / "gig/apply-direct"


def test_scheduled_gc_preserves_a_live_apply_run_past_recent_grace(monkeypatch, tmp_path: Path) -> None:
    state = tmp_path / "gig"
    root = state / "apply-direct"
    live = root / "gig-apply-direct-live"
    newer = root / "gig-apply-direct-newer"
    live.mkdir(parents=True)
    newer.mkdir()
    (live / "evidence.bin").write_bytes(b"live")
    (newer / "evidence.bin").write_bytes(b"newer")
    old = time.time() - 7200
    os.utime(live, (old, old))
    pin = evidence_gc.register_live_evidence_pin(state, live, "apply-direct-test")
    monkeypatch.setattr(evidence_gc, "_process_start_signature", lambda _pid: None)
    try:
        result = evidence_gc.collect(
            state_dir=state,
            evidence_root=root,
            policy=evidence_gc.Policy(
                high_water_bytes=1,
                low_water_bytes=1,
                apply_direct_keep_last=1,
                apply_direct_keep_daily=1,
            ),
            now=time.time(),
        )
    finally:
        shutil.rmtree(pin, ignore_errors=True)

    assert result.errors == 0
    assert live.is_dir()
