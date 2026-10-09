import importlib.util
import json
import os
from pathlib import Path
import sys
from dataclasses import replace

from runtime.host.bounded_output import start_stderr_relay, read_relay_snapshot
from runtime.host.storage_policy import load_storage_policy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime/agent-runner"))
spec = importlib.util.spec_from_file_location("bounded_agent_runner", ROOT / "runtime/agent-runner/agent_runner.py")
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def test_codex_usage_survives_large_raw_diagnostics(tmp_path):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    binding = {"owner_id": policy.owner_id, "run_id": "run-1", "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a"*40}
    handle = start_stderr_relay(tmp_path, policy, binding, stream_kind="codex")
    event = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3}}).encode()+b"\n"
    for _ in range(2048): os.write(handle.stdin_write_fd, b"x"*4096)
    os.write(handle.stdin_write_fd, b"\n"+event)
    os.close(handle.stdin_write_fd); handle.process.wait(timeout=10)
    read_relay_snapshot(handle); handle.control_socket.close()
    text = (tmp_path / "semantic-stdout.json").read_text()
    usage = runner.extract_provider_usage("codex", text)
    assert usage["input_tokens"] == 7 and usage["output_tokens"] == 3
    assert usage["total_tokens"] == 10
    assert sum(p.stat().st_size for p in tmp_path.iterdir() if p.is_file()) <= 2*1024**2+40*1024


def test_provider_process_keeps_result_and_usage_with_bounded_capture(tmp_path):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    binding = {"owner_id": policy.owner_id, "run_id": "run-1", "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a"*40}
    result = tmp_path / "result.json"
    code = "import os,json;os.write(1,b'x'*(8*1024**2)+b'\\n');os.write(2,b'y'*(4*1024**2));print(json.dumps({'type':'turn.completed','usage':{'input_tokens':7,'output_tokens':3}}));open("+repr(str(result))+",'w').write('{\"status\":\"success\"}')"
    with (tmp_path / "stdout.log").open("wb") as out, (tmp_path / "stderr.log").open("wb") as err:
        rc = runner.run_provider_process([sys.executable, "-c", code], stdout=out, stderr=err,
            timeout=10, cwd=str(tmp_path), input_bytes=None, stdin=None, env=dict(os.environ),
            bounded_capture={"policy": policy, "binding": binding, "root": tmp_path / "capture", "provider": "codex"})
    assert rc == 0
    assert json.loads(result.read_text()) == {"status": "success"}
    stdout_text, stderr_text, error = runner.read_provider_capture(tmp_path / "capture")
    assert error is None
    assert runner.extract_provider_usage("codex", stdout_text)["total_tokens"] == 10
    assert len(stderr_text.encode()) <= 65536 + 64


def test_oversized_structured_record_is_never_accepted_as_complete(tmp_path):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    policy = replace(policy, structured_record_max_bytes=64)
    binding = {"owner_id": policy.owner_id, "run_id": "run-1", "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a"*40}
    handle = start_stderr_relay(tmp_path, policy, binding, stream_kind="json")
    os.write(handle.stdin_write_fd, json.dumps({"result": "x"*1000}).encode())
    os.close(handle.stdin_write_fd); handle.process.wait(timeout=10)
    receipt = read_relay_snapshot(handle); handle.control_socket.close()
    assert receipt["result_oversized"] is True
    assert (tmp_path / "semantic-stdout.json").read_text() == ""
