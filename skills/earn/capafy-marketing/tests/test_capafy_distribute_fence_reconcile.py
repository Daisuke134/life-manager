import datetime as dt
import json
import sys
from pathlib import Path

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


def test_commit_without_live_page_stays_fenced():
    p = proof(200, {"ok": True, "commits": [{"sha": "abc", "slug": EXPECTED_SLUG}]},
              {"ok": True, "posts": []}, status=404)
    assert not p["verified"]


def test_no_commit_too_recent_stays_fenced():
    assert not proof(30, {"ok": True, "commits": []}, {"ok": True, "posts": []})["verified"]


def test_no_commit_no_post_after_window_is_no_effect():
    p = proof(200, {"ok": True, "commits": []}, {"ok": True, "posts": []})
    assert p["verified"] and p["effected"] is False


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
    (run_dir / "gates/occurrence.json").write_text(json.dumps({
        "schema": rec.OCCURRENCE_SCHEMA,
        "owner_id": rec.OWNER_ID,
        "run_id": occurrence_id.rsplit(":", 1)[1],
        "occurrence_id": occurrence_id,
        "slot": slot,
        "article_slug": slug,
    }))
    (run_dir / "prompt.txt").write_text(f"Publish this article: https://aniccaai.com/blog/{slug}\n")
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_EVENTS_PATH", str(events))
    monkeypatch.setenv("CAPAFY_DISTRIBUTE_RUNS_ROOT", str(runs_root))


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
    path = tmp_path / "runs/capafy-distribute-2026-09-30-h00m00/gates/occurrence.json"
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


def test_occurrence_manifest_rejects_runtime_identity_mismatch(tmp_path):
    path = tmp_path / "occurrence.json"
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
