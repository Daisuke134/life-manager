import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "gig_release.py"
SPEC = importlib.util.spec_from_file_location("gig_release_gc_test", SCRIPT)
gig_release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gig_release)


def test_writer_notification_identity_has_no_personal_public_default(monkeypatch):
    monkeypatch.setattr(gig_release, "OVERRIDES", Path("/nonexistent/install.json"))
    _, table = gig_release.settings(Path("/release"))
    wrapper = (
        gig_release.REPO_ROOT
        / "skills/writer-agent/scripts/opportunity-response-owner"
    ).read_text()

    assert "@gmail.com" not in wrapper
    assert "LIFE_MANAGER_GMAIL_ACCOUNT" in wrapper
    assert table["WRITER_TELEGRAM_TARGET"] == ""


def test_shared_launchd_path_resolves_user_installed_agent_tools(monkeypatch):
    monkeypatch.setattr(gig_release, "OVERRIDES", Path("/nonexistent/install.json"))
    manifest, table = gig_release.settings(Path("/release"))
    job = next(
        row for row in manifest["jobs"]
        if row["label"] == "ai.anicca.life-manager-upwork-free-loop"
    )

    environment = gig_release.plist_for(job, table)["EnvironmentVariables"]

    assert environment["PATH"].split(":")[0] == f'{table["HOME"]}/.local/bin'


def test_retired_upwork_labels_cannot_be_explicitly_activated():
    with pytest.raises(ValueError, match="retired provider label"):
        gig_release.activation_labels({"ai.anicca.life-manager-upwork-free-loop"})


def test_main_reports_retired_upwork_activation_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(gig_release, "git", lambda *args: "a" * 40)
    monkeypatch.setattr(gig_release, "build", lambda sha: Path("/release"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gig_release.py",
            "activate",
            "--jobs",
            "ai.anicca.life-manager-upwork-free-loop",
            "--dry-run",
        ],
    )

    result = gig_release.main()

    assert result == 2
    assert "retired provider label" in capsys.readouterr().err


