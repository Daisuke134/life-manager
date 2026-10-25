import datetime as dt
import hashlib
import json
import os
import stat
import sys
import types
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capafy_distribute_fence_reconcile as rec  # noqa: E402

Q = dt.datetime(2026, 9, 29, 8, 0, tzinfo=dt.timezone.utc)
OCC = "capafy-distribute-daily:run-1"
EXPECTED_SLUG = "capafy-x-2026-09-29-h15"


def proof(now_min, commits, x, status=200):
    return rec.build_proof(OCC, Q, started_at=Q, expected_slug=EXPECTED_SLUG,
                           now=Q + dt.timedelta(minutes=now_min),
                           commits=commits, x_posts=x, page_status_fn=lambda slug: status)


def test_live_landing_commit_is_effected():
    p = proof(10, {"ok": True, "commits": [{"sha": "abc", "slug": "capafy-x-2026-09-29-h15"}]},
              {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] and "abc" in p["provider_receipt_id"]


def test_effect_proof_writes_runtime_accepted_writer_receipt(tmp_path, monkeypatch):
    from runtime.loop.lm_loop_run import _verified_terminal_effect_result

    sha = "d2a734607fc85c0fde294243f4085401dcc8fb0f"
    slug = "capafy-x-2026-09-29-h21m00"
    url = f"https://aniccaai.com/blog/{slug}"
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug, slot="2026-09-29-h21m00")
    monkeypatch.setattr(rec, "occurrence_queued_at", lambda _occurrence: Q)
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [{"sha": sha, "slug": slug}],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {
        "ok": True, "posts": [],
    })
    monkeypatch.setattr(rec, "page_status", lambda checked_slug: 200 if checked_slug == slug else 404)
    hint = tmp_path / "entrypoint-result.json"

    proof = rec.write_result_hint(OCC, hint)
    assert proof["hint_written"] is True
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600
    entrypoint = "skills/earn/capafy-marketing/capafy-distribute-daily.sh"
    result = _verified_terminal_effect_result(hint, rec.OWNER_ID, OCC, entrypoint)
    assert result == ("reconciled", f"writer://runs/{sha}", url)


def test_success_hint_ignores_untrusted_event_and_manifest_path_overrides(
        tmp_path, monkeypatch):
    occurrence_id = "capafy-distribute-daily:override-attempt"
    started = Q + dt.timedelta(hours=4)
    canonical_slug = "capafy-x-2026-09-29-h21m00"
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    occurrence_run(canonical_root, monkeypatch, occurrence_id, started, canonical_slug)
    canonical_events = rec.EVENTS_PATH
    canonical_runs = rec.RUNS_ROOT
    canonical_occurrences = rec.OCCURRENCES_ROOT

    attacker_slug = "capafy-x-2026-09-29-h22m00"
    attacker_root = tmp_path / "attacker"
    attacker_root.mkdir()
    occurrence_run(attacker_root, monkeypatch, occurrence_id, started, attacker_slug,
                   slot="2026-09-29-h22m00")
    monkeypatch.setattr(rec, "EVENTS_PATH", canonical_events)
    monkeypatch.setattr(rec, "RUNS_ROOT", canonical_runs)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", canonical_occurrences)
    monkeypatch.setattr(rec, "occurrence_queued_at", lambda _occurrence: started)
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [{"sha": "c" * 40, "slug": attacker_slug}],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {"ok": True, "posts": []})
    monkeypatch.setattr(rec, "page_status", lambda slug: 200 if slug == attacker_slug else 404)

    hint = tmp_path / "attacker-result.json"
    proof = rec.write_result_hint(occurrence_id, hint)
    assert proof["hint_written"] is False
    assert not hint.exists()


def test_success_hint_rejects_queue_timestamp_after_execute_start(tmp_path, monkeypatch):
    occurrence_id = "capafy-distribute-daily:future-queue"
    started = Q + dt.timedelta(hours=4)
    slug = "capafy-x-2026-09-29-h21m00"
    occurrence_run(tmp_path, monkeypatch, occurrence_id, started, slug)
    monkeypatch.setattr(rec, "occurrence_queued_at", lambda _occurrence: (
        started + dt.timedelta(hours=1)))
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [{"sha": "d" * 40, "slug": slug}],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {"ok": True, "posts": []})
    monkeypatch.setattr(rec, "page_status", lambda checked_slug: 200 if checked_slug == slug else 404)

    hint = tmp_path / "future-queue-result.json"
    proof = rec.write_result_hint(occurrence_id, hint)
    assert proof["hint_written"] is False
    assert not hint.exists()


def test_expected_slug_ignores_model_writable_run_directory_manifest(tmp_path, monkeypatch):
    occurrence_id = "capafy-distribute-daily:writer-canary"
    trusted_slug = "capafy-x-2026-09-29-h21m00"
    trusted_root = tmp_path / "occurrences"
    trusted_root.mkdir(mode=0o700)
    rec.record_occurrence_manifest(
        trusted_root / "writer-canary.json",
        owner_id=rec.OWNER_ID,
        run_id="writer-canary",
        occurrence_id=occurrence_id,
        slot="2026-09-29-h21m00",
        article_slug=trusted_slug,
    )

    attacker_root = tmp_path / "writer-workspace"
    attacker_root.mkdir()
    occurrence_run(
        attacker_root,
        monkeypatch,
        occurrence_id,
        Q + dt.timedelta(hours=4),
        "capafy-x-2026-09-29-h22m00",
        slot="2026-09-29-h22m00",
    )
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", trusted_root, raising=False)

    assert rec.expected_article_slug(occurrence_id) == trusted_slug


