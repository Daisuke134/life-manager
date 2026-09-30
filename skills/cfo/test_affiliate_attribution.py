"""Focused tests for pure Affiliate provider-to-B0 attribution."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import economic_attribution as contract  # noqa: E402
from adapters import affiliate  # noqa: E402


SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"
FIXTURES = Path(__file__).parent / "fixtures/economic_attribution"
AFFILIATE_SCRIPTS = Path(__file__).parents[1] / "affiliate/scripts"
sys.path.insert(0, str(AFFILIATE_SCRIPTS))
from revenue_cli import normalize_commission_row  # noqa: E402

ARTIFACT_EVIDENCE = (
    "lm-affiliate://partnerstack/artifacts/"
    "a16c999a2552649c689e26b7e08f7b8f303fa6837ccddc6cd60f66a8c195e7eb"
)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def rehash_bundle(payload: dict) -> dict:
    payload["capture"]["rendered_artifact_sha256"] = hashlib.sha256(
        json.dumps(payload["artifact"], sort_keys=True).encode()
    ).hexdigest()
    return payload


def commission_transition(row: dict, source_hash: str, placement: dict) -> dict:
    identity = {
        "provider": "elevenlabs",
        "provider_transaction_id": row["provider_transaction_id"],
        "provider_status": row["provider_status"],
        "gross_commission_minor": row["gross_commission_minor"],
        "reversal_minor": row["reversal_minor"],
        "net_commission_minor": row["net_commission_minor"],
        "currency": row["currency"],
        "provider_settlement_id": row["provider_settlement_id"],
        "provider_payout_id": row["provider_payout_id"],
        "attribution": row.get("attribution") or {},
        "placement": placement,
    }
    return {
        "schema_version": 1,
        "receipt_type": "COMMISSION_TRANSITION",
        "transition_id": hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest(),
        **identity,
        "source_artifact_sha256": source_hash,
        "status": row["status"],
        "created_at": row["created_at"],
        "offer": row.get("offer"),
        "target_type": row.get("target_type"),
        "action": row.get("action"),
        "observed_at": SNAPSHOT,
    }


class AffiliateAttributionTest(unittest.TestCase):
    def adapt(self, payload: dict) -> list[dict]:
        return affiliate.adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
            evidence_base="lm-affiliate://partnerstack/artifacts/fixture",
        )

    def test_commission_fixture_matches_the_production_normalizer_exactly(self):
        artifact = fixture("affiliate-partnerstack-complete.json")["artifact"]
        self.assertEqual(
            [normalize_commission_row(row) for row in artifact["commission_rows"]],
            artifact["normalized_commissions"],
        )

    def test_paid_is_revenue_once_while_pending_approved_payout_and_metrics_are_not(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        payload["artifact"]["metrics"] = [
            {"kind": "click", "count": 12}, {"kind": "lead", "count": 3},
        ]
        records = self.adapt(rehash_bundle(payload))
        receipts = [row for row in records if row["record_type"] == "receipt"]
        by_id = {row["receipt_id"]: row for row in receipts}

        self.assertEqual(
            by_id["partnerstack-elevenlabs:commission:reward-paid-1:paid"]["components"],
            [{"category": "settled_external_revenue", "amount": "25"}],
        )
        self.assertEqual(
            by_id["partnerstack-elevenlabs:commission:reward-pending-1:pending"]["components"],
            [{"category": "pending_revenue", "amount": "7"}],
        )
        self.assertEqual(
            by_id["partnerstack-elevenlabs:commission:reward-approved-1:approved"]["components"],
            [{"category": "pending_revenue", "amount": "9"}],
        )
        self.assertFalse(any("click" in row["receipt_id"] or "lead" in row["receipt_id"] for row in receipts))

        self.assertEqual(sum(
            component["category"] == "settled_external_revenue"
            for receipt in receipts for component in receipt["components"]
        ), 1)

    def test_reversal_fees_and_non_revenue_cash_movements_stay_separate(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        paid = dict(payload["artifact"]["normalized_commissions"][0])
        paid.update(net_commission_minor=2400, settled_at="2026-09-30T12:00:00Z")
        evidence = payload["capture"]["rendered_artifact_sha256"]
        evidence = f"lm-affiliate://partnerstack/artifacts/{evidence}"
        rows = [
            affiliate._commission(paid, evidence),
            affiliate._commission({
                **payload["artifact"]["normalized_commissions"][3],
                "reversed_at": "2026-09-29T12:00:00Z",
            }, evidence),
            affiliate._fee({
                "provider": "elevenlabs", "provider_fee_id": "network-fee-1",
                "fee_type": "network", "status": "settled", "amount_minor": 100,
                "currency": "USD", "occurred_at": "2026-09-30T12:00:00Z",
                "settled_at": "2026-09-30T12:00:00Z",
            }, evidence),
            affiliate._fee({
                "provider": "elevenlabs", "provider_fee_id": "payment-fee-1",
                "fee_type": "payment", "status": "settled", "amount_minor": 50,
                "currency": "USD", "occurred_at": "2026-09-30T12:00:00Z",
                "settled_at": "2026-09-30T12:00:00Z",
            }, evidence),
            affiliate._payout({
                "provider": "elevenlabs", "provider_payout_id": "payout-1",
                "status": "deposited", "amount_minor": 2500, "currency": "USD",
                "occurred_at": "2026-09-30T13:00:00Z",
                "settled_at": "2026-09-30T13:05:00Z",
            }, evidence),
        ]
        for movement, category, amount, occurred_at in (
            ("owner-deposit-1", "owner_deposit", 1000, "2026-09-30T14:00:00Z"),
            ("self-payment-1", "self_payment", 1100, "2026-09-30T15:00:00Z"),
            ("internal-transfer-1", "internal_transfer", 1200, "2026-09-30T16:00:00Z"),
        ):
            rows.append(affiliate._cash({
                "provider": "elevenlabs", "movement_id": movement, "kind": category,
                "amount_minor": amount, "currency": "USD", "occurred_at": occurred_at,
            }, evidence))
        components = {
            row["receipt_id"]: row["components"]
            for row in rows
        }
        self.assertEqual(
            components["partnerstack-elevenlabs:commission:reward-reversed-1:reversed"],
            [{"category": "refund", "amount": "10"}],
        )
        self.assertEqual(
            components["partnerstack-elevenlabs:fee:network-fee-1:settled"],
            [{"category": "provider_fee", "amount": "1"}],
        )
        self.assertEqual(
            components["partnerstack-elevenlabs:fee:payment-fee-1:settled"],
            [{"category": "payment_fee", "amount": "0.5"}],
        )
        self.assertEqual(
            components["partnerstack-elevenlabs:commission:reward-paid-1:paid"],
            [{"category": "settled_external_revenue", "amount": "25"}],
        )
        self.assertEqual(
            components["partnerstack-elevenlabs:payout:payout-1:deposited"],
            [{"category": "payout", "amount": "25"}],
        )
        for movement, category in (
            ("owner-deposit-1", "owner_deposit"),
            ("self-payment-1", "self_payment"),
            ("internal-transfer-1", "internal_transfer"),
        ):
            self.assertEqual(
                components[f"partnerstack-elevenlabs:cash:{movement}:{category}"],
                [{"category": category, "amount": {"owner_deposit": "10", "self_payment": "11", "internal_transfer": "12"}[category]}],
            )

    def test_unknown_provider_status_currency_and_missing_settlement_fail_to_coverage_gap(self):
        base = fixture("affiliate-partnerstack-complete.json")
        cases = {}
        unknown_provider = copy.deepcopy(base)
        unknown_provider["capture"]["provider"] = "mystery-network"
        cases["unknown_provider"] = unknown_provider
        unknown_source = copy.deepcopy(base)
        unknown_source["capture"]["receipt_type"] = "INTERNAL_ESTIMATE"
        cases["unknown_source"] = unknown_source
        unknown_status = copy.deepcopy(base)
        unknown_status["artifact"]["normalized_commissions"][0]["status"] = "maybe"
        cases["unknown_status"] = rehash_bundle(unknown_status)
        inconsistent_status = copy.deepcopy(base)
        inconsistent_status["artifact"]["normalized_commissions"][0]["provider_status"] = "pending"
        cases["inconsistent_provider_status"] = rehash_bundle(inconsistent_status)
        unknown_currency = copy.deepcopy(base)
        unknown_currency["artifact"]["normalized_commissions"][0]["currency"] = "UNKNOWN"
        cases["unsupported_currency"] = rehash_bundle(unknown_currency)
        unsupported_exponent = copy.deepcopy(base)
        unsupported_exponent["artifact"]["normalized_commissions"][0]["currency"] = "JPY"
        cases["unsupported_currency_exponent"] = rehash_bundle(unsupported_exponent)
        missing_settlement = copy.deepcopy(base)
        missing_settlement["artifact"]["normalized_commissions"][0]["provider_settlement_id"] = None
        cases["missing_settlement"] = rehash_bundle(missing_settlement)
        missing_settlement_time = copy.deepcopy(base)
        missing_settlement_time["artifact"]["commission_rows"][0].pop("settled_at")
        cases["missing_settlement_time"] = rehash_bundle(missing_settlement_time)
        producer_impossible_settled = copy.deepcopy(base)
        producer_impossible_settled["artifact"]["commission_rows"][0]["reward_status"] = "settled"
        producer_impossible_settled["artifact"]["normalized_commissions"][0].update(
            provider_status="settled", status="settled",
        )
        cases["producer_impossible_settled"] = rehash_bundle(producer_impossible_settled)
        self_declared_status_extension = copy.deepcopy(base)
        self_declared_status_extension["capture"]["commission_status_extension"] = {
            "provider": "elevenlabs", "statuses": ["chargeback", "settled"],
        }
        cases["self_declared_status_extension"] = self_declared_status_extension
        self_declared_financial_extension = copy.deepcopy(base)
        self_declared_financial_extension["capture"]["financial_extension"] = {
            "provider": "elevenlabs",
        }
        cases["self_declared_financial_extension"] = self_declared_financial_extension
        null_extensions = copy.deepcopy(base)
        null_extensions["capture"].update({
            "commission_status_extension": None,
            "financial_extension": None,
            "normalized_fees": [],
            "normalized_payouts": [],
            "cash_movements": [],
        })
        cases["null_or_capture_extensions"] = null_extensions
        aliased_artifact_rows = copy.deepcopy(base)
        aliased_artifact_rows["artifact"].update(fees=[], payouts=[])
        cases["aliased_artifact_rows"] = rehash_bundle(aliased_artifact_rows)

        for name, payload in cases.items():
            with self.subTest(name=name):
                records = self.adapt(payload)
                self.assertFalse(any(
                    row["record_type"] == "receipt"
                    and row["receipt_id"].endswith("reward-paid-1:paid")
                    for row in records
                ))
                coverage = [row for row in records if row["record_type"] == "coverage"]
                self.assertEqual({row["coverage_state"] for row in coverage}, {"gap"})
                if name == "unsupported_currency_exponent":
                    self.assertEqual(
                        [row["reason"] for row in coverage[:2]],
                        ["unsupported_currency", "unsupported_currency"],
                    )

    def test_stale_empty_official_readback_is_not_fake_zero(self):
        records = self.adapt(fixture("affiliate-partnerstack-stale-empty.json"))
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        coverage = [row for row in records if row["record_type"] == "coverage"]
        self.assertEqual([row["projection"] for row in coverage], ["historical", "trailing", "as_of"])
        self.assertEqual([row["reason"] for row in coverage], [
            "stale_readback", "stale_readback", "missing_category",
        ])

    def test_provider_scoped_ids_make_replay_zero_and_conflicts_fail_closed(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        once = self.adapt(payload)
        replayed = contract.project(
            [*once, *copy.deepcopy(once)],
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertIn(
            {
                "provider": "partnerstack-elevenlabs",
                "receipt_id": "partnerstack-elevenlabs:commission:reward-paid-1:paid",
            },
            replayed["duplicate_receipts"],
        )
        changed = copy.deepcopy(payload)
        changed["artifact"]["commission_rows"][0]["commission_amount"] = "26.00"
        changed["artifact"]["normalized_commissions"][0]["gross_commission_minor"] = 2600
        changed["artifact"]["normalized_commissions"][0]["net_commission_minor"] = 2600
        rehash_bundle(changed)
        with self.assertRaisesRegex(contract.ContractError, "receipt_conflict"):
            contract.project(
                [*once, *self.adapt(changed)],
                snapshot_at=SNAPSHOT,
                trailing_start=TRAILING_START,
            )

    def test_coverage_has_exact_historical_trailing_and_as_of_windows(self):
        records = self.adapt(fixture("affiliate-partnerstack-complete.json"))
        coverage = [row for row in records if row["record_type"] == "coverage"]
        self.assertEqual(coverage, [
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "coverage",
                "product_loop_id": "affiliate",
                "source_id": "affiliate-partnerstack-financial-record",
                "projection": "historical",
                "window_start": None,
                "window_end": "2026-10-01T00:00:00.000000Z",
                "coverage_state": "gap",
                "reason": "missing_coverage",
                "covered_categories": [],
                "observed_at": "2026-10-01T00:00:00.000000Z",
                "evidence_refs": [ARTIFACT_EVIDENCE],
            },
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "coverage",
                "product_loop_id": "affiliate",
                "source_id": "affiliate-partnerstack-financial-record",
                "projection": "trailing",
                "window_start": "2026-09-24T00:00:00.000000Z",
                "window_end": "2026-10-01T00:00:00.000000Z",
                "coverage_state": "gap",
                "reason": "missing_coverage",
                "covered_categories": [],
                "observed_at": "2026-10-01T00:00:00.000000Z",
                "evidence_refs": [ARTIFACT_EVIDENCE],
            },
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "coverage",
                "product_loop_id": "affiliate",
                "source_id": "affiliate-partnerstack-financial-record",
                "projection": "as_of",
                "window_start": None,
                "window_end": "2026-10-01T00:00:00.000000Z",
                "coverage_state": "gap",
                "reason": "missing_category",
                "covered_categories": [],
                "observed_at": "2026-10-01T00:00:00.000000Z",
                "evidence_refs": [ARTIFACT_EVIDENCE],
            },
        ])

    def test_path_adapter_is_deterministic_and_uses_sanitized_evidence_uri(self):
        path = FIXTURES / "affiliate-partnerstack-complete.json"
        first = affiliate.adapt_path(path, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)
        second = affiliate.adapt_path(path, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)
        self.assertEqual(first, second)
        refs = {ref for row in first for ref in row["evidence_refs"]}
        self.assertTrue(refs)
        self.assertTrue(all(
            ref.startswith("lm-affiliate://partnerstack/artifacts/") for ref in refs
        ))
        self.assertNotIn("/Users/", json.dumps(first))
        self.assertNotIn(path.name, json.dumps(first))

    def test_path_supplies_content_hash_for_native_rendered_artifact(self):
        artifact = fixture("affiliate-partnerstack-stale-empty.json")
        artifact.pop("rendered_artifact_sha256")
        with tempfile.TemporaryDirectory() as directory:
            digest = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()
            path = Path(directory) / f"{digest}.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            (Path(directory) / "latest.json").write_text(json.dumps({
                "schema_version": 1,
                "receipt_type": "PARTNERSTACK_REPORT_CAPTURE",
                "provider": "elevenlabs",
                "currency_display": "USD",
                "commission_row_count": 0,
                "commission_row_state": "EMPTY",
                "normalizer_state": "NO_LIVE_ROWS",
                "rendered_artifact_sha256": digest,
                "observed_at": artifact["observed_at"],
            }), encoding="utf-8")
            records = affiliate.adapt_path(
                path, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )
        coverage = [row for row in records if row["record_type"] == "coverage"]
        self.assertEqual(coverage[0]["reason"], "stale_readback")

    def test_capture_artifact_hash_mismatch_cannot_create_verified_receipts(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        payload["artifact"]["normalized_commissions"][0]["gross_commission_minor"] = 9900
        records = self.adapt(payload)
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertEqual(
            [row["reason"] for row in records if row["record_type"] == "coverage"][:2],
            ["unverified_receipt", "unverified_receipt"],
        )

    def test_normalized_descriptive_fields_must_exactly_match_the_raw_provider_row(self):
        mutations = {
            "offer": "forged-offer",
            "target_type": "forged-target",
            "action": "forged-action",
            "attribution": {
                "sub_id_1": "forged-sub-id", "sub_id_2": None, "sub_id_3": None,
                "shared_id": None, "clicked_at": None, "link_sha256": None,
                "referrer_sha256": None, "landing_page_sha256": None,
            },
        }
        for field, forged in mutations.items():
            with self.subTest(field=field):
                payload = fixture("affiliate-partnerstack-complete.json")
                payload["artifact"]["normalized_commissions"][0][field] = forged
                records = self.adapt(rehash_bundle(payload))
                self.assertFalse(any(
                    row.get("receipt_id") ==
                    "partnerstack-elevenlabs:commission:reward-paid-1:paid"
                    for row in records
                ))
                self.assertEqual(
                    [row["reason"] for row in records if row["record_type"] == "coverage"][:2],
                    ["unverified_receipt", "unverified_receipt"],
                )

    def test_artifact_extension_keys_fail_closed_even_when_null(self):
        for key in ("commission_status_extension", "financial_extension"):
            with self.subTest(key=key):
                payload = fixture("affiliate-partnerstack-complete.json")
                payload["artifact"][key] = None
                records = self.adapt(rehash_bundle(payload))
                self.assertFalse(any(row["record_type"] == "receipt" for row in records))
                self.assertEqual(
                    [row["reason"] for row in records if row["record_type"] == "coverage"][:2],
                    ["unverified_receipt", "unverified_receipt"],
                )

    def test_bundle_schema_and_row_count_require_exact_integer_types(self):
        mutations = (
            ("capture_schema_bool", "capture", "schema_version", True),
            ("artifact_schema_bool", "artifact", "schema_version", True),
            ("row_count_float", "capture", "commission_row_count", 4.0),
        )
        for name, section, field, value in mutations:
            with self.subTest(name=name):
                payload = fixture("affiliate-partnerstack-complete.json")
                payload[section][field] = value
                records = self.adapt(rehash_bundle(payload))
                self.assertFalse(any(
                    row.get("receipt_id") ==
                    "partnerstack-elevenlabs:commission:reward-paid-1:paid"
                    for row in records
                ))
                self.assertEqual(
                    [row["reason"] for row in records if row["record_type"] == "coverage"][:2],
                    ["unverified_receipt", "unverified_receipt"],
                )

    def test_declined_commission_is_not_a_refund(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        raw = payload["artifact"]["commission_rows"][3]
        normalized = payload["artifact"]["normalized_commissions"][3]
        raw["reward_status"] = "declined"
        normalized["provider_status"] = "declined"
        normalized["status"] = "reversed"
        rehash_bundle(payload)
        records = self.adapt(payload)
        self.assertFalse(any(
            row["record_type"] == "receipt"
            and "reward-reversed-1" in row["receipt_id"]
            for row in records
        ))

    def test_chargeback_is_a_refund_at_the_adapter_boundary(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        row = dict(payload["artifact"]["normalized_commissions"][3])
        row.update(provider_status="chargeback", reversed_at="2026-09-29T12:00:00Z")
        receipt = affiliate._commission(row, ARTIFACT_EVIDENCE)
        self.assertEqual(receipt["components"], [{"category": "refund", "amount": "10"}])

    def test_settled_provider_status_maps_only_from_canonical_paid_row(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        row = dict(payload["artifact"]["normalized_commissions"][0])
        row.update(provider_status="settled", settled_at="2026-09-30T12:00:00Z")
        receipt = affiliate._commission(row, ARTIFACT_EVIDENCE)
        self.assertEqual(
            receipt["components"],
            [{"category": "settled_external_revenue", "amount": "25"}],
        )

    def test_durable_ledger_rebinds_to_immutable_artifact_and_replay_is_stable(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        artifact = payload["artifact"]
        source_hash = payload["capture"]["rendered_artifact_sha256"]
        normalized = artifact["normalized_commissions"][0]
        transition = commission_transition(
            normalized, source_hash, {"state": "UNMATCHED"},
        )
        later_artifact = copy.deepcopy(artifact)
        later_artifact["observed_at"] = "2026-10-01T00:00:01Z"
        later_artifact["commission_rows"].append({
            "reward_key": "reward-approved-2", "reward_status": "approved",
            "commission_amount": "3.00", "created_at_date": "2026-09-29T12:00:00Z",
            "currency": "USD",
        })
        later_artifact["normalized_commissions"].append({
            "provider_transaction_id": "reward-approved-2", "provider_status": "approved",
            "status": "approved", "currency": "USD", "gross_commission_minor": 300,
            "reversal_minor": 0, "net_commission_minor": 300,
            "created_at": "2026-09-29T12:00:00Z", "provider_settlement_id": None,
            "provider_payout_id": None, "offer": None, "target_type": None,
            "action": None,
            "attribution": {
                "sub_id_1": None, "sub_id_2": None, "sub_id_3": None,
                "shared_id": None, "clicked_at": None, "link_sha256": None,
                "referrer_sha256": None, "landing_page_sha256": None,
            },
        })
        later_hash = hashlib.sha256(
            json.dumps(later_artifact, sort_keys=True).encode()
        ).hexdigest()
        later_transition = commission_transition(
            later_artifact["normalized_commissions"][-1], later_hash,
            {"state": "UNMATCHED"},
        )
        corrected_placement = commission_transition(
            later_artifact["normalized_commissions"][0], later_hash,
            {"state": "MATCHED", "placement_id": "placement-1"},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            artifact_root = state / "provider-reports/partnerstack"
            artifact_root.mkdir(parents=True)
            (artifact_root / f"{source_hash}.json").write_text(
                json.dumps(artifact), encoding="utf-8",
            )
            (artifact_root / f"{later_hash}.json").write_text(
                json.dumps(later_artifact), encoding="utf-8",
            )
            ledger = state / "commission-ledger.jsonl"
            line = json.dumps(transition)
            ledger.write_text(line + "\n", encoding="utf-8")
            before = affiliate.adapt_path(
                ledger, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )
            ledger.write_text(
                "\n".join((line, json.dumps(later_transition),
                             json.dumps(corrected_placement))) + "\n",
                encoding="utf-8",
            )
            after = affiliate.adapt_path(
                ledger, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )
            forged_row = copy.deepcopy(normalized)
            forged_row["attribution"] = {
                **forged_row["attribution"], "sub_id_1": "forged-placement",
            }
            ledger.write_text(
                json.dumps(commission_transition(
                    forged_row, source_hash, {"state": "UNMATCHED"},
                )) + "\n",
                encoding="utf-8",
            )
            rejected = affiliate.adapt_path(
                ledger, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )
        paid_id = "partnerstack-elevenlabs:commission:reward-paid-1:paid"
        self.assertEqual(
            next(row for row in before if row.get("receipt_id") == paid_id),
            next(row for row in after if row.get("receipt_id") == paid_id),
        )
        self.assertTrue(any(
            row.get("receipt_id") ==
            "partnerstack-elevenlabs:commission:reward-approved-2:approved"
            for row in after
        ))
        self.assertFalse(any(row["record_type"] == "receipt" for row in rejected))
        self.assertEqual(
            [row["reason"] for row in rejected if row["record_type"] == "coverage"][:2],
            ["unverified_receipt", "unverified_receipt"],
        )

    def test_path_evidence_never_contains_a_pii_bearing_filename(self):
        payload = fixture("affiliate-partnerstack-complete.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private@example.com-secret.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            records = affiliate.adapt_path(
                path, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )
        self.assertNotIn("private@example.com", json.dumps(records))
        self.assertNotIn("secret", json.dumps(records))

    def test_every_output_is_a_valid_b0_record(self):
        for record in self.adapt(fixture("affiliate-partnerstack-complete.json")):
            self.assertEqual(contract.validate_record(record), record)


if __name__ == "__main__":
    unittest.main()
