from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "note-publish" / "set-eyecatch-draft.py"


def test_upload_uses_current_svg_image_add_control(tmp_path: Path) -> None:
    """The current Note editor exposes image-add as an aria-labelled SVG."""
    home = tmp_path / "home"
    work = home / ".local/state/life-manager/writer/note-work"
    work.mkdir(parents=True)
    (work / "thumb.png").write_bytes(b"immutable-cover")
    (work / "note-cookies.json").write_text(json.dumps({"session": "test"}))
    fake = tmp_path / "cloakbrowser.py"
    fake.write_text(
        """
import os

EXISTING = "https://assets.st-note.com/production/uploads/images/new.png"

class FileValue:
    def set_files(self, value):
        with open(os.environ["CALLS"], "a") as stream:
            stream.write("file=" + value + "\\n")
        os.environ["UPLOADED"] = "1"

class FileChooser:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    @property
    def value(self):
        return FileValue()

class Page:
    def set_viewport_size(self, value):
        pass
    def goto(self, *args, **kwargs):
        pass
    def evaluate(self, source):
        if "document.body.innerText" in source:
            return "公開に進む"
        if "svg[aria-label=\\\"画像を追加\\\"]" in source:
            with open(os.environ["CALLS"], "a") as stream:
                stream.write("svg\\n")
            return True
        if "img[alt=\\\"eyecatch\\\"]" in source:
            return EXISTING if os.environ.get("UPLOADED") == "1" else ""
        return None
    def click(self, selector):
        with open(os.environ["CALLS"], "a") as stream:
            stream.write(selector + "\\n")
        if selector == 'button[aria-label="画像を追加"]':
            raise RuntimeError("legacy image-add button must not be used")
    def expect_file_chooser(self, **kwargs):
        return FileChooser()
    def screenshot(self, path):
        with open(path, "wb") as stream:
            stream.write(b"png")

class Context:
    def add_cookies(self, value):
        pass
    def new_page(self):
        return Page()
    def close(self):
        pass

def launch_context(**kwargs):
    return Context()
""".lstrip()
    )
    calls = tmp_path / "calls"
    env = {
        **os.environ,
        "HOME": str(home),
        "NOTE_KEY": "n-new",
        "CALLS": str(calls),
        "PYTHONPATH": str(tmp_path),
        "WRITER_STATE_DIR": str(home / ".local/state/life-manager/writer"),
    }

    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (
        "EYECATCH_IN_EDITOR: "
        "https://assets.st-note.com/production/uploads/images/new.png"
        in completed.stdout
    )
    calls_text = calls.read_text()
    assert "svg" in calls_text
    assert 'button[aria-label="画像を追加"]' not in calls_text
