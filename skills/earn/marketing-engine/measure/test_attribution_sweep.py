from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import attribution_sweep as sweep  # noqa: E402


OBSERVED_AT = "2026-08-03T21:15:00Z"


def identity(**changes):
    row = {
        "schema_version": 1,
        "postiz_state": "PUBLISHED",
        "postiz_post_id": "postiz-1",
        "postiz_release_id": "native-1",
        "postiz_release_url": "https://example.test/native-1",
        "publish_date": "2026-08-01T20:15:00Z",
        "integration_id": "integration.one",
        "platform": "tiktok",
        "experiment_id": "experiment.one",
        "experiment_id_null_reason": None,
        "publish_key": "publication.one",
        "creative_id": "creative.one",
        "creative_sha256": "a" * 64,
        "creative_sha256_null_reason": None,
        "product_id": "ebook-ja",
        "product_id_null_reason": None,
        "account_id": "account.one",
        "account_id_null_reason": None,
        "hook_id": "hook.one",
        "renderer_id": "renderer.one",
        "attribution_token": "ej_token",
        "scheduled_at": "2026-08-01T20:15:00Z",
        "identity_status": "resolved",
        "native_post_id": "native-1",
        "native_post_url": "https://example.test/native-1",
    }
    return {**row, **changes}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_sweep(tmp_path: Path, identities: list[dict], *, observed_at: str = OBSERVED_AT,
              query_calls: list[tuple[dict, str]] | None = None) -> dict:
    identity_path = tmp_path / "publication-identity.jsonl"
    post_metrics_path = tmp_path / "post-metrics.jsonl"
    business_path = tmp_path / "business-outcomes.jsonl"
    attribution_path = tmp_path / "experiment-attribution.jsonl"
    report_path = tmp_path / "attribution-sweep-latest.json"
    write_jsonl(identity_path, identities)
    write_jsonl(post_metrics_path, [{
        "experiment_id": "experiment.one",
        "native_post_id": "native-1",
        "observed_at": "2026-08-03T20:00:00Z",
        "target_age_hours": 72,
        "checkpoint_status": "observed",
        "views": 20,
        "impressions": 25,
        "raw_evidence_hash": "b" * 64,
    }])
    write_jsonl(business_path, [])

    def query_click(intent: dict, measured_at: str) -> dict:
        if query_calls is not None:
            query_calls.append((intent, measured_at))
        return {
            "status": "unavailable",
            "reason": "test_click_source_unavailable",
            "evidence_refs": ["fixture:click-source"],
        }

    return sweep.run_sweep(
        identity_path=identity_path,
        post_metrics_path=post_metrics_path,
        business_path=business_path,
        attribution_path=attribution_path,
        report_path=report_path,
        observed_at=observed_at,
        query_click=query_click,
    )


def test_exact_publication_writes_truthful_snapshot_and_report(tmp_path):
    calls: list[tuple[dict, str]] = []
    report = run_sweep(tmp_path, [identity()], query_calls=calls)

    rows = [json.loads(line) for line in
            (tmp_path / "experiment-attribution.jsonl").read_text().splitlines()]
    snapshot = rows[0]
    results = {row["metric_name"]: row for row in snapshot["results"]}

    assert report["status"] == "pass"
    assert report["eligible_publications"] == 1
    assert report["snapshots_written"] == 1
    assert calls[0][0]["publish_key"] == "publication.one"
    assert calls[0][1] == OBSERVED_AT
    assert snapshot["schema_version"] == "marketing.experiment-attribution.v2"
    assert snapshot["postiz_post_id"] == "postiz-1"
    assert snapshot["native_post_id"] == "native-1"
    assert results["views"]["value"] == 20
    assert results["actual_cost_usd"]["status"] == "unknown"
    assert results["actual_cost_usd"]["value"] is None
    assert results["human_interventions"]["status"] == "unknown"
    assert results["human_interventions"]["value"] is None
    assert report["unknown_metric_counts"]["actual_cost_usd"] == 1
    persisted_report = json.loads(
        (tmp_path / "attribution-sweep-latest.json").read_text()
    )
    assert persisted_report == report