def test_gc_preserves_release_referenced_by_loaded_launchd_job(tmp_path, monkeypatch):
    current_sha = "a" * 40
    loaded_sha = "b" * 40
    rollback_sha = "c" * 40
    stale_sha = "d" * 40
    for sha in (current_sha, loaded_sha, rollback_sha, stale_sha):
        release = tmp_path / sha
        release.mkdir()
        (release / "marker").write_text(sha, encoding="utf-8")
    (tmp_path / "current").symlink_to(current_sha)

    monkeypatch.setattr(gig_release, "RELEASE_ROOT", tmp_path)
    monkeypatch.setattr(gig_release, "CURRENT_RELEASE", tmp_path / "current")
    monkeypatch.setattr(
        gig_release,
        "loaded_program",
        lambda label: ["/bin/bash", str(tmp_path / loaded_sha / "browser.sh")],
    )
    monkeypatch.setattr(
        gig_release.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    removed = gig_release.collect_old_releases()

    assert loaded_sha not in removed
    assert (tmp_path / loaded_sha).is_dir()


def test_gc_inspects_loaded_disk_cleanup_owner_while_idle(tmp_path, monkeypatch):
    current_sha = "a" * 40
    cleanup_sha = "b" * 40
    rollback_sha = "c" * 40
    stale_sha = "d" * 40
    for sha in (current_sha, cleanup_sha, rollback_sha, stale_sha):
        (tmp_path / sha).mkdir()
    (tmp_path / "current").symlink_to(current_sha)

    monkeypatch.setattr(gig_release, "RELEASE_ROOT", tmp_path)
    monkeypatch.setattr(gig_release, "CURRENT_RELEASE", tmp_path / "current")
    monkeypatch.setattr(
        gig_release,
        "loaded_program",
        lambda label: (
            ["/usr/bin/python3", str(tmp_path / cleanup_sha / "disk_cleanup.py")]
            if label == "ai.anicca.life-manager-disk-cleanup"
            else []
        ),
    )
    monkeypatch.setattr(
        gig_release.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    removed = gig_release.collect_old_releases()

    assert cleanup_sha not in removed
    assert (tmp_path / cleanup_sha).is_dir()


def test_gc_preserves_release_pinned_by_live_wrapper(tmp_path, monkeypatch):
    current_sha = "a" * 40
    pinned_sha = "b" * 40
    rollback_sha = "c" * 40
    stale_sha = "d" * 40
    for sha in (current_sha, pinned_sha, rollback_sha, stale_sha):
        release = tmp_path / sha
        release.mkdir()
        (release / "marker").write_text(sha, encoding="utf-8")
    (tmp_path / "current").symlink_to(current_sha)
    parent = tmp_path / pinned_sha / "skills" / "earn" / "gig" / "scripts" / "application_parent.py"
    parent.parent.mkdir(parents=True)
    parent.touch()

    monkeypatch.setattr(gig_release, "RELEASE_ROOT", tmp_path)
    monkeypatch.setattr(gig_release, "CURRENT_RELEASE", tmp_path / "current")
    monkeypatch.setattr(gig_release, "loaded_program", lambda _label: [])
    monkeypatch.setattr(gig_release.os, "getpid", lambda: 4242)
    monkeypatch.setattr(gig_release.os, "kill", lambda pid, signal: None)
    monkeypatch.setattr(
        gig_release.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    marker = gig_release.pin_release_for_process(parent)
    removed = gig_release.collect_old_releases()

    assert marker == tmp_path / ".pins" / f"4242-{pinned_sha}"
    assert pinned_sha not in removed
    assert (tmp_path / pinned_sha).is_dir()


def test_job_needs_activation_when_loaded_environment_is_stale(monkeypatch):
    job = {
        "label": "ai.anicca.hf-gig-reply-detector",
        "program": ["/usr/bin/python3", "{{RELEASE}}/reply_detector.py"],
        "env": {"GIG_NO_CONTACT_REGISTRY": "{{HOME}}/.config/no-contact.json"},
        "log_basename": "reply",
    }
    table = {
        "RELEASE": "/tmp/current",
        "HOME": "/tmp/test-home",
        "GIG_LOG_DIR": "/tmp/logs",
    }
    desired = gig_release.plist_for(job, table)
    monkeypatch.setattr(gig_release, "loaded_program", lambda _label: desired["ProgramArguments"])
    monkeypatch.setattr(gig_release, "loaded_environment", lambda _label: {})

    assert gig_release.job_needs_activation(job, table) is True


def test_job_does_not_need_activation_when_program_and_environment_match(monkeypatch):
    job = {
        "label": "ai.anicca.hf-gig-reply-detector",
        "program": ["/usr/bin/python3", "{{RELEASE}}/reply_detector.py"],
        "env": {"GIG_NO_CONTACT_REGISTRY": "{{HOME}}/.config/no-contact.json"},
        "log_basename": "reply",
    }
    table = {
        "RELEASE": "/tmp/current",
        "HOME": "/tmp/test-home",
        "GIG_LOG_DIR": "/tmp/logs",
    }
    desired = gig_release.plist_for(job, table)
    monkeypatch.setattr(gig_release, "loaded_program", lambda _label: desired["ProgramArguments"])
    monkeypatch.setattr(
        gig_release,
        "loaded_environment",
        lambda _label: desired["EnvironmentVariables"] | {"XPC_SERVICE_NAME": job["label"]},
    )

    assert gig_release.job_needs_activation(job, table) is False


def test_default_activation_never_restarts_a_busy_continuous_lane():
    label = "ai.anicca.hf-gig-reply-detector"

    assert gig_release.skip_busy_for_requested_activation(label, None) is True
    assert gig_release.skip_busy_for_requested_activation(label, {label}) is False


def test_upwork_browser_running_fence_uses_process_fallback(monkeypatch):
    label = "ai.anicca.life-manager-upwork-browser"
    ps_output = [""]

    def run(command, **_kwargs):
        if command[:2] == ["launchctl", "print"]:
            return SimpleNamespace(returncode=1, stdout="")
        if command == ["ps", "-axo", "command="]:
            return SimpleNamespace(returncode=0, stdout=ps_output[0])
        raise AssertionError(command)

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.is_running(label) is False
    ps_output[0] = "/Applications/Chromium --remote-debugging-port=9233\n"
    assert gig_release.is_running(label) is True


def test_coconala_browser_running_fence_uses_process_fallback(monkeypatch):
    label = "ai.anicca.hf-gig-browser"
    ps_output = [""]

    def run(command, **_kwargs):
        if command[:2] == ["launchctl", "print"]:
            return SimpleNamespace(returncode=1, stdout="")
        if command == ["ps", "-axo", "command="]:
            return SimpleNamespace(returncode=0, stdout=ps_output[0])
        raise AssertionError(command)

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.is_running(label) is False
    ps_output[0] = "/Applications/Chromium --remote-debugging-port=9223\n"
    assert gig_release.is_running(label) is True


def test_default_release_scope_covers_every_coconala_catalog_job():
    catalog = json.loads((gig_release.REPO_ROOT / "apps/life-manager/config/product-loop-catalog.json").read_text())
    product = next(row for row in catalog["loops"] if row["id"] == "gig-coconala")
    registry = json.loads((gig_release.REPO_ROOT / "config/loop-registry.json").read_text())
    assert gig_release.activation_labels(None) == {
        registry["loops"][loop_id]["label"] for loop_id in product["job_ids"]
    }


def test_main_uses_managed_activation_without_publishing_legacy_current(monkeypatch):
    activated = []
    monkeypatch.setattr(gig_release, "git", lambda *args: "a" * 40)
    monkeypatch.setattr(gig_release, "build", lambda sha: Path("/legacy-release"))
    monkeypatch.setattr(gig_release, "managed_release", lambda sha: Path("/managed-release"), raising=False)
    monkeypatch.setattr(gig_release, "activate_managed_jobs",
                        lambda release, wanted, dry_run: activated.append((release, wanted, dry_run)) or 0,
                        raising=False)
    monkeypatch.setattr(gig_release, "publish", lambda *_: pytest.fail("must not move legacy current"))
    monkeypatch.setattr(sys, "argv", ["gig_release.py", "activate"])

    assert gig_release.main() == 0
    assert activated == [(Path("/managed-release"), gig_release.activation_labels(None), False)]


def _managed_release_fixture(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "RELEASE.json").write_text(json.dumps({
        "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
    }))
    (release / "config").mkdir()
    (release / "config/loop-registry.json").write_text(json.dumps({"loops": {
        owner: {"label": "ai.anicca." + owner}
        for owner in ("hf-gig-paid-direct", "hf-gig-daily-report")
    }}))
    return release


def test_managed_release_cuts_a_complete_main_release_without_changing_current(tmp_path, monkeypatch):
    loops_root = tmp_path / "loops"
    release = loops_root / "releases" / "20261023T000000-aaaaaaaa"
    monkeypatch.setenv("LOOPS_ROOT", str(loops_root))
    monkeypatch.setenv("LOOPS_ACTIVATE_CURRENT", "1")
    monkeypatch.setenv("LOOPS_RELEASE_PATHS", "skills/earn/gig")
    monkeypatch.setattr(gig_release, "git", lambda *_: "")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        release.mkdir(parents=True)
        (release / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
            "runtime_python": sys.executable,
        }))
        return SimpleNamespace(returncode=0, stdout=f"dependency build output\nrelease -> {release}  (ancestor-of-origin-main; current unchanged)\n", stderr="")

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.managed_release("a" * 40) == release
    assert len(calls) == 1
    assert calls[0][0] == ["/bin/bash", str(gig_release.REPO_ROOT / "bin/cut-loop-release.sh"), "a" * 40]
    assert calls[0][1]["env"]["LOOPS_ACTIVATE_CURRENT"] == "0"
    assert calls[0][1]["env"]["LOOPS_RELEASE_PATHS"] == ""
    assert calls[0][1]["env"]["LOOPS_RUNTIME_PYTHON"] == sys.executable
    assert gig_release.managed_release("a" * 40) == release
    assert len(calls) == 1


@pytest.mark.parametrize("old_python", ["/removed/venv/bin/python", "/bin/sh"])
def test_managed_release_rebuilds_dead_or_different_runtime(tmp_path, monkeypatch, old_python):
    root = tmp_path / "loops"
    old = root / "releases/old"
    old.mkdir(parents=True)
    (old / "RELEASE.json").write_text(json.dumps({
        "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
        "runtime_python": old_python,
    }))
    monkeypatch.setenv("LOOPS_ROOT", str(root))
    monkeypatch.setattr(gig_release, "git", lambda *_: "")
    new = root / "releases/new"
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        new.mkdir()
        (new / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
            "runtime_python": sys.executable,
        }))
        return SimpleNamespace(returncode=0, stdout=f"release -> {new}  (ancestor-of-origin-main; current unchanged)\n", stderr="")
    monkeypatch.setattr(gig_release.subprocess, "run", run)
    assert gig_release.managed_release("a" * 40) == new
    assert len(calls) == 1


