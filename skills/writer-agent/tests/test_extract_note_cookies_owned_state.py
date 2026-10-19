import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/note-publish/extract-note-cookies.py"


def run(state: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(state / "home"), "WRITER_STATE_DIR": str(state)}
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)


def test_copies_only_note_cookies_from_writer_owned_storage_state(tmp_path):
    (tmp_path / "note-measure-storage.json").write_text(json.dumps({
        "cookies": [
            {"name": "_note_session_v5", "value": "s5", "domain": ".note.com", "path": "/"},
            {"name": "XSRF-TOKEN", "value": "x", "domain": "note.com", "path": "/"},
            {"name": "sid", "value": "other", "domain": ".substack.com", "path": "/"},
        ],
        "origins": [],
    }))
    proc = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "note-work" / "note-cookies.json"
    assert json.loads(out.read_text()) == {"_note_session_v5": "s5", "XSRF-TOKEN": "x"}
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert "s5" not in proc.stdout + proc.stderr


def test_missing_session_fails_without_overwriting_existing_cookies(tmp_path):
    work = tmp_path / "note-work"
    work.mkdir()
    (work / "note-cookies.json").write_text('{"_note_session_v5": "kept"}')
    assert run(tmp_path).returncode != 0
    (tmp_path / "note-measure-storage.json").write_text(json.dumps({"cookies": [
        {"name": "sid", "value": "other", "domain": ".substack.com", "path": "/"}]}))
    assert run(tmp_path).returncode != 0
    assert json.loads((work / "note-cookies.json").read_text()) == {"_note_session_v5": "kept"}