def test_occurrence_manifest_cannot_be_overwritten(tmp_path):
    path = tmp_path / "occurrences" / "writer-canary.json"
    original = rec.record_occurrence_manifest(
        path,
        owner_id=rec.OWNER_ID,
        run_id="writer-canary",
        occurrence_id="capafy-distribute-daily:writer-canary",
        slot="2026-09-29-h21m00",
        article_slug="capafy-x-2026-09-29-h21m00",
    )
    try:
        rec.record_occurrence_manifest(
            path,
            owner_id=rec.OWNER_ID,
            run_id="writer-canary",
            occurrence_id="capafy-distribute-daily:writer-canary",
            slot="2026-09-29-h22m00",
            article_slug="capafy-x-2026-09-29-h22m00",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("an occurrence binding was overwritten")
    assert json.loads(path.read_text()) == original


def test_no_effect_hint_is_exactly_bound_to_already_published_slot(tmp_path, monkeypatch):
    from runtime.loop.lm_loop_run import _verified_terminal_effect_result

    slot = "2026-09-29-h17m00"
    occurrence_run(
        tmp_path, monkeypatch, OCC, Q, "capafy-x-2026-09-29-h17m00", slot=slot,
    )
    state_dir = tmp_path / "capafy-state"
    state_dir.mkdir()
    ledger = state_dir / "ledger.json"
    ledger.write_text(json.dumps({slot: {"status": "published"}}))
    ledger.chmod(0o600)
    monkeypatch.setattr(rec, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(rec, "LEDGER_PATH", ledger)
    hint = tmp_path / "entrypoint-result.json"
    entrypoint = "skills/earn/capafy-marketing/capafy-distribute-daily.sh"
    assert rec.write_no_effect_result_hint(OCC, hint, "daily_limit_reached", slot)
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600
    assert _verified_terminal_effect_result(hint, rec.OWNER_ID, OCC, entrypoint) == (
        "not_applicable", f"lm-no-effect://{rec.OWNER_ID}/{OCC}/daily_limit_reached")

    forged = tmp_path / "forged.json"
    assert not rec.write_no_effect_result_hint(
        "other-owner:run-1", forged, "daily_limit_reached", slot)
    assert not forged.exists()
    assert not rec.write_no_effect_result_hint(OCC, forged, "daily_limit_reached", "2026-09-29-h17m30")
    assert not forged.exists()


def test_no_effect_hint_ignores_untrusted_event_and_state_root_overrides(tmp_path, monkeypatch):
    slot = "2026-09-29-h17m00"
    events = tmp_path / "events.jsonl"
    occurrence_run(
        tmp_path, monkeypatch, OCC, Q, "capafy-x-2026-09-29-h17m00", slot=slot,
    )
    state_dir = tmp_path / "canonical-state"
    state_dir.mkdir()
    ledger = state_dir / "ledger.json"
    ledger.write_text(json.dumps({}))
    monkeypatch.setattr(rec, "EVENTS_PATH", events)
    monkeypatch.setattr(rec, "LEDGER_PATH", ledger)

    attacker_state = tmp_path / "attacker-state"
    attacker_state.mkdir()
    (attacker_state / "ledger.json").write_text(
        json.dumps({slot: {"status": "published"}}))
    attacker_events = tmp_path / "attacker-events.jsonl"
    attacker_events.write_text("{}\n")
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_STATE_DIR", str(attacker_state))
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_EVENTS_PATH", str(attacker_events))

    hint = tmp_path / "attacker-result.json"
    assert not rec.write_no_effect_result_hint(OCC, hint, "daily_limit_reached", slot)
    assert not hint.exists()

    ledger.write_text(json.dumps({slot: {"status": "published"}}))
    assert rec.write_no_effect_result_hint(OCC, hint, "daily_limit_reached", slot)


def test_pii_gate_blocked_no_effect_hint_does_not_mark_slot_published(tmp_path, monkeypatch):
    from runtime.loop.lm_loop_run import write_capafy_pii_gate_attestation

    slot = "2026-09-29-h17m00"
    occurrence_run(tmp_path, monkeypatch, OCC, Q, "capafy-x-2026-09-29-h17m00", slot=slot)
    state_dir = tmp_path / "canonical-state"
    state_dir.mkdir()
    ledger = state_dir / "ledger.json"
    ledger.write_text(json.dumps({}))
    monkeypatch.setattr(rec, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(rec, "LEDGER_PATH", ledger)
    hint = tmp_path / "entrypoint-result.json"

    # A bare CLI reason is not evidence that the trusted wrapper ran the gate.
    assert rec.main([
        "--occurrence", OCC, "--result-hint", str(hint),
        "--no-effect-reason", "pii_gate_blocked", "--slot", slot,
    ]) == 1
    assert not hint.exists()

    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", rec.OWNER_ID)
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", OCC)
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    assert write_capafy_pii_gate_attestation(hint, OCC, slot, gate_exit_code=3)
    assert rec.write_no_effect_result_hint(OCC, hint, "pii_gate_blocked", slot)
    assert json.loads(ledger.read_text()).get(slot) is None
    assert json.loads(hint.read_text()) == {
        "schema_version": 1,
        "kind": "life_manager_no_effect_result",
        "status": "verified_no_effect",
        "effect": 0,
        "owner_id": rec.OWNER_ID,
        "occurrence_id": OCC,
        "reason": "pii_gate_blocked",
        "slot": slot,
    }


def test_pii_gate_attestation_is_exact_private_and_exclusive(tmp_path, monkeypatch):
    from runtime.loop.lm_loop_run import write_capafy_pii_gate_attestation

    slot = "2026-09-29-h17m00"
    occurrence_run(tmp_path, monkeypatch, OCC, Q, "capafy-x-2026-09-29-h17m00", slot=slot)
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", rec.OWNER_ID)
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", OCC)
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    assert not write_capafy_pii_gate_attestation(
        hint, "capafy-distribute-daily:other", slot, gate_exit_code=3)
    attestation = hint.with_name("capafy-pii-gate-attestation.json")
    assert not attestation.exists()
    assert not write_capafy_pii_gate_attestation(hint, OCC, slot, gate_exit_code=0)
    assert not attestation.exists()
    assert write_capafy_pii_gate_attestation(hint, OCC, slot, gate_exit_code=3)
    assert stat.S_IMODE(attestation.stat().st_mode) == 0o600
    assert not write_capafy_pii_gate_attestation(hint, OCC, slot, gate_exit_code=3)

    value = json.loads(attestation.read_text())
    value["provider_phase"] = "publish_started"
    attestation.write_text(json.dumps(value))
    attestation.chmod(0o600)
    forged_hint = tmp_path / "forged-result.json"
    assert not rec.write_no_effect_result_hint(OCC, forged_hint, "pii_gate_blocked", slot)
    assert not forged_hint.exists()


def test_forged_proof_dictionary_is_not_a_writer_api_and_existing_hint_is_never_overwritten(
        tmp_path, monkeypatch):
    prove_occurrence = rec.prove_occurrence
    hint = tmp_path / "entrypoint-result.json"
    forged = {"owner_id": rec.OWNER_ID, "occurrence_id": OCC,
              "verified": True, "effected": True,
              "proof_kind": "official_github_landing_commit_and_live_page",
              "expected_slug": "x",
              "provider_receipt_id": "github:" + "a" * 40 + "|https://aniccaai.com/blog/x"}
    monkeypatch.setattr(rec, "prove_occurrence", lambda _occurrence: (_ for _ in ()).throw(
        AssertionError("invalid occurrence must fail before official readback")))
    assert rec.write_result_hint(forged, hint)["hint_written"] is False
    assert not hint.exists()

    slug = "capafy-x-2026-09-29-h15m00"
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug, slot="2026-09-29-h15m00")
    monkeypatch.setattr(rec, "prove_occurrence", prove_occurrence)
    monkeypatch.setattr(rec, "occurrence_queued_at", lambda _occurrence: Q)
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [{"sha": "a" * 40, "slug": slug}],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {"ok": True, "posts": []})
    monkeypatch.setattr(rec, "page_status", lambda _slug: 200)
    hint.write_text("existing\n")
    assert rec.write_result_hint(OCC, hint)["hint_written"] is False
    assert hint.read_text() == "existing\n"


def test_result_hint_cli_returns_success_only_after_writing_verified_proof(
        tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    slug = "capafy-x-2026-09-29-h15m00"
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug, slot="2026-09-29-h15m00")
    monkeypatch.setattr(rec, "occurrence_queued_at", lambda _occurrence: Q)
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [{"sha": "b" * 40, "slug": slug}],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {"ok": True, "posts": []})
    monkeypatch.setattr(rec, "page_status", lambda checked_slug: 200 if checked_slug == slug else 404)

    assert rec.main(["--occurrence", OCC, "--result-hint", str(hint)]) == 0
    assert json.loads(hint.read_text())["provider_receipt_id"] == "b" * 40

    held_hint = tmp_path / "held-result.json"
    monkeypatch.setattr(rec, "read_landing_commits", lambda _start, _end: {
        "ok": True, "commits": [],
    })
    monkeypatch.setattr(rec, "read_x_posts", lambda _start, _end: {
        "ok": True, "posts": ["unexpected-post"],
    })
    assert rec.main(["--occurrence", OCC, "--result-hint", str(held_hint)]) == 1
    assert not held_hint.exists()


def test_commit_without_live_page_stays_fenced():
    p = proof(200, {"ok": True, "commits": [{"sha": "abc", "slug": EXPECTED_SLUG}]},
              {"ok": True, "posts": []}, status=404)
    assert not p["verified"]


def test_no_commit_too_recent_stays_fenced():
    assert not proof(30, {"ok": True, "commits": []}, {"ok": True, "posts": []})["verified"]


