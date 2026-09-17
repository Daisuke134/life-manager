import json
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/publish_input_contract.py"
LOCK_SCRIPT = Path(__file__).parents[1] / "scripts/with_publish_lock.py"
CP1_CHECK = Path(__file__).parents[1] / "scripts/verify_cp1_model.py"


def prepared(root: Path, skill: str, agent_id: str, model_id: str) -> list[str]:
    home = root / "homes" / "agents" / agent_id
    workspace = home / ".openclaw/workspace"
    skill_dir = workspace / "skills" / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    icon = root / f"{agent_id}.png"
    icon.write_bytes(b"fixture-icon")
    config = home / "listing-config.json"
    config.write_text(json.dumps({"title": skill, "model_id": model_id,
                                  "max_tokens": 8192, "icon": str(icon)}))
    provider = home / ".openclaw/openclaw.json"
    provider.write_text(json.dumps({
        "models": {"providers": {"openrouter": {
            "api": "openai-responses", "apiKey": "${CAPAFY_HOST_OPENROUTER_KEY}",
            "models": [{"id": model_id, "name": model_id, "maxTokens": 8192}],
        }}}, "agents": {"defaults": {"model": {"primary": "openrouter/" + model_id}}},
    }))
    work = root / "work" / agent_id
    work.mkdir(parents=True)
    (work / "publish-work-state.json").write_text(json.dumps({
        "agent_id": agent_id, "agent_version_id": "version-1",
        "extra": {"runtime_dir": str(workspace),
                  "explicit_skill": {"source_path": str(skill_dir)}},
    }))
    return ["--agent-id", agent_id, "--skill-name", skill, "--config", str(config),
            "--workspace", str(workspace), "--publisher-home", str(home),
            "--work-dir", str(work)]


def run(action: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), action, *args],
                          text=True, capture_output=True)


def test_interleaved_agents_keep_distinct_package_and_model(tmp_path: Path) -> None:
    first = prepared(tmp_path, "marketing", "agent-a", "deepseek/deepseek-v4.1-flash")
    second = prepared(tmp_path, "marketing", "agent-b", "anthropic/claude-sonnet-4.6")
    assert run("write", first).returncode == 0
    assert run("write", second).returncode == 0

    verified = run("verify", first)
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout.strip() == "deepseek/deepseek-v4.1-flash 8192"
    assert run("verify", second).returncode == 0


def test_changed_skill_or_model_blocks_before_publish(tmp_path: Path) -> None:
    args = prepared(tmp_path, "marketing", "agent-a", "deepseek/deepseek-v4.1-flash")
    assert run("write", args).returncode == 0
    workspace = Path(args[args.index("--workspace") + 1])
    (workspace / "skills/marketing/SKILL.md").write_text("# changed after preparation\n")
    assert run("verify", args).returncode != 0

    (workspace / "skills/marketing/SKILL.md").write_text("# marketing\n")
    config = Path(args[args.index("--config") + 1])
    changed = json.loads(config.read_text())
    changed["model_id"] = "anthropic/claude-sonnet-4.6"
    config.write_text(json.dumps(changed))
    assert run("verify", args).returncode != 0
    assert run("verify", ["--agent-id", "agent-b", *args[2:]]).returncode != 0


def test_manifest_source_and_version_must_match_prepared_inputs(tmp_path: Path) -> None:
    args = prepared(tmp_path, "marketing", "agent-a", "deepseek/deepseek-v4.1-flash")
    assert run("write", args).returncode == 0
    work = Path(args[args.index("--work-dir") + 1])
    manifest_path = work / "publish-work-state.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["extra"]["explicit_skill"]["source_path"] = str(tmp_path / "wrong-skill")
    manifest_path.write_text(json.dumps(manifest))
    assert run("verify", args).returncode != 0

    manifest["extra"]["explicit_skill"]["source_path"] = str(
        Path(args[args.index("--workspace") + 1]) / "skills/marketing")
    manifest["agent_version_id"] = "version-2"
    manifest_path.write_text(json.dumps(manifest))
    assert run("verify", args).returncode != 0

    manifest["agent_version_id"] = "version-1"
    manifest["extra"]["external_skill_bindings"] = [
        {"source_path": str(tmp_path / "other-skill")},
    ]
    manifest_path.write_text(json.dumps(manifest))
    assert run("verify", args).returncode != 0


def test_publisher_lock_serializes_prepare_and_finish(tmp_path: Path) -> None:
    environment = {**os.environ, "CAPAFY_PUBLISHER_STATE_HOME": str(tmp_path)}
    first = subprocess.Popen([sys.executable, str(LOCK_SCRIPT), "-c", "sleep 1"],
                             env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        lock = tmp_path / "locks/publisher.lock"
        deadline = time.monotonic() + 2
        while not lock.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert lock.exists()
        blocked = subprocess.run([sys.executable, str(LOCK_SCRIPT), "-c", "true"],
                                 env=environment, capture_output=True)
        assert blocked.returncode == 75
    finally:
        first.wait(timeout=3)
    released = subprocess.run([sys.executable, str(LOCK_SCRIPT), "-c", "true"],
                              env=environment, capture_output=True)
    assert released.returncode == 0


def test_official_cp1_model_must_match_exact_version_and_listing_model() -> None:
    spec = importlib.util.spec_from_file_location("verify_cp1_model", CP1_CHECK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    payload = {"code": 0, "data": {"agentId": "9563867391",
                                    "agentVersionId": "version-2",
                                    "model": "DeepSeek V4.1 Flash",
                                    "isConfirmedSkills": 1}}
    assert module.matches(payload, "9563867391", "version-2", "DeepSeek V4.1 Flash")
    assert not module.matches(payload, "9563867391", "version-1", "DeepSeek V4.1 Flash")
    assert not module.matches(payload, "9563867391", "version-2", "Claude Sonnet 4.6")
    payload["data"]["isConfirmedSkills"] = 0
    assert not module.matches(payload, "9563867391", "version-2", "DeepSeek V4.1 Flash")
