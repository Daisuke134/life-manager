from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "composition_owner.py"


class CompositionOwnerTests(unittest.TestCase):
    def test_english_composition_uses_case_study_patterns_and_japanese_subtitles(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            prompt = module.prompt_for(state, {
                "locale": "en", "plan_id": "new-en", "sources": [],
            })
            case_text = "Official first-person affiliate case study fixture."
            case_hash = hashlib.sha256(case_text.encode()).hexdigest()
            case_dir = state / "sources" / "elevenlabs-alec"
            case_dir.mkdir(parents=True)
            (case_dir / f"{case_hash}.md").write_text(case_text, encoding="utf-8")
            case_study_prompt = module.prompt_for(state, {
                "locale": "en", "plan_id": "new-en",
                "sources": [{
                    "source_id": "elevenlabs-alec",
                    "locator": "https://elevenlabs.io/blog/alec-wilcock-on-becoming-a-top-affiliate-for-elevenlabs",
                    "evidence_class": "first_person_case",
                    "raw_sha256": case_hash,
                }],
            })
        self.assertIn("English as the primary language", prompt)
        self.assertIn("Japanese subtitle/summary", prompt)
        self.assertIn("800–1,200 English words", prompt)
        self.assertIn("Never pad or invent", prompt)
        self.assertIn("decision-stage search query", prompt)
        self.assertIn("workflow tutorial", prompt)
        self.assertIn("above the fold", prompt)
        self.assertIn("workflow tutorial", case_study_prompt)
        self.assertIn("single disclosed CTA above the fold after a short intro", case_study_prompt)
        self.assertIn("not guarantees", case_study_prompt)

    def test_experiment_preserves_control_and_uses_fixed_bilingual_format(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            control = {
                "receipt_type": "CAMPAIGN_HANDOFF",
                "state": "READY_FOR_POLICY",
                "plan_id": "control-en",
                "title": "Control title",
                "owned_article_markdown": "English control body.",
            }
            control["handoff_fingerprint"] = hashlib.sha256(json.dumps(
                control, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            handoffs = state / "campaign-handoffs"
            handoffs.mkdir()
            (handoffs / "control-en.json").write_text(json.dumps(control), encoding="utf-8")
            policies = state / "campaign-policy"
            policies.mkdir()
            (policies / "control-en.json").write_text(json.dumps({
                "decision": "PASS",
                "handoff_fingerprint": control["handoff_fingerprint"],
            }), encoding="utf-8")
            case_text = "Official first-person affiliate case study fixture."
            case_hash = hashlib.sha256(case_text.encode()).hexdigest()
            case_dir = state / "sources" / "elevenlabs-alec"
            case_dir.mkdir(parents=True)
            (case_dir / f"{case_hash}.md").write_text(case_text, encoding="utf-8")
            prompt = module.prompt_for(state, {
                "locale": "en", "plan_id": "control-en-experiment-1",
                "sources": [{
                    "source_id": "elevenlabs-alec",
                    "locator": "https://elevenlabs.io/blog/alec-wilcock-on-becoming-a-top-affiliate-for-elevenlabs",
                    "evidence_class": "first_person_case",
                    "raw_sha256": case_hash,
                }],
                "experiment": {
                    "decision_id": "decision-1",
                    "control_plan_id": "control-en",
                    "selected_variable": "title",
                    "instruction": "Change only the title.",
                    "hypothesis": "A title change could improve discovery.",
                    "success_metric": "exact-placement transaction_count >= 1",
                },
            })
        self.assertIn("Change only `title`", prompt)
        self.assertIn("Japanese subtitle/summary", prompt)
        self.assertIn("selected variable", prompt)
        self.assertIn("preserve the control", prompt)

    def test_compact_nested_experiment_lineage_is_accepted(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        experiment = {
            "decision_id": "c682536aed63" + "0" * 52,
            "control_plan_id": (
                "elevenlabs-discovered-subtitle-translator-en-"
                "experiment-1ecf26fe47e1"
            ),
        }
        self.assertTrue(module.experiment_plan_matches(
            "elevenlabs-discovered-subtitle-translator-en-experiment-c682536aed63",
            experiment,
        ))

    def test_budget_retry_after_is_next_jst_midnight(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(
            module.agent_runner.budget_retry_after({
                "budget": {"day": "2026-08-21"},
            }),
            "2026-08-21T15:00:00+00:00",
        )

    def test_budget_retry_becomes_due_on_a_new_jst_day(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            config = root / "config"
            config.mkdir(parents=True)
            (config / "agent-runner.json").write_text(json.dumps({
                "task_classes": {"marketing-agent": {"token_reservation": 32768}},
            }))
            bundle = {"plan_id": "alpha-en", "source_set_sha256": "a" * 64}
            run = state / "composition-runs" / f"alpha-en-{'a' * 16}"
            run.mkdir(parents=True)
            (run / "summary.json").write_text(json.dumps({
                "status": "budget_blocked",
                "budget": {
                    "day": "2026-08-16", "daily_consumed_tokens": 101310,
                    "daily_limit_tokens": 131072,
                },
            }))
            same_day = datetime.fromisoformat("2026-08-16T12:00:00+09:00")
            next_day = datetime.fromisoformat("2026-08-17T00:00:00+09:00")
            self.assertFalse(module.budget_retry_is_due(root, state, bundle, same_day))
            self.assertTrue(module.budget_retry_is_due(root, state, bundle, next_day))

    def test_wake_prioritizes_due_budget_retry_before_fresh_draft(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skill"
            (skill / "config").mkdir(parents=True)
            (skill / "config" / "agent-runner.json").write_text(json.dumps({
                "task_classes": {"marketing-agent": {"token_reservation": 32768}},
            }), encoding="utf-8")
            state = root / "state"
            inbox = state / "composition-inbox"
            inbox.mkdir(parents=True)
            retry_bundle = {
                "schema_version": 1, "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "z-retry-en", "locale": "en",
                "source_set_sha256": "a" * 64, "sources": [],
            }
            fresh_bundle = {
                "schema_version": 1, "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "a-fresh-en", "locale": "en",
                "source_set_sha256": "b" * 64, "sources": [],
            }
            (inbox / "z-retry-en.json").write_text(json.dumps(retry_bundle), encoding="utf-8")
            (inbox / "a-fresh-en.json").write_text(json.dumps(fresh_bundle), encoding="utf-8")
            receipts = state / "composition-receipts"
            receipts.mkdir()
            (receipts / "z-retry-en.json").write_text(json.dumps({
                "state": "FAILED", "failure_class": "RUNNER_REJECTED",
                "source_set_sha256": "a" * 64,
            }), encoding="utf-8")
            run = state / "composition-runs" / f"z-retry-en-{'a' * 16}"
            run.mkdir(parents=True)
            (run / "summary.json").write_text(json.dumps({
                "status": "budget_blocked",
                "budget": {
                    "day": "2000-01-01", "daily_consumed_tokens": 131072,
                    "daily_limit_tokens": 131072,
                },
            }), encoding="utf-8")
            selected: list[str] = []

            def run_model(_skill_root, _state_root, bundle):
                selected.append(bundle["plan_id"])
                return {
                    "state": "READY_FOR_POLICY", "plan_id": bundle["plan_id"],
                    "locale": bundle["locale"],
                    "source_set_sha256": bundle["source_set_sha256"],
                    "result_sha256": "c" * 64,
                }

            with mock.patch.object(
                module, "runtime_guard", return_value={"state": "CLEAR"},
            ):
                result = module.wake(
                    skill, state, run_model=run_model,
                    handoff_builder=mock.Mock(return_value="d" * 64),
                    policy_builder=mock.Mock(return_value="e" * 64),
                )

        self.assertEqual(selected, ["z-retry-en"])
        self.assertEqual(result["plan_id"], "z-retry-en")

    def test_wake_prioritizes_capability_retry_before_fresh_draft(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skill"
            (skill / "config").mkdir(parents=True)
            (skill / "config" / "agent-runner.json").write_text(json.dumps({
                "task_classes": {"marketing-agent": {"token_reservation": 32768}},
            }), encoding="utf-8")
            state = root / "state"
            inbox = state / "composition-inbox"
            inbox.mkdir(parents=True)
            retry_bundle = {
                "schema_version": 1, "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "z-capability-retry-en", "locale": "en",
                "source_set_sha256": "a" * 64, "sources": [],
            }
            fresh_bundle = {
                "schema_version": 1, "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "a-fresh-en", "locale": "en",
                "source_set_sha256": "b" * 64, "sources": [],
            }
            (inbox / "z-capability-retry-en.json").write_text(
                json.dumps(retry_bundle), encoding="utf-8"
            )
            (inbox / "a-fresh-en.json").write_text(json.dumps(fresh_bundle), encoding="utf-8")
            receipts = state / "composition-receipts"
            receipts.mkdir()
            (receipts / "z-capability-retry-en.json").write_text(json.dumps({
                "state": "FAILED", "failure_class": "RUNNER_REJECTED",
                "source_set_sha256": "a" * 64, "runner_capability_sha256": "0" * 64,
            }), encoding="utf-8")
            machine = state / "machine"
            machine.mkdir()
            (machine / "codex-capability.json").write_text(json.dumps({
                "status": "READY", "capability": "repaired",
            }), encoding="utf-8")
            selected: list[str] = []

            def run_model(_skill_root, _state_root, bundle):
                selected.append(bundle["plan_id"])
                return {
                    "state": "READY_FOR_POLICY", "plan_id": bundle["plan_id"],
                    "locale": bundle["locale"],
                    "source_set_sha256": bundle["source_set_sha256"],
                    "result_sha256": "c" * 64,
                }

            with mock.patch.object(
                module, "runtime_guard", return_value={"state": "CLEAR"},
            ):
                result = module.wake(
                    skill, state, run_model=run_model,
                    handoff_builder=mock.Mock(return_value="d" * 64),
                    policy_builder=mock.Mock(return_value="e" * 64),
                )

        self.assertEqual(selected, ["z-capability-retry-en"])
        self.assertEqual(result["plan_id"], "z-capability-retry-en")

    def test_wake_advances_only_one_due_source_set_and_dedupes_terminal_receipt(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            inbox = state / "composition-inbox"
            inbox.mkdir(parents=True)
            bundle = {
                "schema_version": 1,
                "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "alpha-en",
                "locale": "en",
                "source_set_sha256": "a" * 64,
                "sources": [],
            }
            (inbox / "alpha-en.json").write_text(json.dumps(bundle), encoding="utf-8")
            completed = {
                "state": "READY_FOR_POLICY",
                "plan_id": "alpha-en",
                "locale": "en",
                "source_set_sha256": "a" * 64,
                "result_sha256": "b" * 64,
            }
            run_model = mock.Mock(return_value=completed)
            build_handoff = mock.Mock(return_value="c" * 64)
            build_policy = mock.Mock(return_value="d" * 64)

            with mock.patch.object(
                module, "runtime_guard", return_value={"state": "DISK_GUARD_UNKNOWN"},
            ) as guard:
                first = module.wake(
                    root, state, run_model=run_model, handoff_builder=build_handoff,
                    policy_builder=build_policy,
                )
            guard.assert_called_once()
            second = module.wake(
                root, state, run_model=run_model, handoff_builder=build_handoff,
                policy_builder=build_policy,
            )
            third = module.wake(
                root, state, run_model=run_model, handoff_builder=build_handoff,
                policy_builder=build_policy,
            )

            self.assertEqual(first["state"], "READY_FOR_POLICY")
            self.assertEqual(second["policy_sha256"], "d" * 64)
            self.assertEqual(third["state"], "IDLE")
            self.assertEqual(run_model.call_count, 1)
            self.assertEqual(build_handoff.call_count, 1)
            self.assertEqual(build_policy.call_count, 1)
            receipt = json.loads(
                (state / "composition-receipts" / "alpha-en.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["source_set_sha256"], "a" * 64)
            self.assertEqual(receipt["handoff_sha256"], "c" * 64)
            self.assertEqual(receipt["policy_sha256"], "d" * 64)

    def test_published_campaign_never_spends_a_composition_pass(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            inbox = state / "composition-inbox"
            inbox.mkdir(parents=True)
            posts = state / "x-posts"
            posts.mkdir(parents=True)
            receipts = state / "composition-receipts"
            receipts.mkdir(parents=True)
            for plan_id, published in (("alpha-en", True), ("beta-en", False)):
                (inbox / f"{plan_id}.json").write_text(json.dumps({
                    "schema_version": 1, "receipt_type": "COMPOSITION_INPUT",
                    "plan_id": plan_id, "locale": "en",
                    # Sources were refreshed, so the stored receipt hash is stale.
                    "source_set_sha256": "f" * 64, "sources": [],
                }), encoding="utf-8")
                (receipts / f"{plan_id}.json").write_text(json.dumps({
                    "state": "READY_FOR_POLICY", "plan_id": plan_id, "locale": "en",
                    "source_set_sha256": "a" * 64,
                }), encoding="utf-8")
                if published:
                    (posts / f"{plan_id}-1.json").write_text(json.dumps({
                        "state": "LIVE",
                        "public_url": "https://x.com/selawmqt/status/1",
                    }), encoding="utf-8")

            run_model = mock.Mock(return_value={
                "state": "READY_FOR_POLICY", "plan_id": "beta-en", "locale": "en",
                "source_set_sha256": "f" * 64, "result_sha256": "b" * 64,
            })
            result = module.wake(
                root, state, run_model=run_model,
                handoff_builder=mock.Mock(return_value="c" * 64),
                policy_builder=mock.Mock(return_value="d" * 64),
            )

            # The already-live campaign is skipped despite its stale hash, so the
            # single daily pass goes to the campaign that still needs one.
            self.assertEqual(run_model.call_count, 1)
            self.assertEqual(run_model.call_args.args[2]["plan_id"], "beta-en")
            self.assertEqual(result["plan_id"], "beta-en")

    def test_build_policy_writes_one_hash_bound_pass_receipt(self) -> None:
        spec = importlib.util.spec_from_file_location("affiliate_composition_owner", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            raw = b"Official product documentation for the benchmark."
            raw_sha256 = hashlib.sha256(raw).hexdigest()
            source = {
                "source_id": "official-product",
                "locator": "https://example.com/official",
                "evidence_class": "official_product",
                "raw_sha256": raw_sha256,
            }
            source_set_sha256 = hashlib.sha256(json.dumps(
                [source], sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            bundle = {
                "schema_version": 1,
                "receipt_type": "COMPOSITION_INPUT",
                "plan_id": "alpha-en",
                "locale": "en",
                "source_set_sha256": source_set_sha256,
                "sources": [source],
            }
            source_dir = state / "sources" / source["source_id"]
            source_dir.mkdir(parents=True)
            (source_dir / f"{raw_sha256}.md").write_bytes(raw)
            (source_dir / "latest.json").write_text(json.dumps({
                **source,
                "schema_version": 1,
                "receipt_type": "SOURCE_CAPTURE",
                "plan_id": "alpha-en",
                "locale": "en",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }), encoding="utf-8")
            plan_dir = root / "config" / "source-plans"
            plan_dir.mkdir(parents=True)
            (plan_dir / "alpha-en.json").write_text(json.dumps({
                "plan_id": "alpha-en",
                "locale": "en",
                "offer_id": "alpha-offer",
                "buyer_intent": "Buyers comparing the documented product",
                "slug": "alpha-product-guide",
            }), encoding="utf-8")
            article = (
                "A buyer should benchmark the documented product before paying. " * 14
                + "[Official source](https://example.com/official)\n\n"
                + module.DISCLOSURE
                + "\n\n[Review the product]({{AFFILIATE_LINK}})"
            )
            handoff = {
                "schema_version": 1,
                "receipt_type": "CAMPAIGN_HANDOFF",
                "state": "READY_FOR_POLICY",
                "plan_id": "alpha-en",
                "offer_id": "alpha-offer",
                "locale": "en",
                "buyer_intent": "Buyers comparing the documented product",
                "title": "Alpha Product Guide",
                "slug": "alpha-product-guide",
                "owned_article_markdown": article,
                "disclosure": module.DISCLOSURE,
                "cta_placeholder": "{{AFFILIATE_LINK}}",
                "cited_sources": [{
                    "source_id": source["source_id"],
                    "locator": source["locator"],
                    "raw_sha256": raw_sha256,
                }],
                "x_copy": "Affiliate link disclosure: Alpha Product Guide\n\n{{OWNED_ARTICLE_URL}}",
                "source_set_sha256": source_set_sha256,
                "content_fingerprint": hashlib.sha256(article.encode()).hexdigest(),
                "result_fingerprint": "b" * 64,
            }
            handoff["handoff_fingerprint"] = hashlib.sha256(json.dumps(
                handoff, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            handoff_path = state / "campaign-handoffs" / "alpha-en.json"
            handoff_path.parent.mkdir(parents=True)
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            handoff_sha256 = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
            audit_runner = mock.Mock(return_value={
                "decision": "PASS",
                "unsupported_claims": [],
                "rationale": "Every material claim is supported by the supplied source.",
                "result_sha256": "e" * 64,
                "evidence_dir": str(state / "policy-runs" / "alpha-en"),
                "execution": {"selected_model": "gpt-5.6-terra"},
            })

            policy_sha256 = module.build_policy(
                root, state, bundle,
                {"handoff_sha256": handoff_sha256},
                audit_runner=audit_runner,
            )

            policy_path = state / "campaign-policy" / "alpha-en.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(policy_sha256, hashlib.sha256(policy_path.read_bytes()).hexdigest())
            self.assertEqual(policy["decision"], "PASS")
            self.assertTrue(all(policy["checks"].values()))
            self.assertEqual(policy["handoff_sha256"], handoff_sha256)
            self.assertEqual(audit_runner.call_count, 1)

            (source_dir / f"{raw_sha256}.md").write_bytes(b"tampered")
            failed_sha256 = module.build_policy(
                root, state, bundle,
                {"handoff_sha256": handoff_sha256},
                audit_runner=audit_runner,
            )
            failed = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(failed_sha256, hashlib.sha256(policy_path.read_bytes()).hexdigest())
            self.assertEqual(failed["decision"], "FAIL")
            self.assertFalse(failed["checks"]["source_artifacts"])
            self.assertEqual(audit_runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
