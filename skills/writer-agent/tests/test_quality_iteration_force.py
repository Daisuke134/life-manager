import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/writer-agent/scripts"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALITY = load("quality_self_heal_force", SCRIPTS / "quality_self_heal.py")
RESUME = load("publication_resume_force", SCRIPTS / "publication_resume.py")
RECOVERY = load("quality_feedback_recovery_force", SCRIPTS / "quality_feedback_recovery.py")


def _write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def _set_quality_gates(run: Path, iteration: int) -> dict[str, Path]:
    drafts = {}
    for lang in ("ja", "en"):
        draft = run / f"article-{lang}.md"
        draft.write_text(f"# {lang}\niteration {iteration}\nnew evidence {iteration}\n", encoding="utf-8")
        digest = hashlib.sha256(draft.read_bytes()).hexdigest()
        drafts[lang] = draft
        _write(run / "gates" / f"editorial-{lang}.json", {
            "verdict": "FAIL",
            "article_sha256": digest,
            "fixes": [f"rewrite-{iteration}"],
        })
        _write(run / "gates" / f"reader-testing-gate-{lang}.terminal.json", {
            "status": "revision-required",
            "exit_code": 1,
            "article_sha256": digest,
            "payload": {"verdict": "FAIL", "unanswered_questions": ["question"]},
        })
        _write(run / "gates" / f"identity-{lang}.json", {
            "verdict": "PASS",
            "article_sha256": digest,
        })
    return drafts


def _record_invocation(run: Path, attempt: int, recovery_attempt: int) -> None:
    gates = run / "gates"
    value = {
        "version": 1,
        "run_id": run.name,
        "quality_attempt": attempt,
        "recovery_attempt": recovery_attempt,
        "owner_pid": 10000 + recovery_attempt,
        "started_at": f"2026-08-21T00:00:0{recovery_attempt}Z",
        "prompt_sha256": hashlib.sha256(f"prompt-{recovery_attempt}".encode()).hexdigest(),
        "feedback_plan_sha256": hashlib.sha256(b"feedback-plan").hexdigest(),
        "iteration_feedback_plan_sha256": hashlib.sha256(
            f"feedback-plan-{attempt}".encode()
        ).hexdigest(),
        "previous_feedback_invocation_sha256": None,
    }
    if attempt > 2:
        previous = json.loads(
            (gates / f"quality-feedback-invocation-attempt-{attempt - 1}.json").read_text()
        )
        value["previous_feedback_invocation_sha256"] = hashlib.sha256(
            (gates / f"quality-feedback-invocation-attempt-{attempt - 1}.json").read_bytes()
        ).hexdigest()
    value["receipt_sha256"] = QUALITY._receipt_hash(value)
    _write(gates / f"quality-feedback-invocation-attempt-{attempt}.json", value)


def _quality_fixture(tmp_path: Path):
    run = tmp_path / "run"
    gates = run / "gates"
    gates.mkdir(parents=True)
    _set_quality_gates(run, 1)
    _write(gates / "topic-route.json", {
        "topic_id": "topic-1", "editorial_form": "explainer"
    })
    return run


