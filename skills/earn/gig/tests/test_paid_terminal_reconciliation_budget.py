import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from skills.earn.gig.scripts import paid_direct as paid


def test_terminal_reconciliation_is_one_rotating_candidate_per_wake(
    tmp_path, monkeypatch
):
    projects = tmp_path / "projects"
    evidence = tmp_path / "evidence"
    for room in ("100", "200", "300"):
        root = projects / room
        root.mkdir(parents=True)
        (root / "state.json").write_text(json.dumps({
            "talkroom_id": room, "buyer": f"buyer-{room}",
        }))
    calls = []
    monkeypatch.setattr(paid, "_collector", lambda *_args: ["collector"])

    def fail(*_args, **_kwargs):
        calls.append(True)
        raise paid.Failure("terminal_reconciliation")

    monkeypatch.setattr(paid, "_run", fail)
    monkeypatch.setattr(paid.subprocess, "run", lambda *_args, **_kwargs: None)
    args = SimpleNamespace(
        projects_root=projects,
        evidence_dir=evidence,
        cdp_helper=tmp_path / "cdp_default_tab.py",
        cdp_lock_dir=tmp_path / "cdp-locks",
    )

    result = paid._reconcile_absent_talkrooms(args, [])

    assert len(calls) == 1
    assert len(result["results"]) == 1
    assert result["remaining_candidates"] == 2


def test_terminal_reconciliation_budget_stays_below_half_paid_cadence():
    worst_case = paid.PAID_TERMINAL_RECONCILES_PER_WAKE * (
        paid.TERMINAL_RECONCILIATION_TIMEOUT_SECONDS
        + paid.TERMINAL_RECONCILIATION_CLEANUP_TIMEOUT_SECONDS
    )
    assert worst_case < 150


def test_official_cancellation_closes_project_without_an_effect(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    evidence = tmp_path / "evidence"
    root = projects / "18184558"
    paid.project_ledger.init_project(projects, "18184558", "coconala", {
        "talkroom_id": "18184558", "next_action": "delivery_evidence",
    })
    snapshot = evidence / "terminal-reconciliation" / "18184558" / "snapshot.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{}")
    monkeypatch.setattr(paid, "_collector", lambda *_args: ["collector"])
    monkeypatch.setattr(paid, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(paid.subprocess, "run", lambda *_args, **_kwargs: None)
    original_load = paid._load
    monkeypatch.setattr(paid, "_load", lambda path: (
        {"talkroom": {"talkroom_id": "18184558", "transaction_state": "キャンセル",
                      "talkroom_state": "キャンセル"}}
        if path.name == "snapshot.json" else original_load(path)
    ))
    args = SimpleNamespace(projects_root=projects, evidence_dir=evidence,
                           cdp_helper=tmp_path / "cdp.py", cdp_lock_dir=tmp_path / "locks")

    result = paid._reconcile_absent_talkrooms(args, [])

    state = json.loads((root / "state.json").read_text())
    receipt = json.loads((root / "project-terminal.json").read_text())
    assert result["results"][0]["terminal_receipt_written"] is True
    assert state["next_action"] == "terminal_cancelled"
    assert state["work_state"] == "CANCELLED"
    assert receipt["transaction_state"] == receipt["talkroom_state"] == "キャンセル"
    assert receipt["state_sha256"] == hashlib.sha256((root / "state.json").read_bytes()).hexdigest()
    accepted, reason = paid.project_janitor._terminal_receipt(root, root / "state.json")
    assert accepted == receipt
    assert reason == ""

    events_before_replay = (root / "events.jsonl").read_bytes()
    replay = paid._reconcile_absent_talkrooms(args, [])
    assert replay["results"] == []
    assert replay["remaining_candidates"] == 0
    assert (root / "events.jsonl").read_bytes() == events_before_replay


def _closed_project(tmp_path, transaction_state="取引完了"):
    root = tmp_path / "projects" / "100"
    root.mkdir(parents=True)
    state = root / "state.json"
    state.write_text(json.dumps({"transaction_state": transaction_state}))
    (root / "project-terminal.json").write_text(json.dumps({
        "version": 1, "authority": "official_provider_readback", "terminal": True,
        "adapter": "coconala", "project_id": "100", "talkroom_id": "100",
        "transaction_state": transaction_state, "talkroom_state": transaction_state,
        "state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "provider_snapshot_sha256": "a" * 64, "observed_at": 1,
    }))
    return root, tmp_path / "janitor.jsonl"


@pytest.mark.parametrize("transaction_state", ["取引完了", "キャンセル"])
@pytest.mark.parametrize("prior_work_cleanup", [False, True])
def test_closed_project_reclaims_old_outputs_and_preserves_records(
    tmp_path, transaction_state, prior_work_cleanup,
):
    root, ledger = _closed_project(tmp_path, transaction_state)
    preserved = {}
    for dirname in ("work", "artifacts", "delivery", "deliverables"):
        target = root / dirname
        target.mkdir()
        (target / "old.zip").write_bytes(b"x" * 64)
        for name in (
            "state.json", "events.jsonl", "sales.csv", ".env", "tls.key",
            "credentials.zip", "key.zip", "token.zip", "password.zip", "passkey.zip",
            "provider-receipt.zip", "ledger.zip", "auth.zip",
            "cookies.zip", "vault.zip", "owner.lock", "recovery.zip",
            "source/buyer.zip", "evidence/screenshot.png", "context/brief.pdf",
            "memory/keep.zip", "state/history.jsonl",
        ):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep")
            preserved[path] = path.read_bytes()
    # A ledger from the previous work-only policy cannot hide newly reclaimable output.
    if prior_work_cleanup:
        ledger.write_text(json.dumps({
            "project_id": "100", "terminal_state_sha256":
            hashlib.sha256((root / "state.json").read_bytes()).hexdigest(),
        }) + "\n")

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["errors"] == 0
    assert result["bytes_freed"] == 256
    assert all(not (root / name / "old.zip").exists()
               for name in ("work", "artifacts", "delivery", "deliverables"))
    assert all(path.read_bytes() == content for path, content in preserved.items())
    artifact_ledger = ledger.with_name("artifact-janitor.jsonl")
    before_replay = artifact_ledger.read_bytes()
    replay = paid.project_janitor.scan(root.parent, ledger, dry_run=False)
    assert replay["bytes_freed"] == 0
    assert artifact_ledger.read_bytes() == before_replay


def test_closed_output_dry_run_leaves_files_and_ledgers_unchanged(tmp_path):
    root, ledger = _closed_project(tmp_path)
    package = root / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"x" * 64)

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=True)

    assert result["bytes_freed"] == 64
    assert result["would_clean"] == [{
        "project_id": "100", "deleted": ["delivery/old.zip"], "bytes_freed": 64,
    }]
    assert package.read_bytes() == b"x" * 64
    assert not ledger.exists()
    assert not ledger.with_name("artifact-janitor.jsonl").exists()


