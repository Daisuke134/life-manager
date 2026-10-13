import json
import pathlib
import shutil
import tempfile
import unittest
import subprocess

from ebook_packs import load_ebook_packs
from product_router import RoutingError, canonical_product_id, load_registry
from variation import create_plan, eligible_hooks


ENGINE = pathlib.Path(__file__).resolve().parent.parent


class ProductRegistryTest(unittest.TestCase):
    def test_predecessor_product_ids_normalize_only_at_read_boundary(self):
        self.assertEqual(canonical_product_id("aniccaios"), "anicca-ios")
        self.assertEqual(canonical_product_id("honne"), "honne-ai")
        self.assertEqual(canonical_product_id("ebook-ja"), "ebook-ja")

    def test_registry_schemas_are_valid_draft_2020_12(self):
        import jsonschema
        schemas = {}
        for path in (ENGINE / "schemas").glob("*-manifest.schema.json"):
            schema = json.loads(path.read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            jsonschema.Draft202012Validator.check_schema(schema)
            schemas[path.name] = schema
        for path in (ENGINE / "registry" / "products").glob("*.json"):
            jsonschema.validate(json.loads(path.read_text()), schemas["product-manifest.schema.json"])
        for path in (ENGINE / "registry" / "accounts").glob("*.json"):
            jsonschema.validate(json.loads(path.read_text()), schemas["account-manifest.schema.json"])

    def test_canonical_router_has_no_legacy_hook_or_openclaw_dependency(self):
        legacy_terms = ["fixed" + "-strings-", "hookPool" + "-ja.txt", ".open" + "claw"]
        for path in [ENGINE / "gates" / "product_router.py", ENGINE / "gates" / "variation.py",
                     ENGINE / "bin" / "lm"]:
            source = path.read_text()
            for term in legacy_terms:
                self.assertNotIn(term, source, f"{term} found in {path}")

    def test_core_products_and_locked_accounts_validate(self):
        registry = load_registry(ENGINE)
        self.assertLessEqual({
            "anicca-ios", "honne-ai", "ebook-ja", "ebook-en", "life-manager-cloud",
        }, set(registry.products))
        self.assertGreaterEqual(len(registry.accounts), 9)
        for account in registry.accounts.values():
            self.assertIn(account["product_id"], registry.products)
            self.assertEqual(len(account["product_ids"]), 1)

    def test_life_manager_cloud_pack_uses_web_funnel_and_exact_trial_price(self):
        registry = load_registry(ENGINE)
        product = registry.products["life-manager-cloud"]
        self.assertEqual(product["type"], "web_app")
        self.assertEqual(product["destination_url"], "https://aniccaai.com/lm")
        self.assertEqual(product["price"], {
            "amount": 29, "currency": "USD", "basis": "monthly_after_7_day_card_required_trial",
        })
        self.assertIn("life-manager-web-funnel-report", product["metric_adapters"])
        self.assertIn("stripe", product["metric_adapters"])
        self.assertIn("google_connect_start", product["conversion_events"])
        self.assertIn("first_travel_block", product["conversion_events"])
        self.assertIn("paid_invoice", product["revenue_events"])
        self.assertTrue(any("does not read Gmail" in claim for claim in product["approved_claims"]))

    def test_mobile_jobs_and_marketing_registry_share_product_ids(self):
        registry = load_registry(ENGINE)
        mobile = json.loads(
            (ENGINE.parents[2] / "apps/life-manager/config/mobile-app-loops.json").read_text()
        )
        job_products = {row["product_id"] for row in mobile["loops"].values()}
        self.assertEqual(job_products, {"anicca-ios", "honne-ai"})
        self.assertLessEqual(job_products, set(registry.products))

    def test_accounts_lock_exact_postiz_provider_and_complete_settings(self):
        registry = load_registry(ENGINE)
        expected_provider = {
            "instagram.anicca_en": "instagram-standalone",
            "instagram.anicca_encards": "instagram-standalone",
            "instagram.anicca_ios": "instagram-standalone",
            "instagram.anicca_ios_jp": "instagram-standalone",
            "instagram.anicca_jp_videos": "instagram-standalone",
            "instagram.ani_cca1234": "instagram-standalone",
            "instagram.monk_anicca": None,
            "instagram.obou_anicca": "instagram-standalone",
            "tiktok.anicca_buddha": "tiktok",
            "tiktok.anicca_he": "tiktok",
            "tiktok.anicca_jp1": "tiktok",
            "tiktok.anicca_jp4": "tiktok",
            "tiktok.anicca_slideshow": "tiktok",
            "tiktok.anicca_jp": "tiktok",
            "tiktok.aniccaaffirmation": "tiktok",
            "tiktok.aniccaen2": "tiktok",
            "tiktok.honne_reveal": "tiktok",
            "tiktok.honnevideo": "tiktok",
            "tiktok.monk_anicca": "tiktok",
            "tiktok.obou_anicca": "tiktok",
            "youtube.anicca_ai": "youtube",
            "youtube.life_manager_m4p": "youtube",
        }
        self.assertEqual({key: row["publisher_provider"]
                          for key, row in registry.accounts.items()}, expected_provider)
        for row in registry.accounts.values():
            settings = row["publisher_settings"]
            if row["publisher_provider"] is None:
                self.assertIsNone(settings)
            elif row["publisher_provider"] == "tiktok":
                self.assertEqual(set(settings), {
                    "__type", "title", "privacy_level", "duet", "stitch", "comment",
                    "autoAddMusic", "brand_content_toggle", "brand_organic_toggle",
                    "video_made_with_ai", "content_posting_method",
                })
            elif row["publisher_provider"] == "instagram-standalone":
                self.assertEqual(settings, {"__type": "instagram-standalone",
                    "post_type": "post", "is_trial_reel": False, "collaborators": []})
            elif row["publisher_provider"] == "youtube":
                self.assertEqual(set(settings), {"__type", "title", "type",
                                                  "selfDeclaredMadeForKids", "thumbnail", "tags"})

    def test_duplicate_native_account_or_mixed_product_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = ENGINE / "registry"
            (root / "registry" / "products").mkdir(parents=True)
            (root / "registry" / "accounts").mkdir(parents=True)
            for path in (source / "products").glob("*.json"):
                (root / "registry" / "products" / path.name).write_bytes(path.read_bytes())
            (root / "registry" / "renderers.json").write_bytes(
                (source / "renderers.json").read_bytes())
            account = json.loads(next((source / "accounts").glob("*.json")).read_text())
            account["product_ids"] = [account["product_id"], "honne-ai"]
            (root / "registry" / "accounts" / "bad.json").write_text(json.dumps(account))
            with self.assertRaisesRegex(RoutingError, "exactly one product"):
                load_registry(root)

    def test_watercolor_and_monk_renderer_product_boundaries(self):
        registry = load_registry(ENGINE)
        for account in registry.accounts.values():
            formats = set(account["allowed_renderer_ids"])
            if "watercolor-monk" in formats:
                self.assertEqual(account["product_id"], "ebook-ja")
            if "heygen-avatar-iv" in formats:
                self.assertEqual(account["product_id"], "ebook-en")

    def test_english_ebook_pack_uses_two_daily_slots(self):
        packs = load_ebook_packs(ENGINE)
        self.assertEqual(packs["ebook-en-anicca-monk"]["slots_jst"], ["08:00", "21:00"])


class MarketplaceProductProfileTest(unittest.TestCase):
    @staticmethod
    def _marketplace_product_fixture():
        product = json.loads(
            (ENGINE / "registry" / "products" / "life-manager-cloud.json")
            .read_text(encoding="utf-8")
        )
        product["product_id"] = "hook-lab"
        product["type"] = "marketplace_agent"
        product["distribution_profile"] = {
            "economic_role": "customer_revenue",
            "related_loop_id": "capafy",
            "buyer_problem": {
                "statement": "Creators lose viewers before the second sentence.",
                "source_ref": "test://listing",
                "validation_status": "seller_copy_unvalidated",
            },
            "offer_snapshot": {
                "seller_agent_id": "8123079349",
                "published_version": "v1.0.7",
                "observed_at": "2026-10-13T17:40:00+09:00",
                "frozen": True,
                "trial_days": 0,
                "price_tiers": [
                    {"period": "day", "amount": 3.99, "currency": "USD", "cap": 10},
                    {"period": "week", "amount": 9.99, "currency": "USD", "cap": 30},
                    {"period": "month", "amount": 19.99, "currency": "USD", "cap": 80},
                ],
                "source_refs": ["test://offer"],
                "source_conflicts": [{
                    "source_ref": "test://stale-listing",
                    "detail": "Stale price table conflicts with official offer.",
                    "resolution": "official_detail_snapshot_preferred",
                }],
            },
            "allowed_channel_accounts": [{
                "account_ref": "life-manager-capafy-ig",
                "platform": "instagram",
                "native_handle": "@capafy.hooklab",
                "publisher_integration_id": "test-postiz",
                "campaign_token": "hooklab_ig",
                "last_observed_at": "2026-10-13T19:00:00+09:00",
                "operational_status": "disabled_last_observed_current_unverified",
                "publish_enabled": False,
            }],
            "destination": {
                "url": "https://capafy.ai/agent/8123079349",
                "campaign_token": "hooklab_ig",
                "per_slot_attribution": "shared_token_not_per_slot",
                "source_ref": "test://destination",
            },
            "outcome_sources": [
                {"metric": "capafy_impressions", "source": "Capafy traffic-sources v2",
                 "status": "available", "attribution_granularity": "channel_window",
                 "source_ref": "test://traffic"},
                {"metric": "settled_net_contribution", "source": "Official order receipt join",
                 "status": "unknown", "attribution_granularity": "occurrence_bound",
                 "source_ref": "test://settlement"},
                {"metric": "actual_model_cost", "source": "Provider usage receipt join",
                 "status": "unknown", "attribution_granularity": "occurrence_bound",
                 "source_ref": "test://cost"},
            ],
        }
        return product

    def test_hook_lab_marketplace_profile_is_frozen_and_not_routable(self):
        registry = load_registry(ENGINE)
        product = registry.products["hook-lab"]
        profile = product["distribution_profile"]
        offer = profile["offer_snapshot"]

        self.assertEqual(product["product_id"], "hook-lab")
        self.assertEqual(product["type"], "marketplace_agent")
        self.assertEqual(product["price"], {
            "amount": 3.99, "currency": "USD",
            "basis": "starting_day_plan_full_schedule_in_distribution_profile",
        })
        self.assertEqual(profile["economic_role"], "customer_revenue")
        self.assertEqual(profile["related_loop_id"], "capafy")
        self.assertEqual(profile["buyer_problem"]["validation_status"],
                         "seller_copy_unvalidated")
        self.assertIn("viewers swipe before the second sentence",
                      profile["buyer_problem"]["statement"])

        self.assertEqual(offer["seller_agent_id"], "8123079349")
        self.assertEqual(offer["published_version"], "v1.0.7")
        self.assertEqual(offer["observed_at"], "2026-10-13T17:40:00+09:00")
        self.assertTrue(offer["frozen"])
        self.assertEqual(offer["trial_days"], 0)
        self.assertEqual(offer["price_tiers"], [
            {"period": "day", "amount": 3.99, "currency": "USD", "cap": 10},
            {"period": "week", "amount": 9.99, "currency": "USD", "cap": 30},
            {"period": "month", "amount": 19.99, "currency": "USD", "cap": 80},
        ])
        self.assertTrue(any(
            row["source_ref"] == "skills/capafy/catalog/hook-lab/LISTING.md#pricing"
            and "$1.99" in row["detail"] and "$4.99" in row["detail"]
            and "$9.99" in row["detail"]
            for row in offer["source_conflicts"]
        ))

        channel = profile["allowed_channel_accounts"][0]
        self.assertEqual(channel["account_ref"], "life-manager-capafy-ig")
        self.assertEqual(channel["platform"], "instagram")
        self.assertEqual(channel["native_handle"], "@capafy.hooklab")
        self.assertEqual(channel["publisher_integration_id"], "cmuuycr5402uzqw0yhanqggo9")
        self.assertEqual(channel["campaign_token"], "hooklab_ig")
        self.assertFalse(channel["publish_enabled"])

        destination = profile["destination"]
        self.assertEqual(destination["url"], "https://capafy.ai/agent/8123079349")
        self.assertEqual(destination["campaign_token"], "hooklab_ig")
        self.assertEqual(destination["per_slot_attribution"], "shared_token_not_per_slot")
        self.assertEqual(product["primary_metric"], "settled_net_contribution")
        self.assertEqual(profile["outcome_sources"][0]["metric"], "capafy_impressions")
        self.assertEqual(next(row["status"] for row in profile["outcome_sources"]
                              if row["metric"] == "settled_net_contribution"), "unknown")
        self.assertEqual(next(row["status"] for row in profile["outcome_sources"]
                              if row["metric"] == "actual_model_cost"), "unknown")
        self.assertNotIn("hook-lab", {
            row["product_id"] for row in registry.accounts.values()
        })

    def test_marketplace_profile_missing_offer_or_outcome_source_fails_closed(self):
        for mutation, expected_error in (
            ("published_version", "offer"),
            ("settled_net_contribution", "outcome_sources"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                shutil.copytree(ENGINE / "registry", root / "registry")
                profile_path = root / "registry" / "products" / "hook-lab.json"
                product = self._marketplace_product_fixture()
                profile = product["distribution_profile"]
                if mutation == "published_version":
                    profile["offer_snapshot"].pop("published_version")
                else:
                    profile["outcome_sources"] = [
                        row for row in profile["outcome_sources"]
                        if row["metric"] != mutation
                    ]
                profile_path.write_text(json.dumps(product), encoding="utf-8")

                with self.assertRaisesRegex(RoutingError, expected_error):
                    load_registry(root)

class VariationPlanTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(ENGINE)
        self.hooks = ENGINE / "intel" / "hook-library.jsonl"

    def test_only_exact_product_language_hooks_are_eligible(self):
        en = eligible_hooks(self.registry, self.hooks, "ebook-en", "tiktok.monk_anicca")
        ja = eligible_hooks(self.registry, self.hooks, "ebook-ja", "tiktok.obou_anicca")
        self.assertGreaterEqual(len(en), 5)
        self.assertGreaterEqual(len(ja), 6)
        self.assertTrue(all(row["product_ids"] == ["ebook-en"] and row["language"] == "en"
                            for row in en))
        self.assertTrue(all(row["product_ids"] == ["ebook-ja"] and row["language"] == "ja"
                            for row in ja))
        self.assertEqual(eligible_hooks(self.registry, self.hooks, "anicca-ios",
                                        "tiktok.anicca_jp"), [])

    def test_cross_product_account_and_renderer_are_rejected(self):
        hook_id = eligible_hooks(self.registry, self.hooks, "ebook-en",
                                 "tiktok.monk_anicca")[0]["id"]
        with self.assertRaisesRegex(RoutingError, "account product mismatch"):
            create_plan(self.registry, self.hooks, product_id="ebook-en",
                        account_id="tiktok.obou_anicca", hook_id=hook_id,
                        tactic_id="tactic.faceless-visual-refresh-captions.v1",
                        renderer_id="heygen-avatar-iv", idempotency_key="test-1")
        with self.assertRaisesRegex(RoutingError, "renderer not allowed"):
            create_plan(self.registry, self.hooks, product_id="ebook-en",
                        account_id="tiktok.monk_anicca", hook_id=hook_id,
                        tactic_id="tactic.faceless-visual-refresh-captions.v1",
                        renderer_id="watercolor-monk", idempotency_key="test-1")

    def test_plan_is_idempotent_and_has_full_attribution_tuple(self):
        hook_id = eligible_hooks(self.registry, self.hooks, "ebook-en",
                                 "tiktok.monk_anicca")[0]["id"]
        args = dict(product_id="ebook-en", account_id="tiktok.monk_anicca",
                    hook_id=hook_id,
                    tactic_id="tactic.faceless-visual-refresh-captions.v1",
                    renderer_id="heygen-avatar-iv", idempotency_key="gate10-live-safe-en")
        first = create_plan(self.registry, self.hooks, **args)
        second = create_plan(self.registry, self.hooks, **args)
        self.assertEqual(first, second)
        self.assertEqual(set(first) >= {
            "experiment_id", "creative_id", "product_id", "account_id",
            "hook_id", "tactic_id", "renderer_id", "cta", "destination_url",
            "primary_metric", "attribution_method", "status",
        }, True)
        self.assertEqual(first["status"], "planned")
        changed = create_plan(self.registry, self.hooks, **{**args, "idempotency_key": "other"})
        self.assertNotEqual(first["experiment_id"], changed["experiment_id"])
        self.assertNotEqual(first["creative_id"], changed["creative_id"])

    def test_recent_history_excludes_hook_by_id(self):
        hooks = eligible_hooks(self.registry, self.hooks, "ebook-en", "tiktok.monk_anicca")
        with tempfile.TemporaryDirectory() as tmp:
            history = pathlib.Path(tmp) / "history.jsonl"
            history.write_text(json.dumps({
                "account_id": "tiktok.monk_anicca", "hook_id": hooks[0]["id"],
                "planned_at": "2099-01-01T00:00:00Z",
            }) + "\n")
            remaining = eligible_hooks(self.registry, self.hooks, "ebook-en",
                                       "tiktok.monk_anicca", history_path=history,
                                       now="2099-01-02T00:00:00Z")
            self.assertNotIn(hooks[0]["id"], {row["id"] for row in remaining})

    def test_lm_exposes_canonical_creative_candidates(self):
        result = subprocess.run([
            str(ENGINE / "bin" / "lm"), "creative", "candidates",
            "--product", "ebook-en", "--account", "tiktok.monk_anicca",
        ], check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "success")
        self.assertGreaterEqual(len(payload["candidates"]), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
