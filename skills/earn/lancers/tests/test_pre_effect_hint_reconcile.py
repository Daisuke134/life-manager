from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
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
    monkeypatch.delenv("LIFE_MANAGER_HOST_PROFILE", raising=False)


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


def _host_profile(source: Path) -> None:
    home = Path.home().resolve()
    path = home / ".config/life-manager/host.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": 1, "owner_home": str(home), "tenant_id": "local-fixture",
        "source_checkout": str(source),
        "runtime": {"python": sys.executable, "node": sys.executable},
        "browser_registry": str(home / "browsers.toml"),
        "agent_runner_config": str(home / "agent-runner.json"),
        "environment_file": str(home / "environment.env"),
    }), encoding="utf-8")
    path.chmod(0o600)


def _assert_retained(module, state_root: Path, owner: str) -> None:
    occurrence = f"{owner}:run-1"
    calls = []

    def resolver(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    with pytest.raises(RuntimeError, match="^exact_pre_effect_marker_unavailable$"):
        module.reconcile(state_root=state_root, owner=owner, occurrence=occurrence,
                         resolve=True, resolver=resolver)
    assert calls == []
    assert module.find_pre_effect_proof(state_root, owner, occurrence) is None


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


@pytest.mark.parametrize("case", [
    "source_binding_missing", "source_binding_invalid", "source_binding_symlink",
    "host_binding_invalid", "host_binding_malformed", "trusted_source_missing",
    "event_missing", "event_other_owner", "event_other_occurrence",
    "event_sha_missing", "event_sha_invalid", "event_sha_ambiguous",
    "historical_object_missing", "historical_source_missing", "main_ref_missing", "not_main_ancestor",
])
def test_unproven_provenance_never_resolves(tmp_path: Path, monkeypatch, case: str) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    safe_sha, unsafe_sha = _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    source = tmp_path / "source"
    event_path = tmp_path / "events.jsonl"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", safe_sha)
    if case == "source_binding_missing":
        monkeypatch.delenv("LIFE_MANAGER_SOURCE_REPO")
    elif case == "source_binding_invalid":
        _host_profile(source)
        monkeypatch.setenv("LIFE_MANAGER_SOURCE_REPO", str(tmp_path / "missing-source"))
    elif case == "source_binding_symlink":
        link = tmp_path / "source-link"
        link.symlink_to(source, target_is_directory=True)
        monkeypatch.setenv("LIFE_MANAGER_SOURCE_REPO", str(link))
    elif case == "host_binding_invalid":
        _host_profile(source)
        (Path.home() / ".config/life-manager/host.json").chmod(0o644)
        monkeypatch.delenv("LIFE_MANAGER_SOURCE_REPO")
    elif case == "host_binding_malformed":
        _host_profile(source)
        (Path.home() / ".config/life-manager/host.json").write_text("[]", encoding="utf-8")
        monkeypatch.delenv("LIFE_MANAGER_SOURCE_REPO")
    elif case == "trusted_source_missing":
        monkeypatch.setattr(module, "ROOT", tmp_path / "missing-trusted-source")
    elif case == "event_missing":
        event_path.unlink()
    elif case.startswith("event_"):
        if case == "event_other_owner":
            event["loop_id"] = "lancers-revenue-negotiate"
        elif case == "event_other_occurrence":
            event["occurrence_id"] = f"{owner}:run-2"
        elif case == "event_sha_missing":
            del event["release_sha"]
        elif case == "event_sha_invalid":
            event["release_sha"] = "not-a-release"
        elif case == "event_sha_ambiguous":
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**event, "release_sha": unsafe_sha}) + "\n")
        if case != "event_sha_ambiguous":
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    elif case == "historical_object_missing":
        _event(tmp_path, owner, "0" * 40)
    elif case == "historical_source_missing":
        _git(source, "rm", "-q", "skills/earn/lancers/scripts/application_tick.py")
        _git(source, "commit", "-qm", "source missing")
        sha = _git(source, "rev-parse", "HEAD")
        _git(source, "update-ref", "refs/remotes/origin/main", sha)
        _event(tmp_path, owner, sha)
    elif case == "main_ref_missing":
        _git(source, "update-ref", "-d", "refs/remotes/origin/main")
    elif case == "not_main_ancestor":
        _git(source, "commit", "--allow-empty", "-qm", "unmerged source")
        _event(tmp_path, owner, _git(source, "rev-parse", "HEAD"))

    _assert_retained(module, tmp_path, owner)


@pytest.mark.parametrize(("owner", "name"), [
    ("lancers-revenue-application", name) for name in WRITER_SOURCES[:4]
] + [("lancers-revenue-negotiate", name) for name in WRITER_SOURCES[4:]])
def test_changed_writer_contract_source_never_resolves(
    tmp_path: Path, monkeypatch, owner: str, name: str,
) -> None:
    module = _load()
    _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    source = tmp_path / "source"
    with (source / name).open("ab") as handle:
        handle.write(b"\n# different writer contract\n")
    _git(source, "add", name)
    _git(source, "commit", "-qm", "changed writer source")
    sha = _git(source, "rev-parse", "HEAD")
    _git(source, "update-ref", "refs/remotes/origin/main", sha)
    _event(tmp_path, owner, sha)

    _assert_retained(module, tmp_path, owner)


def test_host_binding_supplies_source_repo_when_environment_is_absent(
    tmp_path: Path, monkeypatch,
) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    _host_profile(tmp_path / "source")
    monkeypatch.delenv("LIFE_MANAGER_SOURCE_REPO")

    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-1") is not None


def test_matching_historical_writer_contract_does_not_require_current_release_sha(
    tmp_path: Path, monkeypatch,
) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    source = tmp_path / "source"
    _git(source, "commit", "--allow-empty", "-qm", "newer main release")
    current_sha = _git(source, "rev-parse", "HEAD")
    _git(source, "update-ref", "refs/remotes/origin/main", current_sha)
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", current_sha)

    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-1") is not None


def test_writer_contract_sources_are_scoped_to_owner(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    owner = "lancers-revenue-negotiate"
    _safe_sha, unsafe_application_sha = _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)
    _event(tmp_path, owner, unsafe_application_sha)

    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-1") is not None


def test_unregistered_owner_never_resolves(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    owner = "lancers-revenue-storefront"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    _marker(tmp_path, owner)

    _assert_retained(module, tmp_path, owner)


@pytest.mark.parametrize("case", ["extra_field", "wrong_mode", "symlink", "hardlink", "wrong_uid"])
def test_private_marker_contract_is_preserved(tmp_path: Path, monkeypatch, case: str) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    _provenance_fixture(tmp_path, monkeypatch, owner)
    marker = _marker(tmp_path, owner)
    if case == "extra_field":
        marker.write_text('{"status":"pre_effect_failure","effect":0,"verified":true}',
                          encoding="utf-8")
    elif case == "wrong_mode":
        marker.chmod(0o644)
    elif case == "symlink":
        target = marker.with_name("marker-target.json")
        marker.rename(target)
        marker.symlink_to(target)
    elif case == "hardlink":
        os.link(marker, marker.with_name("marker-alias.json"))
    elif case == "wrong_uid":
        uid = os.getuid()
        monkeypatch.setattr(module.os, "getuid", lambda: uid + 1)

    _assert_retained(module, tmp_path, owner)
