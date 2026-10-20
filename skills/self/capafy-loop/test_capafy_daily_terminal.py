from pathlib import Path

import json
import subprocess

import pytest

from capafy_daily_terminal import append_event, classify_result, streak_status


def test_streak_requires_started_and_healthy_terminal_for_each_day(tmp_path: Path) -> None:
    ledger = tmp_path / "terminals.jsonl"
    append_event(ledger, "a", "started", None, None, "2026-08-20T00:00:00Z")
    append_event(ledger, "a", "terminal", 0, "CAP_FULL", "2026-08-20T00:01:00Z")
    append_event(ledger, "b", "started", None, None, "2026-08-21T00:00:00Z")
    append_event(ledger, "b", "terminal", 0, "CAP_FULL", "2026-08-21T00:01:00Z")
    append_event(ledger, "c", "started", None, None, "2026-08-22T00:00:00Z")
    append_event(ledger, "c", "terminal", 0, "CAP_FULL", "2026-08-22T00:01:00Z")

    assert streak_status(ledger, "2026-08-22")["consecutive_healthy_days"] == 3


def test_failure_or_missing_terminal_breaks_streak(tmp_path: Path) -> None:
    ledger = tmp_path / "terminals.jsonl"
    append_event(ledger, "a", "started", None, None, "2026-08-21T00:00:00Z")
    append_event(ledger, "a", "terminal", 1, "SERVER_UNREADABLE", "2026-08-21T00:01:00Z")
    append_event(ledger, "b", "started", None, None, "2026-08-22T00:00:00Z")
    append_event(ledger, "b", "terminal", 0, "CAP_FULL", "2026-08-22T00:01:00Z")

    assert streak_status(ledger, "2026-08-22")["consecutive_healthy_days"] == 1

    append_event(ledger, "c", "started", None, None, "2026-08-22T02:00:00Z")
    assert streak_status(ledger, "2026-08-22")["consecutive_healthy_days"] == 0


@pytest.mark.parametrize(("status", "expected_rc"), (("success", 0), ("no_op", 0), ("failure", 1)))
def test_classify_result_maps_status_to_terminal_rc(tmp_path: Path, status: str, expected_rc: int) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = evidence / "attempt.result.json"
    result.write_text(json.dumps({"status": status, "evidence": ["official readback"]}), encoding="utf-8")
    summary = evidence / "summary.json"
    summary.write_text(json.dumps({"result_path": str(result)}), encoding="utf-8")

    rc, value = classify_result(summary)

    assert rc == expected_rc
    assert value["status"] == status


@pytest.mark.parametrize(
    "summary_builder",
    (
        lambda root: root / "missing-summary.json",
        lambda root: _write_summary(root, "not-json", None),
        lambda root: _write_summary(root, json.dumps({"result_path": str(root.parent / "outside.json")}), None),
        lambda root: _write_summary(root, json.dumps({"result_path": str(root / "result.json")}), {"status": "unknown", "evidence": ["x"]}),
        lambda root: _write_nested_summary(root),
    ),
)
def test_classify_result_invalid_or_escaped_is_rc2(tmp_path: Path, summary_builder) -> None:
    summary = summary_builder(tmp_path)
    rc, value = classify_result(summary)
    assert rc == 2
    assert value["status"] == "invalid"


def _write_summary(root: Path, summary_text: str, result: dict | None) -> Path:
    summary = root / "summary.json"
    summary.write_text(summary_text, encoding="utf-8")
    if result is not None:
        (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return summary


def _write_nested_summary(root: Path) -> Path:
    nested = root / "nested"
    nested.mkdir()
    (nested / "result.json").write_text(json.dumps({"status": "success", "evidence": ["x"]}), encoding="utf-8")
    return _write_summary(root, json.dumps({"result_path": str(nested / "result.json")}), None)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _offline_source_fixture(tmp_path: Path, case: str = "valid"):
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    repo.mkdir()
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "README.md").write_text("base")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "-u", "origin", "main")
    candidate = repo / "skills/capafy/catalog/new-candidate"
    for name in ("SKILL.md", "LISTING.md", "icon.svg", "icon.png",
                 "evidence/verified-demonstration.md"):
        if case == "missing_png" and name == "icon.png":
            continue
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture artifact")
    if case == "symlink_png":
        (candidate / "icon.png").unlink()
        (candidate / "icon.png").symlink_to("icon.svg")
    _git(repo, "add", "skills")
    _git(repo, "commit", "-m", "candidate")
    commit = _git(repo, "rev-parse", "HEAD")
    if case != "not_on_main":
        _git(repo, "push", "origin", "main")
    if case == "already_present":
        base = commit
    _git(repo, "checkout", "--detach", base)
    # A successful verifier must refresh the tracking ref, not trust stale refs.
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = {"status": "success", "evidence": ["merged-source fixture"],
              "source_commit": commit, "candidate_slug": "new-candidate"}
    if case == "path_escape":
        result["candidate_slug"] = "../escape"
    elif case == "bad_sha":
        result["source_commit"] = "--help"
    elif case in ("failure", "no_op"):
        result.update(status=case, source_commit=None, candidate_slug=None)
    summary = _write_summary(evidence, json.dumps({"result_path": str(evidence / "result.json")}), result)
    return repo, base, commit, summary


def test_offline_source_accepts_merged_candidate_with_stale_checkout(tmp_path):
    repo, base, commit, summary = _offline_source_fixture(tmp_path)
    assert not (repo / "skills/capafy/catalog/new-candidate").exists()
    assert classify_result(summary)[0] == 2  # Publisher results keep their existing contract.

    rc, value = classify_result(summary, source_repo=repo, source_base=base)

    assert rc == 0
    assert value["source_commit"] == commit
    assert value["candidate_slug"] == "new-candidate"
    assert value["source_status"] == "merged_main"
    assert value["runtime_adoption"] == "pending"
    assert _git(repo, "rev-parse", "HEAD") == base
    assert _git(repo, "status", "--porcelain") == ""
    assert not (repo / "skills/capafy/catalog/new-candidate").exists()


@pytest.mark.parametrize(("case", "expected_rc"), [
    ("not_on_main", 2), ("already_present", 2), ("missing_png", 2), ("symlink_png", 2),
    ("path_escape", 2), ("bad_sha", 2), ("failure", 1), ("no_op", 1),
])
def test_offline_source_rejects_unproven_or_non_new_completion(tmp_path, case, expected_rc):
    repo, base, commit, summary = _offline_source_fixture(tmp_path, case)

    rc, value = classify_result(summary, source_repo=repo, source_base=base)

    assert rc == expected_rc
    assert value.get("source_status") != "merged_main"
    assert _git(repo, "rev-parse", "HEAD") == base
    assert _git(repo, "status", "--porcelain") == ""
