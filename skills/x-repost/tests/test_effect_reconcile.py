from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/x-repost/scripts/effect_reconcile.py"
_spec = importlib.util.spec_from_file_location("x_repost_effect_reconcile", SCRIPT)
ADAPTER = None
if _spec is not None and _spec.loader is not None and SCRIPT.exists():
    ADAPTER = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ADAPTER)

UTC = dt.timezone.utc
OWNER = "x-repost"
RUN_ID = "18d619b58da7e748-16052"
OCCURRENCE = f"{OWNER}:{RUN_ID}"
RELEASE_SHA = "c16f437b93028ea5d94014a1fa32c091795cbee0"
QUEUED_RUN_ID = "18d61a2e141e1b30-39087"
QUEUED_OCCURRENCE = f"{OWNER}:{QUEUED_RUN_ID}"
REBOUND_RUN_ID = "18db8c60e536c100-75588"
REBOUND_RELEASE_SHA = "88872a85cc652877f242ead444108a813084cfc9"
OLD_QUEUED_RELEASE_SHA = "86fa863d4fe04ec0b5c44e8a2e513e55edaf2928"
INTEGRATION_ID = "cmt4l2jld031tqp0y8qtyo983"
OTHER_RELEASE_SHA = "1" * 40
START = dt.datetime(2026, 9, 17, 11, 56, 9, 485319, UTC)
REPORTED = dt.datetime(2026, 9, 17, 11, 56, 19, 2106, UTC)
FINAL = REPORTED + dt.timedelta(seconds=900)
QUEUED_START = dt.datetime(2026, 9, 17, 12, 4, 47, 136940, UTC)
QUEUED_REPORTED = dt.datetime(2026, 9, 17, 12, 5, 2, 417290, UTC)
REBOUND_START = dt.datetime(2026, 10, 5, 5, 53, 44, 637767, UTC)
REBOUND_REPORTED = dt.datetime(2026, 10, 5, 5, 55, 11, 470144, UTC)
REBOUND_FINAL = REBOUND_REPORTED + dt.timedelta(seconds=900)


def events(release_sha: str = RELEASE_SHA) -> list[dict]:
    common = {
        "loop_id": OWNER,
        "owner_id": OWNER,
        "release_sha": release_sha,
        "provider": "shared-agent-runner",
        "effect_class": "publish",
    }
    return [
        {**common, "run_id": RUN_ID, "phase": "execute", "status": "running",
         "effect_status": "started", "timestamp": START.isoformat()},
        {**common, "run_id": RUN_ID, "phase": "report", "status": "pass",
         "effect_status": "unknown",
         "timestamp": REPORTED.isoformat()},
    ]


def later_linked_report() -> dict:
    return {
        "loop_id": OWNER,
        "owner_id": OWNER,
        "run_id": "18d625fdcc85e358-11100",
        "release_sha": RELEASE_SHA,
        "provider": "shared-agent-runner",
        "effect_class": "publish",
        "phase": "report",
        "status": "pass",
        "effect_status": "unknown",
        "timestamp": "2026-09-17T12:01:29Z",
        "evidence_refs": [f"lm-occurrence://{OWNER}/{RUN_ID}/claim"],
    }


def readback_only_evidence(mtime: str = "2026-09-17T11:56:16.347559+00:00") -> dict:
    return {
        "pass_id": "20260917T205610",
        "mtime": mtime,
        "affiliate_job_reconcile": {
            "posted": "unverified",
            "mode": "reconcile",
            "provider_submission_id": "cmtd0r5em06k7o10yemh6fltr",
            "reason": "Postiz effect is not published with an exact X URL",
        },
        "affiliate_success_recovery": {"pending": False},
        "generic_recovery": {"pending": False},
        "crash_recovery": {"recovered": False},
        "affiliate_job_post": None,
        "post": None,
        "errors": "",
    }


def queued_attempt_events(
    *, run_id: str, occurrence_id: str, start_at: dt.datetime,
    report_at: dt.datetime, release_sha: str, start_occurrence_id: str | None = None,
    status: str = "pass", exit_code: int | None = None,
) -> list[dict]:
    common = {
        "loop_id": OWNER, "owner_id": OWNER, "release_sha": release_sha,
        "provider": "shared-agent-runner", "effect_class": "publish",
    }
    report = {
        **common, "run_id": run_id, "occurrence_id": occurrence_id,
        "phase": "report", "status": status, "effect_status": "unknown",
        "timestamp": report_at.isoformat(),
    }
    if exit_code is not None:
        report["exit_code"] = exit_code
    if status == "fail":
        report.update(blocker="entrypoint_exit_1", error_class="entrypoint_exit_1")
    return [
        {**common, "run_id": run_id, "occurrence_id": start_occurrence_id,
         "phase": "execute", "status": "running", "effect_status": "started",
         "timestamp": start_at.isoformat()},
        report,
    ]