def test_no_commit_no_post_after_window_is_no_effect():
    p = proof(200, {"ok": True, "commits": []}, {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] is False


def pre_provider_prompt_failure(tmp_path, monkeypatch, *, release_sha=None, error_detail=None,
                                event_occurrence_id=None, duplicate_failure=False):
    occurrence_id = "capafy-distribute-daily:18e077fbebd96ce8-96969"
    run_id = occurrence_id.rsplit(":", 1)[1]
    started = dt.datetime(2026, 10, 21, 6, 36, 15, 594033, tzinfo=dt.timezone.utc)
    events_path = tmp_path / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "event_id": "pre-provider-start",
            "owner_id": rec.OWNER_ID,
            "loop_id": rec.OWNER_ID,
            "job_id": rec.OWNER_ID,
            "run_id": run_id,
            "occurrence_id": occurrence_id,
            "phase": "execute",
            "status": "running",
            "timestamp": started.isoformat(),
            "release_sha": release_sha or "70c93940bc712261f3dd01aa9556b467b1481539",
            "effect_class": "publish",
            "effect_status": "started",
            "provider_receipt_id": None,
            "official_readback_ref": None,
        },
        {
            "event_id": "pre-provider-fail",
            "owner_id": rec.OWNER_ID,
            "loop_id": rec.OWNER_ID,
            "job_id": rec.OWNER_ID,
            "run_id": run_id,
            "occurrence_id": occurrence_id,
            "phase": "report",
            "status": "fail",
            "timestamp": "2026-10-21T06:36:20.522605+00:00",
            "release_sha": release_sha or "70c93940bc712261f3dd01aa9556b467b1481539",
            "effect_class": "publish",
            "effect_status": "unknown",
            "effect_identity_status": "not_written",
            "failure_layer": "entrypoint",
            "error_class": "entrypoint_exit_1",
            "error_detail": error_detail or "line 237: CRAFT_GUIDANCE: unbound variable",
            "exit_code": 1,
            "provider_receipt_id": None,
            "official_readback_ref": None,
        },
    ]
    if event_occurrence_id is not None:
        for row in rows:
            row["occurrence_id"] = event_occurrence_id
    if duplicate_failure:
        rows[-1]["event_id"] = rows[0]["event_id"]
    events_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(rec, "EVENTS_PATH", events_path)
    return occurrence_id, started


def reconcile_pre_provider_prompt_failure(
    tmp_path, monkeypatch, posts, *, age_seconds=None, release_sha=None, error_detail=None,
    event_occurrence_id=None, duplicate_failure=False,
):
    occurrence_id, started = pre_provider_prompt_failure(
        tmp_path, monkeypatch, release_sha=release_sha, error_detail=error_detail,
        event_occurrence_id=event_occurrence_id, duplicate_failure=duplicate_failure,
    )
    return rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=age_seconds or rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": True, "posts": posts},
        started_at_fn=lambda _occurrence: started,
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        model_no_response_fn=lambda _started, _slot: None,  # never read the developer's real daily log
    )


def test_exact_pre_provider_failure_excludes_only_its_known_postiz_post(tmp_path, monkeypatch):
    result = reconcile_pre_provider_prompt_failure(
        tmp_path, monkeypatch, ["cmvhqvaid0429oh0ywbv95g8r"]
    )

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["proof_kind"] == "official_github_postiz_window_after_pre_provider_prompt_failure"
    assert result["excluded_postiz_post_ids"] == ["cmvhqvaid0429oh0ywbv95g8r"]


def test_exact_pre_provider_failure_keeps_any_other_postiz_post_fenced(tmp_path, monkeypatch):
    result = reconcile_pre_provider_prompt_failure(
        tmp_path, monkeypatch, ["cmvhqvaid0429oh0ywbv95g8r", "unknown-post"]
    )

    assert result["verified"] is False
    assert result["reason"] == "x_post_without_article"


def test_exact_pre_provider_failure_keeps_other_preexisting_post_fenced(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {
            "ok": True,
            "posts": ["cmvhqvaid0429oh0ywbv95g8r"],
            "preexisting_posts": [{"post_id": "other-post", "receipt_path": "/receipt"}],
        },
        started_at_fn=lambda _occurrence: started,
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        model_no_response_fn=lambda _started, _slot: None,  # never read the developer's real daily log
    )

    assert result["verified"] is False
    assert result["reason"] == "x_post_without_article"


def test_exact_pre_provider_failure_still_waits_for_full_effect_window(tmp_path, monkeypatch):
    result = reconcile_pre_provider_prompt_failure(
        tmp_path,
        monkeypatch,
        ["cmvhqvaid0429oh0ywbv95g8r"],
        age_seconds=rec.NO_EFFECT_MIN_AGE_SECONDS - 1,
    )

    assert result["verified"] is False
    assert result["reason"].startswith("too_recent:")


def test_pre_provider_post_exclusion_requires_exact_release_and_error(tmp_path, monkeypatch):
    for i, (release_sha, error_detail) in enumerate((
        ("f" * 40, "line 237: CRAFT_GUIDANCE: unbound variable"),
        ("70c93940bc712261f3dd01aa9556b467b1481539", "unrelated entrypoint failure"),
    )):
        result = reconcile_pre_provider_prompt_failure(
            tmp_path / str(i), monkeypatch, ["cmvhqvaid0429oh0ywbv95g8r"],
            release_sha=release_sha, error_detail=error_detail,
        )

        assert result["verified"] is False
        assert result["reason"] == "x_post_without_article"


def test_pre_provider_post_exclusion_rejects_wrong_occurrence_events(tmp_path, monkeypatch):
    result = reconcile_pre_provider_prompt_failure(
        tmp_path, monkeypatch, ["cmvhqvaid0429oh0ywbv95g8r"],
        event_occurrence_id="capafy-distribute-daily:other-run",
    )

    assert result["verified"] is False
    assert result["reason"] == "x_post_without_article"


def test_pre_provider_post_exclusion_rejects_duplicate_event_id(tmp_path, monkeypatch):
    result = reconcile_pre_provider_prompt_failure(
        tmp_path, monkeypatch, ["cmvhqvaid0429oh0ywbv95g8r"], duplicate_failure=True
    )

    assert result["verified"] is False
    assert result["reason"] == "x_post_without_article"


