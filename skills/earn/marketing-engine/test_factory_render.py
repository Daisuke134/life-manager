from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

import pytest

import factory_render


ENGINE = Path(__file__).resolve().parent
CLI = ENGINE / "bin" / "lm"
READY = {"LIFE_MANAGER_HEYGEN": "/usr/bin/true"}
HOST_DISK_ADMISSION = factory_render._host_disk_admission


def user_config(tmp_path, language="en", project_id="your-project"):
    return {
        "schema_version": "ai-monk-factory.config.v1",
        "project_id": project_id,
        "language": language,
        "heygen": {"avatar_id": f"{language}_avatar_12345678", "voice_id": f"{language}_voice_12345678"},
        "postiz": {"platform": "tiktok", "integration_id": "your-integration"},
        "product": {"name": "Your product", "url": "https://example.invalid/product"},
        "state_root": str(tmp_path / project_id),
    }


class HeygenExecutor:
    def __init__(self, *, balances=(20, 19.5, 19, 18.5), status="completed", auth=True, uncertain=False,
                 delay=0):
        self.calls = []
        self.requests = []
        self.balances = iter(balances)
        self.status = status
        self.auth = auth
        self.uncertain = uncertain
        self.delay = delay
        self.active = self.max_active = 0
        self.lock = threading.Lock()

    def __call__(self, args, **kwargs):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.execute(args, **kwargs)
        finally:
            with self.lock:
                self.active -= 1

    def execute(self, args, **kwargs):
        self.calls.append((args, kwargs))
        assert kwargs == {"input": kwargs.get("input"), "text": True, "capture_output": True, "check": True}
        if args[1:3] == ["auth", "status"]:
            if not self.auth:
                raise subprocess.CalledProcessError(1, args)
            payload = {}
        elif args[1:4] == ["user", "me", "get"]:
            payload = {"data": {"wallet": {
                "currency": "usd", "remaining_balance": next(self.balances),
                "auto_reload": {"enabled": True, "amount_usd": 10, "threshold_usd": 5},
            }}}
        elif args[1:3] == ["video", "create"]:
            self.requests.append(json.loads(kwargs["input"]))
            if self.uncertain:
                raise RuntimeError("connection lost after create")
            payload = {"data": {"video_id": "video_12345678", "status": self.status}}
        elif args[1:3] == ["video", "get"]:
            payload = {"data": {"id": "video_12345678", "status": "completed"}}
        elif args[1:3] == ["video", "download"]:
            Path(args[-1]).write_bytes(b"video")
            payload = {}
        else:
            raise AssertionError(f"unexpected provider command: {args[1:4]}")
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")


