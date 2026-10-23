"""Exercise installer runtime selection without touching the host toolchain."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[1]


class RuntimeSandbox:
    def __init__(self, root: Path):
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        self.home = root / "home"
        self.home.mkdir()
        self.repo = root / "repo"
        self.calls = root / "calls"
        self.apple = root / "apple"
        self.intel = root / "intel"
        self.python_prefix = root / "python-formula"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        SANDBOX_CALLS=str(self.calls), SANDBOX_BIN=str(self.bin),
                        SANDBOX_PYTHON_PREFIX=str(self.python_prefix))
        for name in ("PYTHON", "LIFE_MANAGER_PYTHON", "LM_PYTHON", "LM_BREW"):
            self.env.pop(name, None)
        for name in ("bash", "dirname", "basename", "mkdir", "mktemp", "rm", "cp"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.executable(self.bin / "uname", '#!/bin/bash\n[ "$1" = -s ] && echo Darwin || echo arm64\n')
        self.executable(self.bin / "codex", "#!/bin/bash\nexit 0\n")
        self.brew_template = self.executable(root / "brew-template", """#!/bin/bash
printf 'brew %s\n' "$*" >> "$SANDBOX_CALLS"
case "$1" in
  --version) echo 'Homebrew fixture' ;;
  --prefix) printf '%s\n' "$SANDBOX_PYTHON_PREFIX" ;;
  shellenv) printf 'export PATH="%s:%s"\n' "$(dirname "$0")" "$PATH" ;;
  install) echo 'brew install diagnostics'; [ "${SANDBOX_BREW_FAIL:-0}" = 0 ] ;;
  *) exit 91 ;;
esac
""")
        self.env["SANDBOX_BREW_TEMPLATE"] = str(self.brew_template)
        self.env["SANDBOX_BREW_TARGET"] = str(self.apple / "bin/brew")
        self.executable(self.bin / "curl", """#!/bin/bash
printf 'curl %s\n' "$*" >> "$SANDBOX_CALLS"
destination=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) destination="$2"; shift ;;
    https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh) ;;
    -fsSL) ;;
    *) exit 92 ;;
  esac
  shift
done
installer='#!/bin/bash
/bin/mkdir -p "$(dirname "$SANDBOX_BREW_TARGET")"
/bin/cp "$SANDBOX_BREW_TEMPLATE" "$SANDBOX_BREW_TARGET"'
if [ -n "$destination" ]; then
  printf '%s\n' "$installer" > "$destination"
else
  printf '%s\n' "$installer"
fi
""")

    @staticmethod
    def executable(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)
        return path

    def python(self, path: Path, *, suitable: bool = True) -> Path:
        version_exit = 0 if suitable else 1
        return self.executable(path, f"""#!/bin/bash
printf 'python %s %s\n' "$0" "$*" >> "$SANDBOX_CALLS"
if [ "${{1:-}}" = -c ]; then
  case "$2" in
    *sys.version_info*) exit {version_exit} ;;
    *'import websockets'*) exit "${{SANDBOX_IMPORTS_MISSING:-0}}" ;;
  esac
fi
if [ "${{1:-}}" = -m ] && [ "${{2:-}}" = venv ]; then
  target="${{@: -1}}"
  mkdir -p "$target/bin"
  cp "$0" "$target/bin/python"
  printf '%s\n' "$0" >> "$SANDBOX_CALLS.venv"
  printf '#!/bin/bash\\necho pip-diagnostics\\n' > "$target/bin/pip"
  chmod +x "$target/bin/pip"
