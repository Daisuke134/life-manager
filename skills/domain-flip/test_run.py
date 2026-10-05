from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest


SKILL_DIR = Path(__file__).parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = load_module("domain_flip_run", "run.py")
effect_reconcile = load_module("domain_flip_effect_reconcile", "effect_reconcile.py")
core = load_module("domain_flip_core_for_run_test", "core.py")
openprovider = load_module("domain_flip_openprovider_for_run_test", "openprovider.py")


def context(run_id: str = "run-1"):
    return {
        "run_id": run_id,
        "owner_id": "domain-flip",
        "occurrence_id": f"domain-flip:{run_id}",
        "release_sha": "a" * 40,
        "loaded_argv": ["skills/domain-flip/run.py"],
        "loaded_env": {"LIFE_MANAGER_LOOP_ID": "domain-flip"},
    }


def business_funding(remaining: str = "100.00"):
    return {
        "source_type": "business_dedicated",
        "source_owner_id": "domain-flip",
        "source_verified": True,
        "currency": "EUR",
        "lifetime_cap_eur": "100.00",
        "owner_funded_total_eur": "100.00",
        "remaining_eur": remaining,
        "funding_receipt_id": "funding-1",
        "balance_readback_verified": True,
        "balance_provider_receipt_id": "balance-readback-1",
        "balance_readback_at": datetime.now(timezone.utc).isoformat(),
        "top_up_count": 1,
        "automatic_refill_enabled": False,
    }


def verified_registrant():
    return {
        "legal_holder_verified": True,
        "holder_type": "natural_person",
        "whois_email_functional": True,
        "whois_email_receiving_verified": True,
        "whois_public_fields": ["email"],
        "whois_optional_fields_opted_in": [],
        "whois_policy_verified": True,
        "whois_policy_evidence_refs": ["https://www.register.si/splosni-pogoji/#pravila_whois"],
        "owner_handle": "OWNER-1",
        "owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest(),
        "contact_fingerprint": "c" * 64,
        "whois_email_fingerprint": "e" * 64,
    }


def complete_rights():
    return {
        "status": "complete",
        "source": "euipo",
        "total_elements": 0,
        "records": [],
        "evidence_refs": ["euipo://trademark-search/novara"],
    }


def quote():
    return {
        "domain": "novara.si",
        "provider": "openprovider",
        "available": True,
        "currency": "EUR",
        "registration_cost_eur": "10.00",
        "renewal_cost_eur": "10.00",
        "provider_receipt_id": None,
        "readback_verified": True,
        "evidence_refs": ["openprovider://price/novara.si"],
    }


def market_evidence():
    return {"status": "reported", "evidence_refs": ["market://si/brandables/novara"]}


def fee_evidence():
    return {
        "readback_verified": True,
        "readback_at": datetime.now(timezone.utc).isoformat(),
        "cost_readback_verified": True,
        "cost_readback_at": datetime.now(timezone.utc).isoformat(),
        "cost_evidence_refs": ["domain-flip://cost-readback/run-1"],
        "minimum_sale_price_eur": "20.00",
        "sedo_fee_rate": "0.20",
        "direct_marketplace_fee_rate": "0.15",
        "sedomls_fee_rate": "0.20",
        "domain_category": "I",
        "source_sha256": "a" * 64,
        "tax_eur": "0.00",
        "payout_fee_eur": "0.00",
        "fx_fee_eur": "0.00",
        "measured_model_cost_eur": "0.00",
        "measured_infra_cost_eur": "0.00",
        "evidence_refs": ["https://sedo.com/us/what-we-offer/price-list/"],
    }


def review_register(*_args, **_kwargs):
    return {
        "action": "register",
        "selected_domain": "novara.si",
        "listing_price_eur": "500.00",
        "minimum_accepted_price_eur": "300.00",
        "rights_risk": "clear",
        "reason": "A concise brandable name fits the supplied source evidence.",
        "evidence_refs": ["euipo://trademark-search/novara"],
    }


def review_current_candidate(packet):
    domain = packet["candidate"]["domain"]
    return {
        "action": "register",
        "selected_domain": domain,
        "listing_price_eur": "500.00",
        "minimum_accepted_price_eur": "300.00",
        "rights_risk": "clear",
        "reason": "A concise brandable name fits the supplied source evidence.",
        "evidence_refs": [packet["rights"]["evidence_refs"][0]],
    }


class FakeRights:
    def __init__(self, result=None):
        self.result = result or complete_rights()
        self.calls = []

    def search_wordmark(self, candidate):
        self.calls.append(candidate)
        return self.result


class FakeRegistrar:
    def __init__(self, *, registration_status="ACT", registration_unknown=False):
        self.registration_status = registration_status
        self.registration_unknown = registration_unknown
        self.register_calls = 0
        self.read_calls = []
        self.domains = []
        self.registered_domain = "novara.si"
        self.current_customer = {
            "provider": "openprovider",
            "readback_verified": True,
            "holder_type": "natural_person",
            "owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest(),
            "contact_fingerprint": "c" * 64,
            "email_fingerprint": "e" * 64,
            "email_verified": True,
        }

    def get_customer(self, owner_handle):
        self.read_calls.append(("customer", owner_handle))
        return dict(self.current_customer)

    def check_domain(self, domain):
        self.read_calls.append(("check", domain))
        return {
            "domain": domain,
            "available": True,
            "provider": "openprovider",
            "provider_receipt_id": None,
            "readback_verified": True,
            "evidence_refs": [f"openprovider://availability/{domain}"],
        }

    def quote_create(self, domain, funding_fx_basis=None):
        self.read_calls.append(("quote", domain))
        result = quote()
        result["domain"] = domain
        result["evidence_refs"] = [f"openprovider://price/{domain}"]
        return result

    def register(self, domain, owner_handle, idempotency_key):
        self.register_calls += 1
        self.registered_domain = domain
        if self.registration_unknown:
            raise openprovider.EffectUnknown()
        return {
            "domain": domain,
            "domain_id": "123",
            "provider_receipt_id": "123",
            "provider": "openprovider",
            "status": "submitted",
            "readback_verified": False,
        }

    def get_domain(self, domain_id):
        self.read_calls.append(("get", str(domain_id)))
        return {
            "id": str(domain_id),
            "domain": self.registered_domain,
            "status": self.registration_status,
            "provider": "openprovider",
            "provider_receipt_id": str(domain_id),
            "readback_verified": True,
            "owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest(),
        }

    def list_domains(self):
        self.read_calls.append(("list", ""))
        return self.domains


