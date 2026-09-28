from __future__ import annotations

import datetime as dt
import contextlib
import io
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("publication_ledger.py")
BINDING_PATH = Path(__file__).with_name("product_binding.py")
BINDING_SPEC = importlib.util.spec_from_file_location("product_binding", BINDING_PATH)
assert BINDING_SPEC and BINDING_SPEC.loader
binding = importlib.util.module_from_spec(BINDING_SPEC)
sys.modules[BINDING_SPEC.name] = binding
BINDING_SPEC.loader.exec_module(binding)
SPEC = importlib.util.spec_from_file_location("publication_ledger", MODULE_PATH)
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ledger
SPEC.loader.exec_module(ledger)


def post(identifier="p1", platform="instagram-standalone", state="PUBLISHED"):
    return {
        "id": identifier,
        "group": "g1",
        "state": state,
        "content": "  Full caption\ntext ",
        "publishDate": "2026-08-01T00:00:00Z",
        "releaseId": "native1" if state == "PUBLISHED" else None,
        "releaseURL": "https://www.instagram.com/reel/abc/" if state == "PUBLISHED" else None,
        "integration": {"id": "i1", "name": "account", "providerIdentifier": platform},
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def binding_registries(root: Path, *, integration_id: str = "integration-ebook-ja") -> tuple[Path, Path]:
    products = root / "products"
    accounts = root / "accounts"
    products.mkdir()
    accounts.mkdir()
    write_json(products / "ebook-ja.json", {"product_id": "ebook-ja"})
    write_json(
        accounts / "ebook-ja.json",
        {
            "account_id": "tiktok.obou_anicca",
            "product_id": "ebook-ja",
            "publisher_integration_id": integration_id,
        },
    )
    return products, accounts


def unbound_row(identifier: str, integration_id: str = "integration-ebook-ja") -> dict:
    value = post(identifier)
    value["publishDate"] = "2026-08-05T09:00:00Z"
    value["releaseId"] = f"native-{identifier}"
    value["integration"]["id"] = integration_id
    return ledger.make_row(value, [], "2026-08-01T01:00:00Z")


class PublicationLedgerTest(unittest.TestCase):
    def test_quality_gate_can_use_distinct_attention_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "publication-identity.jsonl"
            report = root / "report.json"

            result = ledger.main([
                "--bind-existing-only",
                "--output", str(output),
                "--report", str(report),
                "--quality-gate-exit-code", "3",
            ])

        self.assertEqual(result, 3)

    def test_live_reconcile_of_exact_tiktok_receipt_requires_no_paid_scraper(self):
        value = post(platform="tiktok")
        value["releaseId"] = "7669159327655054613"
        value["releaseURL"] = (
            "https://www.tiktok.com/@handle/video/7669159327655054613"
        )
        value["integration"]["id"] = "integration-ebook-ja"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "publication-identity.jsonl"
            report = root / "report.json"
            env = root / ".env"
            env.write_text("POSTIZ_API_KEY=test-only\n", encoding="utf-8")
            products, accounts = binding_registries(root)
            with mock.patch.object(ledger, "fetch_postiz_posts", return_value=[value]):
                result = ledger.main([
                    "--days", "8",
                    "--env-file", str(env),
                    "--output", str(output),
                    "--report", str(report),
                    "--product-registry", str(products),
                    "--account-registry", str(accounts),
                ])
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(result, 0)
        self.assertEqual(row["native_post_id"], "7669159327655054613")
        self.assertEqual(row["provenance"], ["postiz_public_api"])

    def test_profile_only_tiktok_receipt_uses_free_public_browser_snapshot(self):
        value = post(platform="tiktok")
        value["releaseId"] = "publish-token"
        value["releaseURL"] = "https://www.tiktok.com/@handle"
        value["integration"]["id"] = "integration-ebook-ja"
        public_item = {
            "id": "7669159327655054613",
            "webVideoUrl": "https://www.tiktok.com/@handle/video/7669159327655054613",
            "text": "Full caption text",
            "createTimeISO": "2026-08-01T00:00:10Z",
            "authorMeta": {"name": "handle"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "publication-identity.jsonl"
            report = root / "report.json"
            env = root / ".env"
            env.write_text("POSTIZ_API_KEY=test-only\n", encoding="utf-8")
            products, accounts = binding_registries(root)
            with (
                mock.patch.object(ledger, "fetch_postiz_posts", return_value=[value]),
                mock.patch.object(
                    ledger,
                    "fetch_tiktok_public_profiles",
                    return_value=[public_item],
                ) as free_fetch,
            ):
                result = ledger.main([
                    "--days", "8",
                    "--env-file", str(env),
                    "--output", str(output),
                    "--report", str(report),
                    "--product-registry", str(products),
                    "--account-registry", str(accounts),
                ])
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(result, 0)
        free_fetch.assert_called_once_with(["handle"], cdp_url="http://localhost:9222")
        self.assertEqual(row["identity_status"], "resolved")
        self.assertEqual(row["native_post_id"], "7669159327655054613")
        self.assertEqual(
            row["provenance"],
            ["postiz_public_api", "public_tiktok_profile_snapshot"],
        )

    def test_direct_provider_receipt_resolves(self):
        row = ledger.make_row(post(), [], "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "resolved")
        self.assertEqual(row["native_post_id"], "native1")
        self.assertEqual(row["resolution_method"], "postiz_provider_native_receipt")

    def test_error_is_retained_without_native_identity(self):
        row = ledger.make_row(post(state="ERROR"), [], "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "error")
        self.assertIsNone(row["native_post_id"])
        ledger.validate_rows([row])

    def test_tiktok_publish_token_is_not_treated_as_native_id(self):
        value = post(platform="tiktok")
        value["releaseId"] = "v_pub_file~v2-1.123456789"
        value["releaseURL"] = "https://www.tiktok.com/@handle"
        row = ledger.make_row(value, [], "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "unresolved")
        self.assertIsNone(row["native_post_id"])

    def test_tiktok_requires_unique_full_caption_and_time_match(self):
        value = post(platform="tiktok")
        value["releaseURL"] = "https://www.tiktok.com/@handle"
        item = {
            "id": "video1", "webVideoUrl": "https://www.tiktok.com/@handle/video/video1",
            "text": "Full caption text", "createTimeISO": "2026-08-01T00:00:10Z",
            "authorMeta": {"name": "handle"},
        }
        row = ledger.make_row(value, [item], "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "resolved")
        self.assertEqual(row["native_post_id"], "video1")

    def test_duplicate_tiktok_candidates_remain_ambiguous(self):
        value = post(platform="tiktok")
        value["releaseURL"] = "https://www.tiktok.com/@handle"
        items = [{
            "id": f"video{number}", "webVideoUrl": f"https://x/{number}",
            "text": "Full caption text", "createTimeISO": f"2026-08-01T00:00:0{number}Z",
            "authorMeta": {"name": "handle"},
        } for number in (1, 2)]
        row = ledger.make_row(value, items, "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "ambiguous")
        self.assertIsNone(row["native_post_url"])
        self.assertEqual(row["candidate_count"], 2)

    def test_reused_caption_resolves_when_only_one_exact_candidate_is_near_publish_time(self):
        value = post(platform="tiktok")
        value["releaseURL"] = "https://www.tiktok.com/@handle"
        items = [
            {
                "id": "old-video",
                "webVideoUrl": "https://www.tiktok.com/@handle/video/old-video",
                "text": "Full caption text",
                "createTimeISO": "2026-07-29T00:00:00Z",
                "authorMeta": {"name": "handle"},
            },
            {
                "id": "near-video",
                "webVideoUrl": "https://www.tiktok.com/@handle/video/near-video",
                "text": "Full caption text",
                "createTimeISO": "2026-08-01T00:00:10Z",
                "authorMeta": {"name": "handle"},
            },
        ]
        row = ledger.make_row(value, items, "2026-08-01T01:00:00Z")
        self.assertEqual(row["identity_status"], "resolved")
        self.assertEqual(row["native_post_id"], "near-video")
        self.assertEqual(row["candidate_count"], 1)

    def test_caption_hash_is_not_mislabeled_as_creative_hash(self):
        row = ledger.make_row(post(), [], "2026-08-01T01:00:00Z")
        self.assertIsNotNone(row["content_sha256"])
        self.assertIsNone(row["creative_sha256"])
        self.assertEqual(row["creative_sha256_null_reason"], "legacy_postiz_list_omits_asset_identity")

    def test_duplicate_native_identity_is_rejected(self):
        one = ledger.make_row(post("p1"), [], "2026-08-01T01:00:00Z")
        two = ledger.make_row(post("p2"), [], "2026-08-01T01:00:00Z")
        with self.assertRaisesRegex(ValueError, "duplicate native identity"):
            ledger.validate_rows([one, two])

    def test_merge_is_idempotent_by_postiz_id(self):
        one = ledger.make_row(post("p1"), [], "2026-08-01T01:00:00Z")
        newer = dict(one, observed_at="2026-08-01T02:00:00Z")
        rows = ledger.merge_rows([one], [newer])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["observed_at"], "2026-08-01T02:00:00Z")

    def test_merge_never_downgrades_resolved_identity_to_unresolved(self):
        existing = ledger.make_row(post("p1"), [], "2026-08-01T01:00:00Z")
        current_post = post("p1", platform="tiktok")
        current_post["releaseId"] = "publish-token"
        current_post["releaseURL"] = "https://www.tiktok.com/@handle"
        current = ledger.make_row(current_post, [], "2026-08-05T13:00:00Z")
        self.assertEqual(current["identity_status"], "unresolved")

        merged = ledger.merge_rows([existing], [current])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["identity_status"], "resolved")
        self.assertEqual(merged[0]["native_post_id"], "native1")
        self.assertEqual(
            merged[0]["resolution_method"], "postiz_provider_native_receipt"
        )
        self.assertEqual(merged[0]["observed_at"], "2026-08-05T13:00:00Z")

    def test_report_uses_only_published_denominator(self):
        published = ledger.make_row(post("p1"), [], "2026-08-01T01:00:00Z")
        error = ledger.make_row(post("p2", state="ERROR"), [], "2026-08-01T01:00:00Z")
        start = dt.datetime(2026, 7, 31, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc)
        report = ledger.reconciliation_report([published, error], start, end, "now")
        self.assertEqual(report["published_denominator"], 1)
        self.assertEqual(report["published_resolved"], 1)
        self.assertTrue(report["passes_95_percent_gate"])

    def test_bind_merged_rows_backfills_complete_ledger_and_keeps_unmatched_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products, accounts = binding_registries(root)
            legacy_unbound = unbound_row("legacy")
            current_unbound = unbound_row("current")
            merged = ledger.merge_rows([legacy_unbound], [current_unbound])

            bound, report = ledger.bind_merged_rows(
                merged, product_registry=products, account_registry=accounts
            )

            self.assertEqual(report["bound"], 2)
            self.assertEqual({row["product_id"] for row in bound}, {"ebook-ja"})
            self.assertTrue(
                all(row["account_id"] == "tiktok.obou_anicca" for row in bound)
            )
            self.assertTrue(all(row["product_id_null_reason"] is None for row in bound))

            unmatched, unmatched_report = ledger.bind_merged_rows(
                [unbound_row("unmatched", "integration-unknown")],
                product_registry=products,
                account_registry=accounts,
            )
            self.assertIsNone(unmatched[0]["product_id"])
            self.assertEqual(
                unmatched[0]["product_id_null_reason"],
                "account_manifest_integration_unmapped",
            )
            self.assertEqual(unmatched_report["unmapped"], 1)

    def test_identical_cli_runs_are_byte_equivalent_and_include_binding_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products, accounts = binding_registries(root, integration_id="integration-custom")
            posts_path = root / "posts.json"
            write_json(
                posts_path,
                [
                    {
                        **post("cli-one"),
                        "publishDate": "2026-08-05T09:00:00Z",
                        "releaseId": "native-cli-one",
                        "integration": {
                            "id": "integration-custom",
                            "name": "account",
                            "providerIdentifier": "instagram-standalone",
                        },
                    }
                ],
            )
            snapshot_path = root / "tiktok.json"
            write_json(snapshot_path, [])
            output = root / "publication-identity.jsonl"
            output.write_text(
                json.dumps(
                    unbound_row("legacy-cli", "integration-custom"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            report_path = root / "report.json"
            fixed_now = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)
            argv = [
                "--posts-fixture",
                str(posts_path),
                "--tiktok-snapshot",
                str(snapshot_path),
                "--output",
                str(output),
                "--report",
                str(report_path),
                "--account-registry",
                str(accounts),
                "--product-registry",
                str(products),
            ]
            with mock.patch.object(ledger, "utc_now", return_value=fixed_now):
                self.assertEqual(ledger.main(argv), 0)
            first_output = output.read_bytes()
            first_report = report_path.read_bytes()
            with mock.patch.object(ledger, "utc_now", return_value=fixed_now):
                self.assertEqual(ledger.main(argv), 0)
            self.assertEqual(output.read_bytes(), first_output)
            report = json.loads(first_report)
            self.assertEqual(len(ledger.read_jsonl(output)), 2)
            self.assertEqual(report["binding"]["bound"], 2)
            replay_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(replay_report["binding"]["bound"], 2)
            self.assertEqual(replay_report["binding"]["already_bound"], 1)

    def test_cli_uses_default_registries_through_binding_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            posts_path = root / "posts.json"
            default_integration = "cmo5s4edx00vgn10ygnu34a0n"
            write_json(
                posts_path,
                [
                    {
                        **post("default-registry"),
                        "publishDate": "2026-08-05T09:00:00Z",
                        "releaseId": "native-default",
                        "integration": {
                            "id": default_integration,
                            "name": "account",
                            "providerIdentifier": "tiktok",
                        },
                        "releaseURL": "https://www.tiktok.com/@obou_anicca/video/native-default",
                    }
                ],
            )
            snapshot_path = root / "tiktok.json"
            write_json(snapshot_path, [])
            output = root / "publication-identity.jsonl"
            report_path = root / "report.json"
            fixed_now = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)
            with mock.patch.object(ledger, "utc_now", return_value=fixed_now):
                self.assertEqual(
                    ledger.main(
                        [
                            "--posts-fixture",
                            str(posts_path),
                            "--tiktok-snapshot",
                            str(snapshot_path),
                            "--output",
                            str(output),
                            "--report",
                            str(report_path),
                        ]
                    ),
                    0,
                )
            row = ledger.read_jsonl(output)[0]
            self.assertEqual(row["product_id"], "ebook-ja")
            self.assertEqual(row["account_id"], "tiktok.obou_anicca")

    def test_bind_existing_only_skips_credentials_and_network_helpers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products, accounts = binding_registries(root, integration_id="integration-existing")
            output = root / "publication-identity.jsonl"
            report_path = root / "report.json"
            output.write_text(
                json.dumps(
                    unbound_row("existing", "integration-existing"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            fixed_now = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)
            stdout = io.StringIO()
            with (
                mock.patch.object(ledger, "utc_now", return_value=fixed_now),
                mock.patch.object(ledger, "load_env", side_effect=AssertionError("env loaded")),
                mock.patch.object(
                    ledger, "fetch_postiz_posts", side_effect=AssertionError("Postiz called")
                ),
                mock.patch.object(ledger, "http_json", side_effect=AssertionError("HTTP called")),
                contextlib.redirect_stdout(stdout),
            ):
                rc = ledger.main(
                    [
                        "--bind-existing-only",
                        "--output",
                        str(output),
                        "--report",
                        str(report_path),
                        "--account-registry",
                        str(accounts),
                        "--product-registry",
                        str(products),
                    ]
                )
            self.assertEqual(rc, 0)
            row = ledger.read_jsonl(output)[0]
            self.assertEqual(row["product_id"], "ebook-ja")
            self.assertEqual(row["product_id_null_reason"], None)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["binding"]["bound"], 1)
            self.assertEqual(json.loads(stdout.getvalue())["binding"]["bound"], 1)

    def test_conflicting_binding_fails_before_output_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products, accounts = binding_registries(root, integration_id="integration-conflict")
            output = root / "publication-identity.jsonl"
            report_path = root / "report.json"
            conflict = unbound_row("conflict", "integration-conflict")
            conflict["product_id"] = "ebook-en"
            original = json.dumps(conflict, ensure_ascii=False, sort_keys=True) + "\n"
            output.write_text(original, encoding="utf-8")
            posts_path = root / "posts.json"
            write_json(posts_path, [])
            with self.assertRaisesRegex(ValueError, "publication product binding conflict"):
                ledger.main(
                    [
                        "--posts-fixture",
                        str(posts_path),
                        "--output",
                        str(output),
                        "--report",
                        str(report_path),
                        "--account-registry",
                        str(accounts),
                        "--product-registry",
                        str(products),
                    ]
                )
            self.assertEqual(output.read_text(encoding="utf-8"), original)
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
