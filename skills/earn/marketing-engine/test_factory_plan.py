from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import runpy
import socket
import sqlite3
import subprocess
import urllib.request

import pytest

from render_eval.heygen_candidate import build_request


ENGINE = Path(__file__).resolve().parent
CLI = ENGINE / "bin" / "lm"


def user_config(tmp_path, language="en"):
    return {
        "schema_version": "ai-monk-factory.config.v1",
        "project_id": "your-project",
        "language": language,
        "heygen": {"avatar_id": "your_avatar_id", "voice_id": "your_voice_id"},
        "postiz": {"platform": "tiktok", "integration_id": "your-postiz-integration"},
        "product": {"name": "Your product", "url": "https://example.invalid/your-product"},
        "state_root": str(tmp_path / f"your-state-{language}"),
    }


def expected_plan(config, script):
    request = build_request(script, {"status": "ready", **config["heygen"]}, language=config["language"])
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "ai-monk-factory.plan.v1",
        "status": "planned",
        "project_id": config["project_id"],
        "language": config["language"],
        "state_root": os.path.normpath(str(Path(config["state_root"]).expanduser())),
        "render_request": request,
        "request_sha256": hashlib.sha256(encoded).hexdigest(),
        "publication_plan": {"provider": "postiz", **config["postiz"], "product": config["product"]},
        "provider_calls": 0,
        "external_effects": [],
    }


def forbid_effects(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline plan attempted an external effect")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", forbidden)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)


def invoke_cli(config_path, script_path, monkeypatch):
    forbid_effects(monkeypatch)
    read_text = Path.read_text

    def input_only(path, *args, **kwargs):
        assert path in (config_path, script_path), "offline plan read a non-input file"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", input_only)
    main = runpy.run_path(str(CLI))["main"]
    try:
        return main(["factory", "plan", "--config", str(config_path), "--script", str(script_path)])
    except SystemExit as exc:
        return exc.code


@pytest.mark.parametrize("language,script", [("en", "  Breathe slowly.  "), ("ja", "  一度だけ肩をゆるめてください。  ")])
def test_cli_plans_user_inputs_without_provider_calls(tmp_path, monkeypatch, capsys, language, script):
    config = user_config(tmp_path, language)
    config_path = tmp_path / "config.json"
    script_path = tmp_path / "script.txt"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    marker = "fixture-secret-must-not-appear"
    for name in ("HEYGEN_API_KEY", "POSTIZ_API_KEY", "LM_EBOOK_EN_HEYGEN_AVATAR_ID", "LM_EBOOK_EN_HEYGEN_VOICE_ID"):
        monkeypatch.setenv(name, marker)

    code = invoke_cli(config_path, script_path, monkeypatch)

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.err == ""
    assert json.loads(captured.out) == expected_plan(config, script)
    assert marker not in captured.out + captured.err
    assert not Path(config["state_root"]).exists()


@pytest.mark.parametrize("language,script", [("en", "  Breathe slowly.  "), ("ja", "  一度だけ肩をゆるめてください。  ")])
def test_build_plan_reuses_canonical_request_and_user_destinations(tmp_path, monkeypatch, language, script):
    from factory_plan import build_plan

    config = user_config(tmp_path, language)
    original = json.loads(json.dumps(config))
    forbid_effects(monkeypatch)

    plan = build_plan(config, script)

    assert plan == expected_plan(config, script)
    assert config == original
    assert not Path(config["state_root"]).exists()


def test_build_plan_expands_and_normalizes_state_without_reading_it(tmp_path, monkeypatch):
    from factory_plan import build_plan

    config = user_config(tmp_path)
    config["state_root"] = "~/your-factory-unused/../your-factory-state"
    monkeypatch.setenv("HOME", str(tmp_path))
    forbid_effects(monkeypatch)

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("planner read state or credentials")

    monkeypatch.setattr(Path, "read_text", forbidden_read)

    plan = build_plan(config, "Breathe.")

    assert plan["state_root"] == str(tmp_path / "your-factory-state")
    assert not (tmp_path / "your-factory-state").exists()


INVALID_CONFIGS = [
    ((), None),
    (("schema_version",), "wrong-schema"),
    (("schema_version",), None),
    (("project_id",), "Your Project"),
    (("project_id",), "p" * 65),
    (("language",), "fr"),
    (("language",), []),
    (("heygen",), []),
    (("heygen", "avatar_id"), "short"),
    (("heygen", "voice_id"), 12345678),
    (("postiz", "platform"), "youtube"),
    (("postiz", "platform"), []),
    (("postiz", "integration_id"), ""),
    (("postiz", "integration_id"), "has space"),
    (("postiz", "integration_id"), "has\x00control"),
    (("postiz", "integration_id"), "i" * 129),
    (("postiz", "integration_id"), 123),
    (("product", "name"), "  "),
    (("product", "name"), "n" * 201),
    (("product", "name"), []),
    (("product", "url"), "http://example.invalid/product"),
    (("product", "url"), "https://user:fixture-secret@example.invalid/product"),
    (("product", "url"), "https:///product"),
    (("product", "url"), "https://example.invalid:invalid/product"),
    (("product", "url"), "https://example.invalid/has\nnewline"),
    (("product", "url"), []),
    (("state_root",), "relative/state"),
    (("state_root",), []),
]


@pytest.mark.parametrize("path,value", INVALID_CONFIGS)
def test_build_plan_rejects_invalid_config_without_echoing_values(tmp_path, path, value):
    from factory_plan import build_plan

    config = user_config(tmp_path)
    if not path:
        config = value
    else:
        target = config
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    with pytest.raises(ValueError) as caught:
        build_plan(config, "Breathe.")
    assert "fixture-secret" not in str(caught.value)


@pytest.mark.parametrize("section", [None, "heygen", "postiz", "product"])
def test_build_plan_rejects_unknown_credential_fields_without_echo(tmp_path, section):
    from factory_plan import build_plan

    config = user_config(tmp_path)
    target = config if section is None else config[section]
    target["fixture-secret-field"] = "fixture-secret-value"
    with pytest.raises(ValueError) as caught:
        build_plan(config, "Breathe.")
    assert "fixture-secret" not in str(caught.value)


@pytest.mark.parametrize("script", ["", "  \n", "s" * 5001, None])
def test_build_plan_rejects_invalid_script(tmp_path, script):
    from factory_plan import build_plan

    with pytest.raises(ValueError, match="script"):
        build_plan(user_config(tmp_path), script)


@pytest.mark.parametrize("contents", [
    '{"fixture-secret-value":',
    '[]',
    '{"schema_version": "ai-monk-factory.config.v1", "api_key": "fixture-secret-value"}',
])
def test_cli_rejects_invalid_inputs_as_secret_free_json(tmp_path, monkeypatch, capsys, contents):
    config_path = tmp_path / "config.json"
    script_path = tmp_path / "script.txt"
    config_path.write_text(contents, encoding="utf-8")
    script_path.write_text("Breathe.", encoding="utf-8")

    code = invoke_cli(config_path, script_path, monkeypatch)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["status"] == "failed"
    assert error["error"]
    assert "fixture-secret" not in captured.err