@pytest.mark.parametrize("provenance,paths", [
    ("pushed-not-yet-on-main", "ALL"),
    ("ancestor-of-origin-main", "skills/earn/gig"),
])
def test_managed_release_refuses_nonmain_or_sparse_receipts(tmp_path, monkeypatch, provenance, paths):
    monkeypatch.setenv("LOOPS_ROOT", str(tmp_path / "loops"))
    monkeypatch.setattr(gig_release, "git", lambda *_: "")
    release = tmp_path / "loops/releases/candidate"

    def run(command, **kwargs):
        release.mkdir(parents=True)
        (release / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": provenance, "release_paths": paths,
        }))
        return SimpleNamespace(returncode=0, stdout=f"release -> {release}  (pushed-not-yet-on-main; current unchanged)\n", stderr="")

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    with pytest.raises(ValueError, match="complete.*main"):
        gig_release.managed_release("a" * 40)


def test_dry_run_neither_builds_a_release_nor_observes_launchd(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gig_release.py", "activate", "--dry-run"])
    monkeypatch.setattr(gig_release, "git", lambda *_: pytest.fail("dry-run must not build"))
    monkeypatch.setattr(gig_release.subprocess, "run", lambda *_a, **_k: pytest.fail("dry-run must not observe launchd"))

    assert gig_release.main() == 0
    assert len(json.loads(capsys.readouterr().out)["jobs"]) == len(gig_release.coconala_jobs())


def test_uninstall_stops_every_catalog_owner_and_keeps_private_state(tmp_path, monkeypatch, capsys):
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    private = tmp_path / "private-state"
    private.write_text("preserved")
    jobs = gig_release.coconala_jobs()
    for label in jobs:
        (agents / f"{label}.plist").write_text("definition")
    monkeypatch.setattr(gig_release, "LAUNCH_AGENTS", agents)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0].endswith("launchctl-safe"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        owner = command[-1]
        return SimpleNamespace(returncode=0, stdout=json.dumps([{
            "label": "ai.anicca." + owner, "return_code": 0,
        }]), stderr="")

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.stop_managed_jobs(True) == 0
    assert set(command[-1] for command in calls[1:]) == set(jobs.values())
    assert calls[-1][-1] == "hf-gig-browser"
    assert list(agents.iterdir()) == []
    assert private.read_text() == "preserved"
    assert json.loads(capsys.readouterr().out)["jobs"] == len(jobs)


def test_managed_activation_installs_unloaded_job_and_preserves_loaded_busy_owner(tmp_path, monkeypatch, capsys):
    release = _managed_release_fixture(tmp_path)
    wanted = {"ai.anicca.hf-gig-paid-direct", "ai.anicca.hf-gig-daily-report"}
    calls = []
    monkeypatch.setattr(gig_release, "coconala_jobs", lambda *_: {
        "ai.anicca.hf-gig-paid-direct": "hf-gig-paid-direct",
        "ai.anicca.hf-gig-daily-report": "hf-gig-daily-report",
    }, raising=False)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0].endswith("launchctl-safe"):
            if command[1] == "preflight":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[-1].endswith("hf-gig-paid-direct"):
                return SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")
            return SimpleNamespace(returncode=0, stdout="state = running\narguments = {\n/old/runner\n}\n", stderr="")
        label = "ai.anicca." + kwargs["env"]["LIFE_MANAGER_APPLY_TARGET"]
        row = {"ok": True, "label": label, "release_sha": "a" * 40}
        if label.endswith("daily-report"):
            row["skipped"] = "running"
        return SimpleNamespace(returncode=0, stdout=json.dumps([row]), stderr="")

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.activate_managed_jobs(release, wanted, False) == 2
    applied = [(command, options["env"]) for command, options in calls
               if command[0].endswith("/bin/lm-loop")]
    assert len(applied) == 2
    for command, environment in applied:
        assert environment["LIFE_MANAGER_RELEASE_ROOT"] == str(release)
        if environment["LIFE_MANAGER_APPLY_TARGET"].endswith("paid-direct"):
            assert command[1:] == ["apply"]
        else:
            assert command[1:] == ["apply", "--loaded-idle-only"]
    assert json.loads(capsys.readouterr().out)["status"] == "waiting"


