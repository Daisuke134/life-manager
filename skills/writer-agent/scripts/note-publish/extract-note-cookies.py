#!/usr/bin/env python3
"""Copy note.com cookies from the Writer-owned storage_state into note-work/note-cookies.json.

The storage_state is the 0600 session measure-sales.py keeps from its own ephemeral headless
CloakBrowser context (NOTE_STORAGE_STATE there). No personal browser profile is read. Without a
note session this fails and leaves the existing note-cookies.json untouched."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from writer_runtime_paths import note_work_dir, writer_state_dir

STORAGE = writer_state_dir() / "note-measure-storage.json"
OUT = note_work_dir() / "note-cookies.json"

try:
    state = json.loads(STORAGE.read_text(encoding="utf-8"))
except (OSError, ValueError) as error:
    raise SystemExit(f"note storage_state unavailable at {STORAGE}: {type(error).__name__}")
cookies = {
    item["name"]: item["value"]
    for item in state.get("cookies", [])
    if ("." + str(item.get("domain", "")).lstrip(".")).endswith(".note.com") and item.get("value")
}
if "_note_session_v5" not in cookies:
    raise SystemExit(f"no note session in {STORAGE}; writer-sales-measure refreshes it")
OUT.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(dir=OUT.parent, prefix=".note-cookies-", suffix=".tmp")
try:
    with os.fdopen(fd, "w") as handle:
        json.dump(cookies, handle)
    os.replace(temporary, OUT)
except BaseException:
    os.unlink(temporary)
    raise
print(f"copied {len(cookies)} note.com cookies -> {OUT}")
print("keys:", ",".join(sorted(cookies))[:200])
