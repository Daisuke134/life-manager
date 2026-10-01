from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image


SCRIPT = Path(__file__).parents[1] / "scripts" / "render-slide-image.py"


def load_renderer_module():
    spec = importlib.util.spec_from_file_location("render_slide_image", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contrast_fixture(*pixels: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (len(pixels), 1))
    for x, pixel in enumerate(pixels):
        image.putpixel((x, 0), pixel)
    return image


def rec709(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_measure_contrast_preserves_rec709_float_luminance_for_green_fixture() -> None:
    renderer = load_renderer_module()
    pixels = ((100, 255, 100), (0, 0, 0))

    std, ok = renderer.measure_contrast(contrast_fixture(*pixels), (0, 0, 2, 1))

    expected_std = abs(rec709(pixels[0]) - rec709(pixels[1])) / 2
    assert math.isclose(std, expected_std, rel_tol=0.0, abs_tol=1e-12)
    assert ok is True


def test_measure_contrast_preserves_rec709_float_luminance_for_red_fixture() -> None:
    renderer = load_renderer_module()
    pixels = ((255, 180, 180), (0, 0, 0))

    std, ok = renderer.measure_contrast(contrast_fixture(*pixels), (0, 0, 2, 1))

    expected_std = abs(rec709(pixels[0]) - rec709(pixels[1])) / 2
    assert math.isclose(std, expected_std, rel_tol=0.0, abs_tol=1e-12)
    assert ok is False


def test_measure_contrast_empty_region_is_not_contrast() -> None:
    renderer = load_renderer_module()

    assert renderer.measure_contrast(Image.new("RGB", (2, 2)), (0, 0, 0, 0)) == (0.0, False)


def test_measure_contrast_uses_strict_90_and_200_boundaries() -> None:
    renderer = load_renderer_module()

    at_dark_boundary = contrast_fixture((90, 90, 90), (255, 255, 255))
    at_bright_boundary = contrast_fixture((200, 200, 200), (0, 0, 0))

    assert renderer.measure_contrast(at_dark_boundary, (0, 0, 2, 1))[1] is False
    assert renderer.measure_contrast(at_bright_boundary, (0, 0, 2, 1))[1] is False


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
