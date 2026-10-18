from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/mercor/scripts/reconcile_fence_readback.py"
APP = "mercor-revenue-application"
REPLY = "mercor-revenue-reply"
PAID = "mercor-revenue-paid"
T0 = 1790812800  # 2026-10-01T00:00:00Z
# Shapes copied from real `gog gmail messages search --json` output (ids masked).
GOG_EMPTY = {"messages": [], "nextPageToken": ""}
GOG_HIT = {"messages": [{
    "id": "<id>", "threadId": "<thread>", "date": "2026-09-19 15:37",
    "from": "Mercor <team@mercor.com>",
    "subject": "Application Submitted - Example Expert on Mercor",
    "labels": ["UNREAD", "IMPORTANT", "CATEGORY_UPDATES", "INBOX"],
}], "nextPageToken": ""}


def load():
    spec = importlib.util.spec_from_file_location("mercor_fence_readback_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Never read the production DB; a late queued_at keeps the history check satisfied.
    module._queued_at = lambda occurrence: float(T0 + 10**6)
    return module


def event(owner, run_id, phase, timestamp, **extra):
    row = {"loop_id": owner, "run_id": run_id, "phase": phase,
           "status": "running" if phase == "execute" else "fail",
           "timestamp": timestamp, "evidence_refs": []}
    row.update(extra)
    return row


def write_events(root: Path, rows) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return root


def write_outbox(root: Path, *claimed_at: str) -> None:
    with sqlite3.connect(root / "telegram-outbox.sqlite3") as connection:
        connection.execute("CREATE TABLE telegram_outbox (event_key TEXT PRIMARY KEY, "
                           "status TEXT NOT NULL, created_at TEXT NOT NULL, claimed_at TEXT)")
        connection.executemany(
            "INSERT INTO telegram_outbox VALUES (?, 'delivered', '2026-09-01T00:00:00Z', ?)",
            [(f"k{i}", value) for i, value in enumerate(claimed_at)])


class Search:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        return self.result


def app_root(tmp_path: Path) -> Path:
    occurrence = f"{APP}:run-a"
    return write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00", occurrence_id=occurrence),
        event(APP, "run-a", "report", "2026-10-01T00:08:00+00:00",
              occurrence_id=occurrence, release_sha="a" * 40),
    ])


def test_application_claim_run_without_submission_mail_is_pre_effect(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    search = Search(GOG_EMPTY)
    calls = []

    result = module.reconcile(
        state_root=app_root(tmp_path), owner=APP, occurrence=occurrence, resolve=True,
        search=search,
        resolver=lambda owner, occ, *, pre_effect_readback, expected_state:
            calls.append((owner, occ, pre_effect_readback(), expected_state)) or True,
    )

    assert search.queries == [
        f'in:anywhere from:mercor.com subject:"Application Submitted" after:{T0 - 60} '
        f'before:{T0 + 480 + 600}'
    ]
    assert result["resolved"] is True and result["proof_type"] == "pre_effect"
    assert result["release_sha"] == "a" * 40
    assert calls[0][0:2] == (APP, occurrence)
    assert calls[0][2]["evidence_ref"].startswith("gmail-search://")
    assert calls[0][3] == "claimed"


def test_any_submission_mail_or_incomplete_search_keeps_application_fenced(tmp_path):
    module = load()
    root = app_root(tmp_path)
    for result in (GOG_HIT, {"messages": [], "nextPageToken": "next"}, None,
                   {"messages": None, "nextPageToken": ""}):
        proof, reason = module.find_proof(root, APP, f"{APP}:run-a", search=Search(result))
        assert (proof, reason) == (None, "official_readback_not_absent")


def test_application_ignores_the_host_pre_effect_hint(tmp_path):
    # The host writes this hint before every spawn; it does not prove that the
    # agent never submitted, so Application must still read Gmail.
    module = load()
    root = app_root(tmp_path)
    marker = root / "loop-tmp" / APP / "run-a" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"status": "pre_effect_failure", "effect": 0}), encoding="utf-8")
    marker.chmod(0o600)
    search = Search(GOG_HIT)

    assert module.find_proof(root, APP, f"{APP}:run-a", search=search) == (
        None, "official_readback_not_absent")
    assert len(search.queries) == 1


