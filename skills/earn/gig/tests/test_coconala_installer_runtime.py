"""Coconala prepare/preflight interpreter and Homebrew boundaries."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("macos_runtime_fixtures", REPO / "scripts/test_macos_runtime.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def _sandbox(tmp_path):
    box = fixtures.RuntimeSandbox(tmp_path)
    (box.bin / "chmod").symlink_to("/bin/chmod")
    box.copy_script("scripts/macos-runtime.sh")
    box.installer = box.copy_script("skills/earn/gig/install.sh")
    box.executable(box.bin / "node", "#!/bin/bash\nexit 0\n")
    box.executable(box.bin / "npm", "#!/bin/bash\nexit 0\n")
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


def test_preflight_requires_the_managed_node_and_npm_runtime(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3")
    (box.bin / "npm").unlink()

    result = _run(box, "preflight")

    assert result.returncode == 2
    assert json.loads(result.stdout)["node_runtime"] is False
    assert "brew " not in box.log()


def test_prepare_installs_node_only_when_the_runtime_is_missing(tmp_path):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3")
    (box.bin / "node").unlink()
    (box.bin / "npm").unlink()
    box.executable(box.bin / "gog", "#!/bin/bash\nexit 0\n")
    brew = box.brew()
    brew.write_text(brew.read_text().replace(
        "install) echo 'brew install diagnostics';",
        "install) if [ \"$2\" = node ]; then\n"
        "printf '#!/bin/bash\\nexit 0\\n' > \"$SANDBOX_BIN/node\"\n"
        "printf '#!/bin/bash\\nexit 0\\n' > \"$SANDBOX_BIN/npm\"\n"
        "chmod +x \"$SANDBOX_BIN/node\" \"$SANDBOX_BIN/npm\"\nfi\n"
        "echo 'brew install diagnostics';",
    ))

    result = _run(box, "prepare")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["node_runtime"] is True
    assert "brew install node" in box.log()


@pytest.mark.parametrize("architecture", ["arm64", "x86_64"])
def test_preflight_requires_a_browser_build_for_the_current_mac_architecture(tmp_path, architecture):
    box = _sandbox(tmp_path)
    box.python(box.bin / "python3")
    box.executable(box.bin / "uname", f'#!/bin/bash\n[ "$1" = -s ] && echo Darwin || echo {architecture}\n')

    result = _run(box, "preflight")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["architecture_supported"] is True
    assert json.loads(result.stdout)["browser_platform"] is True
    assert "SUPPORTED_PLATFORMS" in box.log()


def test_preflight_refuses_intel_when_the_installed_browser_package_has_no_build(tmp_path):
    box = _sandbox(tmp_path)
    python = box.python(box.bin / "python3")
    python.write_text(python.read_text().replace(
        'if [ "${1:-}" = -c ]; then',
        'if [ "${1:-}" = -c ]; then\n  case "$2" in *SUPPORTED_PLATFORMS*) exit 1 ;; esac',
    ))
    box.executable(box.bin / "uname", '#!/bin/bash\n[ "$1" = -s ] && echo Darwin || echo x86_64\n')

    result = _run(box, "preflight")

    assert result.returncode == 2
    assert json.loads(result.stdout)["browser_platform"] is False