class HighCostRegistrar(FakeRegistrar):
    def quote_create(self, domain, funding_fx_basis=None):
        self.read_calls.append(("quote", domain))
        result = quote()
        result.update(domain=domain, registration_cost_eur="40.00", renewal_cost_eur="10.00")
        result["evidence_refs"] = [f"openprovider://price/{domain}"]
        return result


class RealisticRegistrar(FakeRegistrar):
    """Match the real adapter contract before owner-local evidence is attached."""

    def check_domain(self, domain):
        row = super().check_domain(domain)
        row.pop("evidence_refs")
        row["readback_payload"] = {"code": 0, "result": {"domain": domain, "status": "free"}}
        return row

    def quote_create(self, domain, funding_fx_basis=None):
        row = quote()
        row["available"] = None
        row["registration_amount"] = Decimal("10.00")
        row["renewal_amount"] = Decimal("10.00")
        row.pop("evidence_refs")
        row["readback_payloads"] = {
            "create": {
                "code": 0, "is_premium": False, "is_promotion": False,
                "price": {"currency": "EUR", "amount": "10.00"},
            },
            "renew": {
                "code": 0, "is_premium": False, "is_promotion": False,
                "price": {"currency": "EUR", "amount": "10.00"},
            },
        }
        return row


class MalformedQuoteRegistrar(RealisticRegistrar):
    def __init__(self, field_path, value):
        super().__init__()
        self.field_path = field_path
        self.value = value

    def quote_create(self, domain, funding_fx_basis=None):
        row = super().quote_create(domain, funding_fx_basis)
        target = row
        for key in self.field_path[:-1]:
            target = target[key]
        target[self.field_path[-1]] = self.value
        return row


class MalformedAvailabilityRegistrar(RealisticRegistrar):
    def __init__(self, private_value):
        super().__init__()
        self.private_value = private_value

    def check_domain(self, domain):
        row = super().check_domain(domain)
        result = row["readback_payload"]["result"]
        result.update(is_premium=self.private_value, reason=self.private_value, price=self.private_value)
        row["status"] = self.private_value
        return row


class FakeSedo:
    def __init__(self, *, listing_confirmed=False, price=Decimal("500.00"), min_price=Decimal("300.00"), currency="EUR"):
        self.listing_confirmed = listing_confirmed
        self.price = Decimal(str(price))
        self.min_price = Decimal(str(min_price))
        self.currency = currency
        self.insert_calls = 0
        self.read_calls = []

    def insert_for_sale(self, domain, price_eur, min_price_eur):
        self.insert_calls += 1
        return {
            "domain": domain,
            "status": "listing-pending",
            "listed": False,
            "provider": "sedo",
            "provider_receipt_id": None,
        }

    def domain_status(self, domain):
        self.read_calls.append(("status", domain))
        return {
            "domain": domain,
            "listed": self.listing_confirmed,
            "status": "listed" if self.listing_confirmed else "not-listed",
            "price": self.price,
            "currency": self.currency,
            "provider": "sedo",
            "provider_receipt_id": None,
            "readback_verified": True,
        }

    def domain_list(self, domains):
        domain = domains[0]
        self.read_calls.append(("list", domain))
        return [{
            "domain": domain,
            "listed": self.listing_confirmed,
            "price": self.price,
            "min_price": self.min_price,
            "fixed_price": False,
            "currency": self.currency,
            "provider": "sedo",
            "readback_verified": True,
        }]


def event_for(occurrence_id: str, *, effect: str, phase: str, candidate_id: str = "novara.si"):
    return {
        **context(occurrence_id.split(":", 1)[1]),
        "occurrence_id": occurrence_id,
        "candidate_id": candidate_id,
        "phase": phase,
        "command": "register",
        "exit_code": None,
        "effect": effect,
        "readback": None,
        "provider_receipt_id": None,
        "evidence_refs": [],
        "error_class": "effect_unknown" if effect == "effect_unknown" else None,
        "retryable": False,
        "next_action": "official_readback",
    }


def seed_listed_holding(
    state_root: Path,
    domain: str = "novara.si",
    resource_id: str = "123",
    registration_phase: str = "registration-readback",
    reserve_loss: bool = True,
) -> None:
    occurrence_id = "domain-flip:prior-run"
    owner_handle_fingerprint = hashlib.sha256(b"OWNER-1").hexdigest()
    registration = event_for(occurrence_id, effect="pending", phase="registration-dispatch", candidate_id=domain)
    registration_readback = {"owner_handle_fingerprint": owner_handle_fingerprint}
    if reserve_loss:
        registration_readback["maximum_loss_eur"] = "20.00"
    registration["readback"] = registration_readback
    run.append_event(state_root, registration)
    registration_readback = event_for(
        occurrence_id, effect="verified", phase=registration_phase, candidate_id=domain,
    )
    registration_readback.update(
        command="get_domain",
        provider_receipt_id=resource_id,
        readback={
            "id": resource_id,
            "domain": domain,
            "status": "ACT",
            "provider": "openprovider",
            "provider_receipt_id": resource_id,
            "readback_verified": True,
            "owner_handle_fingerprint": owner_handle_fingerprint,
        },
    )
    run.append_event(state_root, registration_readback)
    listing_dispatch = event_for(
        occurrence_id, effect="pending", phase="listing-dispatch", candidate_id=domain,
    )
    listing_dispatch.update(
        command="sedo_insert",
        readback={
            "domain": domain,
            "price": "500.00",
            "minimum_accepted_price_eur": "300.00",
            "currency": "EUR",
        },
    )
    run.append_event(state_root, listing_dispatch)
    listing_readback = event_for(
        occurrence_id, effect="verified", phase="listing-readback", candidate_id=domain,
    )
    listing_readback.update(
        command="sedo_status",
        readback={
            "domain": domain,
            "listed": True,
            "status": "listed",
            "price": "500.00",
            "min_price_eur": "300.00",
            "currency": "EUR",
            "provider": "sedo",
            "readback_verified": True,
        },
    )
    run.append_event(state_root, listing_readback)


