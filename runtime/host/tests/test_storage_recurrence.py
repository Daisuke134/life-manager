"""Private recurrence probes: never fill the host or invoke a real provider."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import sys
import importlib.util

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime/agent-runner"))
spec = importlib.util.spec_from_file_location("recurrence_runner", ROOT / "runtime/agent-runner/agent_runner.py")
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
from runtime.host.storage_policy import load_storage_policy


def test_concurrent_log_bursts_and_next_wake_keep_results_and_usage(tmp_path):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    def invoke(number):
        run = tmp_path / f"run-{number}"; run.mkdir()
        result = run / "result.json"
        binding = {"owner_id": policy.owner_id, "run_id": run.name,
                   "occurrence_id": policy.owner_id+":"+run.name, "release_sha":"a"*40}
        code = "import os,json;os.write(1,b'x'*(3*1024**2)+b'\\n');os.write(2,b'y'*(3*1024**2));print(json.dumps({'type':'turn.completed','usage':{'input_tokens':7,'output_tokens':3}}));open("+repr(str(result))+",'w').write("+repr(json.dumps({"occurrence":number}))+ ")"
        with (run / "stdout.log").open("wb") as stdout, (run / "stderr.log").open("wb") as stderr:
            rc = runner.run_provider_process([sys.executable,"-c",code], stdout=stdout, stderr=stderr,
                timeout=15, cwd=str(run), input_bytes=None, stdin=None, env=dict(os.environ),
                bounded_capture={"policy":policy,"binding":binding,"root":run/"capture","provider":"codex"})
        text, _, error = runner.read_provider_capture(run/"capture")
        assert rc == 0 and error is None
        assert runner.extract_provider_usage("codex",text)["total_tokens"] == 10
        assert sum(p.stat().st_size for p in (run/"capture").rglob("*") if p.is_file()) < 5*1024**2
        return json.loads(result.read_text())["occurrence"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        occurrences = list(pool.map(invoke, [1,2]))
    occurrences.append(invoke(3))
    assert sorted(occurrences) == [1,2,3] and len(set(occurrences)) == 3


def test_shared_host_budget_is_partitioned_over_registered_owners(tmp_path):
    path = tmp_path / "storage-policy.json"
    policy = json.loads((ROOT / "config/storage-policy.json").read_text())
    policy["defaults"]["host_diagnostic_retained_bytes"] = 1024
    path.write_text(json.dumps(policy))
    (tmp_path / "loop-registry.json").write_text(json.dumps({"loops":{"one":{},"two":{}}}))
    assert sum(load_storage_policy(path, o).owner_diagnostic_retained_bytes for o in ["one","two"]) <= 1024