fi
exit 0
""")

    def brew(self, *, intel: bool = False, on_path: bool = True) -> Path:
        target = (self.intel if intel else self.apple) / "bin/brew"
        self.executable(target, self.brew_template.read_text())
        if on_path:
            (self.bin / "brew").symlink_to(target)
        return target

    def copy_script(self, relative: str) -> Path:
        source = REPO / relative
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            target.write_text(source.read_text().replace("/opt/homebrew", str(self.apple))
                              .replace("/usr/local", str(self.intel)))
        return target

    def run_helper(self, command: str) -> subprocess.CompletedProcess[str]:
        helper = self.copy_script("scripts/macos-runtime.sh")
        return subprocess.run(["/bin/bash", "-c", 'set -eu; source "$1"; ' + command,
                               "runtime-test", str(helper)], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def log(self) -> str:
        return self.calls.read_text() if self.calls.exists() else ""


def test_source_does_not_probe_or_change_python(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.env["PYTHON"] = "/custom/python"
    result = box.run_helper('printf "%s" "$PYTHON"')
    assert result.returncode == 0, result.stderr
    assert result.stdout == "/custom/python"
    assert box.log() == ""


@pytest.mark.parametrize("gog_present", [False, True])
def test_full_host_prepare_installs_only_missing_gmail_tool(tmp_path, gog_present):
    box = RuntimeSandbox(tmp_path)
    script = box.copy_script("scripts/install-local.sh")
    box.copy_script("scripts/macos-runtime.sh")
    python = box.python(box.home / ".local/share/life-manager/venv/bin/python")
    box.env["LIFE_MANAGER_PYTHON"] = str(python)
    for name in ("node", "npm", "jq", "ffmpeg", "fc-list"):
        box.executable(box.bin / name, "#!/bin/bash\nexit 0\n")
    box.brew()
    if gog_present:
        box.executable(box.bin / "gog", "#!/bin/bash\nexit 0\n")
    result = subprocess.run(["/bin/bash", str(script), "prepare"], env=box.env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert ("brew install gogcli" in box.log()) is not gog_present
    assert "brew install jq" not in box.log()


@pytest.mark.parametrize("auth", ["existing", "login", "failed", "unconfirmed", "prepare"])
def test_full_host_install_authenticates_before_registering_jobs(tmp_path, auth):
    box = RuntimeSandbox(tmp_path)
    script = box.copy_script("scripts/install-local.sh")
    box.copy_script("scripts/macos-runtime.sh")
    python = box.python(box.home / ".local/share/life-manager/venv/bin/python")
    box.env["LIFE_MANAGER_PYTHON"] = str(python)
    box.env["SANDBOX_AUTH"] = auth
    box.env["SANDBOX_AUTH_FILE"] = str(tmp_path / "authenticated")
    if auth == "existing":
        (tmp_path / "authenticated").touch()
    for name in ("node", "npm", "jq", "ffmpeg", "fc-list", "gog"):
        box.executable(box.bin / name, "#!/bin/bash\nexit 0\n")
    box.executable(box.bin / "codex", '''#!/bin/bash
printf 'codex %s\n' "$*" >> "$SANDBOX_CALLS"
if [ "$*" = 'login status' ]; then
  [ -f "$SANDBOX_AUTH_FILE" ]; exit $?
fi
[ "$*" = login ] || exit 94
[ "$SANDBOX_AUTH" != failed ] || exit 1
if [ "$SANDBOX_AUTH" = login ]; then
  printf authenticated > "$SANDBOX_AUTH_FILE"
fi
''')
    command = "prepare" if auth == "prepare" else "install"
    result = subprocess.run(["/bin/bash", str(script), command], env=box.env,
                            capture_output=True, text=True, timeout=10)
    dispatched = f"-m runtime.loop.local_install {command}" in box.log()
    if auth in {"failed", "unconfirmed"}:
        assert result.returncode != 0
        assert not dispatched
    else:
        assert result.returncode == 0, result.stderr
        assert dispatched
    if auth == "prepare":
        assert "codex " not in box.log()
    elif auth == "existing":
        assert "codex login status" in box.log()
        assert "codex login\n" not in box.log()
    else:
        assert "codex login\n" in box.log()


def test_compatible_node_and_npm_do_not_install_dependencies(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.executable(box.bin / "node", "#!/bin/bash\nexit 0\n")
    box.executable(box.bin / "npm", "#!/bin/bash\nexit 0\n")
    result = box.run_helper('lm_ensure_node')
    assert result.returncode == 0, result.stderr
    assert "brew " not in box.log()


@pytest.mark.parametrize("version, npm_present, ready", [
    ("20.19.0", True, False),
    ("21.0.0", True, False),
    ("22.18.0", True, False),
    ("22.19.0", True, True),
    ("22.20.0", True, True),
    ("23.0.0", True, False),
    ("24.0.0", True, True),
    ("25.0.0", True, True),
    ("24.0.0", False, False),
])
def test_node_readiness_matches_production_locks(tmp_path, version, npm_present, ready):
    box = RuntimeSandbox(tmp_path)
    node = shutil.which("node")
    assert node is not None, "Node is required to exercise the installer predicate"
    box.env["SANDBOX_NODE_VERSION"] = version
    box.executable(box.bin / "node", f'''#!{node}
Object.defineProperty(process.versions, "node", {{value: process.env.SANDBOX_NODE_VERSION}});
if (process.argv[2] !== "-e") process.exit(91);
eval(process.argv[3]);
''')
    if npm_present:
        box.executable(box.bin / "npm", "#!/bin/bash\nexit 0\n")
    result = box.run_helper('lm_node_ready')
    assert (result.returncode == 0) is ready, result.stderr
    assert box.log() == ""


def test_full_host_prepare_refuses_incomplete_browser_dependencies(tmp_path):
    box = RuntimeSandbox(tmp_path)
    script = box.copy_script("scripts/install-local.sh")
    box.copy_script("scripts/macos-runtime.sh")
    python = box.python(box.home / ".local/share/life-manager/venv/bin/python")
    box.env.update(LIFE_MANAGER_PYTHON=str(python), SANDBOX_IMPORTS_MISSING="1")
    for name in ("node", "npm", "jq", "ffmpeg", "fc-list", "gog"):
        box.executable(box.bin / name, "#!/bin/bash\nexit 0\n")
    result = subprocess.run(["/bin/bash", str(script), "prepare"], env=box.env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "-m runtime.loop.local_install" not in box.log()
    assert "codex " not in box.log()


def test_old_node_is_replaced_by_selected_homebrew_node(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.executable(box.bin / "node", "#!/bin/bash\nexit 1\n")
    box.executable(box.bin / "npm", "#!/bin/bash\nexit 0\n")
    brew = box.brew(on_path=False)
    new_node = box.executable(brew.parent / "node", "#!/bin/bash\nexit 0\n")
    box.executable(brew.parent / "npm", "#!/bin/bash\nexit 0\n")
    result = box.run_helper('lm_ensure_node; command -v node')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(new_node)
    assert "brew install node" in box.log()


@pytest.mark.parametrize("variable", ["LIFE_MANAGER_PYTHON", "PYTHON"])
def test_compatible_explicit_python_needs_no_homebrew(tmp_path, variable):
    box = RuntimeSandbox(tmp_path)
    python = box.python(tmp_path / "chosen-python")
    box.env[variable] = str(python)
    result = box.run_helper('lm_ensure_python; printf "%s" "$LM_PYTHON"')
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(python)
    assert "brew " not in box.log()
    assert "curl " not in box.log()


def test_installed_python_is_selected_from_formula_not_old_path(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.python(box.bin / "python3", suitable=False)
    python = box.python(box.python_prefix / "bin/python3.14")
    box.brew()
    result = box.run_helper('lm_ensure_python; printf "%s" "$LM_PYTHON"')
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(python)
    assert "brew install python@3.14" in box.log()
    assert "brew --prefix python@3.14" in box.log()
    assert "brew install diagnostics" in result.stderr


@pytest.mark.parametrize("intel", [False, True])
def test_new_homebrew_is_rediscovered_at_both_macos_prefixes(tmp_path, intel):
    box = RuntimeSandbox(tmp_path)
    expected = (box.intel if intel else box.apple) / "bin/brew"
    box.env["SANDBOX_BREW_TARGET"] = str(expected)
    result = box.run_helper('lm_ensure_homebrew; printf "%s" "$LM_BREW"')
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(expected)
    assert "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh" in box.log()


def test_failed_python_install_does_not_select_old_interpreter(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.python(box.bin / "python3", suitable=False)
    box.python(box.python_prefix / "bin/python3.14")
    box.brew()
    box.env["SANDBOX_BREW_FAIL"] = "1"
    result = box.run_helper('lm_ensure_python; printf "%s" "$LM_PYTHON"')
    assert result.returncode != 0
    assert result.stdout == ""
    assert "brew install python@3.14" in box.log()


def test_python_install_must_provide_a_compatible_interpreter(tmp_path):
    box = RuntimeSandbox(tmp_path)
    box.python(box.bin / "python3", suitable=False)
    box.python(box.python_prefix / "bin/python3.14", suitable=False)
    box.brew()
    result = box.run_helper('lm_ensure_python; printf "%s" "$LM_PYTHON"')
    assert result.returncode != 0
    assert result.stdout == ""
    assert "brew --prefix python@3.14" in box.log()