def test_legacy_journal_without_occurrence_binding_reads_back_until_now(tmp_path):
    module = load()
    root = write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00"),
        event(APP, "run-a", "report", "2026-10-01T00:08:00+00:00"),
    ])
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(root, APP, f"{APP}:run-a", search=search)

    assert reason == "ok" and proof["window"] == [float(T0), None]
    assert search.queries == [
        f'in:anywhere from:mercor.com subject:"Application Submitted" after:{T0 - 60}'
    ]


def test_window_spans_nested_runner_rows_of_the_occurrence(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    root = write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00", occurrence_id=occurrence),
        event(APP, "agent-1", "execute", "2026-10-01T00:00:02+00:00", occurrence_id=occurrence),
        event(APP, "run-a", "report", "2026-10-01T00:00:04+00:00", occurrence_id=occurrence),
        event(APP, "agent-1", "report", "2026-10-01T00:07:00+00:00", occurrence_id=occurrence),
    ])
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(root, APP, occurrence, search=search)

    assert reason == "ok" and proof["window"] == [float(T0), float(T0 + 420)]
    assert search.queries[0].endswith(f"after:{T0 - 60} before:{T0 + 420 + 600}")


def reply_root(tmp_path: Path) -> Path:
    occurrence = f"{REPLY}:old-run"
    root = write_events(tmp_path / "reply", [
        event(REPLY, "old-run", "execute", "2026-09-01T00:00:00+00:00"),
        event(REPLY, "old-run", "report", "2026-09-01T00:01:00+00:00", status="pass",
              evidence_refs=[f"lm-occurrence://{REPLY}/older/claim"]),
        event(REPLY, "claimer", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=f"{REPLY}:claimer"),
        event(REPLY, "claimer", "report", "2026-10-01T00:00:04+00:00",
              occurrence_id=occurrence,
              evidence_refs=[f"lm-occurrence://{REPLY}/old-run/claim"]),
    ])
    write_outbox(root, "2026-09-30T23:50:00Z")
    return root


def test_reply_uses_the_later_run_that_claimed_the_occurrence(tmp_path):
    module = load()
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(reply_root(tmp_path), REPLY, f"{REPLY}:old-run",
                                      search=search)

    assert reason == "ok" and proof["window"] == [float(T0), float(T0 + 4)]
    assert proof["telegram_outbox_claims_in_window"] == 0
    assert search.queries == [f"in:anywhere from:me after:{T0 - 60} before:{T0 + 4 + 600}"]


def deferred_wake_root(tmp_path: Path, **wake_report) -> Path:
    # Production shape (mercor-revenue-reply:18df0351cb226510-21162): the wake
    # is deferred at host admission, a run one day later claims it.
    occurrence = f"{REPLY}:wake"
    report = {"status": "blocked", "exit_code": 75, "failure_layer": "admission",
              "blocker": "host_admission_deferred:resource_capacity_busy",
              "effect_identity_status": "not_written", **wake_report}
    root = write_events(tmp_path / "reply", [
        event(REPLY, "wake", "execute", "2026-09-30T00:00:00+00:00",
              occurrence_id=occurrence),
        event(REPLY, "wake", "report", "2026-09-30T00:00:02+00:00",
              occurrence_id=occurrence, **report),
        event(REPLY, "claimer", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=f"{REPLY}:claimer"),
        event(REPLY, "claimer", "report", "2026-10-01T00:00:15+00:00", status="pass",
              occurrence_id=occurrence, release_sha="b" * 40,
              evidence_refs=[f"lm-occurrence://{REPLY}/wake/claim"]),
    ])
    write_outbox(root, "2026-09-30T00:00:01Z")
    return root