def test_managed_activation_never_treats_a_failed_probe_as_a_new_job(tmp_path, monkeypatch):
    release = _managed_release_fixture(tmp_path)
    label = "ai.anicca.hf-gig-paid-direct"
    monkeypatch.setattr(gig_release, "coconala_jobs", lambda *_: {label: "hf-gig-paid-direct"}, raising=False)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0 if command[1] == "preflight" else 141,
                               stdout="", stderr="Reentrancy avoided")

    monkeypatch.setattr(gig_release.subprocess, "run", run)

    assert gig_release.activate_managed_jobs(release, {label}, False) == 75
    assert all(command[0].endswith("launchctl-safe") for command in calls)


def test_coconala_resume_from_another_checkout_preserves_owner_source_binding(tmp_path, monkeypatch):
    release = _managed_release_fixture(tmp_path)
    label, owner = "ai.anicca.hf-gig-paid-direct", "hf-gig-paid-direct"
    binding = {"LIFE_MANAGER_HOST_PROFILE": "/owner/host.json",
               "LIFE_MANAGER_SOURCE_REPO": "/owner/source-A",
               "LIFE_MANAGER_RUNTIME_PYTHON": sys.executable}
    monkeypatch.setattr(gig_release, "REPO_ROOT", Path("/owner/source-B"))
    monkeypatch.setattr(gig_release, "_runtime_environment", lambda: binding)
    monkeypatch.setattr(gig_release, "coconala_jobs", lambda *_: {label: owner})
    printed = "arguments = {\n" + "\n".join([str(release / "bin/lm-loop-run"), owner, str(release)]) + "\n}\nenvironment = {\n"
    printed += "\n".join(f"{key} => {value}" for key, value in binding.items()) + "\n}\n"
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if "apply" in command:
            return SimpleNamespace(returncode=0, stdout=json.dumps([{
                "ok": True, "label": label, "skipped": "loaded-running"}]), stderr="")
        return SimpleNamespace(returncode=0, stdout=printed, stderr="")
    monkeypatch.setattr(gig_release.subprocess, "run", run)
    assert gig_release.activate_managed_jobs(release, {label}, False) == 0
    assert not any("apply" in command for command in calls)


