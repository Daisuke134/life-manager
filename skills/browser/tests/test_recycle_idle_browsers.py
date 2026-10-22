import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import recycle_idle_browsers as recycler  # noqa: E402
from recycle_idle_browsers import recycle_targets, should_recycle  # noqa: E402
from runtime.host import disk_admission  # noqa: E402

REG = {"identity": [
    {"id": "interactive:dais", "profile": "~/.cloak/profiles/daily-driver", "launched_by": "ai.anicca.dais-browser"},
    {"id": "lancers:dais", "profile": "~/.local/state/anicca/lancers/browser-profile", "launched_by": "ai.anicca.lancers-revenue-browser"},
    {"id": "colors:owner", "profile": "~/.cloak/profiles/colors", "launched_by": "skills/browser/ensure_provision_browser.sh"},
    {"id": "x:anicca", "profile": "~/.cloak/profiles/x-repost-daily", "launched_by": "~/loops/current/skills/browser/ensure_provision_browser.sh"},
]}


def test_only_launchd_keepalive_owners_and_never_dais_chrome():
    assert [t["id"] for t in recycle_targets(REG)] == ["lancers:dais"]


def test_recycles_only_after_max_age():
    assert should_recycle(5 * 3600, 4 * 3600) is True
    assert should_recycle(3 * 3600, 4 * 3600) is False
    assert should_recycle(None, 4 * 3600) is False


@pytest.fixture
def run_recycler(monkeypatch, tmp_path, capsys):
    """Keep all process, browser and capacity operations inside fixtures."""
    registry = tmp_path / "browsers.toml"
    registry.write_text("\n".join(
        "[[identity]]\n" + "\n".join(f"{k} = {json.dumps(v)}" for k, v in ident.items())
        for ident in REG["identity"]
    ))
    loops = tmp_path / "loops.json"
    monkeypatch.setattr(recycler, "REGISTRY", registry)
    monkeypatch.setattr(recycler, "LOOP_REGISTRY", loops, raising=False)
    monkeypatch.setattr(recycler, "MAX_AGE", 14400)
    monkeypatch.delenv("LIFE_MANAGER_PRODUCER_FLOOR_BYTES", raising=False)

    def run(*, free=(9 * 1024**3,), snapshots=((101, 10800),), cadence=3600,
            acquire_rc=0, endpoint="http://fixture", acquire_error=False,
            registry_text=None, second=False):
        loops.write_text(registry_text if registry_text is not None else json.dumps({
            "loops": {"browser-recycle-idle": {"cadence": {"start_interval_seconds": cadence}}}}))
        if second:
            with registry.open("a") as handle:
                handle.write('\n[[identity]]\nid = "second:owner"\nprofile = "/fixture/second"\n'
                             'launched_by = "ai.anicca.second-browser"\n')
        events = []
        age_reads = iter(snapshots)
        disk_reads = iter(free)
        current_age = snapshots[-1]
        current_free = free[-1]

        def capacity(_path):
            nonlocal current_free
            current_free = next(disk_reads, current_free)
            return SimpleNamespace(free=current_free)

        def command(argv, **_kwargs):
            nonlocal current_age
            if argv[0] == "ps":
                current_age = next(age_reads, current_age)
                if current_age is None:
                    return SimpleNamespace(returncode=0, stdout="")
                pid, age = current_age
                etime = f"{age // 3600:02}:{age // 60 % 60:02}:{age % 60:02}"
                prefix = f"{pid} " if "pid=" in argv[-1] else ""
                out = (
                    f"{prefix}{etime} /Applications/Chromium.app/Contents/MacOS/Chromium "
                    "--user-data-dir=/fixture/lancers\n")
                if second:
                    out += (f"{pid + 1} {etime} /Applications/Chromium.app/Contents/MacOS/Chromium "
                            "--user-data-dir=/fixture/second\n")
                return SimpleNamespace(returncode=0, stdout=out)
            assert argv[:2] == ["bash", str(recycler.HERE / "browser-guard.sh")]
            assert argv[3] in ("lancers:dais", "second:owner")
            events.append(argv[2])
            if argv[2] == "acquire":
                if acquire_error:
                    raise OSError("fixture guard unavailable")
                return SimpleNamespace(returncode=acquire_rc, stdout=endpoint)
            assert argv[2] == "release"
            return SimpleNamespace(returncode=0, stdout="")

        monkeypatch.setattr(disk_admission.shutil, "disk_usage", capacity)
        monkeypatch.setattr(recycler.subprocess, "run", command)
        monkeypatch.setattr(recycler, "_close", lambda _cdp: events.append("close"))
        assert recycler.main() == 0
        return json.loads(capsys.readouterr().out), events

    # No real profile is read; only the command marker is used by the ps fixture.
    contents = registry.read_text().replace(
        "~/.local/state/anicca/lancers/browser-profile", "/fixture/lancers")
    registry.write_text(contents)
    return run


