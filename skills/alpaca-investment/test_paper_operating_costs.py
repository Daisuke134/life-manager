from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_performance import _closed_round_trips, write_paper_performance
from test_paper_performance import OBSERVATION, OWNER, RISK, _prior_rows, _rows


def _readback(rows=None):
    trips, _ = _closed_round_trips(rows or _rows())
    end = "2026-10-20T14:31:09Z"
    document = {
        "provider": "openai", "document_type": "invoice", "invoice_id": "invoice-paper",
        "official": True, "source_type": "official_invoice", "status": "paid",
        "currency": "USD", "billing_period_start": "2026-09-01T00:00:00Z",
        "billing_period_end": "2026-10-20T14:31:06Z", "paid_at": "2026-10-20T14:31:08Z",
        "line_items": [],
    }
    joins = []
    for index, trip in enumerate(trips):
        for category, amount in (("model_cost", "0.01"), ("tool_cost", "0.02"),
                                 ("browser_cost", "0.03"), ("infra_cost", "0.04")):
            identity = f"trip-{index}-{category}"
            document["line_items"].append({
                "line_item_id": identity, "category": category, "amount": amount,
                "basis": "official_invoice", "occurred_at": trip["closed_at"],
                "allocations": [{"allocation_id": identity, "product_loop_id": "investment",
                                 "amount": amount, "job_id": identity}],
            })
            joins.append({
                "provider": "openai", "document_type": "invoice", "document_id": "invoice-paper",
                "line_item_id": identity, "allocation_id": identity, "job_id": identity,
                "status": "completed", "product_loop_id": "investment", "owner_id": OWNER,
                "mode": "paper", "paper": True, "order_ids": trip["order_ids"],
                "period_start": trip["period_start"], "period_end": trip["closed_at"],
                "source_receipt_ids": trip["source_receipt_ids"],
            })
    return {
        "schema_version": 1,
        "readback": {"kind": "official_billing_readback", "observed_at": end,
                     "historical": {"complete": True, "window_start": None, "window_end": end},
                     "trailing": {"complete": True, "window_start": "2026-09-01T00:00:00Z",
                                  "window_end": end}},
        "sources": [{"provider": "openai", "status": "available", "product_loop_ids": ["investment"]}],
        "documents": [document], "job_joins": joins,
    }


def _write_state(state, rows):
    (state / "receipts.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
    )