def test_pre_provider_failure_with_matching_landing_commit_is_effected(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    commit = {"sha": "a" * 40, "slug": "youtube-outro-script"}
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": [commit]},
        x_fn=lambda _start, _end: {"ok": True, "posts": ["cmvhqvaid0429oh0ywbv95g8r"]},
        page_status_fn=lambda _slug: 200,
        started_at_fn=lambda _occurrence: started,
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        model_no_response_fn=lambda _started, _slot: None,  # never read the developer's real daily log
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"].startswith(f"github:{'a' * 40}|")


def test_pre_provider_failure_with_other_landing_commit_stays_fenced(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    commit = {"sha": "b" * 40, "slug": "other-capafy-article"}
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": [commit]},
        x_fn=lambda _start, _end: {"ok": True, "posts": ["cmvhqvaid0429oh0ywbv95g8r"]},
        started_at_fn=lambda _occurrence: started,
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        model_no_response_fn=lambda _started, _slot: None,  # never read the developer's real daily log
    )

    assert result["verified"] is False
    assert result["reason"] == "landing_commit_in_window_during_pre_provider_failure"


def test_pre_provider_failure_keeps_fence_on_postiz_readback_failure(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": False, "reason": "postiz_readback_failed"},
        started_at_fn=lambda _occurrence: started,
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        model_no_response_fn=lambda _started, _slot: None,  # never read the developer's real daily log
    )

    assert result["verified"] is False
    assert result["reason"] == "postiz_readback_failed"


def test_resolve_persists_provider_readback_snapshot_before_closing(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    occurrences_root = tmp_path / "occurrences"
    occurrences_root.mkdir(mode=0o700)
    occurrences_root.chmod(0o700)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", occurrences_root)
    resolved_proof = {}
    postiz_row = {
        "id": "cmvhqvaid0429oh0ywbv95g8r",
        "integration": {"id": rec.X_INTEGRATION_ID},
        "status": "PUBLISHED",
        "content": "Unrelated eBook case-study CTA",
        "publishDate": "2026-10-21T06:41:00.000Z",
        "nativeId": "2112796610917003351",
    }
    original_fsync = os.fsync
    fsynced_directory = False

    def record_fsync(descriptor):
        nonlocal fsynced_directory
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            fsynced_directory = True
        return original_fsync(descriptor)

    monkeypatch.setattr(rec.os, "fsync", record_fsync)

    def resolve_fn(_owner, _occurrence, *, official_readback, expected_state):
        assert fsynced_directory is True
        resolved_proof.update(official_readback())
        assert expected_state == "claimed"
        return True

    result = rec.reconcile(
        occurrence_id,
        resolve=True,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {
            "ok": True,
            "posts": ["cmvhqvaid0429oh0ywbv95g8r"],
            "integration_posts": [postiz_row],
        },
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        started_at_fn=lambda _occurrence: started,
        resolve_fn=resolve_fn,
    )

    snapshot_path = Path(result["official_readback_ref"])
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    assert result["closed"] is True
    assert result["readback_snapshot_sha256"] == hashlib.sha256(snapshot_bytes).hexdigest()
    expected_event_ref = f"{rec.EVENTS_PATH}#event_id=pre-provider-fail"
    assert result["evidence_refs"] == [str(snapshot_path), expected_event_ref]
    assert resolved_proof["official_readback_ref"] == str(snapshot_path)
    assert snapshot["github"]["landing_commits"] == []
    assert snapshot["postiz"]["matching_post_ids"] == ["cmvhqvaid0429oh0ywbv95g8r"]
    assert snapshot["postiz"]["integration_posts"] == [postiz_row]
    assert snapshot["excluded_postiz_post_ids"] == ["cmvhqvaid0429oh0ywbv95g8r"]
    assert snapshot["pre_provider_failure_event_id"] == "pre-provider-fail"
    assert snapshot["pre_provider_failure_event_ref"] == expected_event_ref
    assert snapshot_path.stat().st_mode & 0o777 == 0o600
    assert occurrences_root.stat().st_mode & 0o777 == 0o700


def test_resolve_does_not_close_if_readback_snapshot_cannot_be_persisted(tmp_path, monkeypatch):
    occurrence_id, started = pre_provider_prompt_failure(tmp_path, monkeypatch)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", tmp_path / "missing-occurrences")
    resolve_calls = []
    result = rec.reconcile(
        occurrence_id,
        resolve=True,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": True, "posts": ["cmvhqvaid0429oh0ywbv95g8r"]},
        expected_slug_fn=lambda _occurrence: "youtube-outro-script",
        started_at_fn=lambda _occurrence: started,
        resolve_fn=lambda *_args, **_kwargs: resolve_calls.append(True) or True,
    )

    assert result["verified"] is False
    assert result["reason"] == "readback_snapshot_persist_failed"
    assert resolve_calls == []


def test_legacy_missing_binding_requires_complete_empty_official_window(tmp_path, monkeypatch):
    occurrence_id = "capafy-distribute-daily:legacy-run"
    started = Q + dt.timedelta(hours=4)
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps({
        "owner_id": rec.OWNER_ID,
        "run_id": "legacy-run",
        "occurrence_id": occurrence_id,
        "phase": "execute",
        "status": "running",
        "timestamp": started.isoformat(),
    }) + "\n")
    monkeypatch.setattr(rec, "EVENTS_PATH", events)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", tmp_path / "missing-occurrences")
    commits = {"ok": True, "commits": []}
    posts = {"ok": True, "posts": []}

    def reconcile(now, commits_result=commits, posts_result=posts,
                  page_status_fn=lambda _slug: 200):
        return rec.reconcile(
            occurrence_id,
            now=now,
            fenced_row_fn=lambda *_args: ("claimed", started - dt.timedelta(seconds=1)),
            commits_fn=lambda *_args: commits_result,
            x_fn=lambda *_args: posts_result,
            page_status_fn=page_status_fn,
        )

    early = reconcile(started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS - 1))
    assert early["verified"] is False
    assert early["reason"].startswith("too_recent:")

    effect_possible = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        {"ok": True, "commits": [{
            "sha": "e" * 40,
            "slug": "capafy-x-2026-09-29-h21m00",
            "at": (started + dt.timedelta(minutes=5)).isoformat(),
        }]},
    )
    assert effect_possible["verified"] is True
    assert effect_possible["effected"] is True
    assert effect_possible["proof_kind"] == "official_unique_capafy_commit_and_live_page_for_legacy_occurrence"
    assert effect_possible["provider_receipt_id"] == (
        f"github:{'e' * 40}|https://aniccaai.com/blog/capafy-x-2026-09-29-h21m00")

    article_commit = {"ok": True, "commits": [{
        "sha": "e" * 40,
        "slug": "capafy-x-2026-09-29-h21m00",
        "at": (started + dt.timedelta(minutes=5)).isoformat(),
    }]}
    post_possible = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        article_commit,
        posts_result={"ok": True, "posts": ["unknown-post"]},
    )
    assert post_possible["verified"] is False
    assert post_possible["reason"] == "x_post_in_window_without_occurrence_manifest"

    post_readback_failed = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        article_commit,
        posts_result={"ok": False, "reason": "postiz_unavailable"},
    )
    assert post_readback_failed["verified"] is False
    assert post_readback_failed["reason"] == "postiz_unavailable"

    ambiguous = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        {"ok": True, "commits": [
            {"sha": "f" * 40, "slug": "capafy-x-2026-09-29-h21m00",
             "at": (started + dt.timedelta(minutes=5)).isoformat()},
            {"sha": "1" * 40, "slug": "tiktok-hook-generator-free",
             "at": (started + dt.timedelta(minutes=6)).isoformat()},
        ]},
    )
    assert ambiguous["verified"] is False
    assert ambiguous["reason"] == "ambiguous_legacy_capafy_commits"

    page_unavailable = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        {"ok": True, "commits": [{
            "sha": "e" * 40,
            "slug": "capafy-x-2026-09-29-h21m00",
            "at": (started + dt.timedelta(minutes=5)).isoformat(),
        }]},
        page_status_fn=lambda _slug: 404,
    )
    assert page_unavailable["verified"] is False
    assert page_unavailable["reason"] == "legacy_capafy_commit_without_live_page"

    post_possible = reconcile(
        started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        posts_result={"ok": True, "posts": ["unknown-post"]},
    )
    assert post_possible["verified"] is False

    empty_window = reconcile(started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1))
    assert empty_window["verified"] is True
    assert empty_window["effected"] is False
    assert empty_window["proof_kind"] == "official_github_postiz_empty_after_legacy_manifest_gap"


def test_x_post_without_article_stays_fenced():
    assert not proof(200, {"ok": True, "commits": []}, {"ok": True, "posts": ["p1"]})["verified"]


def test_readback_failure_stays_fenced():
    assert not proof(200, {"ok": False, "reason": "x"}, {"ok": True, "posts": []})["verified"]


def occurrence_run(tmp_path, monkeypatch, occurrence_id, started, slug, slot="2026-09-29-h21m00"):
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps({
        "owner_id": rec.OWNER_ID,
        "run_id": occurrence_id.rsplit(":", 1)[1],
        "occurrence_id": occurrence_id,
        "phase": "execute",
        "status": "running",
        "timestamp": started.isoformat(),
    }) + "\n")
    runs_root = tmp_path / "runs"
    run_dir = runs_root / f"capafy-distribute-{slot}"
    (run_dir / "gates").mkdir(parents=True)
    occurrences_root = tmp_path / "occurrences"
    rec.record_occurrence_manifest(
        occurrences_root / f"{occurrence_id.rsplit(':', 1)[1]}.json",
        owner_id=rec.OWNER_ID,
        run_id=occurrence_id.rsplit(":", 1)[1],
        occurrence_id=occurrence_id,
        slot=slot,
        article_slug=slug,
    )
    (run_dir / "prompt.txt").write_text(f"Publish this article: https://aniccaai.com/blog/{slug}\n")
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_EVENTS_PATH", str(events))
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr(rec, "EVENTS_PATH", events)
    monkeypatch.setattr(rec, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", occurrences_root)


def test_occurrence_start_rejects_mismatched_owner_or_run_id(tmp_path):
    occurrence_id = "capafy-distribute-daily:delayed-attempt"
    started = Q + dt.timedelta(hours=4)
    events = tmp_path / "events.jsonl"
    for owner_id, run_id in (
        ("line-sticker-distribute", "delayed-attempt"),
        (rec.OWNER_ID, "another-run"),
    ):
        events.write_text(json.dumps({
            "owner_id": owner_id,
            "run_id": run_id,
            "occurrence_id": occurrence_id,
            "phase": "execute",
            "status": "running",
            "timestamp": started.isoformat(),
        }) + "\n")
        try:
            rec.occurrence_started_at(occurrence_id, events)
        except ValueError:
            continue
        raise AssertionError(f"mismatched owner/run identity accepted: {owner_id}/{run_id}")


def test_occurrence_start_rejects_matching_event_with_malformed_timestamp(tmp_path):
    occurrence_id = "capafy-distribute-daily:delayed-attempt"
    started = Q + dt.timedelta(hours=4)
    identity = {
        "owner_id": rec.OWNER_ID,
        "run_id": "delayed-attempt",
        "occurrence_id": occurrence_id,
        "phase": "execute",
        "status": "running",
    }
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({**identity, "timestamp": started.isoformat()}) + "\n"
        + json.dumps({**identity, "timestamp": "not-a-timestamp"}) + "\n"
    )

    try:
        rec.occurrence_started_at(occurrence_id, events)
    except ValueError:
        return
    raise AssertionError("malformed duplicate execute-start event was ignored")