@pytest.mark.parametrize("receipt_change", ["missing", "unofficial", "stale", "active"])
def test_unproven_project_keeps_outputs(tmp_path, receipt_change):
    root, ledger = _closed_project(tmp_path)
    package = root / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"keep")
    receipt_path = root / "project-terminal.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt_change == "missing":
        receipt_path.unlink()
    elif receipt_change == "unofficial":
        receipt["authority"] = "local_workflow"
        receipt_path.write_text(json.dumps(receipt))
    elif receipt_change == "stale":
        (root / "state.json").write_text("{}")
    else:
        receipt["transaction_state"] = receipt["talkroom_state"] = "取引中"
        receipt_path.write_text(json.dumps(receipt))

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"


@pytest.mark.parametrize("relative_root", [False, True])
def test_closed_cleanup_preserves_owner_retained_latest_package(tmp_path, monkeypatch, relative_root):
    root, ledger = _closed_project(tmp_path)
    delivery = root / "delivery"
    delivery.mkdir()
    retained = delivery / "latest.zip"
    retained.write_bytes(b"latest")
    (delivery / "old.zip").write_bytes(b"x" * 64)
    context = root / "context"
    context.mkdir()
    (context / "owner-authorized-cleanup.json").write_text(json.dumps({
        "version": 1, "authority": "account_owner_instruction",
        "disposition": "retain_latest_package_remove_old_work_and_video",
        "remove_old_versions": True, "retained_path": str(retained),
        "retained_bytes": 6, "retained_sha256": hashlib.sha256(b"latest").hexdigest(),
    }))

    monkeypatch.chdir(tmp_path)
    scan_root = Path("projects") if relative_root else root.parent
    result = paid.project_janitor.scan(scan_root, ledger, dry_run=False)

    assert result["bytes_freed"] == 64
    assert retained.read_bytes() == b"latest"
    assert not (delivery / "old.zip").exists()


@pytest.mark.parametrize("boundary", ["project", "work", "delivery", "nested"])
def test_closed_cleanup_never_follows_symlinks(tmp_path, boundary):
    root, ledger = _closed_project(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / "old.zip").write_bytes(b"keep")
    if boundary == "project":
        real = tmp_path / "real-project"
        root.rename(real)
        root.symlink_to(real, target_is_directory=True)
        (real / "work").symlink_to(external, target_is_directory=True)
    else:
        link = root / ("delivery/link" if boundary == "nested" else boundary)
        link.parent.mkdir(exist_ok=True)
        link.symlink_to(external, target_is_directory=True)

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert (external / "old.zip").read_bytes() == b"keep"
    if boundary != "project":
        assert link.is_symlink()


