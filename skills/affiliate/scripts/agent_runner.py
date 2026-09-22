#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import machine_capability_inventory as inventory


SKILL_ROOT = HERE.parent
REPO_ROOT = SKILL_ROOT.parents[1]
VENDOR = REPO_ROOT / "runtime" / "agent-runner"


class PinError(Exception):
    pass


class EvidenceError(Exception):
    pass


PASSTHROUGH_ENV = (
    "LANG",
    "LC_ALL",
    "TZ",
    "ANICCA_BUDGET_SCOPE_ID",
    "ANICCA_PASS_TOKEN_BUDGET",
    "ANICCA_LOOP_DAILY_TOKEN_BUDGET",
    "ANICCA_BUDGET_REQUIRED",
    "ANICCA_BUDGET_DAILY_SCOPE",
    "ANICCA_TOKEN_BUDGET_LEDGER",
    "ANICCA_BUDGET_DAY_TZ",
    "ANICCA_USAGE_LEDGER",
)


def budget_retry_after(summary: dict) -> str | None:
    """Return the next JST budget boundary without exposing provider data."""
    budget = summary.get("budget") if isinstance(summary, dict) else None
    day = budget.get("day") if isinstance(budget, dict) else None
    if not isinstance(day, str):
        return None
    try:
        boundary = datetime.fromisoformat(day).replace(
            hour=0, minute=0, second=0, microsecond=0,
            tzinfo=ZoneInfo("Asia/Tokyo"),
        ) + timedelta(days=1)
    except ValueError:
        return None
    return boundary.astimezone(timezone.utc).isoformat()


def _owner_path(value: str, owner_home: Path) -> Path:
    if value == "~":
        return owner_home
    if value.startswith("~/"):
        return owner_home / value[2:]
    path = Path(value)
    return path if path.is_absolute() else owner_home / path


