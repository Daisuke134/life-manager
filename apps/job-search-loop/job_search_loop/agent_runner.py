from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any


TASK_CLASSES = {
    "extract": "composition-agent",
    "tailor": "composition-agent",
    "inbox": "composition-agent",
    "mercor_pass": "browser-lane-agent",
    "submit": "browser-lane-agent",
    "improve": "high-value-agent",
}
AGENT_RUNNER_TIMEOUT_SECONDS = 1_000


class ContractError(RuntimeError):
    pass


class PassAlreadyRunning(RuntimeError):
    pass


def _terminate_process_group(process: subprocess.Popen) -> None:
    """Stop an agent-runner process and its provider descendants after timeout."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    else:
        process.kill()
        process.wait(timeout=5)


def _forward_signal_after_cleanup(
    signum: int, _frame: Any, process: subprocess.Popen,
) -> None:
    """Stop the owned runner group before preserving the parent's signal."""
    _terminate_process_group(process)
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def wrap_untrusted(name: str, text: str) -> str:
    safe_name = "".join(character for character in name if character.isalnum() or character in "_-")
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return (
        f'<untrusted_data name="{safe_name}" encoding="base64">\n'
        + encoded
        + "\n</untrusted_data>"
    )


class AgentRunner:
    def __init__(self, *, evidence_root: Path, runner_path: Path | None = None):
        repo_root = Path(__file__).resolve().parents[3]
        self.runner_path = Path(
            runner_path
            or repo_root / "runtime" / "agent-runner" / "agent_runner.py"
        )
        self.evidence_root = Path(evidence_root)

    @staticmethod
    def validate(value: Any, schema: dict[str, Any]) -> None:
        if schema.get("type") == "object" and not isinstance(value, dict):
            raise ContractError("result must be an object")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    raise ContractError(f"missing required result field: {key}")

    def run(
        self,
        *,
        task: str,
        prompt: str,
        schema_path: Path,
        workdir: Path,
        run_id: str,
    ) -> dict[str, Any]:
        task_class = TASK_CLASSES.get(task)
        if task_class is None:
            raise ValueError(f"unknown task: {task}")
        evidence_dir = self.evidence_root / run_id
        evidence_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(evidence_dir, 0o700)
        prompt_path = evidence_dir / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        os.chmod(prompt_path, 0o600)
        argv = [
            "python3",
            str(self.runner_path),
            "--task-class",
            task_class,
        ]
        if task == "mercor_pass":
            argv.extend([
                "--escalation-reason",
                "bounded multi-page Mercor application completion with official browser readback",
            ])
        prompt_input = None
        if task_class in {"composition-agent", "diagnostic-agent"}:
            argv.append("--prompt-stdin")
            prompt_input = prompt
        else:
            argv.extend(["--prompt-file", str(prompt_path)])
        argv.extend([
            "--schema",
            str(schema_path),
            "--evidence-dir",
            str(evidence_dir),
            "--workdir",
            str(workdir),
            "--loop",
            "job-search",
            "--task-label",
            task,
        ])
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if prompt_input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
        previous_handlers: dict[int, Any] = {}
        if os.name == "posix":
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(
                    signum,
                    lambda received, frame, process=process: _forward_signal_after_cleanup(
                        received, frame, process
                    ),
                )
        try:
            stdout, stderr = process.communicate(
                input=prompt_input, timeout=AGENT_RUNNER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            _terminate_process_group(process)
            raise ContractError("agent runner timed out") from error
        except BaseException:
            _terminate_process_group(process)
            raise
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
        completed = subprocess.CompletedProcess(
            argv, process.returncode, stdout, stderr,
        )
        if (
            completed.returncode == 75
            and "LIFE_MANAGER_PROVIDER_LEASE_BUSY" in completed.stderr.splitlines()
        ):
            raise PassAlreadyRunning()
        if completed.returncode != 0:
            raise ContractError(
                f"agent runner failed rc={completed.returncode}: {completed.stderr[-500:]}"
            )
        try:
            summary = json.loads(completed.stdout)
            result_path = Path(summary["result_path"])
            value = json.loads(result_path.read_text(encoding="utf-8"))
            schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        except (KeyError, OSError, json.JSONDecodeError) as error:
            raise ContractError(f"invalid runner evidence: {error}") from error
        self.validate(value, schema)
        return value
