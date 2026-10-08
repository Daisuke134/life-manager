from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import time
from pathlib import Path


def _is_duplicate_runtime_module_typo(command: str) -> bool:
    if any(
        marker in command
        for marker in ("$(", "`", ";", "&&", "||", "|", ">", "<", "\n")
    ):
        return False
    try:
        parts = shlex.split(command)
        if parts[:2] == ["/bin/zsh", "-lc"] and len(parts) == 3:
            parts = shlex.split(parts[2])
    except ValueError:
        return False
    return (
        len(parts) >= 3
        and parts[0]
        in {
            "/opt/homebrew/bin/python3",
            "/opt/homebrew/opt/python@3.14/bin/python3.14",
        }
        and parts[1:3]
        == ["-m", "job_search_loop.browser_agent.browser_agent.runtime"]
    )


def _runtime_command_parts(command: str) -> list[str]:
    if any(marker in command for marker in ("$(", "`", ";", "&&", "||", "|", ">", "<", "\n")):
        return []
    try:
        parts = shlex.split(command)
        if parts[:2] == ["/bin/zsh", "-lc"] and len(parts) == 3:
            parts = shlex.split(parts[2])
        return parts
    except ValueError:
        return []


def validate_pass_result(evidence_dir: Path) -> str | None:
    summary_path = evidence_dir / "summary.json"
    if not summary_path.is_file():
        return None
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        result_path = Path(str(summary.get("result_path") or ""))
        attempts_path = Path(str(summary.get("attempts_path") or ""))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        result_path.parent != evidence_dir
        or attempts_path.parent != evidence_dir
        or not result_path.is_file()
        or not attempts_path.is_file()
    ):
        return None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    status = result.get("status")
    if result.get("submit_unknown"):
        return "submission_outcome_unknown"
    if result.get("submitted"):
        return None
    retry_in_progress = (
        status == "in_progress"
        and result.get("submitted") == []
        and result.get("submit_unknown") == []
    )
    retry_queue_complete = (
        status == "queue_complete"
        and result.get("submitted") == []
        and result.get("submit_unknown") == []
        and result.get("blocked") == []
    )
    retry_reason = (
        "in_progress_without_terminal_outcome"
        if retry_in_progress
        else (
            "observed_row_without_terminal_outcome"
            if retry_queue_complete
            else "transport_failed_without_command_failure"
        )
    )
    try:
        attempt = json.loads(attempts_path.read_text(encoding="utf-8").splitlines()[-1])
        stdout_path = Path(str(attempt.get("stdout_path") or ""))
    except (OSError, json.JSONDecodeError, IndexError):
        return retry_reason if status == "transport_failed" else None
    if stdout_path.parent != evidence_dir or not stdout_path.is_file():
        return retry_reason if status == "transport_failed" else None
    latest_observe_status: str | None = None
    active_runtime_ids: set[str] = set()
    real_nonzero_runtime_completion = False
    for line in stdout_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        item_id = item.get("id")
        item_id = item_id if isinstance(item_id, str) and item_id else None
        command = str(item.get("command") or "")
        command_parts = _runtime_command_parts(command)
        canonical_runtime = (len(command_parts) >= 4 and Path(command_parts[0]).name in {"python", "python3", "python3.14"} and command_parts[1:3] == ["-m", "job_search_loop.browser_agent.runtime"])
        if event_type == "item.started" and canonical_runtime and item_id:
            if real_nonzero_runtime_completion:
                return "runtime_command_after_nonzero_completion"
            active_runtime_ids.add(item_id)
        matched_runtime = bool(item_id and item_id in active_runtime_ids)
        if matched_runtime and event_type == "item.completed":
            active_runtime_ids.remove(item_id)
        if (
            event_type == "item.completed"
            and canonical_runtime
            and isinstance(item.get("exit_code"), int)
            and not isinstance(item.get("exit_code"), bool)
            and item["exit_code"] == 0
        ):
            if command_parts[3:] == ["observe"]:
                output = item.get("aggregated_output")
                if isinstance(output, str):
                    try:
                        observe_result = json.loads(output)
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(observe_result, dict) and isinstance(
                            observe_result.get("status"), str
                        ):
                            latest_observe_status = observe_result["status"]
        if (
            event_type == "item.completed"
            and isinstance(item.get("exit_code"), int)
            and item["exit_code"] != 0
        ):
            output = str(item.get("aggregated_output") or "")
            if output.startswith("zsh:") and "unmatched" in output:
                continue
            if (
                "job_search_loop.runtime" in command
                and "job_search_loop.browser_agent.runtime" not in command
                and "following arguments are required: command" in output
            ):
                continue
            if (
                _is_duplicate_runtime_module_typo(command)
                and "ModuleNotFoundError" in output
            ):
                continue
            if canonical_runtime and matched_runtime:
                real_nonzero_runtime_completion = True
                continue
            return None
    if real_nonzero_runtime_completion:
        return "runtime_command_nonzero_completion"
    if (
        status != "transport_failed"
        and not retry_in_progress
        and not retry_queue_complete
    ):
        return None
    if retry_queue_complete and latest_observe_status != "observed":
        return None
    return retry_reason


def invoke_runner(
    *,
    runner: Path,
    prompt: Path,
    schema: Path,
    evidence_dir: Path,
    workdir: Path,
    timeout_seconds: int,
    python: str,
    active_provider: str,
) -> int:
    """Delegate one wake to the existing bounded model runner."""
    environment = os.environ.copy()
    if active_provider == "all":
        environment.pop("JOB_SEARCH_ACTIVE_APPLICATION_PROVIDER", None)
    else:
        environment["JOB_SEARCH_ACTIVE_APPLICATION_PROVIDER"] = active_provider
    reason = None
    deadline = time.monotonic() + timeout_seconds
    for semantic_attempt in range(2):
        remaining_seconds = math.ceil(deadline - time.monotonic())
        if remaining_seconds < 1:
            break
        command = [
            python,
            str(runner),
            "--task-class",
            "job-hunter-agent",
            "--escalation-reason",
            "repeated browser form completion abandoned before provider terminal outcome",
            "--timeout-seconds",
            str(remaining_seconds),
            "--prompt-file",
            str(prompt),
            "--schema",
            str(schema),
            "--evidence-dir",
            str(evidence_dir),
            "--task-label",
            "job-search-daily",
            "--loop",
            "job-search",
            "--workdir",
            str(workdir),
        ]
        returncode = subprocess.run(command, check=False, env=environment).returncode
        if returncode != 0:
            return returncode
        reason = validate_pass_result(evidence_dir)
        if reason is None:
            return 0
        if reason == "submission_outcome_unknown":
            break
        if semantic_attempt == 0:
            continue
    receipt = evidence_dir / "semantic-validation.json"
    receipt.write_text(
        json.dumps({"status": "failed", "reason": reason}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(receipt, 0o600)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument(
        "--active-provider", choices=("workday", "ashby", "all"), required=True
    )
    args = parser.parse_args(argv)
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")
    return invoke_runner(
        runner=args.runner,
        prompt=args.prompt,
        schema=args.schema,
        evidence_dir=args.evidence_dir,
        workdir=args.workdir,
        timeout_seconds=args.timeout_seconds,
        python=args.python,
        active_provider=args.active_provider,
    )


if __name__ == "__main__":
    raise SystemExit(main())