def test_existing_listing_holding_is_reconciled_each_pass(tmp_path):
    seed_listed_holding(tmp_path)
    registrar = FakeRegistrar()
    sedo_client = FakeSedo(listing_confirmed=True)

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("held domain must not be reviewed for purchase"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["domain_already_held"]
    assert registrar.read_calls == [("get", "123")]
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    monitor = next(event for event in reversed(run.read_events(tmp_path))
                   if event["phase"] == "holding-monitor")
    assert monitor["effect"] == "verified"
    assert monitor["readback"]["listed"] is True


def test_unlisted_holding_is_not_counted_as_sale(tmp_path):
    seed_listed_holding(tmp_path)
    registrar = FakeRegistrar()
    sedo_client = FakeSedo(listing_confirmed=False)

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("changed listing must wait for sale readback"),
    )

    assert result["status"] == "sale_or_listing_change_unresolved"
    assert result["reason_codes"] == ["sale_or_listing_change_unresolved"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    monitor = next(event for event in reversed(run.read_events(tmp_path))
                   if event["phase"] == "holding-monitor")
    assert monitor["effect"] == "verified"
    assert monitor["readback"]["listed"] is False
    assert "revenue" not in monitor["readback"]


def test_holding_readback_failure_does_not_relist_or_claim_sale(tmp_path):
    seed_listed_holding(tmp_path)

    class FailingSedo(FakeSedo):
        def domain_status(self, domain):
            self.read_calls.append(("status", domain))
            raise openprovider.ProviderError("provider_read_failed")

    registrar = FakeRegistrar()
    sedo_client = FailingSedo(listing_confirmed=True)
    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("readback failure must not trigger a write"),
    )

    assert result["status"] == "holding_readback_unavailable"
    assert result["reason_codes"] == ["holding_readback_unavailable"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    monitor = next(event for event in reversed(run.read_events(tmp_path))
                   if event["phase"] == "holding-monitor")
    assert monitor["effect"] == "none"
    assert monitor["error_class"] == "provider_read_failed"


def test_registration_reconciled_event_is_a_valid_holding_readback(tmp_path):
    seed_listed_holding(tmp_path, registration_phase="registration-reconciled")
    registrar = FakeRegistrar()
    sedo_client = FakeSedo(listing_confirmed=True)

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("reconciled holding must not be reviewed for purchase"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["domain_already_held"]
    assert registrar.read_calls == [("get", "123")]
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]


def test_reconciled_registration_without_listing_dispatch_still_reads_all_providers(tmp_path):
    occurrence_id = "domain-flip:prior-run"
    owner_handle_fingerprint = hashlib.sha256(b"OWNER-1").hexdigest()
    dispatch = event_for(
        occurrence_id, effect="effect_unknown", phase="registration-dispatch",
    )
    dispatch["readback"] = {
        "owner_handle_fingerprint": owner_handle_fingerprint,
        "maximum_loss_eur": "20.00",
    }
    run.append_event(tmp_path, dispatch)

    registrar = FakeRegistrar()
    registrar.domains = [{
        "id": "123",
        "domain": "novara.si",
        "status": "ACT",
        "provider": "openprovider",
        "provider_receipt_id": "123",
        "readback_verified": True,
        "owner_handle_fingerprint": owner_handle_fingerprint,
    }]
    sedo_client = FakeSedo(listing_confirmed=False)
    reconciled = effect_reconcile.reconcile_occurrence(
        occurrence_id=occurrence_id,
        state_root=tmp_path,
        registrar=registrar,
    )

    assert reconciled["status"] == "resolved_registered"
    assert registrar.read_calls == [("list", "")]
    registrar.read_calls.clear()

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["nextcandidate.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("a recovered holding must not be reviewed for purchase"),
    )

    assert result["status"] == "holding_readback_unavailable"
    assert result["reason_codes"] == ["listing_terms_missing"]
    assert registrar.read_calls == [("get", "123")]
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    monitor = next(event for event in reversed(run.read_events(tmp_path))
                   if event["run_id"] == "run-2" and event["phase"] == "holding-monitor")
    assert monitor["error_class"] == "listing_terms_missing"


@pytest.mark.parametrize("alpha_mode", ["unlisted", "read_failed"])
def test_first_holding_issue_does_not_starve_later_holdings(tmp_path, alpha_mode):
    seed_listed_holding(tmp_path, domain="alpha.si", resource_id="123")
    seed_listed_holding(tmp_path, domain="beta.si", resource_id="456")

    class MultiRegistrar(FakeRegistrar):
        def get_domain(self, domain_id):
            self.read_calls.append(("get", str(domain_id)))
            domain = {"123": "alpha.si", "456": "beta.si"}[str(domain_id)]
            return {
                "id": str(domain_id),
                "domain": domain,
                "status": "ACT",
                "provider": "openprovider",
                "provider_receipt_id": str(domain_id),
                "readback_verified": True,
                "owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest(),
            }

    class MultiSedo(FakeSedo):
        def domain_status(self, domain):
            self.read_calls.append(("status", domain))
            if domain == "alpha.si" and alpha_mode == "read_failed":
                raise openprovider.ProviderError("provider_read_failed")
            listed = domain == "beta.si"
            return {
                "domain": domain,
                "listed": listed,
                "status": "listed" if listed else "not-listed",
                "price": self.price,
                "currency": self.currency,
                "provider": "sedo",
                "provider_receipt_id": None,
                "readback_verified": True,
            }

        def domain_list(self, domains):
            domain = domains[0]
            self.read_calls.append(("list", domain))
            listed = domain == "beta.si"
            return [{
                "domain": domain,
                "listed": listed,
                "price": self.price,
                "min_price": self.min_price,
                "fixed_price": False,
                "currency": self.currency,
                "provider": "sedo",
                "readback_verified": True,
            }]

    registrar = MultiRegistrar()
    sedo_client = MultiSedo(listing_confirmed=True)
    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["neonorbit.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("changed holding must stop new purchase review"),
    )

    assert result["status"] == (
        "holding_readback_unavailable" if alpha_mode == "read_failed"
        else "sale_or_listing_change_unresolved"
    )
    assert registrar.read_calls == [("get", "123"), ("get", "456")]
    expected_sedo_calls = [
        [("status", "alpha.si")]
        if alpha_mode == "read_failed" else [("status", "alpha.si"), ("list", "alpha.si")],
        [("status", "beta.si"), ("list", "beta.si")],
    ]
    assert sedo_client.read_calls == [call for group in expected_sedo_calls for call in group]
    monitors = [event for event in run.read_events(tmp_path)
                if event["run_id"] == "run-2" and event["phase"] == "holding-monitor"]
    assert {event["candidate_id"] for event in monitors} == {"alpha.si", "beta.si"}


def test_effect_unknown_candidate_does_not_starve_known_holding_monitor(tmp_path):
    seed_listed_holding(tmp_path, domain="beta.si", resource_id="456")
    unknown = event_for(
        "domain-flip:unknown-run", effect="effect_unknown", phase="registration-dispatch",
        candidate_id="alpha.si",
    )
    unknown["readback"] = {"maximum_loss_eur": "20.00"}
    run.append_event(tmp_path, unknown)
    registrar = FakeRegistrar()
    registrar.registered_domain = "beta.si"
    sedo_client = FakeSedo(listing_confirmed=True)

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-current"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["alpha.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("unknown candidate must remain fenced"),
    )

    assert result["status"] == "effect_unknown"
    assert registrar.read_calls == [("get", "456")]
    assert sedo_client.read_calls == [("status", "beta.si"), ("list", "beta.si")]
    assert registrar.register_calls == 0


