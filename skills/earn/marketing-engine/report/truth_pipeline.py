#!/usr/bin/env python3
"""Serialized free-only publication truth, metrics, and owner-report sweep."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import subprocess
import sys
from collections.abc import Callable


HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
ENGINE_ROOT = HERE.parent


def build_commands(
    repo_root: pathlib.Path,
    home: pathlib.Path,
    *,
    state_root: pathlib.Path | None = None,
    python: str = sys.executable,
) -> list[list[str]]:
    repo_root = pathlib.Path(repo_root)
    home = pathlib.Path(home)
    engine = repo_root / "skills/earn/marketing-engine"
    mutable_root = pathlib.Path(state_root) if state_root is not None else engine
    state = mutable_root / "state"
    evidence = mutable_root / "evidence/metrics"
    publication_ledger = state / "publication-identity.jsonl"
    env = home / "anicca/.env"
    commands = [
        [
            python,
            str(engine / "identity/publication_ledger.py"),
            "--days",
            "8",
            "--env-file",
            str(env),
            "--output",
            str(publication_ledger),
            "--report",
            str(evidence / "publication-reconcile-latest.json"),
            "--quality-gate-exit-code",
            "3",
        ],
        [
            python,
            str(engine / "measure/native_metrics.py"),
            "--ledger",
            str(publication_ledger),
            "--state",
            str(state / "post-metrics.jsonl"),
            "--env",
            str(env),
            "collect",
            "--raw-evidence",
            str(evidence / "provider-responses.jsonl"),
            "--report",
            str(evidence / "native-metrics-latest.json"),
        ],
    ]
    owner_cli = engine / "report/owner_report_cli.py"
    for kind in ("action", "checkpoint", "incident", "experiment"):
        commands.append(
            [
                python,
                str(owner_cli),
                "sweep",
                "--kind",
                kind,
                "--state-root",
                str(state),
            ]
        )
    # product_daily/portfolio_weekly read the metrics loop's own
    # business-outcomes.jsonl (revenue, MRR, subs, trials, installs,
    # proceeds), not this pipeline's post-metrics/publication state.
    metrics_state = home / ".local/state/life-manager/marketing-metrics-daily/state"
    for kind in ("product_daily", "portfolio_weekly"):
        commands.append(
            [
                python,
                str(owner_cli),
                "sweep",
                "--kind",
                kind,
                "--state-root",
                str(metrics_state),
            ]
        )
    return commands


def _stage_name(command: list[str]) -> str:
    rendered = " ".join(command)
    if "publication_ledger.py" in rendered:
        return "reconcile"
    if "native_metrics.py" in rendered:
        return "collect"
    if "owner_report_cli.py" in rendered and "--kind" in command:
        return "report:" + command[command.index("--kind") + 1]
    return command[0]


def run_pipeline(
    commands: list[list[str]],
    *,
    lock_path: pathlib.Path,
    run_command: Callable[[list[str]], int] | None = None,
) -> dict:
    lock_path = pathlib.Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    run_command = run_command or (
        lambda command: subprocess.run(command, check=False).returncode
    )
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {
                "status": "locked",
                "failed_stages": [],
                "attention_stages": [],
                "stages": [],
            }
        stages = []
        failed = []
        attention = []
        for command in commands:
            stage = _stage_name(command)
            returncode = int(run_command(command))
            if stage == "reconcile" and returncode == 3:
                result = "attention"
                attention.append(stage)
            elif returncode != 0:
                result = "fail"
                failed.append(stage)
            else:
                result = "pass"
            stages.append(
                {"stage": stage, "returncode": returncode, "result": result}
            )
        return {
            "status": "failed" if failed else "completed",
            "failed_stages": failed,
            "attention_stages": attention,
            "stages": stages,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    parser.add_argument("--home", type=pathlib.Path, default=pathlib.Path.home())
    parser.add_argument(
        "--state-root",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("LIFE_MANAGER_STATE_ROOT", str(ENGINE_ROOT))),
    )
    parser.add_argument(
        "--lock-path", type=pathlib.Path
    )
    args = parser.parse_args(argv)
    lock_path = args.lock_path or args.state_root / "state/.truth-pipeline.lock"
    result = run_pipeline(
        build_commands(args.repo_root, args.home, state_root=args.state_root),
        lock_path=lock_path,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
