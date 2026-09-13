import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_absent_brake_is_free_without_spawning(monkeypatch, tmp_path):
    brake = load_script("operator_brake.py")
    monkeypatch.setattr(
        brake.subprocess, "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    assert brake.status(tmp_path / "gig_brake.sh", path=tmp_path / "operator.brake") == "free"


def test_existing_brake_retries_one_transient_timeout(monkeypatch, tmp_path):
    brake = load_script("operator_brake.py")
    script = tmp_path / "gig_brake.sh"
    script.write_text("#!/bin/sh\n")
    state = tmp_path / "operator.brake"
    state.write_text("held\n")
    calls = []

    def run(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise brake.subprocess.TimeoutExpired("gig_brake", 5)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(brake.subprocess, "run", run)

    assert brake.status(script, path=state) == "held"
    assert calls == [1, 1]


def test_existing_brake_fails_closed_after_two_probe_failures(monkeypatch, tmp_path):
    brake = load_script("operator_brake.py")
    script = tmp_path / "gig_brake.sh"
    script.write_text("#!/bin/sh\n")
    state = tmp_path / "operator.brake"
    state.write_text("held\n")
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(1)
        raise OSError("fork pressure")

    monkeypatch.setattr(brake.subprocess, "run", fail)

    assert brake.status(script, path=state) == "failed"
    assert calls == [1, 1]