def test_pressure_recycles_three_hour_idle_browser(run_recycler):
    report, events = run_recycler()
    assert report["browsers"][0]["action"] == "recycled"
    assert events == ["acquire", "close", "release"]


@pytest.mark.parametrize("age,action", [(10800, "keep"), (14400, "keep"), (18000, "recycled")])
def test_normal_capacity_preserves_four_hour_age(run_recycler, age, action):
    report, _ = run_recycler(free=(20 * 1024**3,), snapshots=((101, age),))
    assert report["browsers"][0]["action"] == action


@pytest.mark.parametrize("free", [None, -1, True, "low", 1.5, 12 * 1024**3])
def test_unknown_invalid_or_at_floor_capacity_keeps_normal_age(run_recycler, free):
    report, events = run_recycler(free=(free,))
    assert report["browsers"][0]["action"] == "keep"
    assert events == []


@pytest.mark.parametrize("cadence", [None, 0, -1, True, "3600", 1.5, {}, 18000])
def test_invalid_or_long_cadence_does_not_shorten_normal_age(run_recycler, cadence):
    report, events = run_recycler(cadence=cadence)
    assert report["browsers"][0]["action"] == "keep"
    assert events == []


@pytest.mark.parametrize("raw", ["", "null", "{}", '{"loops": {"browser-recycle-idle": {}}}'])
def test_missing_or_malformed_registry_keeps_normal_age(run_recycler, raw):
    report, events = run_recycler(registry_text=raw)
    assert report["browsers"][0]["action"] == "keep"
    assert events == []


def test_unreadable_registry_keeps_normal_age(run_recycler, monkeypatch, tmp_path):
    monkeypatch.setattr(recycler, "LOOP_REGISTRY", tmp_path / "missing.json")
    report, events = run_recycler()
    assert report["browsers"][0]["action"] == "keep"
    assert events == []


@pytest.mark.parametrize("snapshot", [None, (101, 3599), (101, 3600)])
def test_pressure_never_recycles_unknown_or_fresh_browser(run_recycler, snapshot):
    report, events = run_recycler(snapshots=(snapshot,))
    assert report["browsers"][0]["action"] == "keep"
    assert events == []


@pytest.mark.parametrize("kwargs", [{"acquire_rc": 1}, {"endpoint": ""},
                                         {"endpoint": "invalid"}, {"acquire_error": True}])
def test_busy_or_failed_acquire_never_closes_browser(run_recycler, kwargs):
    report, events = run_recycler(**kwargs)
    assert report["browsers"][0]["action"] == "busy"
    assert "close" not in events


@pytest.mark.parametrize("fresh", [None, (101, 60), (102, 10800)])
def test_lease_recheck_preserves_missing_fresh_or_replaced_process(run_recycler, fresh):
    report, events = run_recycler(snapshots=((101, 10800), fresh))
    assert report["browsers"][0]["action"] == "keep"
    assert events == ["acquire", "release"]


def test_pressure_resolution_inside_lease_restores_normal_age(run_recycler):
    report, events = run_recycler(free=(9 * 1024**3, 20 * 1024**3))
    assert report["browsers"][0]["action"] == "keep"
    assert events == ["acquire", "release"]


def test_pressure_resolution_keeps_remaining_three_hour_browser(run_recycler):
    report, events = run_recycler(free=(9 * 1024**3, 9 * 1024**3, 20 * 1024**3), second=True)
    assert [row["action"] for row in report["browsers"]] == ["recycled", "keep"]
    assert events == ["acquire", "close", "release"]


def test_small_host_calibration_is_respected(run_recycler, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_FLOOR_BYTES", str(8 * 1024**3))
    report, events = run_recycler()
    assert report["browsers"][0]["action"] == "keep"
    assert events == []