def test_migrated_paid_job_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    assert all(row["label"] != "ai.anicca.hf-gig-paid-direct" for row in manifest["jobs"])
    assert "ai.anicca.hf-gig-paid-direct" not in gig_release.JOB_PROCESS_MARKERS


def test_migrated_writer_claim_job_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    assert all(row["label"] != "ai.anicca.writer-claim-loop" for row in manifest["jobs"])
    assert "ai.anicca.writer-claim-loop" not in gig_release.JOB_PROCESS_MARKERS
    installer = gig_release.REPO_ROOT / "skills/writer-agent/scripts/install-claim-loop-worker.sh"
    assert not installer.exists()


def test_migrated_writer_money_sync_job_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    assert all(row["label"] != "ai.anicca.writer-money-sync" for row in manifest["jobs"])
    assert "ai.anicca.writer-money-sync" not in gig_release.JOB_PROCESS_MARKERS
    installer = gig_release.REPO_ROOT / "skills/writer-agent/scripts/install-money-sync-worker.sh"
    assert not installer.exists()


def test_migrated_writer_opportunity_discovery_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    label = "ai.anicca.writer-opportunity-discovery"
    assert all(row["label"] != label for row in manifest["jobs"])
    assert label not in gig_release.JOB_PROCESS_MARKERS
    installer = gig_release.REPO_ROOT / "skills/writer-agent/scripts/install-opportunity-discovery-worker.sh"
    assert not installer.exists()