@pytest.fixture(autouse=True)
def isolated_host(tmp_path, monkeypatch):
    monkeypatch.setenv("LM_DATA_DIR", str(tmp_path / "host"))
    monkeypatch.setattr(factory_render, "_host_disk_admission", lambda: True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("test attempted a live subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def invoke_cli(tmp_path, config, script, monkeypatch, executor):
    config_path = tmp_path / "config.json"
    script_path = tmp_path / "script.txt"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    render = factory_render.render_from_config
    monkeypatch.setattr(factory_render, "render_from_config", lambda config, script, run_id:
                        render(config, script, run_id, environment=READY, executor=executor))
    main = runpy.run_path(str(CLI))["main"]
    try:
        return main(["factory", "render", "--config", str(config_path), "--script", str(script_path),
                     "--run-id", "first-video"])
    except SystemExit as exc:
        return exc.code


@pytest.mark.parametrize("language,script,voice_settings", [
    ("en", "  Breathe slowly.  ", {"speed": 0.9, "locale": "en-US"}),
    ("ja", "  一度だけ肩をゆるめてください。  ", {"speed": 0.9}),
])
def test_cli_renders_user_request_with_shared_intent(tmp_path, monkeypatch, capsys, language, script, voice_settings):
    config = user_config(tmp_path, language)
    executor = HeygenExecutor()

    code = invoke_cli(tmp_path, config, script, monkeypatch, executor)

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.err == ""
    receipt = json.loads(captured.out)
    assert receipt["schema_version"] == "ai-monk-factory.render.v1"
    assert receipt["project_id"] == "your-project"
    assert receipt["run_id"] == "first-video"
    assert receipt["state"] == "rendered"
    assert receipt["wallet_cost"]["cost_usd"] == "0.5"
    assert receipt["output"] == str(tmp_path / "your-project/renders/your-project.first-video.mp4")
    request = {
        "type": "avatar", "avatar_id": f"{language}_avatar_12345678", "script": script.strip(),
        "voice_id": f"{language}_voice_12345678", "voice_settings": voice_settings,
        "engine": {"type": "avatar_iv"}, "aspect_ratio": "9:16", "resolution": "1080p",
        "output_format": "mp4",
    }
    assert executor.requests == [request]
    sidecar = tmp_path / "host/marketing/ebook/runs/factory.your-project.first-video.heygen-effect.json"
    intent = json.loads(sidecar.read_text())
    request_bytes = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert intent["request_sha256"] == hashlib.sha256(request_bytes).hexdigest()
    assert intent["output"] == receipt["output"]
    assert "env" not in executor.calls[0][1]


def test_helper_rejects_invalid_run_id_before_effect_or_directory(tmp_path):
    executor = HeygenExecutor()

    with pytest.raises(ValueError, match="run ID"):
        factory_render.render_from_config(user_config(tmp_path), "Breathe.", "../escape",
                                          environment=READY, executor=executor)

    assert executor.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("receipt", [
    {"state": "setup_required", "missing": ["heygen_auth"], "external_effects": []},
    {"state": "deferred", "reason": "host_disk_admission_required", "external_effects": []},
    {"state": "reconciliation_required", "video_id": "video_12345678", "external_effects": []},
    {"state": "rendered", "wallet_cost": None, "cost_reconciliation_required": True, "external_effects": []},
    {"state": "rendered", "wallet_cost": None, "external_effects": []},
    {"state": "rendered", "wallet_cost": {"currency": "usd", "cost_usd": "0.5"},
     "cost_reconciliation_required": True, "external_effects": []},
])
def test_cli_returns_nonzero_and_preserves_pending_receipt(tmp_path, monkeypatch, capsys, receipt):
    monkeypatch.setattr(factory_render, "render_from_config", lambda *_args, **_kwargs: receipt)

    code = invoke_cli(tmp_path, user_config(tmp_path), "Breathe.", monkeypatch, HeygenExecutor())

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == ""
    assert json.loads(captured.out) == receipt


@pytest.mark.parametrize("run_id", [None, "", "Upper", "a" * 65, "with.dot", "a/b"])
def test_invalid_run_ids_do_not_create_state(tmp_path, monkeypatch, run_id):
    executor = HeygenExecutor()
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: pytest.fail("invalid input created a directory"))

    with pytest.raises(ValueError, match="run ID"):
        factory_render.render_from_config(user_config(tmp_path), "Breathe.", run_id,
                                          environment=READY, executor=executor)

    assert executor.calls == []


@pytest.mark.parametrize("change,script", [
    ({"state_root": "relative/state"}, "Breathe."),
    ({"project_id": "../escape"}, "Breathe."),
    ({"guard_root": "/fixture-secret-value"}, "Breathe."),
    ({"heygen": {"avatar_id": "short", "voice_id": "voice_12345678"}}, "Breathe."),
    ({}, "  "),
])
def test_invalid_config_is_rejected_before_gate_provider_or_directory(tmp_path, monkeypatch, change, script):
    config = {**user_config(tmp_path), **change}
    executor = HeygenExecutor()
    monkeypatch.setattr(factory_render, "_host_disk_admission", lambda: pytest.fail("invalid input reached host gate"))
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: pytest.fail("invalid input created a directory"))

    with pytest.raises(ValueError) as caught:
        factory_render.render_from_config(config, script, "first-video", environment=READY, executor=executor)

    assert "fixture-secret" not in str(caught.value)
    assert executor.calls == []


@pytest.mark.parametrize("host_root", ["", "relative/data", "~/.local/state/life-manager"])
def test_nonabsolute_host_root_is_rejected_without_state_or_provider(tmp_path, monkeypatch, host_root):
    executor = HeygenExecutor()
    monkeypatch.setenv("LM_DATA_DIR", host_root)
    monkeypatch.setattr(factory_render, "_host_disk_admission", lambda: pytest.fail("invalid root reached host gate"))
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: pytest.fail("invalid root created a directory"))

    with pytest.raises(ValueError, match="host data root"):
        factory_render.render_from_config(user_config(tmp_path), "Breathe.", "first-video",
                                          environment=READY, executor=executor)

    assert executor.calls == []


def test_shared_root_uses_host_setting_and_config_ids_without_forwarding_auth_env(tmp_path):
    executor = HeygenExecutor()
    supplied_environment = {
        **READY, "LM_DATA_DIR": str(tmp_path / "project-override"),
        "LM_EBOOK_EN_HEYGEN_AVATAR_ID": "wrong_avatar_12345678",
        "LM_EBOOK_EN_HEYGEN_VOICE_ID": "wrong_voice_12345678",
        "HEYGEN_API_KEY": "fixture-secret-value", "POSTIZ_API_KEY": "fixture-secret-value",
    }

    receipt = factory_render.render_from_config(user_config(tmp_path), "Breathe.", "first-video",
                                                environment=supplied_environment, executor=executor)

    assert receipt["state"] == "rendered"
    assert executor.requests[0]["avatar_id"] == "en_avatar_12345678"
    assert executor.requests[0]["voice_id"] == "en_voice_12345678"
    assert all("env" not in kwargs for _args, kwargs in executor.calls)
    assert "fixture-secret" not in json.dumps(receipt)
    assert (tmp_path / "host/marketing/ebook/runs/factory.your-project.first-video.heygen-effect.json").is_file()
    assert not (tmp_path / "project-override").exists()


