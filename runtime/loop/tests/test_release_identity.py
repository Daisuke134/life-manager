import json
from pathlib import Path
from unittest.mock import patch

from runtime.loop import lm_loop_run


SHA_OLD = "a" * 40
SHA_CURRENT = "b" * 40


def _registry(effect_class="application", loop_id="example"):
    return {
        "schema_version": 2,
        "loops": {
            loop_id: {
                "label": f"ai.anicca.{loop_id}",
                "domain": "earn",
                "entrypoint": "bin/effect.sh",
                "cadence": {"start_interval_seconds": 60},
                "effect_class": effect_class,
                "state_root": f"~/.local/state/life-manager/{loop_id}",
                "log_root": f"~/.local/state/life-manager/{loop_id}/logs",
                "cleanup": {"max_runs": 10, "max_age_days": 7},
                "provider_route": "deterministic",
            }
        },
    }


def _release(root: Path, name: str, sha: str, *, effect_class="application",
             loop_id="example") -> Path:
    release = root / name
    (release / "bin").mkdir(parents=True)
    (release / "config").mkdir()
    entrypoint = release / "bin/effect.sh"
    entrypoint.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    runner = release / "bin/lm-loop-run"
    runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    runner.chmod(0o755)
    (release / "config/loop-registry.json").write_text(
        json.dumps(_registry(effect_class, loop_id)), encoding="utf-8"
    )
    (release / "RELEASE.json").write_text(
        json.dumps({"sha": sha, "release_paths": "ALL"}), encoding="utf-8"
    )
    return release


def test_stale_effect_release_is_rejected_before_child_start(tmp_path, monkeypatch):
    old_release = _release(tmp_path, "old", SHA_OLD)
    current_release = _release(tmp_path, "current-release", SHA_CURRENT)
    loops = tmp_path / "loops"
    loops.mkdir()
    (loops / "current").symlink_to(current_release)
    state_root = tmp_path / ".local/state/life-manager/example"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "example")
    monkeypatch.setenv("LIFE_MANAGER_REPO", str(old_release.resolve()))
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", SHA_OLD)
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(state_root))
    started = []

    with patch.object(
        lm_loop_run, "_run_admitted", side_effect=lambda *args: started.append(args) or 0
    ):
        result = lm_loop_run.main(["example", str(old_release)])

    assert result == 78
    assert started == []
    event = json.loads(
        (state_root / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert event["blocker"] == "release_drift"
    assert event["failure_layer"] == "release"


def test_control_plane_release_reconciler_may_run_across_release_drift(tmp_path, monkeypatch):
    loop_id = "life-manager-release-reconciler"
    old_release = _release(
        tmp_path, "old", SHA_OLD, effect_class="none", loop_id=loop_id
    )
    current_release = _release(
        tmp_path, "current-release", SHA_CURRENT, effect_class="none", loop_id=loop_id
    )
    loops = tmp_path / "loops"
    loops.mkdir()
    (loops / "current").symlink_to(current_release)
    state_root = tmp_path / ".local/state/life-manager/life-manager-release-reconciler"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "life-manager-release-reconciler")
    monkeypatch.setenv("LIFE_MANAGER_REPO", str(old_release.resolve()))
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", SHA_OLD)
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(state_root))

    with patch.object(lm_loop_run, "_run_admitted", return_value=0) as run:
        result = lm_loop_run.main([loop_id, str(old_release)])

    assert result == 0
    run.assert_called_once()