def test_migrated_writer_opportunity_response_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    label = "ai.anicca.writer-opportunity-response"
    assert all(row["label"] != label for row in manifest["jobs"])
    assert label not in gig_release.JOB_PROCESS_MARKERS
    installer = gig_release.REPO_ROOT / "skills/writer-agent/scripts/install-opportunity-response-worker.sh"
    assert not installer.exists()


def test_migrated_writer_report_is_not_owned_by_legacy_manifest():
    manifest = json.loads(gig_release.MANIFEST.read_text(encoding="utf-8"))
    label = "ai.anicca.writer-report"
    assert all(row["label"] != label for row in manifest["jobs"])
    assert label not in gig_release.JOB_PROCESS_MARKERS
    installer = gig_release.REPO_ROOT / "skills/writer-agent/scripts/install-writer-report-worker.sh"
    assert not installer.exists()


def test_explicit_release_scope_is_preserved():
    assert gig_release.activation_labels({"example.job"}) == {"example.job"}


def test_release_watch_is_retired_in_favor_of_the_shared_reconciler():
    # 2026-08-28 "chore(gig): retire release watcher" (93d6720ee) deleted the
    # `watch` subcommand from gig_release.py itself: publishing without
    # reactivating launchd is no longer this script's job. The same
    # publish-without-reactivating behaviour now lives one layer up, in the
    # shared `life-manager-release-reconciler` loop
    # (bin/reconcile-agent-runner-release.sh), which cuts/publishes one
    # pushed-main release for every managed runner -- including all four
    # Coconala business lanes -- and reconciles each loop without touching
    # launchd job definitions. Assert the retirement stuck (no `watch` choice
    # survives here) and that the successor that owns the intent still exists
    # and still covers this skill's lanes.
    gig_release_parser_source = SCRIPT.read_text(encoding="utf-8")
    assert 'choices=("build", "activate", "status", "stop", "uninstall")' in gig_release_parser_source
    assert '"watch"' not in gig_release_parser_source

    reconciler = gig_release.REPO_ROOT / "bin" / "reconcile-agent-runner-release.sh"
    assert reconciler.is_file()
    script = reconciler.read_text(encoding="utf-8")
    registry = json.loads(
        (gig_release.REPO_ROOT / "config" / "loop-registry.json").read_text(encoding="utf-8")
    )
    reconciled_routes = {"shared-agent-runner", "deterministic"}
    for route in reconciled_routes:
        assert f'reconcile {route} --loaded-idle-only --max-owners 4' in script
    for loop_id in (
        "hf-gig-apply-direct", "hf-gig-reply-detector",
        "hf-gig-storefront-direct", "hf-gig-paid-direct",
    ):
        assert registry["loops"][loop_id]["provider_route"] in reconciled_routes

    reconciler_loop = registry["loops"]["life-manager-release-reconciler"]
    assert reconciler_loop["entrypoint"] == "bin/reconcile-agent-runner-release.sh"
