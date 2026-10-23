"""Coconala prepare/preflight interpreter and Homebrew boundaries."""
import importlib.util
import json
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("macos_runtime_fixtures", REPO / "scripts/test_macos_runtime.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def _sandbox(tmp_path):
    box = fixtures.RuntimeSandbox(tmp_path)
    (box.bin / "chmod").symlink_to("/bin/chmod")
    box.copy_script("scripts/macos-runtime.sh")
    box.installer = box.copy_script("skills/earn/gig/install.sh")
    chromium = box.home / ".cloakbrowser/chromium-test/Chromium.app/Contents/MacOS/Chromium"
    box.executable(chromium, "#!/bin/bash\nexit 0\n")
    return box


def _run(box, command):
    return subprocess.run(["/bin/bash", str(box.installer), command], env=box.env,
                          capture_output=True, text=True, timeout=10)


def test_prepare_installs_homebrew_for_gog_even_when_python_exists(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3")
    box.env["SANDBOX_IMPORTS_MISSING"] = "1"
    result = _run(box, "prepare")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ready"
    assert "brew install gogcli" in box.log()
    assert "Homebrew/install/HEAD/install.sh" in box.log()
    assert "pip-diagnostics" in result.stderr


def test_prepare_uses_installed_python_for_venv_and_preflight(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3", suitable=False)
    expected = box.python(box.python_prefix / "bin/python3.14")
    box.brew()
    box.executable(box.bin / "gog", "#!/bin/bash\nexit 0\n")
    result = _run(box, "prepare")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python"] is True
    assert Path(str(box.calls) + ".venv").read_text().splitlines() == [str(expected)]


def test_preflight_prefers_explicit_venv_python_without_installing(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3", suitable=False)
    python = box.python(box.home / "custom-venv/bin/python")
    box.env["PYTHON"] = str(python)
    result = _run(box, "preflight")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ready"
    assert "brew " not in box.log()
    assert "curl " not in box.log()
    assert " -m venv " not in box.log()


def test_preflight_does_not_hide_an_incompatible_explicit_python(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3")
    python = box.python(box.home / "custom-venv/bin/python", suitable=False)
    box.env["PYTHON"] = str(python)
    result = _run(box, "preflight")
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["python"] is False
    assert "brew " not in box.log()
    assert "curl " not in box.log()


def test_prepare_rebuilds_an_incompatible_existing_venv(tmp_path):
    box = _sandbox(tmp_path)
    expected = box.python(box.bin / "python3")
    box.python(box.home / ".local/share/anicca/gig/venv/bin/python", suitable=False)
    box.executable(box.bin / "gog", "#!/bin/bash\nexit 0\n")
    result = _run(box, "prepare")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python"] is True
    assert Path(str(box.calls) + ".venv").read_text().splitlines() == [str(expected)]
