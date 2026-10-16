"""Every Writer shell entrypoint must parse.

2026-10-15 01:37 an apostrophe ("row's") inside the single-quoted PROMPT in
article-daily.sh closed the quote; bash refused the whole script and the Writer
lane exited 2 on every wake for ~36 hours with zero articles.
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(p for p in ROOT.rglob("*.sh") if "vendor" not in p.parts)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_shell_script_parses(script):
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
