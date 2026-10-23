from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/_shared/marketplace-core/scripts/reconcile_pre_effect_hint.py"
WRITER_SOURCES = (
    "skills/earn/lancers/scripts/application-owner",
    "skills/earn/lancers/scripts/application_loop.py",
    "skills/earn/lancers/scripts/application_tick.py",
    "skills/_shared/marketplace-core/scripts/application_transaction.py",
    "skills/earn/lancers/scripts/negotiate-owner",
    "skills/_shared/marketplace-core/scripts/reply_kernel.py",
    "skills/earn/lancers/scripts/reply_adapter.py",
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.delenv("LIFE_MANAGER_SOURCE_REPO", raising=False)
    monkeypatch.delenv("LIFE_MANAGER_RELEASE_SHA", raising=False)


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Fixture",
         "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
         "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return result.stdout.strip()


def _provenance_fixture(tmp_path: Path, monkeypatch, owner: str) -> tuple[str, str]:
    source = tmp_path / "source"
    for name in WRITER_SOURCES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    writer = source / "skills/earn/lancers/scripts/application_tick.py"
    safe_writer = writer.read_bytes()
    unsafe_writer = safe_writer.replace(
        b"                    hint_path.unlink(missing_ok=True)\n",
        b"                    pass  # historical writer did not clear before send\n",
        1,
    )
    assert unsafe_writer != safe_writer
    writer.write_bytes(unsafe_writer)
    _git(source, "init", "-q", "-b", "main")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "historical writer without pre-send clear")
    unsafe_sha = _git(source, "rev-parse", "HEAD")
    writer.write_bytes(safe_writer)
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "writer with pre-effect marker contract")
    safe_sha = _git(source, "rev-parse", "HEAD")
    _git(source, "update-ref", "refs/remotes/origin/main", safe_sha)
    monkeypatch.setenv("LIFE_MANAGER_SOURCE_REPO", str(source))
    _event(tmp_path, owner, safe_sha)
    return safe_sha, unsafe_sha


def _event(state_root: Path, owner: str, release_sha: str) -> None:
    (state_root / "events.jsonl").write_text(
        json.dumps({"loop_id": owner, "owner_id": owner, "run_id": "run-1",
                    "occurrence_id": f"{owner}:run-1", "release_sha": release_sha}) + "\n",
        encoding="utf-8",
    )


def _marker(state_root: Path, owner: str) -> Path:
    marker = state_root / "loop-tmp" / owner / "run-1" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
    marker.chmod(0o600)
    return marker


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_pre_effect_hint_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_marker_is_bound_to_owner_and_occurrence(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    occurrence = f"{owner}:run-1"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    marker = _marker(tmp_path, owner)

    proof = module.find_pre_effect_proof(tmp_path, owner, occurrence)
    assert proof == {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-pre-effect://{owner}/run-1/entrypoint-result.json",
    }
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-2") is None


def test_marker_with_effect_or_extra_shape_is_not_a_no_effect_proof(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    occurrence = f"{owner}:run-1"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    marker = _marker(tmp_path, owner)
    marker.write_text(
        json.dumps({"status": "pre_effect_failure", "effect": 1}), encoding="utf-8"
    )
    marker.chmod(0o600)
    assert module.find_pre_effect_proof(tmp_path, owner, occurrence) is None


def test_reconcile_uses_resolver_only_after_exact_marker(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    owner = "lancers-revenue-negotiate"
    occurrence = f"{owner}:run-1"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    calls = []

    def resolver(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
        calls.append((owner_id, occurrence_id, expected_state, pre_effect_readback()))
        return True

    result = module.reconcile(
        state_root=tmp_path,
        owner=owner,
        occurrence=occurrence,
        resolve=True,
        resolver=resolver,
    )
    assert result["resolved"] is True
    assert calls == [(owner, occurrence, "claimed", module.find_pre_effect_proof(tmp_path, owner, occurrence))]


def test_marker_from_historical_writer_without_pre_send_clear_is_not_a_proof(
    tmp_path: Path, monkeypatch,
) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    safe_sha, unsafe_sha = _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    _event(tmp_path, owner, unsafe_sha)
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", safe_sha)

    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-1") is None


def test_marker_from_historical_writer_without_pre_send_clear_never_resolves(
    tmp_path: Path, monkeypatch,
) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    occurrence = f"{owner}:run-1"
    safe_sha, unsafe_sha = _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    _event(tmp_path, owner, unsafe_sha)
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", safe_sha)
    calls = []

    def resolver(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    try:
        module.reconcile(state_root=tmp_path, owner=owner, occurrence=occurrence,
                         resolve=True, resolver=resolver)
    except RuntimeError as error:
        assert str(error) == "exact_pre_effect_marker_unavailable"

    assert calls == []