def _orphan_fixture(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    partial = run / "gates" / "quality-attempt-1"
    partial.mkdir()
    return run, drafts, partial


def _orphan_digest(filename: str, content: bytes) -> str:
    return hashlib.sha256(filename.encode() + b"\0" + content + b"\0").hexdigest()


def _advance_to_force(run: Path, monkeypatch) -> dict:
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    result = QUALITY.assess(run, drafts)
    assert result["attempt"] == 1
    return {"run": run, "drafts": drafts, "result": result}


def _write_advisory_terminals(run: Path, drafts: dict[str, Path]) -> None:
    for lang, draft in drafts.items():
        _write(run / "gates" / f"quality-terminal-{lang}.json", {
            "status": "terminal",
            "lang": lang,
            "article_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
            "editorial_gate": "ADVISORY",
            "reader_gate": "ADVISORY",
            "identity_gate": "PASS",
            "safety_gate": "ALLOW",
        })


def test_first_quality_iteration_emits_force_publish_advisory(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    state = _advance_to_force(run, monkeypatch)
    result = state["result"]
    assert result["action"] == "force_publish_advisory"
    assert result["force_publish_after_iterations"] == 1
    assert result["quality_advisory"] is True
    assert QUALITY.validate_force_receipt(run, state["drafts"])


def test_force_advisory_resume_goes_directly_to_publication_handoff(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    _advance_to_force(run, monkeypatch)
    ledger = tmp_path / "articles.jsonl"
    ledger.write_text("", encoding="utf-8")
    _write(run / "gates" / "quality-repair-state.json", {
        "version": 1,
        "status": "terminal-incomplete",
        "run_id": run.name,
        "attempts": 2,
    })

    decision = RECOVERY.plan(run, ledger)
    assert decision["reason"] == "terminal-quality-publication-handoff"
    handoff = RECOVERY.prepare_publication_handoff(run, ledger)
    assert handoff["status"] == "publication-prepared"
    assert not (run / "gates" / "quality-feedback-plan.json").exists()

    unsafe = _quality_fixture(tmp_path / "unsafe")
    identity = unsafe / "gates" / "identity-ja.json"
    value = json.loads(identity.read_text())
    value["verdict"] = "FAIL"
    _write(identity, value)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    unsafe_result = QUALITY.assess(unsafe, {
        lang: unsafe / f"article-{lang}.md" for lang in ("ja", "en")
    })
    assert unsafe_result["action"] != "force_publish_advisory"
    assert RECOVERY.plan(unsafe, ledger)["reason"] != (
        "terminal-quality-publication-handoff"
    )


def test_initial_ready_resume_goes_directly_to_publication_handoff(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = {lang: run / f"article-{lang}.md" for lang in ("ja", "en")}
    for lang, draft in drafts.items():
        digest = hashlib.sha256(draft.read_bytes()).hexdigest()
        _write(run / "gates" / f"editorial-{lang}.json", {
            "verdict": "PASS", "article_sha256": digest, "fixes": [],
        })
        _write(run / "gates" / f"reader-testing-gate-{lang}.terminal.json", {
            "status": "pass", "exit_code": 0, "article_sha256": digest,
            "payload": {"verdict": "PASS", "unanswered_questions": []},
        })
    assert QUALITY.assess(run, drafts)["action"] == "ready_to_freeze"
    ledger = tmp_path / "ready-ledger.jsonl"
    ledger.write_text("", encoding="utf-8")

    assert RECOVERY.plan(run, ledger)["reason"] == (
        "terminal-quality-publication-handoff"
    )
    handoff = RECOVERY.prepare_publication_handoff(run, ledger)
    assert handoff["status"] == "publication-prepared"
    assert not (run / "gates" / "quality-feedback-plan.json").exists()


def test_orphan_quality_snapshot_is_archived_before_fresh_snapshot(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    old_bytes = b"orphan evidence that must remain unchanged\n"
    (partial / "editorial-ja.json").write_bytes(old_bytes)
    orphan_digest = _orphan_digest("editorial-ja.json", old_bytes)

    result = QUALITY.assess(run, drafts)

    archive = (
        run / "gates" / "quality-attempt-orphans" / f"attempt-1-{orphan_digest}"
    )
    assert result["attempt"] == 1
    assert archive.is_dir()
    assert (archive / "editorial-ja.json").read_bytes() == old_bytes
    decision = json.loads(
        (run / "gates" / "quality-self-heal-attempt-1.json").read_text()
    )
    assert decision["attempt"] == 1
    snapshot = run / "gates" / "quality-attempt-1"
    assert {
        path.name for path in snapshot.iterdir()
    } == {
        "editorial-ja.json",
        "editorial-en.json",
        "reader-testing-gate-ja.terminal.json",
        "reader-testing-gate-en.terminal.json",
        "identity-ja.json",
        "identity-en.json",
    }


def test_orphan_quality_snapshot_rejects_symlink(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside\n")
    (partial / "editorial-ja.json").symlink_to(outside)

    with pytest.raises(QUALITY.QualitySelfHealError, match="symlink"):
        QUALITY.assess(run, drafts)
    assert (partial / "editorial-ja.json").is_symlink()
    assert not (run / "gates" / "quality-self-heal-attempt-1.json").exists()


def test_orphan_quality_snapshot_rejects_nonregular_file(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    os.mkfifo(partial / "receipt.pipe")

    with pytest.raises(QUALITY.QualitySelfHealError, match="non-regular"):
        QUALITY.assess(run, drafts)
    assert (partial / "receipt.pipe").exists()


def test_orphan_quality_snapshot_collision_preserves_evidence(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    old_bytes = b"collision evidence\n"
    (partial / "editorial-ja.json").write_bytes(old_bytes)
    orphan_digest = _orphan_digest("editorial-ja.json", old_bytes)
    target = run / "gates" / "quality-attempt-orphans" / f"attempt-1-{orphan_digest}"
    target.mkdir(parents=True)
    marker = target / "marker"
    marker.write_bytes(b"existing archive\n")

    with pytest.raises(QUALITY.QualitySelfHealError, match="collision"):
        QUALITY.assess(run, drafts)
    assert (partial / "editorial-ja.json").read_bytes() == old_bytes
    assert marker.read_bytes() == b"existing archive\n"


def test_orphan_quality_snapshot_same_digest_gets_next_occurrence(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    old_bytes = b"repeatable orphan evidence\n"
    (partial / "editorial-ja.json").write_bytes(old_bytes)
    orphan_digest = _orphan_digest("editorial-ja.json", old_bytes)
    archive_root = run / "gates" / "quality-attempt-orphans"
    existing = archive_root / f"attempt-1-{orphan_digest}"
    existing.mkdir(parents=True)
    (existing / "editorial-ja.json").write_bytes(old_bytes)

    result = QUALITY.assess(run, drafts)

    second = archive_root / f"attempt-1-{orphan_digest}-2"
    assert result["attempt"] == 1
    assert (existing / "editorial-ja.json").read_bytes() == old_bytes
    assert (second / "editorial-ja.json").read_bytes() == old_bytes
    assert (run / "gates" / "quality-attempt-1").is_dir()
    assert (run / "gates" / "quality-self-heal-attempt-1.json").is_file()


def test_orphan_snapshot_no_replace_race_advances_occurrence(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    old_bytes = b"raced orphan evidence\n"
    (partial / "editorial-ja.json").write_bytes(old_bytes)
    orphan_digest = _orphan_digest("editorial-ja.json", old_bytes)
    archive_root = run / "gates" / "quality-attempt-orphans"
    raced = archive_root / f"attempt-1-{orphan_digest}"
    calls = 0
    real_rename = getattr(QUALITY, "_rename_no_replace", None)

    def compete(source, target):
        nonlocal calls
        calls += 1
        if calls == 1:
            raced.mkdir(parents=True)
            (raced / "editorial-ja.json").write_bytes(old_bytes)
            raise FileExistsError(target)
        assert real_rename is not None
        return real_rename(source, target)

    monkeypatch.setattr(QUALITY, "_rename_no_replace", compete, raising=False)

    result = QUALITY.assess(run, drafts)

    second = archive_root / f"attempt-1-{orphan_digest}-2"
    assert calls == 2
    assert result["attempt"] == 1
    assert (raced / "editorial-ja.json").read_bytes() == old_bytes
    assert (second / "editorial-ja.json").read_bytes() == old_bytes
    assert partial.is_dir()
    assert (partial / "editorial-en.json").is_file()


def test_orphan_snapshot_no_replace_race_with_different_digest_fails_closed(
    tmp_path, monkeypatch
):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    old_bytes = b"raced source evidence\n"
    (partial / "editorial-ja.json").write_bytes(old_bytes)
    orphan_digest = _orphan_digest("editorial-ja.json", old_bytes)
    archive_root = run / "gates" / "quality-attempt-orphans"
    raced = archive_root / f"attempt-1-{orphan_digest}"

    def compete(_source, target):
        raced.mkdir(parents=True)
        (raced / "different").write_bytes(b"not the same archive\n")
        raise FileExistsError(target)

    monkeypatch.setattr(QUALITY, "_rename_no_replace", compete, raising=False)

    with pytest.raises(QUALITY.QualitySelfHealError, match="collision"):
        QUALITY.assess(run, drafts)
    assert (partial / "editorial-ja.json").read_bytes() == old_bytes
    assert (raced / "different").read_bytes() == b"not the same archive\n"


def test_orphan_quality_snapshot_scan_error_fails_closed(tmp_path, monkeypatch):
    run, drafts, partial = _orphan_fixture(tmp_path, monkeypatch)
    (partial / "editorial-ja.json").write_bytes(b"unreadable\n")
    real_scandir = QUALITY.os.scandir

    def fail_scan(path):
        if Path(path) == partial:
            raise PermissionError("scan denied")
        return real_scandir(path)

    monkeypatch.setattr(QUALITY.os, "scandir", fail_scan)
    with pytest.raises(QUALITY.QualitySelfHealError, match="not readable"):
        QUALITY.assess(run, drafts)
    assert (partial / "editorial-ja.json").read_bytes() == b"unreadable\n"


def test_advisory_quality_requires_force_marker_before_init(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    _write_advisory_terminals(run, drafts)
    with pytest.raises(RESUME.InvariantError, match="single-evaluation force receipt"):
        RESUME.require_quality_terminals(run, drafts)
    state = _advance_to_force(run, monkeypatch)
    _write_advisory_terminals(run, state["drafts"])
    receipts = RESUME.require_quality_terminals(run, state["drafts"])
    assert receipts["ja"]["editorial_gate"] == "ADVISORY"


def test_force_receipt_rejects_tampered_receipt(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    state = _advance_to_force(run, monkeypatch)
    drafts = state["drafts"]
    receipt = run / "gates" / "quality-self-heal-attempt-1.json"
    value = json.loads(receipt.read_text())
    value["receipt_sha256"] = "0" * 64
    _write(receipt, value)
    assert not QUALITY.validate_force_receipt(run, drafts)


def test_same_draft_cannot_consume_another_quality_iteration(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    QUALITY.assess(run, drafts)
    _record_invocation(run, 2, 1)
    with pytest.raises(QUALITY.QualitySelfHealError, match="rewrite the draft"):
        QUALITY.assess(run, drafts)


def test_failed_feedback_invocation_is_archived_before_retry(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    QUALITY.assess(run, drafts)
    state = {
        "prompt_sha256": hashlib.sha256(b"prompt").hexdigest(),
        "feedback_sha256": hashlib.sha256(b"plan").hexdigest(),
    }
    RECOVERY._record_feedback_invocation(run, state, recovery_attempt=1, owner_pid=12001)
    RECOVERY._record_feedback_invocation(run, state, recovery_attempt=2, owner_pid=12002)
    canonical = json.loads(
        (run / "gates/quality-feedback-invocation-attempt-2.json").read_text()
    )
    assert canonical["recovery_attempt"] == 2
    archived = run / "gates/quality-feedback-invocation-attempt-2-recovery-1.json"
    assert archived.is_file()
    assert json.loads(archived.read_text())["recovery_attempt"] == 1


def test_force_receipt_bypasses_stale_feedback_defect(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    QUALITY.assess(run, drafts)
    prompt = run / "gates" / "quality-feedback-recovery" / "prompt.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("recover", encoding="utf-8")
    _write(run / "gates" / RECOVERY.STATE_NAME, {
        "version": 1,
        "status": "terminal-blocked",
        "run_id": run.name,
        "attempts": 10,
        "prompt_path": str(prompt),
        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
    })
    hashes = {
        lang: hashlib.sha256(drafts[lang].read_bytes()).hexdigest()
        for lang in ("ja", "en")
    }
    _write(run / "gates" / "quality-feedback-recovery-defect.json", {
        "version": 2,
        "status": "blocked",
        "run_id": run.name,
        "scope": "bounded-feedback-recovery",
        "quality_attempt": 1,
        "draft_sha256": hashes,
        "observations": [{"return_code": 75}],
        "preserved_invariants": {
            "publication_or_staging_performed": False,
            "feedback_consumption_verification": "PASS",
            "identity": {"ja": "PASS", "en": "PASS"},
            "reader": {"ja": "PASS", "en": "PASS"},
            "cta": {"ja": "PASS", "en": "PASS"},
        },
        "required_safe_next_action": "rerun gates",
    })
    ledger = run / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    ready = RECOVERY.plan(run, ledger)
    assert ready["reason"] == "terminal-quality-publication-handoff"
    bad = json.loads(
        (run / "gates" / "quality-feedback-recovery-defect.json").read_text()
    )
    bad["run_id"] = "other-run"
    _write(run / "gates" / "quality-feedback-recovery-defect.json", bad)
    assert RECOVERY.plan(run, ledger)["reason"] == (
        "terminal-quality-publication-handoff"
    )


def test_reopen_rejects_symlinked_draft(tmp_path, monkeypatch):
    run = _quality_fixture(tmp_path)
    monkeypatch.setenv("ARTICLE_PUBLICATION_POLICY", "continuous")
    drafts = _set_quality_gates(run, 1)
    QUALITY.assess(run, drafts)
    prompt = run / "gates" / "quality-feedback-recovery" / "prompt.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("recover", encoding="utf-8")
    hashes = {
        lang: hashlib.sha256(drafts[lang].read_bytes()).hexdigest()
        for lang in ("ja", "en")
    }
    _write(run / "gates" / RECOVERY.STATE_NAME, {
        "version": 1, "status": "terminal-blocked", "run_id": run.name,
        "attempts": 10, "prompt_path": str(prompt),
        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
    })
    _write(run / "gates" / "quality-feedback-recovery-defect.json", {
        "version": 2, "status": "blocked", "run_id": run.name,
        "scope": "bounded-feedback-recovery", "quality_attempt": 1,
        "draft_sha256": hashes, "observations": [{"return_code": 75}],
        "preserved_invariants": {
            "publication_or_staging_performed": False,
            "feedback_consumption_verification": "PASS",
            "identity": {"ja": "PASS", "en": "PASS"},
            "reader": {"ja": "PASS", "en": "PASS"},
            "cta": {"ja": "PASS", "en": "PASS"},
        },
        "required_safe_next_action": "rerun gates",
    })
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    drafts["ja"].unlink()
    drafts["ja"].symlink_to(outside)
    ledger = run / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert RECOVERY.plan(run, ledger)["status"] == "REFUSED"
