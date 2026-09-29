from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "capafy_distribute_ledger.py"


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_distribute_ledger", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_is_published_false_when_ledger_missing(tmp_path: Path) -> None:
    module = load_module()
    assert module.is_published(tmp_path / "ledger.json", "2026-09-29") is False


def test_record_then_is_published_true(tmp_path: Path) -> None:
    module = load_module()
    ledger = tmp_path / "ledger.json"
    module.record(ledger, "2026-09-29", {"status": "published", "cta_url": "https://capafy.ai/agent/1?ct=x"})
    assert module.is_published(ledger, "2026-09-29") is True
    assert module.is_published(ledger, "2026-09-30") is False


def test_record_preserves_other_dates(tmp_path: Path) -> None:
    module = load_module()
    ledger = tmp_path / "ledger.json"
    module.record(ledger, "2026-09-28", {"status": "published"})
    module.record(ledger, "2026-09-29", {"status": "published"})
    data = module.load(ledger)
    assert set(data.keys()) == {"2026-09-28", "2026-09-29"}


def test_non_published_status_does_not_count_as_published(tmp_path: Path) -> None:
    module = load_module()
    ledger = tmp_path / "ledger.json"
    module.record(ledger, "2026-09-29", {"status": "skipped"})
    assert module.is_published(ledger, "2026-09-29") is False


def test_cli_check_exits_10_when_already_published(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    module = load_module()
    module.record(ledger, "2026-09-29", {"status": "published"})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--ledger", str(ledger), "--date", "2026-09-29"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 10


def test_cli_check_exits_0_when_not_yet_published(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--ledger", str(ledger), "--date", "2026-09-29"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0


def test_cli_record_round_trips_through_check(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "record", "--ledger", str(ledger), "--date", "2026-09-29",
         "--json", '{"status": "published", "cta_url": "https://capafy.ai/agent/1?ct=x"}'],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--ledger", str(ledger), "--date", "2026-09-29"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 10