def test_missing_cap_reservation_does_not_starve_known_holding_monitor(tmp_path):
    seed_listed_holding(tmp_path, domain="beta.si", resource_id="456", reserve_loss=False)
    registrar = FakeRegistrar()
    registrar.registered_domain = "beta.si"
    sedo_client = FakeSedo(listing_confirmed=True)

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-current"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["neonorbit.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("unknown cap must block candidate review"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["cap_reservation_evidence_missing"]
    assert registrar.read_calls == [("get", "456")]
    assert sedo_client.read_calls == [("status", "beta.si"), ("list", "beta.si")]
    assert registrar.register_calls == 0


def test_event_writer_records_required_occurrence_fields(tmp_path):
    event = event_for("domain-flip:run-1", effect="none", phase="started")
    path = run.append_event(tmp_path, event)

    record = json.loads(path.read_text(encoding="utf-8").strip())
    required = {
        "candidate_id", "run_id", "owner_id", "occurrence_id", "release_sha",
        "loaded_argv", "loaded_env", "phase", "command", "exit_code", "effect",
        "readback", "provider_receipt_id", "evidence_refs", "error_class",
        "retryable", "next_action",
    }
    assert required.issubset(record)
    assert path.name == "events.jsonl"
    assert path.stat().st_mode & 0o777 == 0o600

    bad = dict(event)
    bad["readback"] = {"email": "private@example.test"}
    with pytest.raises(ValueError):
        run.append_event(tmp_path, bad)
    argv_secret = dict(event)
    argv_secret["loaded_argv"] = ["run.py", "--api-key=FAKE_SECRET"]
    with pytest.raises(ValueError):
        run.append_event(tmp_path, argv_secret)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_readback_limits_registration_and_renewal_amounts_to_finite_nonnegative_decimals():
    assert run._valid_readback({
        "registration_amount": Decimal("0.00"),
        "renewal_amount": "10.00",
    })
    for field, value in (
        ("registration_amount", "東京都渋谷区神南1丁目2番3号"),
        ("renewal_amount", "電話番号: ０９０－１２３４－５６７８"),
        ("registration_amount", "〒150-0041"),
        ("registration_amount", "NaN"),
        ("renewal_amount", "-0.01"),
    ):
        assert not run._valid_readback({field: value})


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("registration_amount",), "東京都渋谷区神南1丁目2番3号"),
        (("renewal_amount",), "電話番号: ０９０－１２３４－５６７８"),
        (("readback_payloads", "create", "price", "amount"), "〒150-0041"),
    ],
)
def test_provider_quote_writer_rejects_non_numeric_amount_before_writing(tmp_path, field_path, value):
    quote_readback = RealisticRegistrar().quote_create("novara.si")
    target = quote_readback
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"

    with pytest.raises(ValueError):
        run._save_provider_readback(evidence_dir, "novara.si", "quote", quote_readback)

    assert not (evidence_dir / "openprovider-price-readbacks.json").exists()


@pytest.mark.parametrize(
    "price_value",
    [
        "東京都渋谷区神南1丁目2番3号",
        "電話番号: ０９０－１２３４－５６７８",
    ],
    ids=["japanese_address", "japanese_phone"],
)
def test_availability_evidence_omits_unvalidated_price(price_value, tmp_path):
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"
    availability = {
        "available": True,
        "status": price_value,
        "readback_payload": {
            "code": 0,
            "result": {"domain": "novara.si", "status": "free", "price": price_value},
        },
    }

    run._save_provider_readback(evidence_dir, "novara.si", "availability", availability)

    saved = json.loads((evidence_dir / "openprovider-availability.json").read_text(encoding="utf-8"))
    assert saved["readback_payload"]["result"] == {"domain": "novara.si", "status": "free"}
    assert saved.get("status") is None
    assert price_value not in json.dumps(saved, ensure_ascii=False)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("readback_payloads", "create", "code"), 1),
        (("readback_payloads", "create", "is_premium"), "123 North Main Street"),
        (("readback_payloads", "renew", "is_promotion"), "渋谷区神南1丁目2番3号"),
        (("readback_payloads", "create", "price", "currency"), "150-0041"),
        (("readback_payloads", "renew", "price", "currency"), "CAD"),
        (("readback_payloads", "renew", "price", "amount"), "Infinity"),
    ],
    ids=["create_code", "create_premium_flag", "renew_promotion_flag", "create_currency", "renew_currency", "renew_amount"],
)
def test_provider_quote_writer_rejects_untrusted_metadata_before_writing(tmp_path, field_path, value):
    quote_readback = RealisticRegistrar().quote_create("novara.si")
    target = quote_readback
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"

    with pytest.raises(ValueError):
        run._save_provider_readback(evidence_dir, "novara.si", "quote", quote_readback)

    assert not (evidence_dir / "openprovider-price-readbacks.json").exists()


