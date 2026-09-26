from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/work_sync.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "lancers_work_sync_browser_attach_exit_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_browser_attach_busy_is_classified_as_a_safe_transient_failure():
    module = _module()
    error = module.application_tick.BrowserAttachBusy("browser_attach_lock_timeout")
    assert module._runtime_failure_code(error) == "browser_attach_busy"


def test_worker_exit_code_maps_browser_attach_busy_to_75_not_1():
    module = _module()
    assert module._worker_exit_code({"ok": False, "error": "browser_attach_busy"}) == 75
    # Every other failure keeps the existing exit-1 contract.
    assert module._worker_exit_code({"ok": False, "error": "account_unavailable"}) == 1
    assert module._worker_exit_code({"ok": True}) == 0


def test_watchdog_accepts_the_75_returncode_for_browser_attach_busy(monkeypatch, tmp_path):
    module = _module()
    payload = tmp_path / "result.json"
    payload.write_text('{"ok": false, "error": "browser_attach_busy"}', encoding="utf-8")
    script = tmp_path / "worker.py"
    script.write_text(
        "import sys\n"
        f"sys.stdout.write(open({str(payload)!r}).read())\n"
        "raise SystemExit(75)\n",
        encoding="utf-8",
    )
    result = module._watchdog([sys.executable, str(script)], timeout=5)
    assert result == {"ok": False, "error": "browser_attach_busy"}
