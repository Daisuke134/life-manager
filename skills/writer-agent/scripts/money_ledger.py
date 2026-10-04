#!/usr/bin/env python3
"""Canonical typed Writer metrics, money, subscription, fee, payout, and attribution ledger."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SHA256_RE = re.compile(r"[0-9a-f]{64}")
ARTIFACT_RE = re.compile(r"[A-Za-z0-9-]+__[A-Za-z0-9-]+__[A-Za-z0-9-]+")
CURRENCY_RE = re.compile(r"[A-Z]{3}")
DEFAULT_REVENUE_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "revenue-surfaces.json"
)


class MoneyInvariant(ValueError):
    pass


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoneyInvariant(f"{field} must be nonempty text")
    return " ".join(value.split())


def _timestamp(value: Any, field: str) -> str:
    value = _text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MoneyInvariant(f"{field} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise MoneyInvariant(f"{field} must include timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def _url(value: Any, field: str) -> str:
    value = _text(value, field)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise MoneyInvariant(f"{field} must be public HTTPS")
    return value


def _currency(value: Any) -> str:
    value = _text(value, "currency").upper()
    if CURRENCY_RE.fullmatch(value) is None:
        raise MoneyInvariant("currency must be a three-letter code")
    return value


def _amount(
    value: Any, field: str, *, nullable: bool = False, allow_negative: bool = False
) -> float | None:
    if nullable and value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MoneyInvariant(f"{field} must be a finite number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as error:
        raise MoneyInvariant(f"{field} must be a finite number") from error
    if not math.isfinite(numeric) or (numeric < 0 and not allow_negative):
        constraint = "number" if allow_negative else "nonnegative number"
        raise MoneyInvariant(f"{field} must be a finite {constraint}")
    return numeric


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256(chr(10).join(parts).encode()).hexdigest()[:24]}"


class MoneyLedger:
    def __init__(self, path: Path | str, *, revenue_config: Path | str = DEFAULT_REVENUE_CONFIG):
        self.path = Path(path)
        self.revenue_config = Path(revenue_config)
        self.revenue_surfaces = self._load_revenue_surfaces()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _load_revenue_surfaces(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.revenue_config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MoneyInvariant(f"revenue surface config is unavailable: {error}") from error
        if payload.get("schema_version") != 1:
            raise MoneyInvariant("revenue surface config schema_version must be 1")
        for section in ("destinations", "account_streams"):
            values = payload.get(section)
            if not isinstance(values, dict) or not values:
                raise MoneyInvariant(f"revenue surface config requires {section}")
            for name, contract in values.items():
                if (
                    not isinstance(name, str) or not name
                    or not isinstance(contract, dict)
                    or not isinstance(contract.get("revenue_capable"), bool)
                ):
                    raise MoneyInvariant(f"invalid revenue surface contract in {section}")
        return payload

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS money_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    live_url TEXT NOT NULL UNIQUE,
                    published_at TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metric_observations (
                    observation_id TEXT PRIMARY KEY,
                    artifact_id TEXT REFERENCES money_artifacts(artifact_id),
                    scope TEXT NOT NULL CHECK(scope IN ('artifact','account')),
                    metric TEXT NOT NULL,
                    value REAL,
                    unit TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('verified','unknown','test')),
                    reason TEXT,
                    observed_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    UNIQUE(scope,artifact_id,metric,observed_at,receipt_sha256)
                );
                CREATE TABLE IF NOT EXISTS money_events (
                    event_id TEXT PRIMARY KEY,
                    artifact_id TEXT REFERENCES money_artifacts(artifact_id),
                    scope TEXT NOT NULL CHECK(scope IN ('artifact','account')),
                    stream TEXT NOT NULL,
                    revenue_class TEXT NOT NULL CHECK(
                        revenue_class IN ('direct_writing','product_derived','network_fee')
                    ),
                    kind TEXT NOT NULL CHECK(
                        kind IN ('sale','editorial_fee','subscription_charge','refund')
                    ),
                    amount REAL,
                    currency TEXT,
                    status TEXT NOT NULL CHECK(
                        status IN ('verified_received','pending','unknown','test','refunded')
                    ),
                    counterparty TEXT NOT NULL,
                    external_receipt_id TEXT UNIQUE,
                    source_url TEXT NOT NULL,
                    test INTEGER NOT NULL CHECK(test IN (0,1)),
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscription_contracts (
                    subscription_id TEXT PRIMARY KEY,
                    acquisition_artifact_id TEXT REFERENCES money_artifacts(artifact_id),
                    stream TEXT NOT NULL,
                    amount REAL,
                    currency TEXT,
                    interval_name TEXT NOT NULL CHECK(interval_name IN ('month','year','unknown')),
                    status TEXT NOT NULL CHECK(
                        status IN ('active','canceled','past_due','trial','unknown','test')
                    ),
                    external_contract_id TEXT NOT NULL UNIQUE,
                    source_url TEXT NOT NULL,
                    test INTEGER NOT NULL CHECK(test IN (0,1)),
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS money_fees (
                    fee_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES money_events(event_id),
                    fee_kind TEXT NOT NULL,
                    amount REAL,
                    currency TEXT,
                    status TEXT NOT NULL CHECK(status IN ('verified','unknown','test')),
                    external_receipt_id TEXT NOT NULL UNIQUE,
                    source_url TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS payouts (
                    payout_id TEXT PRIMARY KEY,
                    stream TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('paid','pending','failed','unknown','test')),
                    gross_amount REAL,
                    fee_amount REAL,
                    net_amount REAL,
                    currency TEXT,
                    external_receipt_id TEXT NOT NULL UNIQUE,
                    source_url TEXT NOT NULL,
                    test INTEGER NOT NULL CHECK(test IN (0,1)),
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS payout_allocations (
                    payout_id TEXT NOT NULL REFERENCES payouts(payout_id),
                    event_id TEXT NOT NULL REFERENCES money_events(event_id),
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    PRIMARY KEY(payout_id,event_id)
                );
                CREATE TABLE IF NOT EXISTS commercial_payment_bindings (
                    payment_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE REFERENCES money_events(event_id),
                    payout_id TEXT NOT NULL UNIQUE REFERENCES payouts(payout_id),
                    opportunity_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    delivery_id TEXT NOT NULL,
                    publication_id TEXT,
                    artifact_sha256 TEXT NOT NULL CHECK(
                        length(artifact_sha256)=64
                        AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'
                    ),
                    payment_trigger TEXT NOT NULL CHECK(
                        payment_trigger IN ('APPROVAL','DELIVERY','PUBLICATION')
                    ),
                    trigger_evidence_id TEXT NOT NULL,
                    payment_evidence_id TEXT NOT NULL UNIQUE,
                    revenue_type TEXT NOT NULL CHECK(
                        revenue_type IN ('ONE_TIME','RECURRING_RETAINER')
                    ),
                    recurring_contract_id TEXT,
                    gross_amount REAL NOT NULL CHECK(gross_amount > 0),
                    fee_amount REAL NOT NULL CHECK(fee_amount >= 0),
                    net_amount REAL NOT NULL CHECK(net_amount >= 0),
                    currency TEXT NOT NULL CHECK(
                        length(currency)=3 AND currency=upper(currency)
                    ),
                    received_at TEXT NOT NULL,
                    CHECK(abs(gross_amount-fee_amount-net_amount) < 0.000000001),
                    CHECK(
                        (revenue_type='ONE_TIME' AND recurring_contract_id IS NULL)
                        OR (revenue_type='RECURRING_RETAINER'
                            AND recurring_contract_id IS NOT NULL)
                    )
                );
                CREATE TABLE IF NOT EXISTS artifact_attributions (
                    attribution_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES money_artifacts(artifact_id),
                    target_kind TEXT NOT NULL CHECK(
                        target_kind IN ('visit','activation','purchase','subscription','editorial')
                    ),
                    target_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    UNIQUE(target_kind,target_id)
                );
                CREATE TABLE IF NOT EXISTS product_lineages (
                    click_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES money_artifacts(artifact_id),
                    product_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS product_funnel_events (
                    event_id TEXT PRIMARY KEY,
                    click_id TEXT NOT NULL REFERENCES product_lineages(click_id),
                    event_type TEXT NOT NULL CHECK(event_type IN ('visit','activation','purchase')),
                    target_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    attribution_id TEXT NOT NULL REFERENCES artifact_attributions(attribution_id),
                    money_event_id TEXT REFERENCES money_events(event_id),
                    UNIQUE(event_type,target_id)
                );
                """
            )

    def _require_artifact(self, connection: sqlite3.Connection, artifact_id: str) -> None:
        if connection.execute(
            "SELECT 1 FROM money_artifacts WHERE artifact_id=?", (artifact_id,)
        ).fetchone() is None:
            raise MoneyInvariant("artifact scope requires a registered artifact")

    def _scope(self, connection: sqlite3.Connection, scope: str, artifact_id: str | None) -> None:
        scope = _text(scope, "scope")
        if scope == "artifact":
            if not artifact_id:
                raise MoneyInvariant("artifact scope requires a registered artifact")
            self._require_artifact(connection, artifact_id)
        elif scope == "account":
            if artifact_id is not None:
                raise MoneyInvariant("account scope cannot carry artifact_id")
        else:
            raise MoneyInvariant("scope must be artifact or account")

    def _require_direct_revenue_surface(
        self, connection: sqlite3.Connection, *, artifact_id: str | None, stream: str,
    ) -> None:
        if artifact_id:
            row = connection.execute(
                "SELECT platform FROM money_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            contract = self.revenue_surfaces["destinations"].get(
                str(row["platform"]) if row else ""
            )
            label = f"destination {row['platform']!r}" if row else "unknown destination"
        else:
            contract = self.revenue_surfaces["account_streams"].get(stream)
            label = f"account stream {stream!r}"
        if not isinstance(contract, dict) or contract.get("revenue_capable") is not True:
            raise MoneyInvariant(f"{label} is not revenue_capable for direct writing money")

    def register_artifact(
        self, *, artifact_id: str, run_id: str, platform: str, lang: str,
        live_url: str, published_at: str, artifact_sha256: str,
    ) -> dict[str, Any]:
        artifact_id = _text(artifact_id, "artifact_id")
        if ARTIFACT_RE.fullmatch(artifact_id) is None:
            raise MoneyInvariant("artifact_id is malformed")
        run_id = _text(run_id, "run_id")
        platform = _text(platform, "platform")
        lang = _text(lang, "lang")
        expected = f"{run_id}__{platform}__{lang}"
        if artifact_id != expected:
            raise MoneyInvariant("artifact_id differs from run/platform/lang")
        live_url = _url(live_url, "live_url")
        published_at = _timestamp(published_at, "published_at")
        artifact_sha256 = _text(artifact_sha256, "artifact_sha256").lower()
        if SHA256_RE.fullmatch(artifact_sha256) is None:
            raise MoneyInvariant("artifact_sha256 must be SHA-256")
        with self._connect() as connection:
            inserted = connection.execute(
                "INSERT OR IGNORE INTO money_artifacts VALUES(?,?,?,?,?,?,?)",
                (artifact_id, run_id, platform, lang, live_url, published_at, artifact_sha256),
            ).rowcount == 1
            durable = connection.execute(
                "SELECT * FROM money_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if durable is None or any(
                durable[key] != value
                for key, value in {
                    "run_id": run_id, "platform": platform, "lang": lang,
                    "live_url": live_url, "published_at": published_at,
                    "artifact_sha256": artifact_sha256,
                }.items()
            ):
                raise MoneyInvariant("artifact_id already belongs to different immutable bytes")
        return {"artifact_id": artifact_id, "inserted": inserted}

    def record_metric(
        self, *, artifact_id: str | None, scope: str, metric: str,
        value: float | int | None, unit: str, status: str, observed_at: str,
        source_url: str, receipt_sha256: str, reason: str | None = None,
    ) -> dict[str, Any]:
        metric = _text(metric, "metric")
        unit = _text(unit, "unit")
        status = _text(status, "status").lower()
        if status not in {"verified", "unknown", "test"}:
            raise MoneyInvariant("metric status is invalid")
        if status == "unknown" and value is not None:
            raise MoneyInvariant("unknown measurement value must be null")
        if status != "unknown" and value is None:
            raise MoneyInvariant("measured metric requires a value")
        numeric = _amount(
            value, "value", nullable=True, allow_negative=metric == "net_received"
        )
        if status == "unknown":
            reason = _text(reason, "reason")
        observed_at = _timestamp(observed_at, "observed_at")
        source_url = _url(source_url, "source_url")
        receipt_sha256 = _text(receipt_sha256, "receipt_sha256").lower()
        if SHA256_RE.fullmatch(receipt_sha256) is None:
            raise MoneyInvariant("receipt_sha256 must be SHA-256")
        identity = [scope, artifact_id or "", metric, observed_at, receipt_sha256]
        observation_id = _id("met", *identity)
        with self._connect() as connection:
            self._scope(connection, scope, artifact_id)
            inserted = connection.execute(
                "INSERT OR IGNORE INTO metric_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    observation_id, artifact_id, scope, metric, numeric, unit, status,
                    reason, observed_at, source_url, receipt_sha256,
                ),
            ).rowcount == 1
        return {"observation_id": observation_id, "inserted": inserted}

    def record_money_event(
        self, *, artifact_id: str | None, scope: str, stream: str,
        revenue_class: str, kind: str, amount: float | int | None,
        currency: str | None, status: str, counterparty: str,
        external_receipt_id: str | None, source_url: str, test: bool,
        occurred_at: str,
    ) -> dict[str, Any]:
        stream = _text(stream, "stream")
        revenue_class = _text(revenue_class, "revenue_class")
        if revenue_class not in {"direct_writing", "product_derived", "network_fee"}:
            raise MoneyInvariant("revenue_class is invalid")
        kind = _text(kind, "kind")
        if kind not in {"sale", "editorial_fee", "subscription_charge", "refund"}:
            raise MoneyInvariant("money kind is invalid")
        status = _text(status, "status")
        if status not in {"verified_received", "pending", "unknown", "test", "refunded"}:
            raise MoneyInvariant("money status is invalid")
        if status == "refunded" and kind != "refund":
            raise MoneyInvariant("refunded status is only valid for a refund event")
        if not isinstance(test, bool):
            raise MoneyInvariant("test must be boolean")
        if status == "verified_received" and test:
            raise MoneyInvariant("test money cannot be verified received revenue")
        if status == "unknown":
            if amount is not None or currency is not None:
                raise MoneyInvariant("unknown money amount and currency must be null")
            numeric = None
            normalized_currency = None
        else:
            numeric = _amount(amount, "amount")
            if numeric == 0:
                raise MoneyInvariant("money amount must be positive")
            normalized_currency = _currency(currency)
        counterparty = _text(counterparty, "counterparty")
        receipt = None if external_receipt_id is None else _text(external_receipt_id, "external_receipt_id")
        if status in {"verified_received", "refunded"} and not receipt:
            raise MoneyInvariant("verified received money or refund requires external receipt")
        source_url = _url(source_url, "source_url")
        occurred_at = _timestamp(occurred_at, "occurred_at")
        event_id = _id("money", receipt or source_url, kind, occurred_at)
        immutable = {
            "artifact_id": artifact_id, "scope": scope, "stream": stream,
            "revenue_class": revenue_class, "kind": kind, "amount": numeric,
            "currency": normalized_currency, "status": status,
            "counterparty": counterparty, "source_url": source_url,
            "test": int(test), "occurred_at": occurred_at,
        }
        with self._connect() as connection:
            self._scope(connection, scope, artifact_id)
            if revenue_class == "direct_writing":
                self._require_direct_revenue_surface(
                    connection, artifact_id=artifact_id, stream=stream
                )
            existing = None
            if receipt:
                existing = connection.execute(
                    "SELECT * FROM money_events WHERE external_receipt_id=?", (receipt,)
                ).fetchone()
            if existing is not None:
                if any(existing[key] != value for key, value in immutable.items()):
                    raise MoneyInvariant("external receipt already belongs to a different revenue event")
                return {"event_id": str(existing["event_id"]), "inserted": False}
            inserted = connection.execute(
                "INSERT INTO money_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id, artifact_id, scope, stream, revenue_class, kind, numeric,
                    normalized_currency, status, counterparty, receipt, source_url,
                    int(test), occurred_at,
                ),
            ).rowcount == 1
        return {"event_id": event_id, "inserted": inserted}

    def record_commercial_payment(
        self, *, opportunity_db: Path | str, payment_evidence_id: str,
    ) -> dict[str, Any]:
        """Atomically bind one external publisher payment to its commercial chain."""
        opportunity_db = Path(opportunity_db).resolve()
        if opportunity_db == self.path.resolve() or not opportunity_db.is_file():
            raise MoneyInvariant("opportunity database is unavailable")
        payment_evidence_id = _text(payment_evidence_id, "payment_evidence_id")
        with self._connect() as connection:
            connection.execute("ATTACH DATABASE ? AS opportunity", (str(opportunity_db),))
            connection.execute("BEGIN")
            evidence = connection.execute(
                "SELECT opportunity_id,kind,url,observed_at,payload_json "
                "FROM opportunity.opportunity_evidence WHERE evidence_id=?",
                (payment_evidence_id,),
            ).fetchone()
            if evidence is None or evidence["kind"] != "payment":
                raise MoneyInvariant("commercial payment requires exact payment evidence")
            try:
                payload = json.loads(evidence["payload_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise MoneyInvariant("commercial payment evidence is unreadable") from error
            if not isinstance(payload, dict):
                raise MoneyInvariant("commercial payment evidence must be an object")

            required_text = (
                "contract_id", "assignment_id", "delivery_id", "artifact_sha256",
                "payment_trigger", "trigger_evidence_id", "currency",
                "payment_receipt_id", "fee_receipt_id", "payout_receipt_id",
                "counterparty", "counterparty_kind", "payment_status", "received_by",
                "revenue_type", "payment_source_url", "fee_source_url", "payout_source_url",
            )
            values = {key: _text(payload.get(key), key) for key in required_text}
            receipt_ids = {
                values["payment_receipt_id"], values["fee_receipt_id"],
                values["payout_receipt_id"],
            }
            if len(receipt_ids) != 3:
                raise MoneyInvariant(
                    "payment, fee, and payout require distinct external receipts"
                )
            trigger = values["payment_trigger"].upper()
            if trigger not in {"APPROVAL", "DELIVERY", "PUBLICATION"}:
                raise MoneyInvariant("commercial payment trigger is unsupported")
            revenue_type = values["revenue_type"].upper()
            if revenue_type not in {"ONE_TIME", "RECURRING_RETAINER"}:
                raise MoneyInvariant("commercial revenue_type is invalid")
            if payload.get("test") is not False:
                raise MoneyInvariant("commercial payment must be external non-test money")
            if payload.get("estimated") is not False:
                raise MoneyInvariant("estimated or unknown payment is not received revenue")
            if (
                values["counterparty_kind"].upper() != "EXTERNAL_PUBLISHER"
                or values["payment_status"].upper() != "SETTLED"
            ):
                raise MoneyInvariant(
                    "commercial revenue requires an external settled publisher receipt"
                )
            currency = _currency(values["currency"])
            gross = _amount(payload.get("gross_amount"), "gross_amount")
            fee = _amount(payload.get("fee_amount"), "fee_amount")
            net = _amount(payload.get("net_amount"), "net_amount")
            if gross == 0 or abs(gross - fee - net) > 1e-9:
                raise MoneyInvariant("commercial gross - fee must equal net")
            artifact_sha256 = values["artifact_sha256"].lower()
            if SHA256_RE.fullmatch(artifact_sha256) is None:
                raise MoneyInvariant("commercial artifact_sha256 must be SHA-256")
            payment_url = _url(values["payment_source_url"], "payment_source_url")
            fee_url = _url(values["fee_source_url"], "fee_source_url")
            payout_url = _url(values["payout_source_url"], "payout_source_url")
            if payment_url != evidence["url"]:
                raise MoneyInvariant("payment source URL differs from evidence")
            received_at = _timestamp(evidence["observed_at"], "received_at")

            chain = connection.execute(
                "SELECT o.publisher,c.payment_trigger,c.currency,c.rate_amount,c.status AS contract_status,"
                "a.status AS assignment_status,d.status AS delivery_status,d.artifact_sha256,"
                "d.delivery_evidence_id,p.publication_id,p.status AS publication_status,"
                "p.publication_evidence_id "
                "FROM opportunity.opportunity_contracts c "
                "JOIN opportunity.opportunities o ON o.opportunity_id=c.opportunity_id "
                "JOIN opportunity.opportunity_assignments a ON a.contract_id=c.contract_id "
                "AND a.opportunity_id=c.opportunity_id "
                "JOIN opportunity.opportunity_deliveries d ON d.assignment_id=a.assignment_id "
                "AND d.opportunity_id=c.opportunity_id "
                "LEFT JOIN opportunity.opportunity_publications p ON p.delivery_id=d.delivery_id "
                "AND p.opportunity_id=c.opportunity_id "
                "WHERE c.opportunity_id=? AND c.contract_id=? AND a.assignment_id=? "
                "AND d.delivery_id=? AND d.artifact_sha256=?",
                (
                    evidence["opportunity_id"], values["contract_id"],
                    values["assignment_id"], values["delivery_id"], artifact_sha256,
                ),
            ).fetchone()
            if chain is None:
                raise MoneyInvariant("payment does not bind the exact commercial artifact chain")
            if chain["contract_status"] != "TERMS_COMPLETE":
                raise MoneyInvariant("payment contract terms are incomplete")
            if str(chain["payment_trigger"]).upper() != trigger:
                raise MoneyInvariant("payment trigger differs from the contract")
            if chain["currency"] != currency:
                raise MoneyInvariant("payment currency differs from the contract")
            if abs(float(chain["rate_amount"]) - gross) > 1e-9:
                raise MoneyInvariant("payment gross differs from the contracted rate")
            if values["counterparty"] != chain["publisher"]:
                raise MoneyInvariant("payment counterparty differs from the publisher")

            publication_id = payload.get("publication_id")
            if publication_id is not None:
                publication_id = _text(publication_id, "publication_id")
            if trigger != "PUBLICATION" and publication_id is not None:
                raise MoneyInvariant(
                    "non-publication payment trigger cannot carry publication_id"
                )
            if trigger == "APPROVAL":
                if chain["delivery_status"] != "ACCEPTED":
                    raise MoneyInvariant("approval-trigger payment requires accepted delivery")
                trigger_row = connection.execute(
                    "SELECT evidence_id FROM opportunity.opportunity_commercial_transitions "
                    "WHERE entity_type='delivery' AND entity_id=? AND to_state='ACCEPTED' "
                    "ORDER BY observed_at DESC LIMIT 1",
                    (values["delivery_id"],),
                ).fetchone()
                expected_trigger_evidence = trigger_row["evidence_id"] if trigger_row else None
            elif trigger == "DELIVERY":
                if chain["assignment_status"] != "DELIVERED":
                    raise MoneyInvariant("delivery-trigger payment requires delivered assignment")
                expected_trigger_evidence = chain["delivery_evidence_id"]
            else:
                if (
                    not publication_id or chain["publication_id"] != publication_id
                    or chain["publication_status"] != "PUBLISHED"
                ):
                    raise MoneyInvariant("publication-trigger payment requires exact publication")
                expected_trigger_evidence = chain["publication_evidence_id"]
            if values["trigger_evidence_id"] != expected_trigger_evidence:
                raise MoneyInvariant("payment does not bind the exact trigger evidence")

            recurring_contract_id = payload.get("recurring_contract_id")
            if revenue_type == "ONE_TIME":
                if recurring_contract_id is not None:
                    raise MoneyInvariant("one-time payment cannot carry recurring contract")
                recurring_contract_id = None
            else:
                recurring_contract_id = _text(
                    recurring_contract_id, "recurring_contract_id"
                )
                recurring = connection.execute(
                    "SELECT stream,amount,currency FROM subscription_contracts "
                    "WHERE external_contract_id=? AND status='active' AND test=0",
                    (recurring_contract_id,),
                ).fetchone()
                if (
                    recurring is None or recurring["stream"] != "editorial_retainer"
                    or recurring["currency"] != currency
                    or abs(float(recurring["amount"]) - float(chain["rate_amount"])) > 1e-9
                ):
                    raise MoneyInvariant(
                        "retainer MRR requires matching active editorial retainer contract"
                    )

            event_id = _id(
                "money", values["payment_receipt_id"], "editorial_fee", received_at
            )
            fee_id = _id("fee", event_id, values["fee_receipt_id"])
            payout_id = _id("payout", values["payout_receipt_id"])
            payment_id = _id("commercial", payment_evidence_id)
            cross_receipts = (
                (values["payment_receipt_id"], "money_fees", "payouts"),
                (values["fee_receipt_id"], "money_events", "payouts"),
                (values["payout_receipt_id"], "money_events", "money_fees"),
            )
            for receipt_id, first_table, second_table in cross_receipts:
                if connection.execute(
                    f"SELECT 1 FROM {first_table} WHERE external_receipt_id=? "
                    f"UNION ALL SELECT 1 FROM {second_table} WHERE external_receipt_id=? LIMIT 1",
                    (receipt_id, receipt_id),
                ).fetchone() is not None:
                    raise MoneyInvariant("external receipt was already used by another money type")
            event_values = (
                event_id, None, "account", "editorial_fee", "direct_writing",
                "editorial_fee", gross, currency, "verified_received",
                values["counterparty"], values["payment_receipt_id"], payment_url,
                0, received_at,
            )
            existing_event = connection.execute(
                "SELECT * FROM money_events WHERE external_receipt_id=?",
                (values["payment_receipt_id"],),
            ).fetchone()
            if existing_event is None:
                connection.execute(
                    "INSERT INTO money_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    event_values,
                )
            elif tuple(existing_event) != event_values:
                raise MoneyInvariant("payment receipt already belongs to different money")

            fee_values = (
                fee_id, event_id, "processor", fee, currency, "verified",
                values["fee_receipt_id"], fee_url, received_at,
            )
            existing_fee = connection.execute(
                "SELECT * FROM money_fees WHERE external_receipt_id=?",
                (values["fee_receipt_id"],),
            ).fetchone()
            if existing_fee is None:
                connection.execute("INSERT INTO money_fees VALUES(?,?,?,?,?,?,?,?,?)", fee_values)
            elif tuple(existing_fee) != fee_values:
                raise MoneyInvariant("fee receipt already belongs to different money")

            payout_values = (
                payout_id, "editorial_fee", "paid", gross, fee, net, currency,
                values["payout_receipt_id"], payout_url, 0, received_at,
            )
            existing_payout = connection.execute(
                "SELECT * FROM payouts WHERE external_receipt_id=?",
                (values["payout_receipt_id"],),
            ).fetchone()
            if existing_payout is None:
                connection.execute("INSERT INTO payouts VALUES(?,?,?,?,?,?,?,?,?,?,?)", payout_values)
            elif tuple(existing_payout) != payout_values:
                raise MoneyInvariant("payout receipt already belongs to different money")

            allocation = connection.execute(
                "SELECT amount,currency FROM payout_allocations WHERE payout_id=? AND event_id=?",
                (payout_id, event_id),
            ).fetchone()
            if allocation is None:
                payout_allocated = connection.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM payout_allocations WHERE payout_id=?",
                    (payout_id,),
                ).fetchone()[0]
                event_allocated = connection.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM payout_allocations WHERE event_id=?",
                    (event_id,),
                ).fetchone()[0]
                if payout_allocated + gross > gross + 1e-9:
                    raise MoneyInvariant("commercial payout is already allocated")
                if event_allocated + gross > gross + 1e-9:
                    raise MoneyInvariant("commercial revenue event is already allocated")
                connection.execute(
                    "INSERT INTO payout_allocations VALUES(?,?,?,?)",
                    (payout_id, event_id, gross, currency),
                )
            elif tuple(allocation) != (gross, currency):
                raise MoneyInvariant("commercial payout allocation conflicts")

            binding_values = (
                payment_id, event_id, payout_id, evidence["opportunity_id"],
                values["contract_id"], values["assignment_id"], values["delivery_id"],
                publication_id, artifact_sha256, trigger, values["trigger_evidence_id"],
                payment_evidence_id, revenue_type, recurring_contract_id,
                gross, fee, net, currency, received_at,
            )
            existing_binding = connection.execute(
                "SELECT * FROM commercial_payment_bindings WHERE payment_evidence_id=?",
                (payment_evidence_id,),
            ).fetchone()
            inserted = existing_binding is None
            if inserted:
                connection.execute(
                    "INSERT INTO commercial_payment_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    binding_values,
                )
            elif tuple(existing_binding) != binding_values:
                raise MoneyInvariant("commercial payment evidence already has different binding")
        return {
            "payment_id": payment_id, "event_id": event_id, "payout_id": payout_id,
            "inserted": inserted,
        }

    def record_fee(
        self, *, event_id: str, fee_kind: str, amount: float | int | None,
        currency: str | None, status: str, external_receipt_id: str,
        source_url: str, observed_at: str,
    ) -> dict[str, Any]:
        event_id = _text(event_id, "event_id")
        fee_kind = _text(fee_kind, "fee_kind")
        status = _text(status, "status")
        if status not in {"verified", "unknown", "test"}:
            raise MoneyInvariant("fee status is invalid")
        if status == "unknown":
            if amount is not None or currency is not None:
                raise MoneyInvariant("unknown fee amount and currency must be null")
            numeric = None
            normalized_currency = None
        else:
            numeric = _amount(amount, "amount")
            normalized_currency = _currency(currency)
        receipt = _text(external_receipt_id, "external_receipt_id")
        source_url = _url(source_url, "source_url")
        observed_at = _timestamp(observed_at, "observed_at")
        fee_id = _id("fee", event_id, receipt)
        immutable = {
            "event_id": event_id, "fee_kind": fee_kind, "amount": numeric,
            "currency": normalized_currency, "status": status,
            "source_url": source_url, "observed_at": observed_at,
        }
        with self._connect() as connection:
            event = connection.execute(
                "SELECT currency FROM money_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if event is None:
                raise MoneyInvariant("fee requires a durable money event")
            if normalized_currency and event["currency"] != normalized_currency:
                raise MoneyInvariant("fee currency differs from money event")
            existing = connection.execute(
                "SELECT * FROM money_fees WHERE external_receipt_id=?", (receipt,)
            ).fetchone()
            if existing is not None:
                if any(existing[key] != value for key, value in immutable.items()):
                    raise MoneyInvariant("fee receipt already belongs to different immutable values")
                return {"fee_id": str(existing["fee_id"]), "inserted": False}
            inserted = connection.execute(
                "INSERT INTO money_fees VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    fee_id, event_id, fee_kind, numeric, normalized_currency, status,
                    receipt, source_url, observed_at,
                ),
            ).rowcount == 1
        return {"fee_id": fee_id, "inserted": inserted}

    def record_payout(
        self, *, stream: str, status: str, gross_amount: float | int | None,
        fee_amount: float | int | None, net_amount: float | int | None,
        currency: str | None, external_receipt_id: str, source_url: str,
        test: bool, occurred_at: str,
    ) -> dict[str, Any]:
        stream = _text(stream, "stream")
        status = _text(status, "status")
        if status not in {"paid", "pending", "failed", "unknown", "test"}:
            raise MoneyInvariant("payout status is invalid")
        if not isinstance(test, bool):
            raise MoneyInvariant("test must be boolean")
        if status == "paid" and test:
            raise MoneyInvariant("test payout cannot be paid")
        if status == "unknown":
            if any(value is not None for value in (gross_amount, fee_amount, net_amount, currency)):
                raise MoneyInvariant("unknown payout amounts must be null")
            gross = fee = net = None
            normalized_currency = None
        else:
            gross = _amount(gross_amount, "gross_amount")
            fee = _amount(fee_amount, "fee_amount")
            net = _amount(net_amount, "net_amount")
            normalized_currency = _currency(currency)
            if abs(gross - fee - net) > 1e-9:
                raise MoneyInvariant("payout gross - fee must equal net")
        receipt = _text(external_receipt_id, "external_receipt_id")
        source_url = _url(source_url, "source_url")
        occurred_at = _timestamp(occurred_at, "occurred_at")
        payout_id = _id("payout", receipt)
        immutable = {
            "stream": stream, "status": status, "gross_amount": gross,
            "fee_amount": fee, "net_amount": net, "currency": normalized_currency,
            "source_url": source_url, "test": int(test), "occurred_at": occurred_at,
        }
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM payouts WHERE external_receipt_id=?", (receipt,)
            ).fetchone()
            if existing is not None:
                if any(existing[key] != value for key, value in immutable.items()):
                    raise MoneyInvariant("payout receipt already belongs to different immutable values")
                return {"payout_id": str(existing["payout_id"]), "inserted": False}
            inserted = connection.execute(
                "INSERT INTO payouts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    payout_id, stream, status, gross, fee, net, normalized_currency,
                    receipt, source_url, int(test), occurred_at,
                ),
            ).rowcount == 1
        return {"payout_id": payout_id, "inserted": inserted}

    def allocate_payout(
        self, *, payout_id: str, event_id: str, amount: float | int, currency: str,
    ) -> dict[str, Any]:
        payout_id = _text(payout_id, "payout_id")
        event_id = _text(event_id, "event_id")
        numeric = _amount(amount, "amount")
        normalized_currency = _currency(currency)
        with self._connect() as connection:
            payout = connection.execute(
                "SELECT gross_amount,currency FROM payouts WHERE payout_id=?", (payout_id,)
            ).fetchone()
            event = connection.execute(
                "SELECT amount,currency FROM money_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if payout is None or event is None:
                raise MoneyInvariant("allocation requires durable payout and money event")
            if payout["currency"] != normalized_currency or event["currency"] != normalized_currency:
                raise MoneyInvariant("allocation currency differs")
            existing = connection.execute(
                "SELECT amount,currency FROM payout_allocations WHERE payout_id=? AND event_id=?",
                (payout_id, event_id),
            ).fetchone()
            if existing is not None:
                if existing["amount"] != numeric or existing["currency"] != normalized_currency:
                    raise MoneyInvariant("existing payout allocation has different immutable values")
                return {"payout_id": payout_id, "event_id": event_id, "inserted": False}
            allocated = connection.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payout_allocations WHERE payout_id=?",
                (payout_id,),
            ).fetchone()[0]
            if allocated + numeric > payout["gross_amount"] + 1e-9:
                raise MoneyInvariant("payout allocation exceeds gross amount")
            event_allocated = connection.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payout_allocations WHERE event_id=?",
                (event_id,),
            ).fetchone()[0]
            if event_allocated + numeric > event["amount"] + 1e-9:
                raise MoneyInvariant("revenue event is already allocated up to its received amount")
            inserted = connection.execute(
                "INSERT INTO payout_allocations VALUES(?,?,?,?)",
                (payout_id, event_id, numeric, normalized_currency),
            ).rowcount == 1
        return {"payout_id": payout_id, "event_id": event_id, "inserted": inserted}

    def record_subscription(
        self, *, acquisition_artifact_id: str | None, stream: str,
        amount: float | int | None, currency: str | None, interval: str,
        status: str, external_contract_id: str, source_url: str, test: bool,
        started_at: str, observed_at: str, ended_at: str | None = None,
    ) -> dict[str, Any]:
        stream = _text(stream, "stream")
        interval = _text(interval, "interval")
        if interval not in {"month", "year", "unknown"}:
            raise MoneyInvariant("subscription interval is invalid")
        status = _text(status, "status")
        if status not in {"active", "canceled", "past_due", "trial", "unknown", "test"}:
            raise MoneyInvariant("subscription status is invalid")
        if not isinstance(test, bool):
            raise MoneyInvariant("test must be boolean")
        if status == "active" and test:
            raise MoneyInvariant("test subscription cannot be active revenue")
        if status == "unknown":
            if amount is not None or currency is not None:
                raise MoneyInvariant("unknown subscription amount must be null")
            numeric = None
            normalized_currency = None
        else:
            numeric = _amount(amount, "amount")
            normalized_currency = _currency(currency)
        contract = _text(external_contract_id, "external_contract_id")
        source_url = _url(source_url, "source_url")
        started_at = _timestamp(started_at, "started_at")
        observed_at = _timestamp(observed_at, "observed_at")
        ended_at = _timestamp(ended_at, "ended_at") if ended_at else None
        subscription_id = _id("sub", contract)
        with self._connect() as connection:
            if acquisition_artifact_id:
                self._require_artifact(connection, acquisition_artifact_id)
            existing = connection.execute(
                "SELECT * FROM subscription_contracts WHERE external_contract_id=?", (contract,)
            ).fetchone()
            values = (
                subscription_id, acquisition_artifact_id, stream, numeric,
                normalized_currency, interval, status, contract, source_url, int(test),
                started_at, ended_at, observed_at,
            )
            if existing is None:
                connection.execute(
                    "INSERT INTO subscription_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
                inserted = True
            else:
                if existing["subscription_id"] != subscription_id:
                    raise MoneyInvariant("external contract already belongs elsewhere")
                connection.execute(
                    "UPDATE subscription_contracts SET acquisition_artifact_id=?,stream=?,"
                    "amount=?,currency=?,interval_name=?,status=?,source_url=?,test=?,"
                    "started_at=?,ended_at=?,observed_at=? WHERE subscription_id=?",
                    (
                        acquisition_artifact_id, stream, numeric, normalized_currency,
                        interval, status, source_url, int(test), started_at, ended_at,
                        observed_at, subscription_id,
                    ),
                )
                inserted = False
        return {"subscription_id": subscription_id, "inserted": inserted}

    def record_attribution(
        self, *, artifact_id: str, target_kind: str, target_id: str,
        observed_at: str, receipt_sha256: str,
    ) -> dict[str, Any]:
        artifact_id = _text(artifact_id, "artifact_id")
        target_kind = _text(target_kind, "target_kind")
        if target_kind not in {"visit", "activation", "purchase", "subscription", "editorial"}:
            raise MoneyInvariant("target_kind is invalid")
        target_id = _text(target_id, "target_id")
        observed_at = _timestamp(observed_at, "observed_at")
        receipt_sha256 = _text(receipt_sha256, "receipt_sha256").lower()
        if SHA256_RE.fullmatch(receipt_sha256) is None:
            raise MoneyInvariant("receipt_sha256 must be SHA-256")
        attribution_id = _id("attr", artifact_id, target_kind, target_id)
        with self._connect() as connection:
            self._require_artifact(connection, artifact_id)
            existing = connection.execute(
                "SELECT * FROM artifact_attributions WHERE target_kind=? AND target_id=?",
                (target_kind, target_id),
            ).fetchone()
            if existing is not None:
                if existing["artifact_id"] != artifact_id:
                    raise MoneyInvariant("target already has one attribution lineage")
                return {"attribution_id": str(existing["attribution_id"]), "inserted": False}
            connection.execute(
                "INSERT INTO artifact_attributions VALUES(?,?,?,?,?,?)",
                (
                    attribution_id, artifact_id, target_kind, target_id,
                    observed_at, receipt_sha256,
                ),
            )
        return {"attribution_id": attribution_id, "inserted": True}

    def record_product_event(
        self, *, event_id: str, event_type: str, product_id: str, run_id: str,
        artifact_id: str, variant_id: str, click_id: str, target_id: str,
        occurred_at: str, source_url: str, receipt_sha256: str,
        amount: float | int | None, currency: str | None,
        external_receipt_id: str | None, counterparty: str | None, test: bool,
    ) -> dict[str, Any]:
        """Persist one exact visit -> activation -> purchase lineage atomically.

        A proxy event never becomes money.  Only a positive, external, non-test
        purchase receipt creates a ``product_derived`` money event.
        """
        event_id = _text(event_id, "event_id")
        event_type = _text(event_type, "event_type")
        if event_type not in {"visit", "activation", "purchase"}:
            raise MoneyInvariant("product event_type is invalid")
        product_id = _text(product_id, "product_id")
        run_id = _text(run_id, "run_id")
        artifact_id = _text(artifact_id, "artifact_id")
        variant_id = _text(variant_id, "variant_id")
        click_id = _text(click_id, "click_id")
        target_id = _text(target_id, "target_id")
        occurred_at = _timestamp(occurred_at, "occurred_at")
        source_url = _url(source_url, "source_url")
        receipt_sha256 = _text(receipt_sha256, "receipt_sha256").lower()
        if SHA256_RE.fullmatch(receipt_sha256) is None:
            raise MoneyInvariant("receipt_sha256 must be SHA-256")
        if not isinstance(test, bool):
            raise MoneyInvariant("test must be boolean")

        normalized_target = click_id if event_type == "visit" else target_id
        numeric: float | None = None
        normalized_currency: str | None = None
        receipt: str | None = None
        normalized_counterparty: str | None = None
        if event_type == "purchase":
            numeric = _amount(amount, "amount")
            if numeric == 0:
                raise MoneyInvariant("purchase amount must be positive")
            normalized_currency = _currency(currency)
            receipt = _text(external_receipt_id, "external_receipt_id")
            normalized_counterparty = _text(counterparty, "counterparty")
            if test:
                raise MoneyInvariant("test purchase cannot create verified product revenue")
            normalized_target = receipt
        elif any(value is not None for value in (amount, currency, external_receipt_id, counterparty)):
            raise MoneyInvariant("visit and activation cannot carry money fields")
        elif test:
            raise MoneyInvariant("test funnel events require a separate test ledger")

        normalized = {
            "event_id": event_id, "event_type": event_type,
            "product_id": product_id, "run_id": run_id,
            "artifact_id": artifact_id, "variant_id": variant_id,
            "click_id": click_id, "target_id": normalized_target,
            "occurred_at": occurred_at, "source_url": source_url,
            "receipt_sha256": receipt_sha256, "amount": numeric,
            "currency": normalized_currency, "external_receipt_id": receipt,
            "counterparty": normalized_counterparty, "test": test,
        }
        payload_sha256 = hashlib.sha256(
            json.dumps(
                normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        target_kind = event_type
        attribution_id = _id("attr", artifact_id, target_kind, normalized_target)
        money_event_id = (
            _id("money", receipt, "sale", occurred_at) if receipt else None
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            artifact = connection.execute(
                "SELECT run_id FROM money_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if artifact is None:
                raise MoneyInvariant("product event requires a registered artifact")
            if artifact["run_id"] != run_id:
                raise MoneyInvariant("product event run_id differs from artifact")
            existing_event = connection.execute(
                "SELECT * FROM product_funnel_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing_event is not None:
                if existing_event["payload_sha256"] != payload_sha256:
                    raise MoneyInvariant("event_id already belongs to different immutable evidence")
                return {
                    "event_id": event_id,
                    "attribution_id": str(existing_event["attribution_id"]),
                    "money_event_id": existing_event["money_event_id"],
                    "inserted": False,
                }

            lineage = connection.execute(
                "SELECT * FROM product_lineages WHERE click_id=?", (click_id,)
            ).fetchone()
            lineage_values = {
                "artifact_id": artifact_id, "product_id": product_id,
                "run_id": run_id, "variant_id": variant_id,
            }
            if lineage is None:
                if event_type != "visit":
                    raise MoneyInvariant("visit must establish the product attribution lineage")
                connection.execute(
                    "INSERT INTO product_lineages VALUES(?,?,?,?,?,?,?)",
                    (
                        click_id, artifact_id, product_id, run_id, variant_id,
                        occurred_at, receipt_sha256,
                    ),
                )
            elif any(lineage[key] != value for key, value in lineage_values.items()):
                raise MoneyInvariant("click_id already belongs to a different publication lineage")

            prior_rows = list(connection.execute(
                "SELECT event_type,occurred_at FROM product_funnel_events WHERE click_id=?",
                (click_id,),
            ))
            prior = {str(row["event_type"]): str(row["occurred_at"]) for row in prior_rows}
            required_prior = {"activation": "visit", "purchase": "activation"}.get(event_type)
            if required_prior and required_prior not in prior:
                raise MoneyInvariant(f"{required_prior} must precede {event_type}")
            if required_prior and prior[required_prior] > occurred_at:
                raise MoneyInvariant(f"{required_prior} occurred after {event_type}")

            existing_target = connection.execute(
                "SELECT artifact_id FROM artifact_attributions WHERE target_kind=? AND target_id=?",
                (target_kind, normalized_target),
            ).fetchone()
            if existing_target is not None:
                if existing_target["artifact_id"] != artifact_id:
                    raise MoneyInvariant("target already has one attribution lineage")
                raise MoneyInvariant("target was already recorded under another event_id")
            connection.execute(
                "INSERT INTO artifact_attributions VALUES(?,?,?,?,?,?)",
                (
                    attribution_id, artifact_id, target_kind, normalized_target,
                    occurred_at, receipt_sha256,
                ),
            )

            if event_type == "purchase":
                existing_money = connection.execute(
                    "SELECT * FROM money_events WHERE external_receipt_id=?", (receipt,)
                ).fetchone()
                if existing_money is not None:
                    raise MoneyInvariant("external receipt already belongs to a revenue event")
                connection.execute(
                    "INSERT INTO money_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        money_event_id, artifact_id, "artifact", product_id,
                        "product_derived", "sale", numeric, normalized_currency,
                        "verified_received", normalized_counterparty, receipt,
                        source_url, 0, occurred_at,
                    ),
                )
            connection.execute(
                "INSERT INTO product_funnel_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id, click_id, event_type, normalized_target, occurred_at,
                    source_url, receipt_sha256, payload_sha256, attribution_id,
                    money_event_id,
                ),
            )
        return {
            "event_id": event_id,
            "attribution_id": attribution_id,
            "money_event_id": money_event_id,
            "inserted": True,
        }

    @staticmethod
    def _add(totals: dict[str, float], currency: str, amount: float) -> None:
        totals[currency] = totals.get(currency, 0.0) + float(amount)

    @classmethod
    def _add_nested(
        cls, totals: dict[str, dict[str, float]], group: str, currency: str, amount: float,
    ) -> None:
        cls._add(totals.setdefault(group, {}), currency, amount)

    def summary(self, *, start: str, end: str) -> dict[str, Any]:
        start = _timestamp(start, "start")
        end = _timestamp(end, "end")
        gross: dict[str, float] = {}
        refunds: dict[str, float] = {}
        fees: dict[str, float] = {}
        paid_out: dict[str, float] = {}
        mrr: dict[str, float] = {}
        gross_by_class: dict[str, dict[str, float]] = {}
        gross_by_stream: dict[str, dict[str, float]] = {}
        refund_by_class: dict[str, dict[str, float]] = {}
        refund_by_stream: dict[str, dict[str, float]] = {}
        verified_revenue_event_count = 0
        with self._connect() as connection:
            for row in connection.execute(
                "SELECT kind,amount,currency,revenue_class,stream FROM money_events WHERE "
                "((status='verified_received' AND kind!='refund') OR "
                "(status='refunded' AND kind='refund')) AND test=0 "
                "AND datetime(occurred_at)>=datetime(?) AND datetime(occurred_at)<datetime(?)",
                (start, end),
            ):
                verified_revenue_event_count += 1
                target = refunds if row["kind"] == "refund" else gross
                self._add(target, row["currency"], row["amount"])
                if row["kind"] == "refund":
                    self._add_nested(
                        refund_by_class, row["revenue_class"], row["currency"], row["amount"]
                    )
                    self._add_nested(
                        refund_by_stream, row["stream"], row["currency"], row["amount"]
                    )
                else:
                    self._add_nested(
                        gross_by_class, row["revenue_class"], row["currency"], row["amount"]
                    )
                    self._add_nested(
                        gross_by_stream, row["stream"], row["currency"], row["amount"]
                    )
            for row in connection.execute(
                "SELECT f.amount,f.currency FROM money_fees f JOIN money_events e "
                "ON e.event_id=f.event_id WHERE f.status='verified' AND e.test=0 "
                "AND datetime(f.observed_at)>=datetime(?) AND datetime(f.observed_at)<datetime(?)",
                (start, end),
            ):
                self._add(fees, row["currency"], row["amount"])
            for row in connection.execute(
                "SELECT net_amount,currency FROM payouts WHERE status='paid' AND test=0 "
                "AND datetime(occurred_at)>=datetime(?) AND datetime(occurred_at)<datetime(?)",
                (start, end),
            ):
                self._add(paid_out, row["currency"], row["net_amount"])
            for row in connection.execute(
                "SELECT amount,currency,interval_name FROM subscription_contracts "
                "WHERE status='active' AND test=0"
            ):
                monthly = row["amount"] if row["interval_name"] == "month" else row["amount"] / 12
                self._add(mrr, row["currency"], monthly)
        currencies = set(gross) | set(refunds) | set(fees)
        net = {
            unit: gross.get(unit, 0.0) - refunds.get(unit, 0.0) - fees.get(unit, 0.0)
            for unit in sorted(currencies)
        }
        return {
            "window": {"start": start, "end": end},
            "verified_gross_by_currency": gross,
            "verified_gross_by_revenue_class": gross_by_class,
            "verified_gross_by_stream": gross_by_stream,
            "verified_refunds_by_currency": refunds,
            "verified_refunds_by_revenue_class": refund_by_class,
            "verified_refunds_by_stream": refund_by_stream,
            "verified_fees_by_currency": fees,
            "verified_net_by_currency": net,
            "paid_out_by_currency": paid_out,
            "verified_mrr_by_currency": mrr,
            "verified_revenue_event_count": verified_revenue_event_count,
            "note": "Currencies remain separate; payouts are cash movement and are not added to revenue.",
        }
