"""The legacy monolithic CP1 driver must fail closed."""
import subprocess
import sys
from pathlib import Path


DRIVER = Path(__file__).parents[1] / "scripts" / "drive_cp1.py"


def test_legacy_driver_exits_with_screenshot_guided_recovery_instructions():
    result = subprocess.run(
        [sys.executable, str(DRIVER), "unused-config.json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 64
    assert "drive_cp1.py is retired" in result.stderr
    assert "CP1_AGENTIC.md" in result.stderr
    assert "cp1_agent.py" in result.stderr
    assert "with-browser.sh capafy:kosuke" in result.stderr