def test_unset_host_setting_uses_existing_home_ebook_root(tmp_path, monkeypatch):
    monkeypatch.delenv("LM_DATA_DIR")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    executor = HeygenExecutor()

    receipt = factory_render.render_from_config(user_config(tmp_path), "Breathe.", "first-video",
                                                environment=READY, executor=executor)

    assert receipt["state"] == "rendered"
    assert (tmp_path / "home/.local/state/life-manager/marketing/ebook/runs/"
            "factory.your-project.first-video.heygen-effect.json").is_file()


@pytest.mark.parametrize("pending,state", [
    ({"state": "cost_reconciliation_required", "wallet_cost": None}, "cost_reconciliation_required"),
    ({"state": "completed", "wallet_cost": None}, "completed"),
    ({"state": "provider_created", "wallet_cost": {"currency": "usd", "cost_usd": "0.5"}}, "provider_created"),
    ([], "invalid_sidecar"),
    ("{broken", "unreadable_sidecar"),
])
def test_existing_ebook_pending_blocks_other_project_without_provider_calls(tmp_path, pending, state):
    sidecar = tmp_path / "host/marketing/ebook/runs/ebook-run.existing.heygen-effect.json"
    sidecar.parent.mkdir(parents=True)
    original = pending if isinstance(pending, str) else json.dumps(pending)
    sidecar.write_text(original)
    executor = HeygenExecutor()
    config = user_config(tmp_path, project_id="different-project")

    receipt = factory_render.render_from_config(config, "Breathe.", "another-run",
                                                environment=READY, executor=executor)

    assert receipt["state"] == "setup_required"
    assert receipt["reason"] == "prior_heygen_effect_unresolved"
    assert receipt["pending_render"] == {"run_id": sidecar.name, "state": state}
    assert receipt["external_effects"] == []
    assert executor.calls == []
    assert sidecar.read_text() == original
    assert not Path(config["state_root"]).exists()


def test_same_intent_replays_completed_receipt_without_second_create(tmp_path):
    executor = HeygenExecutor()
    config = user_config(tmp_path)

    first = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    replay = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)

    assert first == replay
    assert len(executor.requests) == 1
    assert sum(args[1:3] == ["video", "download"] for args, _kwargs in executor.calls) == 1
    sidecar = tmp_path / "host/marketing/ebook/runs/factory.your-project.first-video.heygen-effect.json"
    assert json.loads(sidecar.read_text())["state"] == "completed"
    assert sidecar.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "host/marketing/ebook/locks/heygen-avatar-iv-account.lock").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("changed", ["script", "output"])
def test_same_intent_rejects_changed_script_or_output_without_recreate(tmp_path, changed):
    executor = HeygenExecutor()
    config = user_config(tmp_path)
    factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    if changed == "output":
        config["state_root"] = str(tmp_path / "different-output")

    with pytest.raises(ValueError, match="conflicting HeyGen effect replay"):
        factory_render.render_from_config(config, "Pause." if changed == "script" else "Breathe.", "first-video",
                                          environment=READY, executor=executor)

    assert len(executor.requests) == 1
    assert not (tmp_path / "different-output").exists()


def test_two_projects_share_one_account_lock_for_all_provider_work(tmp_path):
    executor = HeygenExecutor(delay=0.01)
    start = threading.Barrier(2)

    def render_project(project_id):
        start.wait(timeout=5)
        return factory_render.render_from_config(user_config(tmp_path, project_id=project_id), "Breathe.",
                                                 "first-video", environment=READY, executor=executor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(render_project, ("first-project", "second-project")))

    assert [receipt["state"] for receipt in receipts] == ["rendered", "rendered"]
    assert len(executor.requests) == 2
    assert executor.max_active == 1
    assert len(list((tmp_path / "host/marketing/ebook/runs").glob("*.heygen-effect.json"))) == 2


def test_host_disk_refusal_is_deferred_with_no_output_or_provider_call(tmp_path, monkeypatch):
    monkeypatch.setattr(factory_render, "_host_disk_admission", lambda: False)
    executor = HeygenExecutor()

    receipt = factory_render.render_from_config(user_config(tmp_path), "Breathe.", "first-video",
                                                environment=READY, executor=executor)

    assert receipt["state"] == "deferred"
    assert receipt["reason"] == "host_disk_admission_required"
    assert receipt["external_effects"] == []
    assert receipt.get("wallet_cost") is None
    assert executor.calls == []
    assert not (tmp_path / "your-project").exists()