def test_availability_evidence_keeps_only_domain_status_and_boolean_flags(tmp_path):
    private_value = "123 North Main Street"
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"
    availability = {
        "available": private_value,
        "status": private_value,
        "readback_payload": {
            "code": 0,
            "result": {
                "domain": "novara.si",
                "status": "free",
                "is_premium": private_value,
                "reason": private_value,
                "price": private_value,
            },
        },
    }

    run._save_provider_readback(evidence_dir, "novara.si", "availability", availability)

    saved = json.loads((evidence_dir / "openprovider-availability.json").read_text(encoding="utf-8"))
    assert saved["readback_payload"]["result"] == {"domain": "novara.si", "status": "free"}
    assert saved.get("status") is None
    assert saved.get("available") is None
    assert private_value not in json.dumps(saved, ensure_ascii=False)


def test_event_writer_rejects_private_values_in_allowed_fields(tmp_path):
    event = event_for("domain-flip:run-1", effect="none", phase="readback")
    event["readback"] = {"status": "FAKE_PERSON@example.invalid"}

    with pytest.raises(ValueError):
        run.append_event(tmp_path, event)

    private_env = event_for("domain-flip:run-1", effect="none", phase="readback")
    private_env["loaded_env"] = {"LM_PRIVATE_NOTE": "123 Main Street; +1 202 555 0123"}
    with pytest.raises(ValueError):
        run.append_event(tmp_path, private_env)


def test_runner_result_is_restricted_to_private_mode(tmp_path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(mode=0o700)
    result_path = evidence_dir / "result.json"
    result_path.write_text(json.dumps(review_register()), encoding="utf-8")
    os.chmod(result_path, 0o644)

    result = run._private_runner_json(result_path, evidence_dir)

    assert result["action"] == "register"
    assert result_path.stat().st_mode & 0o777 == 0o600


def test_review_validator_enforces_schema_types_and_unique_refs():
    allowed = {"euipo://trademark-search/novara"}
    numeric_prices = review_register()
    numeric_prices["listing_price_eur"] = 500
    assert run._validate_review(numeric_prices, "novara.si", allowed) is None

    duplicate_refs = review_register()
    duplicate_refs["evidence_refs"] *= 2
    assert run._validate_review(duplicate_refs, "novara.si", allowed) is None

    contact_text = review_register()
    contact_text["reason"] = "123 Main Street; +1 202 555 0123"
    assert run._validate_review(contact_text, "novara.si", allowed) is None


def test_review_validator_accepts_ordinary_review():
    review = review_register()

    assert run._validate_review(review, "novara.si", {"euipo://trademark-search/novara"}) == review


@pytest.mark.parametrize(
    "reason",
    [
        "東京都渋谷区神南1丁目2番3号",
        "電話番号: ０９０－１２３４－５６７８",
        "〒150-0041",
    ],
    ids=["japanese_address", "japanese_phone", "japanese_postal_code"],
)
def test_review_validator_rejects_japanese_private_contact_text(reason):
    review = review_register()
    review["reason"] = reason

    assert run._validate_review(review, "novara.si", {"euipo://trademark-search/novara"}) is None


@pytest.mark.parametrize(
    "reason",
    [
        "123 North Main Street",
        "123 West Lake View Road",
        "渋谷区神南1丁目2番3号",
        "150-0041",
    ],
    ids=["directional_street", "multiword_street", "japanese_address_without_prefecture", "bare_postal_code"],
)
def test_review_validator_rejects_expanded_address_and_postal_code_text(reason):
    review = review_register()
    review["reason"] = reason

    assert run._validate_review(review, "novara.si", {"euipo://trademark-search/novara"}) is None


def test_pass_is_scout_only_without_provider_credentials(tmp_path):
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=None,
        sedo=None,
        rights_searcher=None,
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("model must not run without providers"),
    )

    assert result["status"] == "scout_only"
    assert "provider_credentials_missing" in result["reason_codes"]
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["effect"] == "none"


