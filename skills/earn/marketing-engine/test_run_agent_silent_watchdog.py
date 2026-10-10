"""run_agent.sh silent-start watchdog (2026-10-08).

17:13 JST the Capafy CP1 agent sat for 1200s producing 0 bytes of stdout/stderr and was killed by the
outer timeout, burning a whole factory pass with nothing to diagnose. If the provider child has
written nothing after RUN_AGENT_SILENT_START_SECONDS the runner is stopped and who holds the
provider profile locks is recorded.
"""
import os
import subprocess
import time
from pathlib import Path

RUN_AGENT = Path(__file__).resolve().parent / "run_agent.sh"
PROMPT = "x" * 400


def _run(tmp_path, runner_body, silent_seconds):
    runner = tmp_path / "fake_runner.py"
    runner.write_text(runner_body)
    evidence = tmp_path / "evidence"
    env = {**os.environ, "AGENT_RUNNER_BIN": str(runner),
           "RUN_AGENT_SILENT_START_SECONDS": str(silent_seconds),
           "RUN_AGENT_SILENT_POLL_SECONDS": "1"}
    started = time.monotonic()
    proc = subprocess.run(
        ["bash", str(RUN_AGENT), "--task-class", "application-lane-agent", "--evidence-dir", str(evidence),
         "--task-label", "t", "--loop", "capafy", "--workdir", str(tmp_path)],
        input=PROMPT, text=True, capture_output=True, env=env, timeout=60)
    return proc, evidence, time.monotonic() - started


SILENT_RUNNER = """
import sys, time
time.sleep(40)  # never writes attempt-01.stdout.log
"""

CHATTY_RUNNER = """
import argparse, pathlib, sys, time
a = argparse.ArgumentParser(); a.add_argument('--evidence-dir'); a.parse_known_args()
args, _ = a.parse_known_args()
d = pathlib.Path(args.evidence_dir); d.mkdir(parents=True, exist_ok=True)
(d / 'attempt-01.stdout.log').write_text('started\\n')
time.sleep(4)
print('{"status":"ok","evidence":["done"]}')
"""


def test_silent_provider_is_stopped_early_and_diagnosed(tmp_path):
    proc, evidence, elapsed = _run(tmp_path, SILENT_RUNNER, silent_seconds=2)
    assert proc.returncode != 0
    assert elapsed < 20, f"must not wait out the runner (took {elapsed:.0f}s)"
    note = (evidence / "silent-start-diagnosis.txt")
    assert note.exists()
    assert "no provider output" in note.read_text()


def test_provider_that_has_started_writing_is_left_alone(tmp_path):
    proc, evidence, elapsed = _run(tmp_path, CHATTY_RUNNER, silent_seconds=2)
    assert proc.returncode == 0, proc.stderr
    assert not (evidence / "silent-start-diagnosis.txt").exists()


# Since #7445 (2026-10-10) agent_runner relays provider output into
# attempt-NN-<id>.capture/{stdout,stderr}/stderr.log and leaves attempt-NN.std*.log empty.
# The watchdog only looked at the top-level logs, so it killed a working Capafy CP1 agent
# at 420s on every pass (12:47, 13:35, 14:03 JST).
CAPTURE_RUNNER = """
import argparse, pathlib, time
a = argparse.ArgumentParser(); a.add_argument('--evidence-dir')
args, _ = a.parse_known_args()
d = pathlib.Path(args.evidence_dir); d.mkdir(parents=True, exist_ok=True)
(d / 'attempt-01.stdout.log').write_text('')
cap = d / 'attempt-01-abc.capture' / 'stdout'; cap.mkdir(parents=True)
(cap / 'stderr.log').write_text('working\\n')
time.sleep(4)
print('{"status":"ok","evidence":["done"]}')
"""


def test_provider_writing_only_into_capture_dir_is_left_alone(tmp_path):
    proc, evidence, elapsed = _run(tmp_path, CAPTURE_RUNNER, silent_seconds=2)
    assert proc.returncode == 0, proc.stderr
    assert not (evidence / "silent-start-diagnosis.txt").exists()
