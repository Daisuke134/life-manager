#!/usr/bin/env python3
"""Legacy Writer judge CLI adapter for the repository-global agent runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
SCHEMA = HERE / "shared-model-output.schema.json"
# An agent pass reports in prose; its effects are the product. The schema {}
# is falsy in agent_runner, so Codex got no --output-schema, answered in prose,
# and every completed pass failed JSON validation as a silent rc=1
# (run 20261017-033711). Same envelope promptbase/gen_examples.py uses.
AGENT_SCHEMA = HERE / "shared-agent-output.schema.json"


def parse_contract_result(text: str) -> object:
    """Extract the contract JSON from a provider reply with optional preamble.

    The canonical agent runner validates this same boundary before returning a
    successful summary.  Keep the adapter's final readback aligned with that
    contract: a judge that says ``I checked...`` followed by one JSON object is
    valid, while prose with no JSON remains a hard failure.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character not in "{[":
                continue
            try:
                value, _ = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                continue
            return value
    raise ValueError("no JSON object in provider result")


def failure_line(returncode: int, evidence: Path) -> str:
    """One stderr line naming why the canonical runner failed, never silent."""
    last: dict = {}
    try:
        rows = (evidence / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        last = json.loads(rows[-1]) if rows else {}
    except (OSError, ValueError):
        pass
    fields = {key: last.get(key) for key in
              ("attempt", "provider", "rc", "timed_out", "error_class",
               "launch_error", "schema_errors")}
    return (f"writer shared runner failed rc={returncode} "
            f"{json.dumps(fields, ensure_ascii=False)[:600]} evidence={evidence}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("agent", "judge", "vision", "repair"))
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    prompt = sys.stdin.read() if args.prompt_file == "-" else Path(args.prompt_file).read_text()
    runner = Path(os.environ.get("AGENT_RUNNER_BIN", DEFAULT_RUNNER))
    state = Path(os.environ.get(
        "WRITER_SHARED_RUNNER_STATE",
        Path.home() / ".local/state/life-manager/writer/agent-runner-evidence"))
    evidence = state / f"{args.mode}-{uuid.uuid4().hex}"
    loop_id = os.environ.get("LIFE_MANAGER_LOOP_ID", "writer")
    role = os.environ.get("ARTICLE_MODEL_ROLE", "terra")
    schema_override = os.environ.get("ARTICLE_CODEX_OUTPUT_SCHEMA", "").strip()
    text_envelope = args.mode == "agent" and not schema_override
    schema_path = Path(schema_override) if schema_override else (
        AGENT_SCHEMA if text_envelope else SCHEMA)
    task_class = "high-value-agent" if args.mode == "agent" else "composition-agent"
    workdir = REPO_ROOT
    if args.mode == "repair":
        task_class = "writer-repair-agent"
        workspace = os.environ.get("ARTICLE_REPAIR_WORKSPACE", "")
        if not workspace or not Path(workspace).is_dir():
            print("writer shared runner repair requires ARTICLE_REPAIR_WORKSPACE", file=sys.stderr)
            return os.EX_USAGE
        workdir = Path(workspace).resolve()
    if role == "sol-audit":
        task_class = "writer-sol-audit"
    command = [sys.executable, str(runner), "--task-class", task_class,
               "--prompt-stdin", "--schema", str(schema_path), "--evidence-dir", str(evidence),
               "--task-label", f"writer-{args.mode}", "--loop", loop_id,
               "--workdir", str(workdir)]
    if args.mode == "vision":
        if not args.image:
            print("writer shared runner vision requires --image", file=sys.stderr)
            return os.EX_USAGE
        command.extend(["--image", args.image])
    if role == "sol-audit":
        command.extend(["--escalation-reason", "writer-sol-trigger"])
    resume_id = os.environ.get("ARTICLE_CODEX_RESUME_SESSION_ID", "").strip()
    if resume_id:
        command.extend(["--codex-resume-session-id", resume_id])
    events_file = os.environ.get("ARTICLE_CODEX_EVENTS_FILE", "").strip()
    if events_file:
        event_path = Path(events_file)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_path.unlink(missing_ok=True)
        event_path.symlink_to(evidence / "attempt-01.stdout.log")
    completed = subprocess.run(
        command,
        input=prompt, capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        sys.stderr.write(completed.stderr)
        sys.stderr.write(failure_line(completed.returncode, evidence) + "\n")
        return completed.returncode
    try:
        summary = json.loads((evidence / "summary.json").read_text())
        value = parse_contract_result(Path(summary["result_path"]).read_text())
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"writer shared runner result invalid: {error}", file=sys.stderr)
        return os.EX_DATAERR
    last_message = os.environ.get("ARTICLE_CODEX_LAST_MESSAGE_FILE", "").strip()
    if last_message:
        Path(last_message).write_text(
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            encoding="utf-8")
    if text_envelope and isinstance(value, dict) and isinstance(value.get("text"), str):
        value = value["text"]
    print(value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