def test_occurrence_start_rejects_malformed_event_rows(tmp_path):
    occurrence_id = "capafy-distribute-daily:run-1"
    valid_start = {
        "owner_id": rec.OWNER_ID,
        "run_id": "run-1",
        "occurrence_id": occurrence_id,
        "phase": "execute",
        "status": "running",
        "timestamp": Q.isoformat(),
    }
    events = tmp_path / "events.jsonl"
    for malformed_row in ('{"owner_id":', json.dumps(["not", "an", "event"])):
        events.write_text(json.dumps(valid_start) + "\n" + malformed_row + "\n")
        try:
            rec.occurrence_started_at(occurrence_id, events)
        except ValueError:
            continue
        raise AssertionError("malformed event row was ignored")


def test_occurrence_manifest_records_exact_runtime_slot(tmp_path):
    occurrence_id = "capafy-distribute-daily:midnight-boundary"
    path = tmp_path / "occurrences/midnight-boundary.json"
    record = rec.record_occurrence_manifest(
        path,
        owner_id=rec.OWNER_ID,
        run_id="midnight-boundary",
        occurrence_id=occurrence_id,
        slot="2026-09-30-h00m00",
        article_slug="capafy-marketing-strategist-2026-09-30-h00m00",
    )

    assert json.loads(path.read_text()) == record
    assert record["slot"] == "2026-09-30-h00m00"
    assert path.stat().st_mode & 0o777 == 0o600


def test_success_proof_uses_exact_parent_occurrence_and_official_landing_receipt(
        tmp_path, monkeypatch):
    started = Q + dt.timedelta(hours=4)
    occurrence_id = "capafy-distribute-daily:parent-run-1"
    slug = "capafy-x-2026-09-29-h21m00"
    occurrence_run(tmp_path, monkeypatch, occurrence_id, started, slug)
    windows = []

    def commits_fn(start, end):
        windows.append((start, end))
        return {"ok": True, "commits": [{"sha": "a" * 40, "slug": slug}]}

    proof = rec.prove_occurrence(
        occurrence_id,
        now=started + dt.timedelta(minutes=5),
        queued_at_fn=lambda _occurrence: Q,
        commits_fn=commits_fn,
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
        page_status_fn=lambda checked_slug: 200 if checked_slug == slug else 404,
    )

    assert windows == [(started, started + dt.timedelta(seconds=rec.MAX_RUN_SECONDS))]
    assert proof["occurrence_id"] == occurrence_id
    assert proof["expected_slug"] == slug
    assert proof["verified"] is True and proof["effected"] is True
    assert proof["provider_receipt_id"] == f"github:{'a' * 40}|https://aniccaai.com/blog/{slug}"


def test_occurrence_manifest_rejects_runtime_identity_mismatch(tmp_path):
    path = tmp_path / "occurrences/midnight-boundary.json"
    try:
        rec.record_occurrence_manifest(
            path,
            owner_id=rec.OWNER_ID,
            run_id="other-run",
            occurrence_id="capafy-distribute-daily:midnight-boundary",
            slot="2026-09-30-h00m00",
            article_slug="capafy-marketing-strategist-2026-09-30-h00m00",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched runtime identity was recorded")
    assert not path.exists()


def test_reconcile_search_window_starts_at_occurrence_execution(tmp_path, monkeypatch):
    queued = Q
    started = queued + dt.timedelta(hours=4)
    occurrence_id = "capafy-distribute-daily:delayed-attempt"
    occurrence_run(
        tmp_path, monkeypatch, occurrence_id, started,
        "capafy-marketing-strategist-2026-09-29-h21m00",
    )
    windows = []

    def commits_fn(start, end):
        windows.append((start, end))
        return {"ok": True, "commits": []}

    rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(minutes=5),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", queued),
        commits_fn=commits_fn,
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
    )

    assert windows == [(started, started + dt.timedelta(seconds=rec.MAX_RUN_SECONDS))]


def test_reconcile_rejects_unrelated_landing_slug_in_old_queue_window(tmp_path, monkeypatch):
    queued = Q
    started = queued + dt.timedelta(hours=4)
    occurrence_id = "capafy-distribute-daily:delayed-attempt"
    occurrence_run(
        tmp_path, monkeypatch, occurrence_id, started,
        "capafy-marketing-strategist-2026-09-29-h21m00",
    )

    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(minutes=5),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", queued),
        commits_fn=lambda _start, _end: {
            "ok": True,
            "commits": [{"sha": "unrelated", "slug": "line-sticker-set-007-2026-10-12-20"}],
        },
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
        page_status_fn=lambda _slug: 200,
    )

    assert result["verified"] is False


def test_reconcile_uses_wrapper_slot_across_jst_boundary(tmp_path, monkeypatch):
    started = dt.datetime(2026, 9, 29, 14, 59, 59, tzinfo=dt.timezone.utc)
    occurrence_id = "capafy-distribute-daily:midnight-boundary"
    actual_slot = "2026-09-30-h00m00"
    actual_slug = "capafy-marketing-strategist-2026-09-30-h00m00"
    old_slot = "2026-09-29-h23m30"
    old_dir = tmp_path / "runs" / f"capafy-distribute-{old_slot}"
    old_dir.mkdir(parents=True)
    (old_dir / "prompt.txt").write_text(
        "Old prompt: https://aniccaai.com/blog/capafy-marketing-strategist-2026-09-29-h23m30\n"
    )
    occurrence_run(tmp_path, monkeypatch, occurrence_id, started, actual_slug, slot=actual_slot)

    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: (
            "claimed", started - dt.timedelta(hours=1)
        ),
        commits_fn=lambda _start, _end: {
            "ok": True,
            "commits": [{"sha": "published-new-slot", "slug": actual_slug}],
        },
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
        page_status_fn=lambda _slug: 200,
    )

    assert result["expected_slug"] == actual_slug
    assert result["verified"] is True
    assert result["effected"] is True


def test_postiz_key_falls_back_to_unique_credential_ssot(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"credentials": [
        {"service": "postiz", "api_key": "secret-from-ssot"},
    ]}))

    assert rec.postiz_key(path) == "secret-from-ssot"


def test_postiz_key_rejects_ambiguous_or_malformed_ssot(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"credentials": [
        {"service": "postiz", "api_key": "first"},
        {"service": "postiz", "api_key": "second"},
    ]}))
    assert rec.postiz_key(path) == ""
    path.write_text("not-json")
    assert rec.postiz_key(path) == ""


def test_postiz_window_at_proof_row_cap_is_not_complete_evidence(monkeypatch):
    class CappedClient:
        def __init__(self, _api_key):
            pass

        def list_posts(self, _start, _end):
            return [{"id": f"post-{index}", "integration": {"id": rec.X_INTEGRATION_ID}}
                    for index in range(500)]

    fake_adapter = types.ModuleType("postiz_adapter")
    fake_adapter.HttpPostizClient = CappedClient
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")
    monkeypatch.setitem(sys.modules, "postiz_adapter", fake_adapter)

    result = rec.read_x_posts(Q, Q + dt.timedelta(minutes=70))

    assert result == {"ok": False, "reason": "postiz_listing_exceeds_proof_row_cap"}