def test_missing_rights_credentials_keep_scout_only(tmp_path):
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()
    rights = FakeRights({"status": "unavailable", "reason_code": "credential_missing"})

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=rights,
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("model must not run without rights evidence"),
    )

    assert result["status"] == "scout_only"
    assert "rights_evidence_missing" in result["reason_codes"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0


def test_model_choice_cannot_bypass_purchase_policy(tmp_path):
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(remaining="1.00"),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "no_purchase"
    assert "funding_insufficient" in result["reason_codes"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0


def test_owner_persists_and_attaches_real_provider_readbacks(tmp_path):
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=RealisticRegistrar(registration_status="PRE"),
        sedo=FakeSedo(),
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "registration_pending"
    events = [json.loads(row) for row in (tmp_path / "events.jsonl").read_text().splitlines()]
    availability = next(row for row in events if row["phase"] == "availability-readback")
    price = next(row for row in events if row["phase"] == "quote-readback")
    assert any(ref.startswith("domain-flip://evidence/") for ref in availability["evidence_refs"])
    assert any(ref.startswith("domain-flip://evidence/") for ref in price["evidence_refs"])
    assert "domain-flip://evidence/run-1/novara/openprovider-availability.json" in availability["evidence_refs"]
    assert "domain-flip://evidence/run-1/novara/openprovider-price-readbacks.json" in price["evidence_refs"]
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"
    assert (evidence_dir / "openprovider-availability.json").stat().st_mode & 0o777 == 0o600
    assert (evidence_dir / "openprovider-price-readbacks.json").stat().st_mode & 0o777 == 0o600


def test_standard_review_runner_artifacts_are_ephemeral_until_validation(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(mode=0o700)
    raw_review = {
        "action": "register",
        "selected_domain": "novara.si",
        "listing_price_eur": "500.00",
        "minimum_accepted_price_eur": "300.00",
        "rights_risk": "clear",
        "reason": "private@example.test",
        "evidence_refs": ["euipo://trademark-search/novara"],
    }

    def fake_subprocess_run(command, **_kwargs):
        runner_dir = Path(command[command.index("--evidence-dir") + 1])
        runner_dir.mkdir(mode=0o700, exist_ok=True)
        result_path = runner_dir / "attempt-01.result.json"
        run._write_private_json(result_path, raw_review)
        run._write_private_json(runner_dir / "summary.json", {"result_path": str(result_path)})
        (runner_dir / "attempt-01.stdout.log").write_text("private@example.test", encoding="utf-8")
        (runner_dir / "attempt-01.stderr.log").write_text("private@example.test", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(run.subprocess, "run", fake_subprocess_run)

    returned = run._run_agent_review({"candidate": {"domain": "novara.si"}}, evidence_dir)

    assert returned["reason"] == "private@example.test"
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in evidence_dir.rglob("*") if path.is_file()
    )
    assert "private@example.test" not in persisted
    assert not list(evidence_dir.glob(".candidate-review-*"))
    assert not (evidence_dir / "review.json").exists()


def test_changed_provider_contact_keeps_candidate_scout_only(tmp_path):
    registrar = RealisticRegistrar()
    registrar.current_customer["contact_fingerprint"] = "d" * 64

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=FakeSedo(),
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["registrant_contact_readback_mismatch"]
    assert registrar.register_calls == 0
    assert ("customer", "OWNER-1") in registrar.read_calls


def test_optional_whois_publication_without_approval_keeps_candidate_scout_only(tmp_path):
    registrar = RealisticRegistrar()
    registrant = verified_registrant()
    registrant["whois_optional_fields_opted_in"] = ["name"]

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=registrant,
        registrar=registrar,
        sedo=FakeSedo(),
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("review must not run without WHOIS scope"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["whois_publication_unverified"]
    assert registrar.register_calls == 0


def test_owner_accepts_openprovider_quote_when_promotion_flag_is_missing(tmp_path):
    class OpenProviderShapeRegistrar(RealisticRegistrar):
        def quote_create(self, domain, funding_fx_basis=None):
            row = super().quote_create(domain, funding_fx_basis)
            for payload in row["readback_payloads"].values():
                payload["is_promotion"] = None
            return row

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=OpenProviderShapeRegistrar(registration_status="PRE"),
        sedo=FakeSedo(),
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "registration_pending"
    readbacks = json.loads(
        (tmp_path / "evidence" / "run-1" / "novara" / "openprovider-price-readbacks.json")
        .read_text(encoding="utf-8")
    )["readback_payloads"]
    for operation in ("create", "renew"):
        assert readbacks[operation]["is_premium"] is False
        assert "is_promotion" not in readbacks[operation]


@pytest.mark.parametrize(
    ("field_path", "private_value"),
    [
        (("registration_amount",), "東京都渋谷区神南1丁目2番3号"),
        (("renewal_amount",), "電話番号: ０９０－１２３４－５６７８"),
        (("registration_amount",), "〒150-0041"),
        (("readback_payloads", "create", "price", "amount"), "東京都渋谷区神南1丁目2番3号"),
        (("readback_payloads", "renew", "price", "amount"), "電話番号: ０９０－１２３４－５６７８"),
        (("readback_payloads", "create", "price", "amount"), "〒150-0041"),
    ],
    ids=["registration_address", "renewal_phone", "registration_postal_code",
         "create_address", "renew_phone", "create_postal_code"],
)
def test_owner_rejects_private_quote_amounts_before_persisting_or_reviewing(
    tmp_path, field_path, private_value,
):
    registrar = MalformedQuoteRegistrar(field_path, private_value)
    sedo_client = FakeSedo()
    reviewer_packets = []

    def reviewer(packet):
        reviewer_packets.append(packet)
        return review_register()

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=reviewer,
    )

    assert result["reason_codes"] == ["registrar_read_failed"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    assert reviewer_packets == []
    evidence_dir = tmp_path / "evidence" / "run-1" / "novara"
    assert not (evidence_dir / "candidate-packet.json").exists()
    assert not (evidence_dir / "openprovider-availability.json").exists()
    assert not (evidence_dir / "openprovider-price-readbacks.json").exists()
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file()
    )
    assert private_value not in persisted
    assert json.dumps(private_value)[1:-1] not in persisted
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert not any(event["phase"] == "quote-readback" for event in events)


@pytest.mark.parametrize(
    ("field_path", "private_value"),
    [
        (("readback_payloads", "create", "is_premium"), "123 North Main Street"),
        (("readback_payloads", "renew", "is_promotion"), "渋谷区神南1丁目2番3号"),
        (("readback_payloads", "create", "price", "currency"), "150-0041"),
    ],
    ids=["premium_flag_address", "promotion_flag_address", "currency_postal_code"],
)
def test_owner_rejects_private_quote_metadata_before_model_or_persistence(
    tmp_path, field_path, private_value,
):
    registrar = MalformedQuoteRegistrar(field_path, private_value)
    sedo_client = FakeSedo()
    reviewer_packets = []

    def reviewer(packet):
        reviewer_packets.append(packet)
        return review_register()

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=reviewer,
    )

    assert result["reason_codes"] == ["registrar_read_failed"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    assert reviewer_packets == []
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file()
    )
    assert private_value not in persisted
    assert not any(private_value in json.dumps(packet, ensure_ascii=False) for packet in reviewer_packets)
    assert not (tmp_path / "evidence" / "run-1" / "novara" / "openprovider-price-readbacks.json").exists()


def test_owner_sanitizes_availability_private_metadata_before_review_or_persistence(tmp_path):
    private_value = "123 North Main Street"
    registrar = MalformedAvailabilityRegistrar(private_value)
    sedo_client = FakeSedo()
    reviewer_packets = []

    def reviewer(packet):
        reviewer_packets.append(packet)
        review = review_register()
        review["action"] = "skip"
        return review

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=reviewer,
    )

    assert result["status"] == "scout_only"
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0
    assert len(reviewer_packets) == 1
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file()
    )
    assert private_value not in persisted
    assert private_value not in json.dumps(reviewer_packets, ensure_ascii=False)
    availability_path = tmp_path / "evidence" / "run-1" / "novara" / "openprovider-availability.json"
    saved = json.loads(availability_path.read_text(encoding="utf-8"))
    assert saved["readback_payload"]["result"] == {"domain": "novara.si", "status": "free"}
    assert saved["available"] is True