def test_reply_window_skips_a_wake_deferred_at_host_admission(tmp_path):
    # The deferred wake never spawned the owner, so its rows must not stretch
    # the window over a day of unrelated mail the account sent.
    module = load()
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(deferred_wake_root(tmp_path), REPLY, f"{REPLY}:wake",
                                      search=search)

    assert reason == "ok" and proof["window"] == [float(T0), float(T0 + 15)]
    assert proof["claim_run_id"] == "claimer"
    assert search.queries == [f"in:anywhere from:me after:{T0 - 60} before:{T0 + 15 + 600}"]


def test_reply_window_keeps_a_tagged_run_that_passed_admission(tmp_path):
    module = load()
    search = Search(GOG_EMPTY)
    root = deferred_wake_root(tmp_path, status="fail", exit_code=1, failure_layer="entrypoint",
                              blocker="entrypoint_exit_1")

    assert module.find_proof(root, REPLY, f"{REPLY}:wake", search=search) == (
        None, "telegram_outbox_not_quiet")
    assert search.queries == [f"in:anywhere from:me after:{T0 - 86400 - 60} "
                              f"before:{T0 + 15 + 600}"]


def test_reply_telegram_send_in_window_or_missing_outbox_keeps_fenced(tmp_path):
    module = load()
    root = reply_root(tmp_path)
    (root / "telegram-outbox.sqlite3").unlink()
    write_outbox(root, "2026-10-01T00:00:03Z")
    assert module.find_proof(root, REPLY, f"{REPLY}:old-run", search=Search(GOG_EMPTY)) == (
        None, "telegram_outbox_not_quiet")

    (root / "telegram-outbox.sqlite3").unlink()
    assert module.find_proof(root, REPLY, f"{REPLY}:old-run", search=Search(GOG_EMPTY)) == (
        None, "telegram_outbox_not_quiet")


def test_reply_pre_effect_hint_still_closes_without_provider_read(tmp_path):
    # Reply-owner removes the host hint before its kernel, and the kernel
    # clears its own hint before every send or notification.
    module = load()
    root = tmp_path / "reply"
    marker = root / "loop-tmp" / REPLY / "run-r" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"status": "pre_effect_failure", "effect": 0}), encoding="utf-8")
    marker.chmod(0o600)
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(root, REPLY, f"{REPLY}:run-r", search=search)

    assert reason == "ok" and proof["evidence_ref"].startswith("lm-pre-effect://")
    assert search.queries == []


def test_ambiguous_or_foreign_claim_keeps_fenced(tmp_path):
    module = load()
    occurrence = f"{REPLY}:old-run"
    claim = [f"lm-occurrence://{REPLY}/old-run/claim"]
    multiple = write_events(tmp_path / "a", [
        event(REPLY, "x", "execute", "2026-10-01T00:00:00+00:00", occurrence_id=f"{REPLY}:x"),
        event(REPLY, "x", "report", "2026-10-01T00:00:04+00:00", occurrence_id=occurrence,
              evidence_refs=claim),
        event(REPLY, "y", "execute", "2026-10-02T00:00:00+00:00", occurrence_id=f"{REPLY}:y"),
        event(REPLY, "y", "report", "2026-10-02T00:00:04+00:00", occurrence_id=occurrence,
              evidence_refs=claim),
    ])
    foreign = write_events(tmp_path / "b", [
        event(REPLY, "old-run", "execute", "2026-10-01T00:00:00+00:00", occurrence_id=occurrence),
        event(REPLY, "old-run", "report", "2026-10-01T00:00:04+00:00",
              occurrence_id=f"{REPLY}:older", status="pass"),
    ])
    no_start = write_events(tmp_path / "c", [
        event(REPLY, "x", "report", "2026-10-01T00:00:04+00:00", occurrence_id=occurrence,
              evidence_refs=claim),
    ])
    for root, reason in ((multiple, "claimed_by_multiple_runs"),
                         (foreign, "claimed_by_other_run"),
                         (no_start, "claim_run_unavailable")):
        search = Search(GOG_EMPTY)
        assert module.find_proof(root, REPLY, occurrence, search=search) == (None, reason)
        assert search.queries == []