def test_postiz_window_with_missing_integration_is_not_complete_evidence(monkeypatch):
    class MissingIntegrationClient:
        def __init__(self, _api_key):
            pass

        def list_posts(self, _start, _end):
            return [{"id": "post-1"}]

    fake_adapter = types.ModuleType("postiz_adapter")
    fake_adapter.HttpPostizClient = MissingIntegrationClient
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")
    monkeypatch.setitem(sys.modules, "postiz_adapter", fake_adapter)

    result = rec.read_x_posts(Q, Q + dt.timedelta(minutes=70))

    assert result == {"ok": False, "reason": "postiz_readback_malformed"}


def test_postiz_window_with_malformed_integration_is_not_complete_evidence(monkeypatch):
    class MalformedIntegrationClient:
        def __init__(self, _api_key):
            pass

        def list_posts(self, _start, _end):
            return [{"id": "post-1", "integration": "not-an-object"}]

    fake_adapter = types.ModuleType("postiz_adapter")
    fake_adapter.HttpPostizClient = MalformedIntegrationClient
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")
    monkeypatch.setitem(sys.modules, "postiz_adapter", fake_adapter)

    result = rec.read_x_posts(Q, Q + dt.timedelta(minutes=70))

    assert result == {"ok": False, "reason": "postiz_readback_malformed"}


def test_postiz_window_preserves_provider_rows_for_private_snapshot(monkeypatch):
    post = {
        "id": "post-1",
        "integration": {"id": rec.X_INTEGRATION_ID},
        "status": "PUBLISHED",
        "content": "CTA",
        "publishDate": "2026-09-29T09:00:00.000Z",
    }

    class Client:
        def __init__(self, _api_key):
            pass

        def list_posts(self, _start, _end):
            return [post]

    fake_adapter = types.ModuleType("postiz_adapter")
    fake_adapter.HttpPostizClient = Client
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")
    monkeypatch.setitem(sys.modules, "postiz_adapter", fake_adapter)

    result = rec.read_x_posts(Q, Q + dt.timedelta(minutes=70))

    assert result["posts"] == ["post-1"]
    assert result["integration_posts"] == [post]


def pre_effect_manifest_failure(tmp_path, monkeypatch, *, artifact=None):
    occurrence_id = "capafy-distribute-daily:18de4680b4bcfe18-18857"
    run_id = occurrence_id.rsplit(":", 1)[1]
    started = dt.datetime(2026, 10, 14, 3, 7, 0, 364089, tzinfo=dt.timezone.utc)
    release_sha = "a299acc04573ab916fb261ad7ff94b1d3f79a119"
    events = tmp_path / "events.jsonl"
    start = {
        "owner_id": rec.OWNER_ID,
        "run_id": run_id,
        "occurrence_id": occurrence_id,
        "phase": "execute",
        "status": "running",
        "timestamp": started.isoformat(),
        "release_sha": release_sha,
        "effect_class": "publish",
        "effect_status": "started",
        "provider_receipt_id": None,
        "official_readback_ref": None,
    }
    failure = {
        "owner_id": rec.OWNER_ID,
        "run_id": run_id,
        "occurrence_id": occurrence_id,
        "phase": "report",
        "status": "fail",
        "timestamp": (started + dt.timedelta(seconds=9.2)).isoformat(),
        "release_sha": release_sha,
        "effect_class": "publish",
        "effect_status": "unknown",
        "effect_identity_status": "not_written",
        "failure_layer": "entrypoint",
        "error_class": "entrypoint_exit_1",
        "error_detail": (
            "[redacted]/skills/earn/capafy-marketing/capafy-distribute-daily.sh: "
            "line 148: cannot create temp file for here document: No space left on device"
        ),
        "exit_code": 1,
        "provider_receipt_id": None,
        "official_readback_ref": None,
    }
    events.write_text(json.dumps(start) + "\n" + json.dumps(failure) + "\n", encoding="utf-8")

    local_started = started.astimezone(ZoneInfo("Asia/Tokyo"))
    slot_minute = (local_started.minute // 30) * 30
    slot = f"{local_started:%Y-%m-%d}-h{local_started.hour:02d}m{slot_minute:02d}"
    runs_root = tmp_path / "runs"
    run_dir = runs_root / f"capafy-distribute-{slot}"
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    if artifact is not None:
        (run_dir / artifact).write_text("unbound output\n", encoding="utf-8")
    run_time = started.timestamp() + 8
    os.utime(gates, (run_time, run_time))
    os.utime(run_dir, (run_time, run_time))
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_EVENTS_PATH", str(events))
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr(rec, "EVENTS_PATH", events)
    monkeypatch.setattr(rec, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(rec, "OCCURRENCES_ROOT", tmp_path / "occurrences")
    return occurrence_id, started


def test_pre_effect_enospc_manifest_failure_needs_empty_official_readbacks(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch)
    now = started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1)
    windows = []

    def commits_fn(start, end):
        windows.append((start, end))
        return {"ok": True, "commits": []}

    result = rec.reconcile(
        occurrence_id,
        now=now,
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=commits_fn,
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
    )

    assert windows == [(started, started + dt.timedelta(seconds=rec.MAX_RUN_SECONDS))]
    assert result["verified"] is True
    assert result["effected"] is False
    assert result["proof_kind"] == "official_github_postiz_empty_after_pre_effect_enospc"


def test_pre_effect_enospc_ignores_unrelated_landing_slug_in_shared_window(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch)
    unrelated_line_sticker_commit = {
        "sha": "a9271bd94298d6a8573143cfe23dad6a2545bc40",
        "at": "2026-10-14T12:09:29+09:00",
        "slug": "line-sticker-set-020-2026-10-14-12",
    }

    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": [unrelated_line_sticker_commit]},
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
    )

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["proof_kind"] == "official_github_postiz_empty_after_pre_effect_enospc"


def test_pre_effect_enospc_keeps_same_slot_capafy_commit_inconclusive(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch)
    same_slot_capafy_commit = {
        "sha": "b" * 40,
        "at": "2026-10-14T12:09:29+09:00",
        "slug": "capafy-tiktok-script-pro-2026-10-14-h12m00",
    }

    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": [same_slot_capafy_commit]},
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
    )

    assert result["verified"] is False
    assert result["reason"] == "landing_commit_in_window_without_occurrence_manifest"


def test_pre_effect_enospc_manifest_failure_stays_fenced_if_postiz_has_a_post(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch)
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": True, "posts": ["post-1"]},
    )

    assert result["verified"] is False
    assert result["reason"] == "x_post_in_window_without_occurrence_manifest"


def test_pre_effect_enospc_manifest_failure_rejects_malformed_postiz_listing(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch)
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": True},
    )

    assert result["verified"] is False
    assert result["reason"] == "postiz_readback_malformed"


def test_legacy_missing_manifest_uses_official_empty_window_despite_run_artifact(tmp_path, monkeypatch):
    occurrence_id, started = pre_effect_manifest_failure(tmp_path, monkeypatch, artifact="prompt.txt")
    result = rec.reconcile(
        occurrence_id,
        now=started + dt.timedelta(seconds=rec.NO_EFFECT_MIN_AGE_SECONDS + 1),
        fenced_row_fn=lambda _owner, _occurrence: ("claimed", started - dt.timedelta(seconds=1)),
        commits_fn=lambda _start, _end: {"ok": True, "commits": []},
        x_fn=lambda _start, _end: {"ok": True, "posts": []},
    )

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["proof_kind"] == "official_github_postiz_empty_after_legacy_manifest_gap"


def test_occurrence_manifest_accepts_listed_seo_keyword_slug(tmp_path):
    record = rec.record_occurrence_manifest(
        tmp_path / "occurrences/seo-run.json", owner_id=rec.OWNER_ID, run_id="seo-run",
        occurrence_id="capafy-distribute-daily:seo-run", slot="2026-10-17-h20m00",
        article_slug="tiktok-hook-generator-free")
    assert record["article_slug"] == "tiktok-hook-generator-free"