class PaperOperatingCostTests(unittest.TestCase):
    def report(self, payload, *, rows=None, observation=None):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, rows or _rows())
            billing = state / "billing.json"
            billing.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                return write_paper_performance(state, observation or OBSERVATION, RISK)

    def test_official_query_diagnostics_reach_daily_without_making_profit(self):
        from skills.cfo.test_actual_cost_attribution import query_payload
        payload = _readback()
        q = query_payload()
        trip = _closed_round_trips(_rows())[0][0]
        scope = q["readback"]["cost_scopes"][0]
        scope.update(owner_id=OWNER, order_ids=trip["order_ids"],
                     period_start=trip["period_start"], period_end=trip["closed_at"],
                     source_receipt_ids=trip["source_receipt_ids"])
        stamp = payload["readback"]["observed_at"]
        query = q["sources"][0]["queries"][0]
        query.update(window_start=trip["period_start"], window_end=stamp,
                     observed_at=stamp, finalized_through=stamp)
        payload["sources"][0].update(billing_account_refs=["billing-account"], queries=[query])
        payload["readback"]["cost_scopes"] = [scope]
        payload["provider_pagination"] = q["provider_pagination"]
        payload["job_joins"].append({**scope, "provider": "openai", "billing_account_ref": "billing-account",
            "query_id": "query-1", "join_type": "scope_query", "job_id": None,
            "run_ids": ["run-1"], "occurrence_ids": [f"{OWNER}:run-1"]})
        result = self.report(payload)
        self.assertEqual(len(result.get("operating_cost_query_observations", [])), 1)
        self.assertEqual(result.get("operating_cost_coverage", {}).get("coverage_state"), "gap")
        self.assertEqual(result["operating_costs_status"], "partial")
        self.assertIsNone(result["net_realized_pnl_usd"])
        self.assertEqual(result["operating_cost_source_receipt_ids"],
                         [row["receipt_id"] for row in result["operating_cost_components"]])

    def test_paid_scoped_components_are_subtotals_not_total_cost_or_profit(self):
        result = self.report(_readback())
        self.assertEqual(result.get("verified_model_cost_subtotal_usd"), "0.01")
        self.assertEqual(result.get("verified_system_cost_subtotal_usd"), "0.09")
        self.assertEqual(result.get("operating_costs_status"), "partial")
        self.assertEqual(result["costs_status"], "partial")
        self.assertEqual(len(result.get("operating_cost_source_receipt_ids", [])), 4)
        self.assertEqual(len(result.get("operating_cost_components", [])), 4)
        for field in ("model_cost_usd", "system_cost_usd", "net_realized_pnl_usd", "fees_usd"):
            self.assertIsNone(result[field])
        self.assertIn("model", result["unknown_cost_categories"])
        self.assertIn("system", result["unknown_cost_categories"])

    def test_each_scope_and_document_join_must_match_exactly(self):
        changes = {
            "owner_id": "alpaca-investment-live", "mode": "live", "paper": False,
            "order_ids": ["other-entry", "paper-exit"],
            "period_start": "2026-09-29T14:31:00Z", "period_end": "2026-10-20T14:31:06Z",
            "document_id": "other-invoice", "allocation_id": "other-allocation",
            "job_id": "other-job", "status": "started", "source_receipt_ids": [],
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                payload = _readback()
                for join in payload["job_joins"]:
                    join[field] = value
                result = self.report(payload)
                self.assertEqual(result.get("operating_costs_status"), "unknown")
                self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))
                self.assertIsNone(result.get("verified_system_cost_subtotal_usd"))

    def test_incomplete_or_unpaid_or_non_usd_readback_does_not_become_cost(self):
        for variant in ("unpaid", "stale", "missing", "allocation", "currency", "unofficial",
                        "outside_trade", "future"):
            with self.subTest(variant=variant):
                payload = _readback()
                doc = payload["documents"][0]
                if variant == "unpaid":
                    doc["status"] = "open"
                elif variant == "stale":
                    payload["readback"]["historical"]["complete"] = False
                elif variant == "missing":
                    payload["sources"][0]["status"] = "missing"
                elif variant == "allocation":
                    for line in doc["line_items"]:
                        line["allocations"][0]["amount"] = "0.001"
                elif variant == "currency":
                    doc["currency"] = "JPY"
                elif variant == "unofficial":
                    doc["official"] = False
                elif variant == "outside_trade":
                    for line in doc["line_items"]:
                        line["occurred_at"] = "2026-09-01T01:00:00Z"
                else:
                    payload["readback"]["observed_at"] = "2026-10-21T14:31:09Z"
                result = self.report(payload)
                self.assertEqual(result.get("operating_costs_status"), "unknown")
                self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))
                self.assertIsNone(result.get("verified_system_cost_subtotal_usd"))

    def test_identical_receipts_and_joins_are_counted_once_and_conflicts_are_rejected(self):
        payload = _readback()
        payload["documents"].append(copy.deepcopy(payload["documents"][0]))
        payload["job_joins"] += copy.deepcopy(payload["job_joins"])
        result = self.report(payload)
        self.assertEqual(result.get("verified_model_cost_subtotal_usd"), "0.01")
        self.assertEqual(result.get("verified_system_cost_subtotal_usd"), "0.09")
        for join in payload["job_joins"][4:]:
            join["order_ids"] = ["other-entry", "other-exit"]
        result = self.report(payload)
        self.assertEqual(result.get("operating_costs_status"), "unknown")
        self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))

    def test_current_day_does_not_include_another_days_components(self):
        rows = [*_prior_rows(), *_rows()]
        result = self.report(_readback(rows), rows=rows)
        self.assertEqual(result.get("verified_model_cost_subtotal_usd"), "0.01")
        self.assertEqual(result.get("verified_system_cost_subtotal_usd"), "0.09")
        self.assertEqual(len(result.get("operating_cost_components", [])), 4)
        self.assertTrue(all(component["order_ids"] == ["paper-entry", "paper-exit"]
                            for component in result["operating_cost_components"]))

    def test_invoice_and_its_paid_receipt_are_one_underlying_cost(self):
        payload = _readback()
        receipt = copy.deepcopy(payload["documents"][0])
        receipt.update(document_type="paid_receipt", source_type="official_paid_receipt",
                       receipt_id=receipt["invoice_id"])
        for line in receipt["line_items"]:
            line["allocations"][0]["job_id"] += "-receipt"
        for join in copy.deepcopy(payload["job_joins"]):
            join.update(document_type="paid_receipt", job_id=join["job_id"] + "-receipt")
            payload["job_joins"].append(join)
        payload["documents"].append(receipt)
        result = self.report(payload)
        self.assertEqual(result.get("verified_model_cost_subtotal_usd"), "0.01")
        self.assertEqual(result.get("verified_system_cost_subtotal_usd"), "0.09")
        self.assertEqual(len(result.get("operating_cost_components", [])), 4)

    def test_previous_day_allocation_cannot_be_reassigned_to_another_trade(self):
        self._assert_reassignment_rejected()

    def test_adding_an_invoice_reference_does_not_allow_receipt_reassignment(self):
        self._assert_reassignment_rejected(enrich_invoice=True)

    def test_receipt_alias_survives_switch_to_the_invoice_representation(self):
        self._assert_reassignment_rejected(enrich_invoice=True, representation_switch=True)

    def _assert_reassignment_rejected(self, *, enrich_invoice=False, representation_switch=False):
        prior = json.loads(json.dumps(_prior_rows()).replace("2026-09-22", "2026-10-19").replace("QQQ", "SPY"))
        prior_observation = copy.deepcopy(OBSERVATION)
        prior_observation["clock"]["observed_at"] = "2026-10-19T14:31:10Z"
        payload = _readback(prior)
        if enrich_invoice:
            document = payload["documents"][0]
            del document["invoice_id"]
            document.update(document_type="paid_receipt", source_type="official_paid_receipt",
                            receipt_id="receipt-paper")
            for join in payload["job_joins"]:
                join.update(document_type="paid_receipt", document_id="receipt-paper")
        for line in payload["documents"][0]["line_items"]:
            line["occurred_at"] = "2026-10-10T00:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            billing = state / "billing.json"
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                _write_state(state, prior)
                write_paper_performance(state, prior_observation, RISK)
                _write_state(state, [*prior, *_rows()])
                billing.write_text(json.dumps(payload))
                write_paper_performance(state, OBSERVATION, RISK)
                original = json.loads((state / "performance-daily-2026-10-19.json").read_text())
                if representation_switch:
                    unreferenced_receipt = copy.deepcopy(payload)
                    payload["documents"][0]["invoice_id"] = "invoice-paper"
                    billing.write_text(json.dumps(payload))
                    write_paper_performance(state, OBSERVATION, RISK)
                    document = payload["documents"][0]
                    document.update(document_type="invoice", source_type="official_invoice")
                    del document["receipt_id"]
                    for join in payload["job_joins"]:
                        join.update(document_type="invoice", document_id="invoice-paper")
                    billing.write_text(json.dumps(payload))
                    write_paper_performance(state, OBSERVATION, RISK)
                    payload = unreferenced_receipt
                    original = json.loads((state / "performance-daily-2026-10-19.json").read_text())
                current_trip = _closed_round_trips(_rows())[0][0]
                for join in payload["job_joins"]:
                    join.update(order_ids=current_trip["order_ids"], period_start=current_trip["period_start"],
                                period_end=current_trip["closed_at"], source_receipt_ids=current_trip["source_receipt_ids"])
                if enrich_invoice and not representation_switch:
                    payload["documents"][0]["invoice_id"] = "invoice-paper"
                billing.write_text(json.dumps(payload))
                result = write_paper_performance(state, OBSERVATION, RISK)
                self.assertEqual(json.loads((state / "performance-daily-2026-10-19.json").read_text()), original)
        self.assertEqual(original["verified_model_cost_subtotal_usd"], "0.01")
        self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))
        self.assertIsNone(result.get("verified_system_cost_subtotal_usd"))

    def test_late_cost_is_attached_to_original_day_and_replay_does_not_add_it_again(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, _rows())
            billing = state / "billing.json"
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                write_paper_performance(state, OBSERVATION, RISK)
                payload = _readback()
                payload["documents"][0]["paid_at"] = "2026-10-21T14:30:00Z"
                for section in (payload["readback"], payload["readback"]["historical"],
                                payload["readback"]["trailing"]):
                    section["observed_at" if "observed_at" in section else "window_end"] = "2026-10-21T14:31:00Z"
                billing.write_text(json.dumps(payload), encoding="utf-8")
                tomorrow = copy.deepcopy(OBSERVATION)
                tomorrow["clock"]["observed_at"] = "2026-10-21T14:32:00Z"
                result = write_paper_performance(state, tomorrow, {"drawdown_usd": "1.25"})
                previous_path = state / "performance-daily-2026-10-20.json"
                previous = json.loads(previous_path.read_text())
                write_paper_performance(state, tomorrow, {"drawdown_usd": "1.25"})
                self.assertEqual(json.loads(previous_path.read_text()), previous)
        self.assertEqual(previous.get("verified_model_cost_subtotal_usd"), "0.01")
        self.assertEqual(previous.get("verified_system_cost_subtotal_usd"), "0.09")
        self.assertEqual(previous["observed_at"], OBSERVATION["clock"]["observed_at"])
        self.assertEqual(previous["gross_strategy_pnl_usd"], "0.250")
        self.assertEqual(previous["risk"], RISK)
        self.assertEqual(previous.get("operating_costs_observed_at"), "2026-10-21T14:31:00Z")
        self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))
        self.assertEqual(result["gross_strategy_pnl_usd"], "0")
        self.assertIsNone(previous["net_realized_pnl_usd"])

    def test_missing_next_readback_does_not_erase_the_existing_cost_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, _rows())
            billing = state / "billing.json"
            billing.write_text(json.dumps(_readback()))
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                write_paper_performance(state, OBSERVATION, RISK)
                path = state / "performance-daily-2026-10-20.json"
                original = path.read_bytes()
                billing.unlink()
                result = write_paper_performance(state, OBSERVATION, RISK)
                self.assertEqual(result, {"status": "unknown", "reason": "paper_operating_cost_readback_incomplete"})
                self.assertEqual(path.read_bytes(), original)

    def test_unreadable_binding_history_is_not_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, _rows())
            (state / "performance-daily-2026-10-19.json").write_bytes(b"\xff")
            billing = state / "billing.json"
            billing.write_text(json.dumps(_readback()))
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                result = write_paper_performance(state, OBSERVATION, RISK)
            self.assertEqual(result, {"status": "unknown", "reason": "paper_operating_cost_binding_unavailable"})
            self.assertFalse((state / "performance-daily-2026-10-20.json").exists())

    def test_extreme_history_timestamp_stays_unknown_without_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, _rows())
            billing = state / "billing.json"
            billing.write_text(json.dumps(_readback()))
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                write_paper_performance(state, OBSERVATION, RISK)
                path = state / "performance-daily-2026-10-20.json"
                previous = json.loads(path.read_text())
                previous["observed_at"] = "0001-01-01T00:00:00+23:00"
                path.write_text(json.dumps(previous))
                original = path.read_bytes()
                result = write_paper_performance(state, OBSERVATION, RISK)
                self.assertEqual(result, {"status": "unknown", "reason": "paper_operating_cost_binding_unavailable"})
                self.assertEqual(path.read_bytes(), original)

    def test_unreadable_or_malformed_json_stays_unknown_without_aborting(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _write_state(state, _rows())
            billing = state / "billing.json"
            with patch.dict(os.environ, {"LM_CFO_ACTUAL_COST_READBACK": str(billing),
                                         "LM_CFO_ACTUAL_COST": ""}):
                for raw in (None, b"\xff", b'{"x":' + b"1" * 5000 + b"}",
                            b"[" * 10000 + b"0" + b"]" * 10000):
                    with self.subTest(raw_kind="missing" if raw is None else raw[:10]):
                        if raw is not None:
                            billing.write_bytes(raw)
                        result = write_paper_performance(state, OBSERVATION, RISK)
                        self.assertEqual(result.get("operating_costs_status"), "unknown")
                        self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))
                        self.assertIsNone(result.get("verified_system_cost_subtotal_usd"))

    def test_malformed_nested_rows_do_not_escape_the_reporting_boundary(self):
        for location in ("document", "line", "allocation", "join"):
            with self.subTest(location=location):
                payload = _readback()
                if location == "document":
                    payload["documents"].append(None)
                elif location == "line":
                    payload["documents"][0]["line_items"].append(None)
                elif location == "allocation":
                    payload["documents"][0]["line_items"][0]["allocations"].append(None)
                else:
                    payload["job_joins"].append({"provider": [], "job_id": {}})
                result = self.report(payload)
                self.assertEqual(result.get("operating_costs_status"), "unknown")
                self.assertIsNone(result.get("verified_model_cost_subtotal_usd"))

    def test_component_addition_is_exact_beyond_default_decimal_precision(self):
        payload = _readback()
        for line in payload["documents"][0]["line_items"]:
            amount = "99999999999999999999999999.99" if line["category"] == "infra_cost" else "0.01"
            line["amount"] = line["allocations"][0]["amount"] = amount
        result = self.report(payload)
        self.assertEqual(result.get("verified_system_cost_subtotal_usd"), "100000000000000000000000000.01")


if __name__ == "__main__":
    unittest.main()
