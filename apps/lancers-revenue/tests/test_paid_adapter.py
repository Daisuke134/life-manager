from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "skills/earn/lancers/scripts/paid_adapter.py"
OWNER = ROOT / "skills/earn/lancers/scripts/paid-owner"


def load():
    spec = importlib.util.spec_from_file_location("lancers_paid_adapter_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LancersPaidAdapterTests(unittest.TestCase):
    def test_owner_enters_shared_kernel_before_reporting(self):
        source = OWNER.read_text(encoding="utf-8")
        kernel = 'skills/_shared/marketplace-core/scripts/paid_kernel.py'
        adapter = 'skills/earn/lancers/scripts/paid_adapter.py'
        reporter = 'skills/earn/lancers/scripts/lane_report.py'
        self.assertIn(kernel, source)
        self.assertIn(adapter, source)
        self.assertLess(source.index(kernel), source.index(reporter))
        self.assertIn('--state-root "$STATE_ROOT/paid"', source)
        self.assertIn('--output "$PAID_OUTPUT"', source)

    def test_build_uses_paid_scoped_official_inventory(self):
        source = PATH.read_text(encoding="utf-8")
        self.assertIn("work_sync.read_paid_inventory", source)
        self.assertNotIn("work_sync.read_only_inventory", source)

    def test_build_wires_provider_for_funded_effects(self):
        module = load()
        adapter, _decide = module.build(["--account-id", "seller-1"])
        self.assertIsNotNone(adapter.provider)

    def test_maps_every_contract_candidate_without_claiming_funding(self):
        module = load()
        snapshot = {
            "ok": True,
            "source_complete": True,
            "contract_candidates": [
                {"source_kind": "project", "provider_id": "7", "board_id": None,
                 "detail_path": "/work/detail/7", "funding_status": "requires_detail_readback"},
                {"source_kind": "monthly", "provider_id": "9", "board_id": None,
                 "detail_path": "/monthly_work_contracts/lancer/9", "funding_status": "requires_detail_readback"},
            ],
            "boards": [],
            "finance": {"source_complete": True, "payment_history_count": 0},
        }
        adapter = module.LancersPaidAdapter(
            account_id="seller-1", inventory_reader=lambda: snapshot,
            clock=lambda: "2026-09-07T00:00:00Z",
        )
        rows = adapter.observe_active()
        self.assertEqual([row["work_id"] for row in rows], ["project:7", "monthly:9"])
        self.assertEqual({row["provider_state"] for row in rows}, {"requires_detail_readback"})
        self.assertEqual(adapter.context("project:7")["contract"]["provider_id"], "7")

    def test_decision_waits_for_official_contract_detail(self):
        module = load()
        decision = module.decide({
            "provider": "lancers", "account_id": "seller-1", "work_id": "project:7",
            "latest_event_id": "digest", "provider_state": "requires_detail_readback",
            "observed_at": "2026-09-07T00:00:00Z", "context": {},
        })
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "official_contract_detail_required")
        self.assertTrue(decision["remaining_work"])

    def test_incomplete_inventory_fails_closed(self):
        module = load()
        adapter = module.LancersPaidAdapter(
            account_id="seller-1",
            inventory_reader=lambda: {"ok": False, "source_complete": False},
            clock=lambda: "2026-09-07T00:00:00Z",
        )
        with self.assertRaisesRegex(RuntimeError, "lancers_paid_inventory_unavailable"):
            adapter.observe_active()

    def test_inventory_failure_preserves_safe_provider_error_code(self):
        module = load()
        adapter = module.LancersPaidAdapter(
            account_id="seller-1",
            inventory_reader=lambda: {
                "ok": False,
                "source_complete": False,
                "error": "browser_connect_failed",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "lancers_paid_inventory_unavailable") as raised:
            adapter.observe_active()
        self.assertEqual(
            getattr(raised.exception, "paid_error_code", None),
            "lancers_paid_inventory_browser_connect_failed",
        )

    def test_readback_marks_absent_work_only_after_complete_inventory(self):
        module = load()
        adapter = module.LancersPaidAdapter(
            account_id="seller-1",
            inventory_reader=lambda: {
                "ok": True, "source_complete": True, "contract_candidates": [],
                "boards": [], "finance": {"source_complete": True},
            },
        )
        self.assertEqual(
            adapter.readback({"work_id": "project:7"}),
            {"verified": False, "authoritative_absent": True},
        )

    def test_funded_detail_with_verified_work_produces_one_answer_intent(self):
        module = load()
        quality = hashlib.sha256(b"quality").hexdigest()
        snapshot = {
            "ok": True,
            "source_complete": True,
            "contract_candidates": [{
                "source_kind": "project", "provider_id": "7", "board_id": None,
                "detail_path": "/work/detail/7", "funding_status": "requires_detail_readback",
            }],
            "boards": [],
            "finance": {"source_complete": True},
        }

        class Provider:
            def read_detail(self, candidate):
                return {
                    "provider_state": "funded", "board_id": "board-7",
                    "buyer_event_id": "buyer-7", "buyer_context": "依頼本文",
                    "prepared_answer": "成果物を提出します。",
                    "correct_work_verified": True,
                    "quality_verdict": "quality_ok", "quality_sha256": quality,
                    "formal_delivery_required": True,
                }

        adapter = module.LancersPaidAdapter(
            account_id="seller-1", inventory_reader=lambda: snapshot,
            provider=Provider(),
        )
        row = adapter.observe_active()[0]
        context = adapter.context(row["work_id"])
        decision = module.decide({**row, "context": context})
        self.assertEqual(decision["action"], "answer")
        self.assertEqual(decision["payload"]["buyer_event_id"], "buyer-7")
        self.assertTrue(decision["payload"]["correct_work_verified"])

    def test_funded_detail_builds_and_quality_checks_answer_before_send(self):
        module = load()
        contract = {
            "provider_state": "funded",
            "buyer_event_id": "buyer-7",
            "buyer_context": "依頼内容に沿った結果をメッセージで提出してください。",
        }
        row = {
            "provider": "lancers", "account_id": "seller-1", "work_id": "project:7",
            "latest_event_id": "digest", "provider_state": "funded",
            "observed_at": "2026-09-07T00:00:00Z", "context": {"contract": contract},
        }
        decision = module.decide(
            row,
            answer_selector=lambda _contract: "依頼内容に沿った結果です。",
            quality_selector=lambda _contract, _body: "quality_ok",
        )

        self.assertEqual(decision["action"], "answer")
        self.assertEqual(decision["payload"]["body"], "依頼内容に沿った結果です。")
        self.assertTrue(decision["payload"]["correct_work_verified"])
        self.assertEqual(decision["payload"]["quality_verdict"], "quality_ok")
        self.assertEqual(
            decision["payload"]["quality_sha256"],
            module._digest({"buyer_context": contract["buyer_context"],
                            "body": decision["payload"]["body"]}),
        )

    def test_funded_detail_waits_when_independent_quality_check_rejects_answer(self):
        module = load()
        contract = {
            "provider_state": "funded",
            "buyer_event_id": "buyer-7",
            "buyer_context": "依頼内容に沿った結果をメッセージで提出してください。",
        }
        decision = module.decide(
            {
                "provider": "lancers", "account_id": "seller-1", "work_id": "project:7",
                "latest_event_id": "digest", "provider_state": "funded",
                "observed_at": "2026-09-07T00:00:00Z", "context": {"contract": contract},
            },
            answer_selector=lambda _contract: "未完成の回答です。",
            quality_selector=lambda _contract, _body: "quality_needs_rework",
        )

        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "work_quality_required")
        self.assertTrue(decision["remaining_work"])

    def test_verified_answer_waits_for_delivery_surface_instead_of_recomposing(self):
        module = load()
        contract = {
            "provider_state": "funded",
            "buyer_event_id": "buyer-7",
            "buyer_context": "依頼内容に沿った結果をメッセージで提出してください。",
        }
        decision = module.decide(
            {
                "provider": "lancers", "account_id": "seller-1", "work_id": "project:7",
                "latest_event_id": "digest", "provider_state": "funded",
                "observed_at": "2026-09-07T00:00:00Z",
                "context": {
                    "contract": contract,
                    "previous_effect_verified": True,
                    "previous_intent": {"action": "answer", "effect_key": "effect-7"},
                },
            },
            answer_selector=lambda _contract: (_ for _ in ()).throw(
                AssertionError("verified answer must not be recomposed")
            ),
        )

        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "formal_delivery_surface_unverified")

    def test_answer_mutation_requires_provider_receipt_and_replays_by_effect_key(self):
        module = load()
        snapshot = {
            "ok": True,
            "source_complete": True,
            "contract_candidates": [{
                "source_kind": "project", "provider_id": "7", "board_id": None,
                "detail_path": "/work/detail/7", "funding_status": "requires_detail_readback",
            }],
            "boards": [],
            "finance": {"source_complete": True},
        }

        class Provider:
            def __init__(self):
                self.sent = []

            def read_detail(self, candidate):
                return {
                    "provider_state": "funded", "board_id": "board-7",
                    "buyer_event_id": "buyer-7", "buyer_context": "依頼本文",
                    "correct_work_verified": True,
                    "quality_verdict": "quality_ok",
                    "quality_sha256": module._quality_digest(
                        {"buyer_context": "依頼本文"}, "確認しました。"
                    ),
                }

            def send_message(self, intent, detail):
                self.sent.append((intent, detail))
                return {"provider_receipt_id": "message-7"}

            def readback(self, intent, detail):
                return {"verified": True, "provider_receipt_id": "message-7",
                        "observed_at": "2026-09-23T00:00:00Z"}

        provider = Provider()
        adapter = module.LancersPaidAdapter(
            account_id="seller-1", inventory_reader=lambda: snapshot,
            provider=provider,
        )
        intent = {
            "action": "answer", "work_id": "project:7", "effect_key": "effect-7",
            "payload": {"body": "確認しました。", "buyer_event_id": "buyer-7",
                        "correct_work_verified": True, "quality_verdict": "quality_ok",
                        "quality_sha256": module._quality_digest(
                            {"buyer_context": "依頼本文"}, "確認しました。"
                        )},
        }
        adapter.mutate(intent)
        readback = adapter.readback(intent)
        self.assertEqual(len(provider.sent), 1)
        self.assertTrue(readback["verified"])
        self.assertEqual(readback["provider_receipt_id"], "message-7")

    def test_answer_mutation_rejects_a_forged_quality_digest(self):
        module = load()
        snapshot = {
            "ok": True, "source_complete": True,
            "contract_candidates": [{
                "source_kind": "project", "provider_id": "7", "board_id": None,
                "detail_path": "/work/detail/7", "funding_status": "requires_detail_readback",
            }],
            "boards": [], "finance": {"source_complete": True},
        }

        class Provider:
            def read_detail(self, candidate):
                return {"provider_state": "funded", "board_id": "board-7",
                        "buyer_event_id": "buyer-7", "buyer_context": "依頼本文"}

            def send_message(self, intent, detail):
                raise AssertionError("forged quality must not send")

        adapter = module.LancersPaidAdapter(
            account_id="seller-1", inventory_reader=lambda: snapshot,
            provider=Provider(),
        )
        with self.assertRaisesRegex(RuntimeError, "lancers_paid_answer_quality_unverified"):
            adapter.mutate({
                "action": "answer", "work_id": "project:7", "effect_key": "effect-7",
                "payload": {"body": "確認しました。", "buyer_event_id": "buyer-7",
                            "correct_work_verified": True, "quality_verdict": "quality_ok",
                            "quality_sha256": "a" * 64},
            })


if __name__ == "__main__":
    unittest.main()