def test_occurrence_manifest_rejects_unlisted_or_unsafe_slugs(tmp_path):
    for slug in ("../etc", "not-a-listed-keyword", "capafy-hook-lab-2026-10-17-h19m30"):
        try:
            rec.record_occurrence_manifest(
                tmp_path / "occurrences/seo-run.json", owner_id=rec.OWNER_ID, run_id="seo-run",
                occurrence_id="capafy-distribute-daily:seo-run", slot="2026-10-17-h20m00",
                article_slug=slug)
        except ValueError:
            continue
        raise AssertionError(f"accepted {slug}")


def test_occurrence_manifest_accepts_keyword_slugs_from_every_seller_list(tmp_path):
    record = rec.record_occurrence_manifest(
        tmp_path / "occurrences/seo-run.json", owner_id=rec.OWNER_ID, run_id="seo-run",
        occurrence_id="capafy-distribute-daily:seo-run", slot="2026-10-18-h02m30",
        article_slug="tiktok-script-template")
    assert record["article_slug"] == "tiktok-script-template"


def test_preexisting_scheduled_video_does_not_fence_failed_article(tmp_path, monkeypatch):
    # A different owner created this scheduled post days before the article run.
    receipts = tmp_path / "videos" / "prior-video"
    receipts.mkdir(parents=True)
    receipt = receipts / "x-receipts-v3.jsonl"
    receipt.write_text(json.dumps({
        "at": "2026-09-25T06:43:57+00:00",
        "integration": rec.X_INTEGRATION_ID,
        "scheduled_for": "2026-09-29T09:00:00.000Z",
        "create": [{"postId": "prior-video", "integration": rec.X_INTEGRATION_ID}],
    }) + "\n")
    monkeypatch.setattr(rec, "X_VIDEO_RECEIPTS_ROOT", tmp_path / "videos", raising=False)
    class Client:
        def __init__(self, _key):
            pass
        def list_posts(self, _start, _end):
            return [{"id": "prior-video", "integration": {"id": rec.X_INTEGRATION_ID},
                     "publishDate": "2026-09-29T09:00:00.000Z"}]
    adapter = types.ModuleType("postiz_adapter")
    adapter.HttpPostizClient = Client
    monkeypatch.setitem(sys.modules, "postiz_adapter", adapter)
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")

    posts = rec.read_x_posts(Q, Q + dt.timedelta(minutes=70))
    result = proof(200, {"ok": True, "commits": []}, posts)

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["preexisting_x_posts"][0]["post_id"] == "prior-video"
    assert result["preexisting_x_posts"][0]["receipt_path"] == str(receipt)


def test_preexisting_x_post_requires_unique_prior_create_receipt(tmp_path, monkeypatch):
    root = tmp_path / "videos"
    directory = root / "prior-video"
    directory.mkdir(parents=True)
    path = directory / "x-receipts-v3.jsonl"
    monkeypatch.setattr(rec, "X_VIDEO_RECEIPTS_ROOT", root)
    post = {"id": "prior-video", "publishDate": "2026-09-29T09:00:00Z"}
    valid = {"at": "2026-09-25T06:43:57Z", "integration": rec.X_INTEGRATION_ID,
             "scheduled_for": "2026-09-29T09:00:00Z",
             "create": [{"postId": "prior-video", "integration": rec.X_INTEGRATION_ID}]}
    variants = [
        {**valid, "at": Q.isoformat()},
        {**valid, "at": "2026-09-30T06:43:57Z"},
        {**valid, "at": "2026-09-25T06:43:57"},
        {**valid, "at": "invalid"},
        {**valid, "scheduled_for": "2026-09-29T09:01:00Z"},
        {**valid, "integration": "other-account"},
        {**valid, "create": [{"postId": "another-post", "integration": rec.X_INTEGRATION_ID}]},
        {**valid, "create": [{"postId": "prior-video", "integration": "other-account"}]},
        {**valid, "create": []},
        {**valid, "create": valid["create"] * 2},
    ]
    for receipt in variants:
        path.write_text(json.dumps(receipt))
        assert rec.preexisting_x_post(post, Q) is None, receipt
    path.write_text(json.dumps(valid))
    assert rec.preexisting_x_post({"id": "prior-video"}, Q) is None
    duplicate = root / "duplicate"
    duplicate.mkdir()
    (duplicate / path.name).write_text(json.dumps(valid))
    assert rec.preexisting_x_post(post, Q) is None
    (duplicate / path.name).unlink()
    path.unlink()
    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps(valid))
    path.symlink_to(outside)
    assert rec.preexisting_x_post(post, Q) is None


def test_unknown_x_post_remains_fenced_alongside_preexisting_video(tmp_path, monkeypatch):
    # Only a proven prior create may be excluded; shared-account activity still holds.
    monkeypatch.setattr(rec, "preexisting_x_post", lambda post, _start:
                        {"post_id": "prior-video"} if post["id"] == "prior-video" else None)
    class Client:
        def __init__(self, _key):
            pass
        def list_posts(self, _start, _end):
            return [{"id": pid, "integration": {"id": rec.X_INTEGRATION_ID}}
                    for pid in ["prior-video", "unknown-post"]]
    adapter = types.ModuleType("postiz_adapter")
    adapter.HttpPostizClient = Client
    monkeypatch.setitem(sys.modules, "postiz_adapter", adapter)
    monkeypatch.setattr(rec, "postiz_key", lambda: "test-key")
    result = proof(200, {"ok": True, "commits": []}, rec.read_x_posts(Q, Q))
    assert result["verified"] is False
    assert result["reason"] == "x_post_without_article"


def test_invalid_utf8_query_does_not_block_exact_ascii_slug_readback(tmp_path, monkeypatch):
    slug = 'capafy-hook-lab-2026-09-29-h21m00'
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug)
    prompt = tmp_path / 'runs/capafy-distribute-2026-09-29-h21m00/prompt.txt'
    prompt.write_bytes(prompt.read_bytes() + b'query: \xe3\\203\xaa\n')
    assert rec.expected_article_slug(OCC) == slug
    for age, posts, verified in ((30, [], False), (90, [], True),
                                 (90, ['unaccounted-post'], False)):
        result = rec.reconcile(
            OCC, now=Q + dt.timedelta(minutes=age),
            fenced_row_fn=lambda *_args: ('claimed', Q),
            commits_fn=lambda *_args: {'ok': True, 'commits': []},
            x_fn=lambda *_args: {'ok': True, 'posts': posts})
        assert result['verified'] is verified
    prompt.write_bytes(prompt.read_bytes() + b'https://aniccaai.com/blog/conflicting-slug\n')
    assert rec.expected_article_slug(OCC) == slug


def test_writer_mutated_prompt_cannot_change_canonical_occurrence_slug(tmp_path, monkeypatch):
    slug = 'capafy-hook-lab-2026-09-29-h21m00'
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug)
    prompt = tmp_path / 'runs/capafy-distribute-2026-09-29-h21m00/prompt.txt'
    prefix = b'https://aniccaai.com/blog/' + slug.encode('ascii')
    for suffix in (b'\xe3', b'/other', b'--broken', b'%2Fother'):
        prompt.write_bytes(prefix + suffix + b'\n')
        assert rec.expected_article_slug(OCC) == slug


def test_damaged_url_is_not_ignored_when_a_valid_url_is_also_present(tmp_path, monkeypatch):
    slug = 'capafy-hook-lab-2026-09-29-h21m00'
    occurrence_run(tmp_path, monkeypatch, OCC, Q, slug)
    prompt = tmp_path / 'runs/capafy-distribute-2026-09-29-h21m00/prompt.txt'
    prefix = b'https://aniccaai.com/blog/'
    for path in (slug.encode('ascii') + b'\xff-other', b''):
        prompt.write_bytes(prefix + slug.encode('ascii') + b'\n' + prefix + path + b'\n')
        assert rec.expected_article_slug(OCC) == slug


