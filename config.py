"""Self-contained config for Life Manager (Python sibling of config.js).
No dependency on any external host runtime or shared profile module — runs anywhere (local OR cloud)."""
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def _load_env():
    out = {}
    f = Path(os.environ.get("LIFE_ENV_FILE", _ROOT / ".env"))
    try:
        raw = f.read_text()
    except OSError:
        return out
    for line in raw.splitlines():
        m = re.match(r"^(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


ENV = _load_env()


def env(k, d=""):
    return os.environ.get(k) or ENV.get(k, d)


def data_dir():
    # Resolved at call time so tests can isolate via LIFE_DATA_DIR / HOME.
    base = os.environ.get("LIFE_DATA_DIR")
    if base:
        return Path(base)
    return Path(os.environ.get("HOME", str(Path.home()))) / ".life-manager"


DATA_DIR = data_dir()


def data_path(*p):
    f = data_dir().joinpath(*p)
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


def home_address():
    return env("LIFE_HOME_ADDRESS")


def google_account():
    return env("GOG_ACCOUNT") or env("LIFE_GOOGLE_ACCOUNT")