@pytest.mark.parametrize("marker", [".git", ".lease", ".lm-protected"])
def test_closed_cleanup_keeps_worktree_or_leased_work(tmp_path, marker):
    root, ledger = _closed_project(tmp_path)
    work = root / "work"
    work.mkdir()
    (work / marker).write_text("owned")
    (work / "old.zip").write_bytes(b"keep")

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert (work / "old.zip").read_bytes() == b"keep"


def test_closed_cleanup_keeps_open_work_files(tmp_path):
    root, ledger = _closed_project(tmp_path)
    work = root / "work"
    work.mkdir()
    package = work / "old.zip"
    package.write_bytes(b"keep")

    with package.open("rb"):
        result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"


def test_cleanup_probe_failure_preserves_outputs(tmp_path, monkeypatch):
    root, ledger = _closed_project(tmp_path)
    work = root / "work"
    work.mkdir()
    (work / "old.zip").write_bytes(b"keep")

    def unavailable(*_args, **_kwargs):
        raise OSError("open-file probe unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["errors"] == 1
    assert result["bytes_freed"] == 0
    assert (work / "old.zip").read_bytes() == b"keep"


def test_failed_directory_removal_never_reports_success_bytes(tmp_path, monkeypatch):
    root, ledger = _closed_project(tmp_path)
    work = root / "work"
    work.mkdir()
    (work / "scratch.bin").write_bytes(b"x" * 64)

    def denied(_path, **kwargs):
        if not kwargs.get("ignore_errors", False):
            raise PermissionError("deletion denied")

    monkeypatch.setattr(shutil, "rmtree", denied)
    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["errors"] == 1
    assert result["cleaned"] == 0
    assert result["bytes_freed"] == 0
    assert not ledger.exists()


def test_projects_root_symlink_never_grants_cleanup_outside_it(tmp_path):
    root, ledger = _closed_project(tmp_path)
    package = root / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"keep")
    link = tmp_path / "linked-projects"
    link.symlink_to(root.parent, target_is_directory=True)

    result = paid.project_janitor.scan(link, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"


def test_closed_workspace_under_owner_git_repo_can_reclaim_output(tmp_path):
    root, ledger = _closed_project(tmp_path / "gig")
    (root.parent.parent / ".git").mkdir()
    (root.parent / ".git").mkdir()
    package = root / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"x" * 64)

    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["errors"] == 0
    assert result["bytes_freed"] == 64
    assert not package.exists()
    assert (root.parent.parent / ".git").is_dir()
    assert (root.parent / ".git").is_dir()


@pytest.mark.parametrize("root_kind", ["source", "worktree"])
def test_closed_cleanup_preserves_git_source_or_worktree_root(tmp_path, root_kind):
    base = tmp_path / ("source" if root_kind == "source" else ".worktrees/task")
    root, ledger = _closed_project(base)
    projects = root.parent
    if root_kind == "source":
        checkout = base / "checkout"
        projects.rename(checkout)
        projects = checkout
    (projects / ".git").mkdir()
    package = projects / "100" / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"keep")

    result = paid.project_janitor.scan(projects, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"
    assert (projects / ".git").is_dir()


def test_projects_root_with_symlink_ancestor_never_grants_cleanup(tmp_path):
    root, ledger = _closed_project(tmp_path / "real" / "gig")
    package = root / "delivery" / "old.zip"
    package.parent.mkdir()
    package.write_bytes(b"keep")
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "real", target_is_directory=True)

    result = paid.project_janitor.scan(link / "gig" / "projects", ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"


@pytest.mark.parametrize("dirname, filename", [("delivery", "old.zip"), ("work", "scratch.bin")])
def test_closed_cleanup_keeps_regular_leaf_owned_by_another_uid(
    tmp_path, monkeypatch, dirname, filename,
):
    root, ledger = _closed_project(tmp_path)
    package = root / dirname / filename
    package.parent.mkdir()
    package.write_bytes(b"keep")
    original_lstat = Path.lstat

    def foreign_leaf(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == package:
            return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink,
                                   st_size=info.st_size, st_uid=os.getuid() + 1)
        return info

    monkeypatch.setattr(Path, "lstat", foreign_leaf)
    result = paid.project_janitor.scan(root.parent, ledger, dry_run=False)

    assert result["bytes_freed"] == 0
    assert package.read_bytes() == b"keep"