# --- model_no_response: the run provably never reached publish (2026-10-24 14:25 JST, Codex usage limit) ---
MANUAL_POST = {"ok": True, "posts": ["cmvlp7rqs0jn2qu1cj6ugacyu"]}  # a teammate's own X post in the window
NO_RESPONSE = {"slot": "2026-09-29-h15", "rc": 1, "published_marker_in_block": False,
               "ledger_has_slot_post": False, "block_started_within_s": 1.0}


def proof_nr(now_min, commits, x, evidence, slot="2026-09-29-h15"):
    return rec.build_proof(OCC, Q, started_at=Q, expected_slug=EXPECTED_SLUG,
                           now=Q + dt.timedelta(minutes=now_min), commits=commits, x_posts=x,
                           page_status_fn=lambda s: 200,
                           model_no_response={**evidence, "expected_slot": slot} if evidence else None)


def test_model_no_response_ignores_a_manual_x_post_in_the_window():
    p = proof_nr(200, {"ok": True, "commits": []}, MANUAL_POST, NO_RESPONSE)
    assert p["verified"] and p["effected"] is False
    assert p["proof_kind"] == "occurrence_bound_model_no_response"


def test_without_the_evidence_a_manual_x_post_still_fences_the_occurrence():
    p = proof_nr(200, {"ok": True, "commits": []}, MANUAL_POST, None)
    assert not p["verified"] and p["reason"] == "x_post_without_article"


def test_model_no_response_never_overrides_a_landing_commit():
    p = proof_nr(200, {"ok": True, "commits": [{"sha": "a" * 40, "slug": EXPECTED_SLUG,
                                                "at": Q.isoformat()}]}, MANUAL_POST, NO_RESPONSE)
    assert p["effected"] is True


def test_model_no_response_with_a_published_marker_or_ledger_post_is_rejected():
    for bad in ({"published_marker_in_block": True}, {"ledger_has_slot_post": True}, {"rc": 0}):
        p = proof_nr(200, {"ok": True, "commits": []}, MANUAL_POST, {**NO_RESPONSE, **bad})
        assert not p["verified"], bad


def test_model_no_response_bound_to_another_slot_or_a_loose_block_is_rejected():
    assert not proof_nr(200, {"ok": True, "commits": []}, MANUAL_POST, NO_RESPONSE,
                        slot="2026-09-29-h16")["verified"]
    loose = {**NO_RESPONSE, "block_started_within_s": 60.0}
    assert not proof_nr(200, {"ok": True, "commits": []}, MANUAL_POST, loose)["verified"]


def test_model_no_response_still_waits_for_the_effect_window():
    assert not proof_nr(30, {"ok": True, "commits": []}, MANUAL_POST, NO_RESPONSE)["verified"]


def proof_nr_finished(now_min, finished):
    return rec.build_proof(OCC, Q, started_at=Q, expected_slug=EXPECTED_SLUG,
                           now=Q + dt.timedelta(minutes=now_min), commits={"ok": True, "commits": []},
                           x_posts=MANUAL_POST, page_status_fn=lambda s: 200,
                           model_no_response={**NO_RESPONSE, "expected_slot": "2026-09-29-h15"},
                           run_finished=finished)


def test_model_no_response_skips_the_85_minute_wait_only_once_the_run_has_finished():
    """2026-10-25: a busy-Codex defer (rc 75 in ~1s) left distribution stopped for 85 minutes per defer.
    The wait exists so a still-running wrapper cannot publish after the proof; a report event removes that risk."""
    assert proof_nr_finished(10, True)["verified"] is True
    assert proof_nr_finished(10, True)["proof_kind"] == "occurrence_bound_model_no_response"
    assert proof_nr_finished(10, False)["verified"] is False


def test_run_finished_reads_only_this_occurrences_report_event(tmp_path):
    events = tmp_path / "events.jsonl"
    rows = [{"owner_id": rec.OWNER_ID, "run_id": "r1", "occurrence_id": OCC, "phase": "execute", "status": "running"},
            {"owner_id": rec.OWNER_ID, "run_id": "r2", "occurrence_id": "capafy-distribute-daily:r2", "phase": "report"}]
    events.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert rec.occurrence_run_finished(OCC, events_path=events) is False
    rows.append({"owner_id": rec.OWNER_ID, "run_id": OCC.split(":", 1)[1], "occurrence_id": OCC, "phase": "report"})
    events.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert rec.occurrence_run_finished(OCC, events_path=events) is True


# --- reading the evidence from the daily log + ledger (real shape captured 2026-10-24) ---
STARTED = dt.datetime(2026, 10, 24, 5, 25, 24, 569423, tzinfo=dt.timezone.utc)  # 14:25:24 JST
FAILED_BLOCK = """\\
=== capafy-distribute-daily run 2026-10-24 14:25:25 JST ===
=== capafy-distribute-daily run 2026-10-24 14:25:26 JST ===
{"already_published": false, "date": "2026-10-24-h14m00"}
capafy-distribute-daily: selection={"date": "2026-10-24", "capafy_skill": "hook-lab"}
capafy-distribute-daily: seo keyword={"query": "tiktok hook formulas", "slug": "tiktok-hook-formulas"}
writer shared runner failed rc=1 {"attempt": 1, "provider": "codex"}
capafy-distribute-daily: model pass exit=1 slot=2026-10-24-h14m00 skill=hook-lab
"""
PUBLISHED_BLOCK = """\\
=== capafy-distribute-daily run 2026-10-24 05:47:28 JST ===
capafy-distribute-daily: model pass exit=0 slot=2026-10-24-h05m30 skill=tiktok-script-pro
capafy-distribute-daily: wrapper publish: {"status": "published", "slug": "tiktok-script-for-etsy-shop"}
capafy-distribute-daily: x post: {"dry_run": false, "action": "published", "post_id": "cmvlg6n9e06cvn61com9yrde8"}
"""


def _log(tmp_path, text):
    p = tmp_path / "daily.log"
    p.write_text(text, encoding="utf-8")
    return p


def _ledger(tmp_path, entries):
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def test_failed_model_block_yields_exact_no_response_evidence(tmp_path):
    ev = rec.model_no_response_evidence(STARTED, "2026-10-24-h14m00",
                                        log_path=_log(tmp_path, PUBLISHED_BLOCK + FAILED_BLOCK),
                                        ledger_path=_ledger(tmp_path, {}))
    assert ev["slot"] == "2026-10-24-h14m00" and ev["rc"] == 1
    assert ev["published_marker_in_block"] is False and ev["ledger_has_slot_post"] is False
    assert 0 <= ev["block_started_within_s"] <= 5


def test_a_published_block_is_never_no_response_evidence(tmp_path):
    started = dt.datetime(2026, 10, 23, 20, 47, 28, 300000, tzinfo=dt.timezone.utc)  # 05:47:28 JST
    ev = rec.model_no_response_evidence(started, "2026-10-24-h05m30",
                                        log_path=_log(tmp_path, PUBLISHED_BLOCK),
                                        ledger_path=_ledger(tmp_path, {}))
    assert ev is None  # rc == 0 and a publish marker: not a no-response block


def test_ledger_post_for_the_slot_voids_the_evidence(tmp_path):
    ledger = {"2026-10-24-h14m00": {"status": "published",
                                    "destinations": {"x": {"post_id": "cmv123", "status": "PUBLISHED"}}}}
    ev = rec.model_no_response_evidence(STARTED, "2026-10-24-h14m00",
                                        log_path=_log(tmp_path, FAILED_BLOCK),
                                        ledger_path=_ledger(tmp_path, ledger))
    assert ev is None or ev["ledger_has_slot_post"] is True


def test_missing_or_unreadable_log_gives_no_evidence(tmp_path):
    assert rec.model_no_response_evidence(STARTED, "2026-10-24-h14m00",
                                          log_path=tmp_path / "absent.log",
                                          ledger_path=_ledger(tmp_path, {})) is None


def test_block_for_a_different_slot_gives_no_evidence(tmp_path):
    assert rec.model_no_response_evidence(STARTED, "2026-10-24-h15m00",
                                          log_path=_log(tmp_path, FAILED_BLOCK),
                                          ledger_path=_ledger(tmp_path, {})) is None
