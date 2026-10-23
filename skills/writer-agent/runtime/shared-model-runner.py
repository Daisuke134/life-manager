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
    parser.add_argument("mode", choices=("agent", "agent-workspace", "judge", "vision", "repair"))
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    workspace: Path | None = None
    workspace_output: Path | None = None
    if args.mode == "agent-workspace":
        workspace_raw = os.environ.get("ARTICLE_RUN_DIR", "")
        output_raw = os.environ.get("ARTICLE_CODEX_OUTPUT_FILE", "")
        schema_raw = os.environ.get("ARTICLE_CODEX_OUTPUT_SCHEMA", "")
        if os.environ.get("ARTICLE_CODEX_NO_TOOLS") != "1":
            print("writer shared runner agent-workspace requires tool-free Codex output", file=sys.stderr)
            return os.EX_USAGE
        workspace_path = Path(workspace_raw)
        output_path = Path(output_raw)
        schema_path = Path(schema_raw)
        if (not workspace_path.is_absolute() or workspace_path.is_symlink()
                or not workspace_path.is_dir() or not output_path.is_absolute()
                or output_path.is_symlink() or output_path.exists()
                or not schema_path.is_absolute() or schema_path.is_symlink()
                or not schema_path.is_file()):
            print("writer shared runner agent-workspace paths are missing or unsafe", file=sys.stderr)
            return os.EX_USAGE
        workspace = workspace_path.resolve()
        if output_path.parent.resolve() != workspace:
            print("writer shared runner agent-workspace output must stay in ARTICLE_RUN_DIR", file=sys.stderr)
            return os.EX_USAGE
        workspace_output = output_path
    prompt = sys.stdin.read() if args.prompt_file == "-" else Path(args.prompt_file).read_text()
    runner = Path(os.environ.get("AGENT_RUNNER_BIN", DEFAULT_RUNNER))
    state = Path(os.environ.get(
        "WRITER_SHARED_RUNNER_STATE",
        Path.home() / ".local/state/life-manager/writer/agent-runner-evidence"))
    evidence = state / f"{args.mode}-{uuid.uuid4().hex}"
    loop_id = os.environ.get("LIFE_MANAGER_LOOP_ID", "writer")
    role = os.environ.get("ARTICLE_MODEL_ROLE", "terra")
    if args.mode == "agent-workspace" and role == "sol-audit":
        print("writer shared runner agent-workspace does not allow sol-audit role", file=sys.stderr)
        return os.EX_USAGE
    schema_override = os.environ.get("ARTICLE_CODEX_OUTPUT_SCHEMA", "").strip()
    text_envelope = args.mode == "agent" and not schema_override
    schema_path = Path(schema_override) if schema_override else (
        AGENT_SCHEMA if text_envelope else SCHEMA)
    task_class = "high-value-agent" if args.mode == "agent" else "composition-agent"
    if args.mode in {"judge", "vision"}:
        # The Writer agent holds acct1 for its whole turn; its judges wait for acct2 instead of
        # failing fast on the account their own parent holds (2026-10-23, run 20261023-053932).
        task_class = "writer-judge-agent"
    workdir = REPO_ROOT
    if args.mode == "agent-workspace":
        # Workspace drafts use the shared runner's tool-less Codex class; the
        # trusted wrapper, not the model, materializes the response file.
        assert workspace is not None
        workdir = workspace
    elif args.mode == "repair":
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
    if args.mode == "agent-workspace":
        if not isinstance(value, dict) or workspace_output is None:
            print("writer shared runner agent-workspace result must be a JSON object", file=sys.stderr)
            return os.EX_DATAERR
        try:
            descriptor = os.open(
                workspace_output,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            print(f"writer shared runner agent-workspace output failed: {type(error).__name__}", file=sys.stderr)
            return os.EX_CANTCREAT
        return 0
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