def test_first_snapshot_waits_until_business_window_is_mature(tmp_path):
    calls: list[tuple[dict, str]] = []
    report = run_sweep(
        tmp_path, [identity()], observed_at="2026-08-02T19:15:00Z",
        query_calls=calls,
    )

    assert report["status"] == "attention"
    assert report["eligible_publications"] == 0
    assert report["snapshots_written"] == 0
    assert report["excluded"]["not_mature_yet"] == 1
    assert calls == []
    assert not (tmp_path / "experiment-attribution.jsonl").exists()


def test_repeated_same_day_sweep_is_idempotent_and_skips_click_query(tmp_path):
    calls: list[tuple[dict, str]] = []
    first = run_sweep(tmp_path, [identity()], query_calls=calls)
    second = run_sweep(
        tmp_path, [identity()], observed_at="2026-08-03T22:15:00Z",
        query_calls=calls,
    )

    rows = (tmp_path / "experiment-attribution.jsonl").read_text().splitlines()
    assert first["snapshots_written"] == 1
    assert second["status"] == "pass"
    assert second["snapshots_written"] == 0
    assert second["snapshots_already_present"] == 1
    assert len(rows) == 1
    assert len(calls) == 1


def test_exact_row_is_rejected_when_same_postiz_id_has_legacy_duplicate(tmp_path):
    legacy = identity(
        publish_key=None,
        experiment_id=None,
        experiment_id_null_reason="legacy_uninstrumented",
    )
    calls: list[tuple[dict, str]] = []

    report = run_sweep(tmp_path, [identity(), legacy], query_calls=calls)

    assert report["status"] == "attention"
    assert report["eligible_publications"] == 0
    assert report["excluded"]["identity_mismatch"] == 2
    assert calls == []


def test_legacy_unresolved_ambiguous_duplicate_and_mismatched_rows_are_excluded(tmp_path):
    legacy = identity(
        postiz_post_id="legacy",
        publish_key=None,
        experiment_id=None,
        experiment_id_null_reason="legacy_uninstrumented",
        native_post_id="native-legacy",
        native_post_url="https://example.test/native-legacy",
    )
    unresolved = identity(
        postiz_post_id="unresolved",
        publish_key="publication.unresolved",
        identity_status="unresolved",
        native_post_id=None,
        native_post_url=None,
    )
    ambiguous = identity(
        postiz_post_id="ambiguous",
        publish_key="publication.ambiguous",
        identity_status="ambiguous",
        native_post_id=None,
        native_post_url=None,
    )
    duplicate_native = [
        identity(
            postiz_post_id="duplicate-native-1",
            publish_key="publication.duplicate-native-1",
        ),
        identity(
            postiz_post_id="duplicate-native-2",
            publish_key="publication.duplicate-native-2",
        ),
    ]
    mismatched = [
        identity(postiz_post_id="mismatch", publish_key="publication.mismatch-a",
                 native_post_id="native-mismatch-a"),
        identity(postiz_post_id="mismatch", publish_key="publication.mismatch-b",
                 native_post_id="native-mismatch-b"),
    ]
    calls: list[tuple[dict, str]] = []

    report = run_sweep(
        tmp_path,
        [legacy, unresolved, ambiguous, *duplicate_native, *mismatched],
        query_calls=calls,
    )

    assert report["status"] == "attention"
    assert report["eligible_publications"] == 0
    assert report["excluded"]["legacy_uninstrumented"] == 1
    assert report["excluded"]["identity_unresolved"] == 1
    assert report["excluded"]["identity_ambiguous"] == 1
    assert report["excluded"]["duplicate_native_receipt"] == 2
    assert report["excluded"]["identity_mismatch"] == 2
    assert calls == []


def test_main_returns_attention_exit_code_for_no_eligible_publication(tmp_path):
    identity_path = tmp_path / "publication-identity.jsonl"
    write_jsonl(identity_path, [identity(identity_status="unresolved")])
    post_metrics_path = tmp_path / "post-metrics.jsonl"
    write_jsonl(post_metrics_path, [])
    business_path = tmp_path / "business-outcomes.jsonl"
    write_jsonl(business_path, [])

    exit_code = sweep.main([
        "--identity", str(identity_path),
        "--post-metrics", str(post_metrics_path),
        "--business", str(business_path),
        "--attribution", str(tmp_path / "experiment-attribution.jsonl"),
        "--report", str(tmp_path / "attribution-sweep-latest.json"),
        "--observed-at", OBSERVED_AT,
        "--repo-root", str(tmp_path),
    ])

    assert exit_code == 3