def empty_listing() -> dict:
    return {"ok": True, "posts": [], "response_count": 0,
            "response_sha256": "a" * 64}


def published_listing(post_id: str = "post-42", published_at: str = "2026-09-17T11:58:30Z") -> dict:
    return {
        "ok": True,
        "posts": [{
            "id": post_id,
            "state": "PUBLISHED",
            "integration": {"id": INTEGRATION_ID},
            "releaseURL": "https://x.com/selawmqt/status/2094445556667778888",
            "publishDate": published_at,
        }],
        "response_count": 1,
        "response_sha256": "b" * 64,
    }


def published_evidence(post_id: str = "post-42") -> dict:
    proof = readback_only_evidence()
    proof["affiliate_job_reconcile"] = None
    proof["post"] = {
        "posted": True,
        "mode": "quote",
        "provider": "postiz",
        "provider_submission_id": post_id,
        "post_url": "https://x.com/selawmqt/status/2094445556667778888",
    }
    return proof


class EffectReconcileTests(unittest.TestCase):
    def adapter(self):
        if ADAPTER is None:
            self.fail("effect_reconcile adapter is missing")
        return ADAPTER

    def test_exact_readback_only_run_and_complete_empty_listing_prove_no_effect(self):
        result = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), empty_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], True)
        self.assertIs(result["effected"], False)
        self.assertIn("postiz-empty-window", result["provider_receipt_id"])
        self.assertIn("20260917T115609485319Z", result["provider_receipt_id"])
        self.assertIn("20260917T121119002106Z", result["provider_receipt_id"])
        self.assertIn("a" * 64, result["provider_receipt_id"])
        self.assertIn(result["query_sha256"], result["provider_receipt_id"])
        self.assertIn("startDate=2026-09-17T11%3A56%3A09.000Z",
                      result["official_query"])
        self.assertIn("endDate=2026-09-17T12%3A11%3A20.000Z",
                      result["official_query"])
        self.assertIn("limit=500", result["official_query"])

    def test_exact_unique_in_window_published_receipt_proves_effect(self):
        result = self.adapter().build_proof(
            OCCURRENCE, events(), published_evidence(), published_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], True)
        self.assertIs(result["effected"], True)
        self.assertEqual(result["provider_receipt_id"], "postiz:post-42")
        self.assertEqual(result["post_url"],
                         "https://x.com/selawmqt/status/2094445556667778888")

    def test_other_release_can_prove_exact_postiz_effect_but_not_no_effect(self):
        positive = self.adapter().build_proof(
            OCCURRENCE, events(OTHER_RELEASE_SHA), published_evidence(),
            published_listing(), now=FINAL,
        )
        empty = self.adapter().build_proof(
            OCCURRENCE, events(OTHER_RELEASE_SHA), readback_only_evidence(),
            empty_listing(), now=FINAL,
        )

        self.assertIs(positive["verified"], True)
        self.assertIs(positive["effected"], True)
        self.assertIs(empty["verified"], False)

    def test_finality_keeps_empty_listing_fenced(self):
        result = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), empty_listing(),
            now=FINAL - dt.timedelta(seconds=1),
        )

        self.assertIs(result["verified"], False)

    def test_reconcile_does_not_read_provider_before_finality(self):
        calls = []
        result = self.adapter().reconcile(
            OCCURRENCE,
            now=FINAL - dt.timedelta(seconds=1),
            events_fn=lambda _occurrence: events(),
            evidence_fn=lambda _start, _reported: calls.append("evidence") or {},
            postiz_fn=lambda _start, _end: calls.append("postiz") or empty_listing(),
        )

        self.assertIs(result["verified"], False)
        self.assertEqual(calls, [])

    def test_runtime_pair_uses_run_id_and_ignores_later_linked_report(self):
        rows = events() + [later_linked_report()]

        result = self.adapter().build_proof(
            OCCURRENCE, rows, readback_only_evidence(), empty_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], True)
        self.assertEqual(result["window_start"], START.isoformat())

    def test_rebound_queue_attempt_pairs_start_run_to_exact_occurrence_report(self):
        rows = queued_attempt_events(
            run_id=REBOUND_RUN_ID, occurrence_id=QUEUED_OCCURRENCE,
            start_at=REBOUND_START, report_at=REBOUND_REPORTED,
            release_sha=REBOUND_RELEASE_SHA,
            start_occurrence_id=f"{OWNER}:{REBOUND_RUN_ID}",
            status="fail", exit_code=1,
        )

        pair = self.adapter()._event_pair(QUEUED_OCCURRENCE, rows)

        self.assertIsNotNone(pair)
        self.assertEqual(pair[0]["run_id"], REBOUND_RUN_ID)
        self.assertEqual(pair[1]["occurrence_id"], QUEUED_OCCURRENCE)

    def test_reconcile_covers_all_queued_attempt_windows_and_ignores_other_posts(self):
        prior = queued_attempt_events(
            run_id=QUEUED_RUN_ID, occurrence_id=QUEUED_OCCURRENCE,
            start_at=QUEUED_START, report_at=QUEUED_REPORTED,
            release_sha=OLD_QUEUED_RELEASE_SHA,
        )
        rebound = queued_attempt_events(
            run_id=REBOUND_RUN_ID, occurrence_id=QUEUED_OCCURRENCE,
            start_at=REBOUND_START, report_at=REBOUND_REPORTED,
            release_sha=REBOUND_RELEASE_SHA,
            start_occurrence_id=f"{OWNER}:{REBOUND_RUN_ID}",
            status="fail", exit_code=1,
        )
        evidence_by_start = {
            QUEUED_START: readback_only_evidence("2026-09-17T12:04:53.330757+00:00"),
            REBOUND_START: readback_only_evidence("2026-10-05T05:54:21.110605+00:00"),
        }
        unrelated_post = {
            "id": "post-from-another-run", "state": "PUBLISHED",
            "integration": {"id": INTEGRATION_ID},
            "publishDate": "2026-10-04T13:22:50Z",
            "releaseURL": "https://x.com/selawmqt/status/2106736899985723579",
        }
        listing = {"ok": True, "posts": [unrelated_post], "response_count": 1,
                   "response_sha256": "c" * 64, "has_more": False}
        evidence_calls = []
        listing_calls = []
        result = self.adapter().reconcile(
            QUEUED_OCCURRENCE,
            now=REBOUND_FINAL,
            events_fn=lambda _occurrence: prior + rebound,
            fenced_row_fn=lambda _owner, _occurrence: ("claimed", QUEUED_START.timestamp() + 0.12),
            evidence_fn=lambda start, _report: evidence_calls.append(start) or evidence_by_start[start],
            postiz_fn=lambda start, end: listing_calls.append((start, end)) or listing,
        )

        self.assertIs(result["verified"], True)
        self.assertIs(result["effected"], False)
        self.assertEqual(evidence_calls, [QUEUED_START, REBOUND_START])
        self.assertEqual(listing_calls, [(QUEUED_START, REBOUND_FINAL)])

    def test_runtime_event_reader_accepts_observed_8506564_byte_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            event_file = Path(temporary) / "events.jsonl"
            event_file.write_text(
                json.dumps({"loop_id": OWNER, "filler": "x" * 8_506_564}) + "\n",
                encoding="utf-8",
            )

            self.assertGreater(event_file.stat().st_size, 8_506_564)
            rows = self.adapter().read_runtime_events(event_file)

        self.assertIsNotNone(rows)
        self.assertEqual(rows[0]["loop_id"], OWNER)

    def test_fence_queued_at_must_match_exact_event_start_before_readbacks(self):
        calls = []
        fence_calls = []
        result = self.adapter().reconcile(
            OCCURRENCE,
            now=FINAL,
            events_fn=lambda _occurrence: events(),
            fenced_row_fn=lambda owner, occurrence: (
                fence_calls.append((owner, occurrence)) or "released",
                START.timestamp() + 2,
            ),
            evidence_fn=lambda _start, _reported: calls.append("evidence") or readback_only_evidence(),
            postiz_fn=lambda _start, _end: calls.append("postiz") or empty_listing(),
        )

        self.assertIs(result["verified"], False)
        self.assertEqual(fence_calls, [(OWNER, OCCURRENCE)])
        self.assertEqual(calls, [])

    def test_pass_artifacts_are_read_from_the_loop_evidence_root(self):
        def write_evidence_directory(directory: Path, mtime: float) -> None:
            directory.mkdir(parents=True)
            values = {
                "affiliate-job-reconcile.json": readback_only_evidence()["affiliate_job_reconcile"],
                "affiliate-success-recovery.json": {"pending": False},
                "generic-recovery.json": {"pending": False},
                "postiz-readback-crash-recovery.json": {"recovered": False},
            }
            for name, value in values.items():
                (directory / name).write_text(json.dumps(value), encoding="utf-8")
            (directory / "affiliate-job-reconcile.err").write_text("", encoding="utf-8")
            os.utime(directory, (mtime, mtime))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root = root / "state"
            evidence_root = root / "loops" / "x-repost-en" / "evidence"
            write_evidence_directory(state_root / "evidence" / "wrong-state-root",
                                     START.timestamp() + 7)
            write_evidence_directory(evidence_root / "20260917T205610",
                                     START.timestamp() + 7)
            old_state_root = self.adapter().STATE_ROOT
            old_evidence_root = getattr(self.adapter(), "EVIDENCE_ROOT", None)
            self.adapter().STATE_ROOT = state_root
            self.adapter().EVIDENCE_ROOT = evidence_root
            try:
                result = self.adapter().read_run_evidence(START, REPORTED)
            finally:
                self.adapter().STATE_ROOT = old_state_root
                if old_evidence_root is None:
                    del self.adapter().EVIDENCE_ROOT
                else:
                    self.adapter().EVIDENCE_ROOT = old_evidence_root

        self.assertIs(result["ok"], True)
        self.assertEqual(result["pass_id"], "20260917T205610")

    def test_postiz_reader_requests_limit_and_parses_valid_response(self):
        body = json.dumps({"posts": []}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=-1):
                return body

        with patch.object(self.adapter().urllib.request, "urlopen", return_value=Response()) as get:
            try:
                listing = self.adapter().read_postiz_listing(START, FINAL, api_key="fixture-key")
            except Exception as error:
                self.fail(f"valid Postiz response raised {type(error).__name__}")

        query = parse_qs(urlsplit(get.call_args.args[0].full_url).query)
        self.assertEqual(query["limit"], ["500"])
        self.assertEqual(query["startDate"], ["2026-09-17T11:56:09.000Z"])
        self.assertEqual(query["endDate"], ["2026-09-17T12:11:20.000Z"])
        self.assertIs(listing["ok"], True)
        self.assertEqual(listing["response_count"], 0)
        self.assertIs(listing["has_more"], False)
        proof = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), listing, now=FINAL,
        )
        self.assertIs(proof["verified"], True)

    def test_malformed_pagination_metadata_stays_fenced(self):
        cases = (
            {"posts": [], "total": "1"},
            {"posts": [], "hasMore": "true"},
            {"posts": [], "pagination": []},
            {"posts": [], "meta": []},
            {"posts": [], "has_more": 1},
            {"posts": [], "total": True},
            {"posts": [], "nextCursor": 123},
            {"posts": [], "pagination": {"page": 1, "totalPages": "2"}},
            {"posts": [], "pagination": {"page": 2, "totalPages": 2}},
            {"posts": [], "total": 0, "hasMore": True},
        )

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=-1):
                return self.body

        for payload in cases:
            with self.subTest(payload=payload):
                body = json.dumps(payload).encode()
                with patch.object(
                    self.adapter().urllib.request, "urlopen", return_value=Response(body),
                ):
                    listing = self.adapter().read_postiz_listing(
                        START, FINAL, api_key="fixture-key",
                    )
                proof = self.adapter().build_proof(
                    OCCURRENCE, events(), readback_only_evidence(), listing, now=FINAL,
                )
                self.assertIs(proof["verified"], False)

    def test_postiz_reader_marks_paged_response_incomplete(self):
        body = json.dumps({"posts": [], "total": 1,
                           "pagination": {"page": 1, "totalPages": 2},
                           "nextCursor": "next-page"}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=-1):
                return body

        with patch.object(self.adapter().urllib.request, "urlopen", return_value=Response()):
            try:
                listing = self.adapter().read_postiz_listing(START, FINAL, api_key="fixture-key")
            except Exception as error:
                self.fail(f"paged Postiz response raised {type(error).__name__}")

        self.assertIs(listing["has_more"], True)
        self.assertIsNone(self.adapter()._listing_posts(listing))

    def test_wrong_occurrence_and_ambiguous_runtime_pair_stay_fenced(self):
        wrong = events()
        wrong[1]["occurrence_id"] = f"{OWNER}:other-run"
        duplicate = events() + [events()[1]]
        wrong_run = events()
        wrong_run[1]["run_id"] = "other-run"
        wrong_run[1]["occurrence_id"] = f"{OWNER}:other-run"
        unsupported_release = events()
        unsupported_release[1]["release_sha"] = "0" * 40
        unsupported_provider = events()
        unsupported_provider[1]["provider"] = "unknown"

        for index, rows in enumerate((wrong, duplicate, wrong_run,
                                      unsupported_release, unsupported_provider)):
            with self.subTest(index=index):
                result = self.adapter().build_proof(
                    OCCURRENCE, rows, readback_only_evidence(), empty_listing(), now=FINAL,
                )
                self.assertIs(result["verified"], False)

    def test_adapter_accepts_a_different_occurrence_from_runtime_records(self):
        other_run = "18d619b58da7e748-16053"
        rows = events()
        for row in rows:
            row["run_id"] = other_run
            row["occurrence_id"] = f"{OWNER}:{other_run}"
        evidence = readback_only_evidence()
        evidence["pass_id"] = "20260917T205640"

        result = self.adapter().build_proof(
            f"{OWNER}:{other_run}", rows, evidence, empty_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], True)
        self.assertEqual(result["occurrence_id"], f"{OWNER}:{other_run}")

    def test_ambiguous_or_wrong_run_evidence_stays_fenced(self):
        late_evidence = readback_only_evidence()
        late_evidence["mtime"] = (REPORTED + dt.timedelta(seconds=1)).isoformat()
        wrong_mode = readback_only_evidence()
        wrong_mode["affiliate_job_reconcile"]["mode"] = "original"

        for evidence in (late_evidence, wrong_mode):
            with self.subTest(evidence=evidence):
                result = self.adapter().build_proof(
                    OCCURRENCE, events(), evidence, empty_listing(), now=FINAL,
                )
                self.assertIs(result["verified"], False)

    def test_stale_august_post_never_counts_as_occurrence_receipt(self):
        listing = published_listing(
            "old-august-post", "2026-08-28T14:02:37Z",
        )
        evidence = published_evidence("old-august-post")

        result = self.adapter().build_proof(
            OCCURRENCE, events(), evidence, listing, now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_post_in_rounded_query_margin_but_before_exact_start_stays_fenced(self):
        listing = published_listing(published_at="2026-09-17T11:56:09.400Z")

        result = self.adapter().build_proof(
            OCCURRENCE, events(), published_evidence(), listing, now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_target_window_post_without_exact_run_receipt_stays_fenced(self):
        result = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), published_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_reconcile_mode_readback_cannot_prove_new_publish_effect(self):
        evidence = published_evidence()
        evidence["post"]["mode"] = "reconcile"

        result = self.adapter().build_proof(
            OCCURRENCE, events(), evidence, published_listing(), now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_multiple_target_window_posts_are_ambiguous(self):
        listing = published_listing()
        listing["posts"].append({
            **listing["posts"][0],
            "id": "post-43",
            "releaseURL": "https://x.com/selawmqt/status/2094445556667778899",
        })
        listing["response_count"] = 2

        result = self.adapter().build_proof(
            OCCURRENCE, events(), published_evidence(), listing, now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_malformed_integration_row_makes_listing_incomplete(self):
        listing = {**empty_listing(), "posts": [{"id": "unknown-integration"}],
                   "response_count": 1}

        result = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), listing, now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_listing_at_or_above_500_is_incomplete(self):
        listing = {**empty_listing(), "response_count": 500,
                   "posts": [{"id": f"post-{index}"} for index in range(500)]}

        result = self.adapter().build_proof(
            OCCURRENCE, events(), readback_only_evidence(), listing, now=FINAL,
        )

        self.assertIs(result["verified"], False)

    def test_missing_or_malformed_listing_hash_stays_fenced(self):
        for listing in (None, {"ok": False},
                        {"ok": True, "posts": [], "response_count": 0}):
            with self.subTest(listing=listing):
                result = self.adapter().build_proof(
                    OCCURRENCE, events(), readback_only_evidence(), listing, now=FINAL,
                )
                self.assertIs(result["verified"], False)

    def test_resolve_is_called_only_after_verified_proof(self):
        calls = []

        def resolve(owner_id, occurrence_id, *, official_readback, expected_state):
            proof = official_readback()
            calls.append((owner_id, occurrence_id, expected_state, proof))
            return True

        def run(listing, evidence):
            return self.adapter().reconcile(
                OCCURRENCE,
                resolve=True,
                now=FINAL,
                events_fn=lambda _occurrence: events(),
                evidence_fn=lambda _start, _reported: evidence,
                postiz_fn=lambda _start, _end: listing,
                fenced_row_fn=lambda owner, occurrence: ("released", START.timestamp() + 0.048),
                resolve_fn=resolve,
            )

        verified = run(empty_listing(), readback_only_evidence())
        self.assertEqual(verified["closed"], True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], (OWNER, OCCURRENCE, "released"))
        self.assertIs(calls[0][3]["verified"], True)

        held = run({**empty_listing(), "response_count": 500}, readback_only_evidence())
        self.assertNotIn("closed", held)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