def test_journal_newer_than_queued_at_keeps_fenced(tmp_path):
    module = load()
    module._queued_at = lambda occurrence: T0 - 3600
    search = Search(GOG_EMPTY)

    assert module.find_proof(app_root(tmp_path), APP, f"{APP}:run-a", search=search) == (
        None, "history_incomplete")
    assert search.queries == []


def test_unknown_queued_at_keeps_fenced(tmp_path):
    module = load()
    module._queued_at = lambda occurrence: None
    search = Search(GOG_EMPTY)

    assert module.find_proof(app_root(tmp_path), APP, f"{APP}:run-a", search=search) == (
        None, "history_incomplete")
    assert search.queries == []


def test_window_younger_than_the_mail_tail_keeps_fenced(tmp_path):
    # A confirmation mail can still arrive up to TAIL after the window closes.
    module = load()
    occurrence = f"{APP}:run-a"
    now = datetime.now(timezone.utc)
    module._queued_at = lambda occurrence: now.timestamp()
    bound = write_events(tmp_path / "bound", [
        event(APP, "run-a", "execute", (now - timedelta(seconds=30)).isoformat(),
              occurrence_id=occurrence),
        event(APP, "run-a", "report", (now - timedelta(seconds=10)).isoformat(),
              occurrence_id=occurrence),
    ])
    legacy = write_events(tmp_path / "legacy", [
        event(APP, "run-a", "execute", (now - timedelta(seconds=30)).isoformat()),
        event(APP, "run-a", "report", (now - timedelta(seconds=10)).isoformat()),
    ])
    for root in (bound, legacy):
        search = Search(GOG_EMPTY)
        assert module.find_proof(root, APP, occurrence, search=search) == (
            None, "window_not_settled")
        assert search.queries == []


def write_snapshot(root: Path, observed_at: str, mtime: float) -> None:
    path = root / "paid-official-snapshot.json"
    path.write_text(json.dumps({"version": 1, "observed_at": observed_at, "contracts": []}),
                    encoding="utf-8")
    os.utime(path, (mtime, mtime))


def paid_root(tmp_path: Path, previous_release: str = "b" * 40) -> Path:
    occurrence = f"{PAID}:run-p"
    return write_events(tmp_path / "mercor", [
        # The previous wake on the same release wrote the snapshot, so that
        # release gates its kernel on a fresh snapshot.
        event(PAID, "run-prev", "execute", "2026-09-30T23:54:50+00:00",
              occurrence_id=f"{PAID}:run-prev", release_sha=previous_release),
        event(PAID, "run-prev", "report", "2026-09-30T23:55:10+00:00", status="pass",
              occurrence_id=f"{PAID}:run-prev", release_sha=previous_release),
        event(PAID, "run-p", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=occurrence, release_sha="b" * 40),
        event(PAID, "run-p", "report", "2026-10-01T00:00:11+00:00",
              occurrence_id=occurrence, release_sha="b" * 40),
    ])


def test_paid_kernel_never_started_when_its_snapshot_was_not_refreshed(tmp_path):
    module = load()
    root = paid_root(tmp_path)
    write_snapshot(root, "2026-09-30T23:55:00+00:00", T0 - 300)
    search = Search(GOG_EMPTY)

    proof, reason = module.find_proof(root, PAID, f"{PAID}:run-p", search=search)

    assert reason == "ok" and proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].startswith("lm-mercor-paid-snapshot://")
    assert proof["snapshot_writer_run_id"] == "run-prev"
    assert search.queries == []


def test_paid_snapshot_refreshed_in_run_or_existing_marker_keeps_fenced(tmp_path):
    module = load()
    occurrence = f"{PAID}:run-p"
    root = paid_root(tmp_path)
    write_snapshot(root, "2026-10-01T00:00:05+00:00", T0 + 5)
    assert module.find_proof(root, PAID, occurrence) == (
        None, "paid_snapshot_refreshed_in_window")

    write_snapshot(root, "2026-09-30T23:55:00+00:00", T0 - 300)
    digest = hashlib.sha256(occurrence.encode()).hexdigest()
    marker = root / "shared-paid" / "runs" / f"{digest}.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"version": 1, "occurrence_id": occurrence,
                                  "status": "effect_started"}), encoding="utf-8")
    assert module.find_proof(root, PAID, occurrence) == (None, "paid_run_marker_present")


