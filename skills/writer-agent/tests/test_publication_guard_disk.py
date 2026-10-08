from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "publication-guard.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("publication_guard_disk", SCRIPT)
GUARD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GUARD)


def test_preflight_does_not_block_on_low_disk_or_legacy_floor_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ARTICLE_AUTOPUBLISH", "1")
    monkeypatch.setenv("ARTICLE_PUBLICATION_STATE", "/tmp/writer/state.json")
    monkeypatch.setenv("ARTICLE_DISK_MIN_FREE_BYTES", "not-a-number")
    monkeypatch.setenv("GIG_DISK_HEADROOM_KIB", "not-a-number")
    monkeypatch.setattr(GUARD, "manual_or_store", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT), "preflight", "--pair", "note/ja",
            "--target-kind", "note-key", "--target", "example",
        ],
    )

    assert GUARD.main() == 0
    assert json.loads(capsys.readouterr().out) == {"action": "manual-unmanaged"}


def test_managed_publication_still_requires_durable_state_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("ARTICLE_RUN_DIR", "ARTICLE_PUBLICATION_STATE", "ARTICLE_LEDGER"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(GUARD.InvariantError, match="ARTICLE_RUN_DIR"):
        GUARD.store_from_env()


def test_launchd_state_override_cannot_bypass_canonical_writer_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    control_dir = home / ".local/state/life-manager/state"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "disk-writers.stop").write_text("owner=operator\n", encoding="utf-8")
    monkeypatch.setattr(GUARD.pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_dir=str(home)))
    monkeypatch.setenv("ARTICLE_AUTOPUBLISH", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", "/tmp/empty-redirected-state")
    monkeypatch.setattr(
        GUARD,
        "manual_or_store",
        lambda: pytest.fail("a stop file must block before publication store access"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT), "preflight", "--pair", "note/ja",
            "--target-kind", "note-key", "--target", "example",
        ],
    )

    with pytest.raises(GUARD.InvariantError, match="disk_writers_stop"):
        GUARD.main()