def allowlisted_environment(source: dict[str, str], executable: Path) -> dict[str, str]:
    owner_home = Path(source.get("HOME") or str(Path.home())).resolve()
    child = {
        "PATH": os.pathsep.join((str(executable.parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin")),
        "HOME": str(owner_home),
        "AGENT_RUNNER_CONFIG": str(VENDOR / "config.json"),
    }
    for name in PASSTHROUGH_ENV:
        if source.get(name):
            child[name] = source[name]
    return child


def secure_evidence_tree(evidence_dir: Path) -> None:
    if evidence_dir.is_symlink():
        raise EvidenceError
    evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in (evidence_dir, *evidence_dir.rglob("*")):
        if path.is_symlink():
            raise EvidenceError
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)
        else:
            raise EvidenceError


def _source_set_sha256(value: str | None, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EvidenceError
    return value


def _result_path(evidence_dir: Path, summary: dict, *, required: bool) -> Path | None:
    value = summary.get("result_path")
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise EvidenceError
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = evidence_dir / candidate
    candidate = candidate.resolve()
    if candidate.parent != evidence_dir.resolve() or not candidate.is_file():
        raise EvidenceError
    return candidate


def seal_evidence(
    evidence_dir: Path, runner_exit_code: int, source_set_sha256: str | None = None
) -> Path:
    secure_evidence_tree(evidence_dir)
    summary_path = evidence_dir / "summary.json"
    attempts_path = evidence_dir / "attempts.jsonl"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise EvidenceError
        attempt_count = int(summary.get("attempt_count", 0))
        attempt_rows = []
        if attempts_path.is_file():
            attempt_rows = [
                json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if any(not isinstance(row, dict) for row in attempt_rows) or len(attempt_rows) != attempt_count:
            raise EvidenceError
        source_set_sha256 = _source_set_sha256(source_set_sha256)
        result_path = _result_path(
            evidence_dir, summary, required=source_set_sha256 is not None
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise EvidenceError
    seal_path = evidence_dir / "evidence-seal.json"
    inventory.write_receipt(seal_path, {
        "schema_version": 1,
        "status": "SEALED",
        "runner_exit_code": runner_exit_code,
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "attempts_sha256": (
            hashlib.sha256(attempts_path.read_bytes()).hexdigest()
            if attempts_path.is_file() else None
        ),
        "result_sha256": (
            hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path else None
        ),
        "source_set_sha256": source_set_sha256,
        "execution": {
            "selected_model": summary.get("selected_model"),
            "selected_effort": summary.get("selected_effort"),
            "provider_usage": summary.get("provider_usage"),
            "budget": summary.get("budget"),
        },
    })
    seal_path.chmod(0o600)
    return seal_path


def verify_evidence_seal(
    evidence_dir: Path, expected_source_set_sha256: str | None = None
) -> dict:
    seal_path = evidence_dir / "evidence-seal.json"
    summary_path = evidence_dir / "summary.json"
    attempts_path = evidence_dir / "attempts.jsonl"
    try:
        if evidence_dir.is_symlink() or evidence_dir.stat().st_mode & 0o077:
            raise EvidenceError
        for path in evidence_dir.rglob("*"):
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise EvidenceError
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        expected_source_set_sha256 = _source_set_sha256(expected_source_set_sha256)
        sealed_source_set_sha256 = _source_set_sha256(seal.get("source_set_sha256"))
        if (
            expected_source_set_sha256 is not None
            and sealed_source_set_sha256 != expected_source_set_sha256
        ):
            raise EvidenceError
        result_path = _result_path(
            evidence_dir, summary, required=sealed_source_set_sha256 is not None
        )
        expected_result = (
            hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path else None
        )
        expected_execution = {
            "selected_model": summary.get("selected_model"),
            "selected_effort": summary.get("selected_effort"),
            "provider_usage": summary.get("provider_usage"),
            "budget": summary.get("budget"),
        }
        expected_attempts = (
            hashlib.sha256(attempts_path.read_bytes()).hexdigest()
            if attempts_path.is_file() else None
        )
        if (
            seal.get("status") != "SEALED"
            or seal.get("summary_sha256") != hashlib.sha256(summary_path.read_bytes()).hexdigest()
            or seal.get("attempts_sha256") != expected_attempts
            or seal.get("result_sha256") != expected_result
            or seal.get("execution") != expected_execution
        ):
            raise EvidenceError
        return seal
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise EvidenceError


def verified_codex_record(receipt_path: Path) -> dict:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        matches = [item for item in receipt["capabilities"]
                   if item.get("name") == "codex-cli" and item.get("kind") == "codex_cli"]
        if receipt.get("status") != "READY" or len(matches) != 1:
            raise PinError
        expected = matches[0]
        observed = inventory.inspect({"name": "codex-cli", "kind": "codex_cli",
                                      "path": expected["canonical_path"]})
        if observed != expected:
            raise PinError
        return observed
    except (KeyError, OSError, TypeError, ValueError, inventory.InventoryError):
        raise PinError


def verify_codex_pin(receipt_path: Path) -> Path:
    try:
        record = verified_codex_record(receipt_path)
    except PinError:
        _refresh_codex_pin(receipt_path)
        record = verified_codex_record(receipt_path)
    return Path(record["canonical_path"])


def _refresh_codex_pin(receipt_path: Path) -> None:
    """Refresh one stale versioned pin through its stable, private request."""
    request_path = receipt_path.with_name("codex-request.json")
    parent = receipt_path.parent
    try:
        if (
            receipt_path.name != "codex-capability.json"
            or receipt_path.is_symlink()
            or request_path.is_symlink()
            or parent.is_symlink()
            or not parent.is_dir()
            or not request_path.is_file()
            or parent.stat().st_mode & 0o077
            or request_path.stat().st_mode & 0o077
        ):
            raise PinError
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        capabilities = previous.get("capabilities")
        if not isinstance(capabilities, list):
            raise PinError
        matches = [
            item for item in capabilities
            if isinstance(item, dict)
            and item.get("name") == "codex-cli"
            and item.get("kind") == "codex_cli"
        ]
        if previous.get("status") != "READY" or len(matches) != 1:
            raise PinError
        canonical_path = matches[0].get("canonical_path")
        if not isinstance(canonical_path, str) or not Path(canonical_path).is_absolute():
            raise PinError
        try:
            Path(canonical_path).lstat()
        except FileNotFoundError:
            pass
        except OSError:
            raise PinError
        else:
            raise PinError
        request_bytes = request_path.read_bytes()
        if previous.get("request_sha256") != hashlib.sha256(request_bytes).hexdigest():
            raise PinError
        inventory.refresh_receipt(request_path, receipt_path)
        receipt_path.chmod(0o600)
    except (OSError, TypeError, ValueError, inventory.InventoryError):
        raise PinError


def write_model_call_pin(receipt_path: Path, evidence_dir: Path) -> Path:
    record = verified_codex_record(receipt_path)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.chmod(0o700)
    target = evidence_dir / "codex-binary-pin.json"
    inventory.write_receipt(target, {
        "schema_version": 1,
        "status": "VERIFIED",
        **record,
        "source_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    })
    target.chmod(0o600)
    return target


def main() -> int:
    os.umask(0o077)
    parent_environment = dict(os.environ)
    receipt_value = parent_environment.get("AFFILIATE_CODEX_CAPABILITY_RECEIPT", "")
    if not receipt_value:
        raise PinError
    receipt_path = Path(receipt_value)
    executable = verify_codex_pin(receipt_path)
    try:
        evidence_dir = Path(sys.argv[sys.argv.index("--evidence-dir") + 1])
    except (ValueError, IndexError):
        raise PinError
    secure_evidence_tree(evidence_dir)
    (evidence_dir / "evidence-seal.json").unlink(missing_ok=True)
    write_model_call_pin(receipt_path, evidence_dir)
    child_environment = allowlisted_environment(parent_environment, executable)
    os.environ.clear()
    os.environ.update(child_environment)
    try:
        task_index = sys.argv.index("--task-class") + 1
        sys.argv[task_index] = {
            "marketing-agent": "affiliate-marketing-agent",
            "escalation-agent": "affiliate-escalation-agent",
        }.get(sys.argv[task_index], sys.argv[task_index])
    except (ValueError, IndexError):
        raise PinError
    sys.path.insert(0, str(VENDOR))
    import agent_runner
    runner_exit_code = agent_runner.run()
    secure_evidence_tree(evidence_dir)
    if (evidence_dir / "summary.json").is_file():
        seal_evidence(
            evidence_dir,
            runner_exit_code,
            parent_environment.get("AFFILIATE_SOURCE_SET_SHA256") or None,
        )
    return runner_exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PinError, EvidenceError):
        print("affiliate agent runner: execution boundary rejected", file=sys.stderr)
        raise SystemExit(1)
