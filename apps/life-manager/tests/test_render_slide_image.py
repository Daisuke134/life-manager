from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image


SCRIPT = Path(__file__).parents[1] / "scripts" / "render-slide-image.py"


def test_renderer_runs_when_numpy_is_unavailable(tmp_path: Path) -> None:
    background = tmp_path / "background.png"
    output = tmp_path / "slide.jpg"
    Image.new("RGB", (120, 160), (80, 120, 180)).save(background)

    blocked_imports = tmp_path / "blocked-imports"
    blocked_imports.mkdir()
    (blocked_imports / "numpy.py").write_text(
        "raise ImportError('numpy is intentionally unavailable')\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(blocked_imports)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(background), str(output), "120", "160", "短い見出し"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