def test_paid_window_starts_at_the_earliest_nested_row(tmp_path):
    # A nested runner row before the claim run's own start moves the window,
    # so a snapshot written between them is not "older than the run".
    module = load()
    occurrence = f"{PAID}:run-p"
    root = paid_root(tmp_path)
    rows = (root / "events.jsonl").read_text(encoding="utf-8")
    nested = event(PAID, "agent-1", "execute", "2026-09-30T23:58:00+00:00",
                   occurrence_id=occurrence)
    (root / "events.jsonl").write_text(rows + json.dumps(nested) + "\n", encoding="utf-8")
    write_snapshot(root, "2026-09-30T23:59:00+00:00", T0 - 60)

    assert module.find_proof(root, PAID, occurrence) == (
        None, "paid_snapshot_refreshed_in_window")


def test_paid_snapshot_written_by_another_release_keeps_fenced(tmp_path):
    # Releases before the snapshot gate exec the kernel directly, so an old
    # snapshot proves nothing unless the claim run's own release wrote it.
    module = load()
    root = paid_root(tmp_path, previous_release="c" * 40)
    write_snapshot(root, "2026-09-30T23:55:00+00:00", T0 - 300)

    assert module.find_proof(root, PAID, f"{PAID}:run-p") == (
        None, "paid_snapshot_writer_unproven")


def test_paid_owner_runs_kernel_only_after_a_fresh_snapshot():
    text = (ROOT / "skills/earn/mercor/scripts/paid-owner").read_text(encoding="utf-8")
    snapshot = text.index("job_search_loop.mercor_paid_snapshot")
    failure_exit = text.index("exit 75", snapshot)
    kernel = text.index("exec ")
    assert snapshot < failure_exit < kernel
    assert text.count("paid_kernel.py") == 1


def test_gmail_search_is_read_only_and_bound_to_the_application_account(tmp_path, monkeypatch):
    module = load()
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"candidate": {"application_email": "a@example.com"}}),
                       encoding="utf-8")
    monkeypatch.setattr(module, "PROFILE", profile)
    seen = []

    class Done:
        returncode = 0
        stdout = json.dumps(GOG_EMPTY)

    monkeypatch.setattr(module.subprocess, "run",
                        lambda argv, **kwargs: seen.append(argv) or Done())

    assert module.gmail_search("in:anywhere from:me") == GOG_EMPTY
    argv = seen[0]
    assert argv[argv.index("--account") + 1] == "a@example.com"
    assert "--gmail-no-send" in argv and argv[4] == "in:anywhere from:me"


def test_gmail_search_loads_keyring_password_from_job_search_private_env(tmp_path, monkeypatch):
    # launchd has no TTY, so gog needs GOG_KEYRING_PASSWORD; the reconciler's env lacks it.
    module = load()
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"candidate": {"application_email": "a@example.com"}}),
                       encoding="utf-8")
    private = tmp_path / "private.env"
    private.write_text("# x\nexport GOG_KEYRING_PASSWORD='s3 cret'\n", encoding="utf-8")
    monkeypatch.setattr(module, "PROFILE", profile)
    monkeypatch.setattr(module, "PRIVATE_ENV", private)
    monkeypatch.delenv("GOG_KEYRING_PASSWORD", raising=False)
    envs = []

    class Done:
        returncode = 0
        stdout = json.dumps(GOG_EMPTY)

    monkeypatch.setattr(module.subprocess, "run",
                        lambda argv, **kwargs: envs.append(kwargs.get("env")) or Done())

    assert module.gmail_search("in:anywhere from:me") == GOG_EMPTY
    assert envs[0]["GOG_KEYRING_PASSWORD"] == "s3 cret"