def test_stale_business_balance_keeps_scout_only(tmp_path):
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()
    funding = business_funding()
    funding["balance_readback_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=funding,
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("model must not run on stale balance"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["business_funding_unverified"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0


def test_stale_sedo_fee_readback_keeps_scout_only(tmp_path):
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()
    fees = fee_evidence()
    fees["readback_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fees,
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("model must not run on stale fee schedule"),
    )

    assert result["status"] == "scout_only"
    assert result["reason_codes"] == ["market_or_fee_evidence_missing"]
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0


def test_stale_measured_cost_readback_keeps_scout_only(tmp_path):
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()
    fees = fee_evidence()
    fees["cost_readback_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fees,
        candidate_names=["novara.si"],
        reviewer=lambda *_args, **_kwargs: pytest.fail("model must not run on stale cost evidence"),
    )

    assert result["status"] == "scout_only"
    assert registrar.register_calls == 0
    assert sedo_client.insert_calls == 0


def test_domain_insert_requires_registered_owner_readback(tmp_path):
    registrar = FakeRegistrar(registration_status="PRE")
    sedo_client = FakeSedo()
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "registration_pending"
    assert registrar.register_calls == 1
    assert sedo_client.insert_calls == 0
    registration_readback = next(
        event for event in reversed(run.read_events(tmp_path))
        if event["phase"] == "registration-readback"
    )
    assert registration_readback["effect"] == "effect_unknown"


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", "999"), ("provider", "sedo"), ("provider_receipt_id", "999")],
)
def test_registration_readback_must_match_provider_resource_id(tmp_path, field, value):
    class MismatchedRegistrar(FakeRegistrar):
        def get_domain(self, domain_id):
            readback = super().get_domain(domain_id)
            readback[field] = value
            return readback

    registrar = MismatchedRegistrar()
    sedo_client = FakeSedo()
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "registration_pending"
    assert registrar.register_calls == 1
    assert sedo_client.insert_calls == 0
    registration_readback = next(
        event for event in reversed(run.read_events(tmp_path))
        if event["phase"] == "registration-readback"
    )
    assert registration_readback["effect"] == "effect_unknown"


def test_registration_submit_receipt_must_match_domain_id(tmp_path):
    class MismatchedReceiptRegistrar(FakeRegistrar):
        def register(self, domain, owner_handle, idempotency_key):
            submitted = super().register(domain, owner_handle, idempotency_key)
            submitted["provider_receipt_id"] = "999"
            return submitted

    registrar = MismatchedReceiptRegistrar()
    sedo_client = FakeSedo()
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "effect_unknown"
    assert registrar.read_calls == [("check", "novara.si"), ("quote", "novara.si"), ("customer", "OWNER-1")]
    assert sedo_client.insert_calls == 0


def test_submitted_registration_is_reconciled_before_reported_resolved(tmp_path):
    event = event_for("domain-flip:run-1", effect="submitted", phase="registration-submitted")
    event["provider_receipt_id"] = "123"
    event["readback"] = {"owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest()}
    run.append_event(tmp_path, event)
    registrar = FakeRegistrar(registration_status="PRE")

    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=registrar,
    )

    assert result["status"] == "held"
    assert registrar.read_calls == [("get", "123")]


def test_submitted_listing_is_reconciled_before_reported_resolved(tmp_path):
    dispatch = event_for("domain-flip:run-1", effect="pending", phase="listing-dispatch")
    dispatch["command"] = "sedo_insert"
    dispatch["readback"] = {
        "domain": "novara.si",
        "price": "500.00",
        "minimum_accepted_price_eur": "300.00",
        "currency": "EUR",
    }
    run.append_event(tmp_path, dispatch)
    submitted = event_for("domain-flip:run-1", effect="submitted", phase="listing-submitted")
    submitted["command"] = "sedo_insert"
    run.append_event(tmp_path, submitted)
    sedo_client = FakeSedo(listing_confirmed=False)

    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=FakeRegistrar(),
        sedo=sedo_client,
    )

    assert result["status"] == "held"
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]


def test_lost_registration_response_is_not_replayed(tmp_path):
    registrar = FakeRegistrar(registration_unknown=True)
    sedo_client = FakeSedo()
    args = {
        "state_root": tmp_path,
        "funding": business_funding(),
        "registrant": verified_registrant(),
        "registrar": registrar,
        "sedo": sedo_client,
        "rights_searcher": FakeRights(),
        "market_evidence": market_evidence(),
        "fee_evidence": fee_evidence(),
        "candidate_names": ["novara.si"],
        "reviewer": review_register,
    }

    first = run.run_once(context=context("run-1"), **args)
    second = run.run_once(context=context("run-2"), **args)

    assert first["status"] == "effect_unknown"
    assert second["status"] == "effect_unknown"
    assert registrar.register_calls == 1
    assert sedo_client.insert_calls == 0


def test_unclassified_registration_exception_keeps_effect_fence(tmp_path):
    class CrashingRegistrar(FakeRegistrar):
        def register(self, domain, owner_handle, idempotency_key):
            self.register_calls += 1
            raise RuntimeError("response stream closed after dispatch")

    registrar = CrashingRegistrar()
    sedo_client = FakeSedo()
    args = {
        "state_root": tmp_path,
        "funding": business_funding(),
        "registrant": verified_registrant(),
        "registrar": registrar,
        "sedo": sedo_client,
        "rights_searcher": FakeRights(),
        "market_evidence": market_evidence(),
        "fee_evidence": fee_evidence(),
        "candidate_names": ["novara.si"],
        "reviewer": review_register,
    }

    first = run.run_once(context=context("run-1"), **args)
    second = run.run_once(context=context("run-2"), **args)

    assert first["status"] == "effect_unknown"
    assert second["status"] == "effect_unknown"
    assert registrar.register_calls == 1
    assert sedo_client.insert_calls == 0