def test_host_disk_gate_is_current_after_waiting_for_account_lock(tmp_path, monkeypatch):
    actual_lock = factory_render.exclusive_lock
    waiting = threading.Event()
    gate_allowed = [True]
    executor = HeygenExecutor()

    @contextmanager
    def observed_lock(path):
        waiting.set()
        with actual_lock(path):
            yield

    monkeypatch.setattr(factory_render, "exclusive_lock", observed_lock)
    monkeypatch.setattr(factory_render, "_host_disk_admission", lambda: gate_allowed[0])
    with ThreadPoolExecutor(max_workers=1) as pool:
        with actual_lock(tmp_path / "host/marketing/ebook/locks/heygen-avatar-iv-account.lock"):
            future = pool.submit(factory_render.render_from_config, user_config(tmp_path), "Breathe.",
                                 "first-video", environment=READY, executor=executor)
            assert waiting.wait(timeout=5)
            gate_allowed[0] = False
        receipt = future.result(timeout=5)

    assert receipt["state"] == "deferred"
    assert receipt["external_effects"] == []
    assert executor.calls == []
    assert not (tmp_path / "your-project").exists()


@pytest.mark.parametrize("exit_code,allowed", [(0, True), (75, False), (1, False)])
def test_host_gate_delegates_existing_producer_with_no_override_env(monkeypatch, exit_code, allowed):
    calls = []
    for key in ("LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_PRODUCER_STATE_DIR", "LIFE_MANAGER_HOST_STATE_DIR",
                "LIFE_MANAGER_PRODUCER_FLOOR_BYTES", "HEYGEN_API_KEY"):
        monkeypatch.setenv(key, "fixture-override")

    def execute(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, exit_code, "", "")

    monkeypatch.setattr(subprocess, "run", execute)

    assert HOST_DISK_ADMISSION() is allowed
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [sys.executable, str(ENGINE.parents[2] / "runtime/host/disk_admission.py"),
                    sys.executable, "-c", "pass"]
    assert kwargs["env"] == {"PATH": os.defpath}
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False


@pytest.mark.parametrize("environment,auth,missing", [
    ({"LIFE_MANAGER_HEYGEN": "/missing-fixture-cli"}, True, ["heygen_cli"]),
    (READY, False, ["heygen_auth"]),
])
def test_existing_renderer_setup_failure_is_preserved(tmp_path, environment, auth, missing):
    executor = HeygenExecutor(auth=auth)

    receipt = factory_render.render_from_config(user_config(tmp_path), "Breathe.", "first-video",
                                                environment=environment, executor=executor)

    assert receipt["state"] == "setup_required"
    assert receipt["missing"] == missing
    assert receipt["external_effects"] == []
    assert len(executor.requests) == 0
    assert not (tmp_path / "your-project").exists()


def test_provider_reconciliation_is_preserved_without_recreate(tmp_path):
    executor = HeygenExecutor(status="processing")
    config = user_config(tmp_path)

    pending = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    replay = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)

    assert pending["state"] == "reconciliation_required"
    assert pending["provider_status"] == "processing"
    assert pending["external_effects"] == ["heygen_video_created"]
    assert replay["state"] == "rendered"
    assert len(executor.requests) == 1


def test_rendered_with_unknown_cost_remains_unknown_and_blocks_other_project(tmp_path):
    executor = HeygenExecutor(balances=(20, 20))
    config = user_config(tmp_path)

    first = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    replay = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    other = factory_render.render_from_config(user_config(tmp_path, project_id="other-project"), "Pause.", "second-video",
                                              environment=READY, executor=executor)

    assert first["state"] == "reconciliation_required"
    assert replay["state"] == "rendered"
    assert replay["wallet_cost"] is None
    assert replay["cost_reconciliation_required"] is True
    assert replay["external_effects"] == []
    assert other["state"] == "setup_required"
    assert other["reason"] == "prior_heygen_effect_unresolved"
    assert len(executor.requests) == 1


def test_unknown_delivery_keeps_durable_fence_and_replay_never_recreates(tmp_path):
    executor = HeygenExecutor(uncertain=True)
    config = user_config(tmp_path)

    with pytest.raises(RuntimeError, match="connection lost"):
        factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)
    replay = factory_render.render_from_config(config, "Breathe.", "first-video", environment=READY, executor=executor)

    assert replay["state"] == "reconciliation_required"
    assert len(executor.requests) == 1
    sidecar = tmp_path / "host/marketing/ebook/runs/factory.your-project.first-video.heygen-effect.json"
    assert json.loads(sidecar.read_text())["state"] == "delivery_uncertain"