def test_prior_purchase_reservations_enforce_cumulative_cap(tmp_path):
    registrar = HighCostRegistrar(registration_status="ACT")
    sedo_client = FakeSedo()
    shared = {
        "state_root": tmp_path,
        "funding": business_funding(remaining="100.00"),
        "registrant": verified_registrant(),
        "registrar": registrar,
        "sedo": sedo_client,
        "rights_searcher": FakeRights(),
        "market_evidence": market_evidence(),
        "fee_evidence": fee_evidence(),
        "reviewer": review_current_candidate,
    }

    first = run.run_once(context=context("run-1"), candidate_names=["alpha.si"], **shared)
    second = run.run_once(context=context("run-2"), candidate_names=["beta.si"], **shared)
    third = run.run_once(context=context("run-3"), candidate_names=["gamma.si"], **shared)

    assert first["status"] == "listing_pending"
    assert second["status"] == "listing_pending"
    assert third["status"] == "no_purchase"
    assert "lifetime_cap_exceeded" in third["reason_codes"]
    assert registrar.register_calls == 2


def test_missing_prior_reservation_fails_closed(tmp_path):
    run.append_event(
        tmp_path,
        event_for("domain-flip:old-run", effect="effect_unknown", phase="registration-dispatch",
                  candidate_id="novara.si"),
    )
    registrar = FakeRegistrar()
    sedo_client = FakeSedo()

    result = run.run_once(
        state_root=tmp_path,
        context=context("run-2"),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["beta.si"],
        reviewer=review_current_candidate,
    )

    assert result["status"] == "scout_only"
    assert "cap_reservation_evidence_missing" in result["reason_codes"]
    assert registrar.register_calls == 0


def test_sedo_listing_is_pending_until_provider_readback(tmp_path):
    registrar = FakeRegistrar(registration_status="ACT")
    sedo_client = FakeSedo(listing_confirmed=False)
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "listing_pending"
    assert sedo_client.insert_calls == 1
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]


def test_listed_requires_matching_current_price_minimum_and_currency(tmp_path):
    registrar = FakeRegistrar(registration_status="ACT")
    sedo_client = FakeSedo(listing_confirmed=True, price="1.00", min_price="0.50", currency="USD")
    result = run.run_once(
        state_root=tmp_path,
        context=context(),
        funding=business_funding(),
        registrant=verified_registrant(),
        registrar=registrar,
        sedo=sedo_client,
        rights_searcher=FakeRights(),
        market_evidence=market_evidence(),
        fee_evidence=fee_evidence(),
        candidate_names=["novara.si"],
        reviewer=review_register,
    )

    assert result["status"] == "listing_pending"
    assert sedo_client.insert_calls == 1
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]


def test_reconcile_uses_read_only_calls_and_holds_ambiguous_state(tmp_path):
    run.append_event(
        tmp_path,
        event_for("domain-flip:run-1", effect="effect_unknown", phase="registration-dispatch"),
    )
    registrar = FakeRegistrar()
    resolver_calls = []

    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=registrar,
        resolve=lambda *_args, **_kwargs: resolver_calls.append("resolve") or True,
    )

    assert result["status"] == "held"
    assert registrar.read_calls == [("list", "")]
    assert registrar.register_calls == 0
    assert resolver_calls == []


def test_reconcile_resolves_only_matching_registered_owner_readback(tmp_path):
    event = event_for("domain-flip:run-1", effect="effect_unknown", phase="registration-dispatch")
    owner_handle_fingerprint = hashlib.sha256(b"OWNER-1").hexdigest()
    event["readback"] = {"owner_handle_fingerprint": owner_handle_fingerprint}
    run.append_event(tmp_path, event)
    registrar = FakeRegistrar()
    registrar.domains = [{
        "id": "123",
        "domain": "novara.si",
        "status": "ACT",
        "provider": "openprovider",
        "provider_receipt_id": "123",
        "readback_verified": True,
        "owner_handle_fingerprint": owner_handle_fingerprint,
    }]
    resolver_calls = []

    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=registrar,
        resolve=lambda *args: resolver_calls.append(args),
    )

    assert result["status"] == "resolved_registered"
    assert result["provider_receipt_id"] == "123"
    assert registrar.read_calls == [("list", "")]
    assert registrar.register_calls == 0
    assert len(resolver_calls) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", "999"), ("provider", "sedo"), ("provider_receipt_id", "999")],
)
def test_reconcile_holds_registration_readback_with_wrong_provider_identity(tmp_path, field, value):
    event = event_for("domain-flip:run-1", effect="effect_unknown", phase="registration-dispatch")
    event["provider_receipt_id"] = "123"
    event["readback"] = {"owner_handle_fingerprint": hashlib.sha256(b"OWNER-1").hexdigest()}
    run.append_event(tmp_path, event)

    class MismatchedRegistrar(FakeRegistrar):
        def get_domain(self, domain_id):
            readback = super().get_domain(domain_id)
            readback[field] = value
            return readback

    registrar = MismatchedRegistrar()
    resolver_calls = []
    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=registrar,
        resolve=lambda *args: resolver_calls.append(args),
    )

    assert result["status"] == "held"
    assert registrar.read_calls == [("get", "123")]
    assert resolver_calls == []


def test_reconcile_holds_listing_with_mismatched_terms(tmp_path):
    event = event_for("domain-flip:run-1", effect="effect_unknown", phase="listing-dispatch")
    event["command"] = "sedo_insert"
    event["readback"] = {
        "domain": "novara.si",
        "price": "500.00",
        "minimum_accepted_price_eur": "300.00",
        "currency": "EUR",
    }
    run.append_event(tmp_path, event)
    sedo_client = FakeSedo(listing_confirmed=True, price="1.00", min_price="0.50", currency="USD")
    resolver_calls = []

    result = effect_reconcile.reconcile_occurrence(
        occurrence_id="domain-flip:run-1",
        state_root=tmp_path,
        registrar=FakeRegistrar(),
        sedo=sedo_client,
        resolve=lambda *args: resolver_calls.append(args),
    )

    assert result["status"] == "held"
    assert result["reason_code"] == "listing_terms_mismatch_or_ambiguous"
    assert sedo_client.read_calls == [("status", "novara.si"), ("list", "novara.si")]
    assert resolver_calls == []
