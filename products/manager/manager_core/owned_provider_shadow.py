"""Explicit opt-in P0 shadow comparison for verified public catalog corrections.

This caller reuses the existing catalog planner, static handoff validation,
baselines, and checkpointed provider. Its records never grant publisher authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
import re
import sqlite3
import time
from typing import Any, Callable

from .ampersand_api import DEFAULT_INSTRUCTIONS, MODEL, SessionFailure, initial_request_body_hash
from .authority import OwnedDigitalScope
from .candidate_verification import TechnicalAssessment, TechnicalCriteria
from .collaboration import (advisory_receipt, render_prompt, parse_advice, AdvisoryResult,
                            _strict_pairs, _no_nonfinite_constant, MAX_FACTS)
from .digital_handoff import OwnedChangeContext, prepare_owned_change
from .owned_checkpoint import CheckpointUnavailable, PrivateCheckpoint
from .owned_provider import (CheckpointedProvider, validate_provider_tables,
                             _SHA, _SESSION, _PROVIDER_TABLES)
from .provider_budget import BudgetExceeded, _money, Usage
from .digital_environment import PUBLISH_PREFIX, PAGES, _url
from .provider_sessions import SessionConflict
from . import collaboration_baselines
from . import owned_catalog_planner

_SCHEMA = "manager.catalog-shadow.v1"
_ALLOWED_ACTIONS = frozenset({"CORRECT_LINK", "IMPROVE_ACCESSIBILITY"})
_REASONS = frozenset({
    "DISABLED", "DEADLINE_EXPIRED", "PLANNER_UNCERTAIN", "NO_CANDIDATE",
    "UNSUPPORTED_CONTEXT", "UNSUPPORTED_ACTION", "CONTEXT_REVALIDATION_FAILED",
    "PRIOR_INTENT_RECONCILIATION_REQUIRED", "BUDGET_EXCEEDED",
    "PROVIDER_TRANSPORT_UNKNOWN", "MODEL_RESPONSE_PARSED", "INPUT_BINDING_MISMATCH",
    "PROVIDER_NOT_CONFIGURED",
})


def _record(status, reason, run_id, **fields):
    return {
        **fields,
        "schema": _SCHEMA,
        "status": status,
        "reason": reason,
        "run_id": run_id,
        "proof_level": "P0",
        "authorized_execution": False,
        "causal_support": False,
        "human_outcome": "NOT_MEASURED",
        "action_writes": 0,
        "settled_cost_usd": None,
    }


def _canonical_operation(context, assessment):
    criteria = context.criteria
    sources = sorted((source.source_id, source.url, source.content_sha256.lower())
                     for source in criteria.official_sources)
    payload = {
        "protocol": _SCHEMA,
        "model": MODEL,
        "instructions": DEFAULT_INSTRUCTIONS,
        "baseline_digest": assessment.baseline_digest,
        "candidate_digest": assessment.candidate_digest,
        "criteria_version": criteria.version,
        "action": criteria.candidate.action,
        "target": criteria.candidate.target,
        "sources": [list(row) for row in sources],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return "catalog_shadow_" + sha256(canonical.encode("utf-8")).hexdigest()


def _source_records(context):
    return [{"source_id": source.source_id, "url": source.url,
             "content_sha256": source.content_sha256.lower()}
            for source in sorted(context.criteria.official_sources,
                                 key=lambda item: (item.source_id, item.url, item.content_sha256))]


def _base_fields(context, assessment, prompt, operation_id):
    return {
        "operation_id": operation_id,
        "context_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
        "baseline_digest": assessment.baseline_digest,
        "candidate_digest": assessment.candidate_digest,
        "candidate": {"action": context.criteria.candidate.action,
                      "target": context.criteria.candidate.target},
        "sources": _source_records(context),
    }


def run_catalog_shadow(checkpoint, client, checkout, workspace, source_commit, *,
                       run_id: str, enabled: bool = False, cap_usd: Decimal,
                       upper_usd: Decimal, deadline_monotonic: float) -> dict:
    """Run one opt-in comparison for a source- and browser-verified legacy fix.

    `checkpoint` must be the caller's already acquired exact PrivateCheckpoint.
    No identity, lease, provider client, planner history clock, or publisher
    packet is created by this function.
    """
    if type(enabled) is not bool:
        raise ValueError("exact boolean opt-in required")
    if not enabled:
        return _record("SKIPPED", "DISABLED", run_id)
    if (type(run_id) is not str or not run_id.isdecimal() or run_id.startswith("0")
            or type(cap_usd) is not Decimal or not cap_usd.is_finite()
            or type(upper_usd) is not Decimal or not upper_usd.is_finite()
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)):
        raise ValueError("bounded run, finite Decimal limits, and absolute deadline required")
    if (type(checkpoint) is not PrivateCheckpoint or checkpoint.db is None
            or checkpoint.revision is None or checkpoint.broken):
        raise CheckpointUnavailable("active acquired private checkpoint required")
    if time.monotonic() >= deadline_monotonic:
        return _record("SKIPPED", "DEADLINE_EXPIRED", run_id)

    planning_now = datetime.now(timezone.utc)
    try:
        planned = owned_catalog_planner.plan_catalog_change(
            checkout, workspace, source_commit, planning_now, run_id=run_id)
    except CheckpointUnavailable:
        raise
    except Exception:
        return _record("UNKNOWN", "PLANNER_UNCERTAIN", run_id)
    after_planning = datetime.now(timezone.utc)
    return compare_prepared_catalog_shadow(checkpoint, planned, now=after_planning,
        run_id=run_id, enabled=enabled, client_factory=lambda: client,
        cap_usd=cap_usd, upper_usd=upper_usd, deadline_monotonic=deadline_monotonic)



_RESULT_TABLE = "catalog_shadow_results"
_RESULT_KEYS = frozenset({
    "schema", "status", "reason", "run_id", "compared_at", "proof_level",
    "authorized_execution", "causal_support", "human_outcome", "action_writes",
    "settled_cost_usd", "operation_id", "context_sha256", "baseline_digest",
    "candidate_digest", "candidate", "sources", "baseline", "provider",
    "model_comparison", "model_status",
})
_BINDING_KEYS = frozenset({"operation_id", "context_sha256", "baseline_digest",
                           "candidate_digest", "candidate", "sources"})
_MAX_RESULT_BYTES = 32768


def _result_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _validated_result(text):
    """Validate only the bounded private comparison receipt, never raw output."""
    if type(text) is not str or len(text.encode("utf-8")) > _MAX_RESULT_BYTES:
        raise ValueError("unbounded saved comparison")
    result = json.loads(text, object_pairs_hook=_strict_pairs,
                        parse_constant=_no_nonfinite_constant)
    if type(result) is not dict:
        raise ValueError("invalid saved comparison")
    model_status = result.get("model_status")
    keys = _RESULT_KEYS | ({"model_advice"} if model_status == "MODEL_ADVICE_P0" else set())
    if (set(result) != keys or result.get("status") != "COMPARED_P0"
            or result.get("reason") != "MODEL_RESPONSE_PARSED"
            or model_status not in ("MODEL_ADVICE_P0", "INVALID_MODEL_OUTPUT")
            or type(result.get("compared_at")) is not str):
        raise ValueError("invalid saved comparison fields")
    # Reuse the public boundary's exact fixed flags, run identity and UTC time.
    public_catalog_shadow_summary(result)
    for key in ("context_sha256", "baseline_digest", "candidate_digest"):
        if type(result[key]) is not str or not _SHA.fullmatch(result[key]):
            raise ValueError("invalid saved comparison digest")
    if (type(result["operation_id"]) is not str or
            not re.fullmatch(r"catalog_shadow_[0-9a-f]{64}", result["operation_id"])):
        raise ValueError("invalid saved comparison identity")
    candidate = result["candidate"]
    if (type(candidate) is not dict or set(candidate) != {"action", "target"}
            or type(candidate["action"]) is not str or candidate["action"] not in _ALLOWED_ACTIONS
            or type(candidate["target"]) is not str
            or candidate["target"] not in {PUBLISH_PREFIX + page for page in PAGES}):
        raise ValueError("invalid saved comparison candidate")
    sources = result["sources"]
    if type(sources) is not list or not 1 <= len(sources) <= MAX_FACTS:
        raise ValueError("invalid saved comparison sources")
    ids = set()
    for source in sources:
        if (type(source) is not dict or set(source) != {"source_id", "url", "content_sha256"}
                or type(source["source_id"]) is not str or not source["source_id"].strip()
                or source["source_id"] in ids or source["source_id"].startswith("synthetic:")
                or type(source["content_sha256"]) is not str
                or not _SHA.fullmatch(source["content_sha256"])):
            raise ValueError("invalid saved comparison source")
        _url(source["url"])
        ids.add(source["source_id"])

    def receipt(value):
        if type(value) is not dict:
            raise ValueError("invalid saved advice receipt")
        parsed = parse_advice(_result_json({key: value.get(key)
                              for key in ("decision", "reason", "source_ids")}), frozenset(ids))
        if type(parsed) is not AdvisoryResult or value != advisory_receipt(parsed):
            raise ValueError("invalid saved advice receipt")
        # Equality alone accepts 0 as False; require the exact non-authorizing flags.
        if value.get("causal_support") is not False or value.get("authorized_execution") is not False:
            raise ValueError("invalid saved advice flags")

    baseline = result["baseline"]
    if type(baseline) is not dict or set(baseline) != {"no_action", "rules"}:
        raise ValueError("invalid saved comparison baselines")
    for value in baseline.values():
        receipt(value)
    if model_status == "MODEL_ADVICE_P0":
        receipt(result["model_advice"])
        comparison = result["model_comparison"]
        expected = {key + "_same_decision": result["model_advice"]["decision"] == value["decision"]
                    for key, value in baseline.items()}
        if (type(comparison) is not dict or comparison != expected
                or any(type(value) is not bool for value in comparison.values())):
            raise ValueError("inconsistent saved decisions")
    elif result["model_comparison"] is not None:
        raise ValueError("invalid model output cannot have comparison decisions")
    provider = result["provider"]
    if (type(provider) is not dict or set(provider) != {
            "session_id", "turn_id", "status", "input_tokens", "output_tokens"}
            or provider["status"] != "completed"
            or type(provider["session_id"]) is not str or not _SESSION.fullmatch(provider["session_id"])
            or type(provider["turn_id"]) is not str
            or not re.fullmatch(r"turn_[A-Za-z0-9_-]{4,128}", provider["turn_id"])):
        raise ValueError("invalid saved comparison provider")
    Usage(provider["input_tokens"], provider["output_tokens"])
    return result


def validate_catalog_shadow_results(db: sqlite3.Connection, tables: set[str]) -> None:
    """Validate the optional result group without DDL, clients or constructors."""
    objects = db.execute("SELECT type,name FROM sqlite_master WHERE name=? COLLATE NOCASE",
                         (_RESULT_TABLE,)).fetchall()
    if objects and objects != [("table", _RESULT_TABLE)]:
        raise ValueError("reserved saved comparison name is not its exact table")
    if _RESULT_TABLE not in tables:
        return
    if not _PROVIDER_TABLES <= tables:
        raise ValueError("saved comparisons require complete provider state")
    validate_provider_tables(db, tables)
    columns = db.execute("PRAGMA table_xinfo(catalog_shadow_results)").fetchall()
    if ([(row[1], row[2].upper(), row[3], row[4], row[5], row[6]) for row in columns] != [
            ("operation_id", "TEXT", 1, None, 1, 0),
            ("body_hash", "TEXT", 1, None, 0, 0),
            ("result_json", "TEXT", 1, None, 0, 0)]):
        raise ValueError("invalid saved comparison schema")
    references = db.execute("PRAGMA foreign_key_list(catalog_shadow_results)").fetchall()
    if (len(references) != 1 or references[0][1:] !=
            (0, "amp_sessions", "operation_id", "request_id", "NO ACTION", "NO ACTION", "NONE")):
        raise ValueError("invalid saved comparison reference schema")
    if db.execute("SELECT operation_id FROM catalog_shadow_results GROUP BY operation_id HAVING COUNT(*)>1").fetchone():
        raise ValueError("duplicate saved comparison")
    for operation, body_hash, text in db.execute(
            "SELECT operation_id,body_hash,result_json FROM catalog_shadow_results"):
        result = _validated_result(text)
        intent = db.execute("SELECT body_hash,status,session_id FROM amp_sessions WHERE request_id=?",
                            (operation,)).fetchone()
        if (type(body_hash) is not str or not _SHA.fullmatch(body_hash)
                or operation != result["operation_id"] or intent is None
                or intent != (body_hash, "BOUND", result["provider"]["session_id"])):
            raise ValueError("saved comparison intent binding mismatch")
        budget_id = CheckpointedProvider._operation_id("initial_", operation)
        reservation = db.execute("SELECT status,usage_json,settled_units FROM budget_reservations WHERE run_id=?",
                                 (budget_id,)).fetchone()
        if (reservation is None or reservation[0] not in (
                "UNKNOWN_USAGE", "TOKENS_OBSERVED_COST_UNSETTLED") or reservation[2] is not None):
            raise ValueError("saved comparison budget binding mismatch")
        tokens = (result["provider"]["input_tokens"], result["provider"]["output_tokens"])
        if reservation[1] is not None:
            usage = Usage(**json.loads(reservation[1], object_pairs_hook=_strict_pairs,
                                       parse_constant=_no_nonfinite_constant))
            if tokens != (usage.input_tokens, usage.output_tokens):
                raise ValueError("saved comparison token binding mismatch")
        elif tokens != (None, None):
            raise ValueError("unknown usage cannot become measured tokens")


def _read_saved_comparison(checkpoint: PrivateCheckpoint, *, operation_id: str,
                           body_hash: str, expected_fields: dict) -> dict | None:
    """Read the original ACKed result or a static input-binding UNKNOWN."""
    if (type(checkpoint) is not PrivateCheckpoint or checkpoint.db is None
            or checkpoint.revision is None or checkpoint.broken):
        raise CheckpointUnavailable("active acquired private checkpoint required")
    if type(expected_fields) is not dict or set(expected_fields) != _BINDING_KEYS:
        raise ValueError("complete comparison input binding required")
    try:
        with sqlite3.connect(checkpoint.db.as_uri() + "?mode=ro", uri=True) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            validate_provider_tables(db, tables)
            validate_catalog_shadow_results(db, tables)
            if _RESULT_TABLE not in tables:
                return None
            row = db.execute("SELECT body_hash,result_json FROM catalog_shadow_results WHERE operation_id=?",
                             (operation_id,)).fetchone()
            if row is None:
                return None
            result = _validated_result(row[1])
            if row[0] != body_hash or any(result[key] != value for key, value in expected_fields.items()):
                return _record("UNKNOWN", "INPUT_BINDING_MISMATCH", result["run_id"], **expected_fields)
            return result
    except (sqlite3.Error, ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        checkpoint.broken = True
        raise CheckpointUnavailable("invalid private provider state; reconcile only") from None


def _save_compared_result(checkpoint: PrivateCheckpoint, *, body_hash: str, result: dict) -> dict:
    """Commit and close locally, then require the existing checkpoint save ACK."""
    if (type(checkpoint) is not PrivateCheckpoint or checkpoint.db is None
            or checkpoint.revision is None or checkpoint.broken):
        raise CheckpointUnavailable("active acquired private checkpoint required")
    try:
        text = _result_json(result)
        _validated_result(text)
        db = sqlite3.connect(checkpoint.db, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            validate_provider_tables(db, tables)
            validate_catalog_shadow_results(db, tables)
            db.execute("""CREATE TABLE IF NOT EXISTS catalog_shadow_results (
                operation_id TEXT PRIMARY KEY NOT NULL,
                body_hash TEXT NOT NULL, result_json TEXT NOT NULL,
                FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id)
            )""")
            db.execute("INSERT INTO catalog_shadow_results VALUES (?,?,?)",
                       (result["operation_id"], body_hash, text))
            validate_catalog_shadow_results(db, tables | {_RESULT_TABLE})
            db.execute("COMMIT")
        finally:
            db.close()
        checkpoint.save()
        return result
    except BaseException as exc:
        checkpoint.broken = True
        if isinstance(exc, Exception):
            raise CheckpointUnavailable("private comparison save uncertain; reconcile only") from None
        raise


def _prior_intent(checkpoint, operation_id):
    """Inspect the acquired database without creating provider or budget state."""
    try:
        with sqlite3.connect(checkpoint.db.as_uri() + "?mode=ro", uri=True) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            validate_provider_tables(db, tables)
            if "amp_sessions" not in tables:
                return None
            return db.execute("SELECT session_id,status,body_hash FROM amp_sessions WHERE request_id=?",
                              (operation_id,)).fetchone()
    except (sqlite3.Error, ValueError):
        checkpoint.broken = True
        raise CheckpointUnavailable("invalid private provider state; reconcile only") from None


def compare_prepared_catalog_shadow(
    checkpoint: PrivateCheckpoint,
    prepared: tuple[OwnedChangeContext, TechnicalAssessment, OwnedDigitalScope] | None,
    *, now: datetime, run_id: str, enabled: bool = False,
    client_factory: Callable[[], Any] | None = None,
    cap_usd: Decimal | None = None, upper_usd: Decimal | None = None,
    deadline_monotonic: float,
) -> dict:
    """Compare the exact host-prepared tuple; never plan or grant authority."""
    if type(enabled) is not bool:
        raise ValueError("exact boolean opt-in required")
    if not enabled:
        return _record("SKIPPED", "DISABLED", run_id)
    if (type(run_id) is not str or not re.fullmatch(r"[1-9][0-9]*", run_id)
            or type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)):
        raise ValueError("bounded run, aware time, and finite absolute deadline required")
    if (type(checkpoint) is not PrivateCheckpoint or checkpoint.db is None
            or checkpoint.revision is None or checkpoint.broken):
        raise CheckpointUnavailable("active acquired private checkpoint required")
    if time.monotonic() >= deadline_monotonic:
        return _record("SKIPPED", "DEADLINE_EXPIRED", run_id)
    if prepared is None:
        return _record("SKIPPED", "NO_CANDIDATE", run_id)
    if (type(prepared) is not tuple or len(prepared) != 3
            or type(prepared[0]) is not OwnedChangeContext
            or type(prepared[1]) is not TechnicalAssessment
            or type(prepared[2]) is not OwnedDigitalScope):
        return _record("SKIPPED", "UNSUPPORTED_CONTEXT", run_id)
    context, assessment, scope = prepared
    if (type(context.criteria) is not TechnicalCriteria
            or context.criteria.candidate.action not in _ALLOWED_ACTIONS):
        return _record("SKIPPED", "UNSUPPORTED_ACTION", run_id)
    try:
        handoff = prepare_owned_change(context, assessment, scope, now,
                                      schema="manager.digital-handoff.v2")
        prompt = render_prompt(context.planner, fictional=False)
    except Exception:
        return _record("SKIPPED", "CONTEXT_REVALIDATION_FAILED", run_id)
    if handoff.status != "PREPARED_PLATFORM_AUTHORITY_REQUIRED":
        return _record("SKIPPED", "CONTEXT_REVALIDATION_FAILED", run_id)
    fields = _base_fields(context, assessment, prompt,
                          _canonical_operation(context, assessment))
    expected_fields = dict(fields)
    body_hash = initial_request_body_hash(prompt)
    fields.update({
        "baseline": {
            "no_action": advisory_receipt(collaboration_baselines.no_action_baseline(context.planner)),
            "rules": advisory_receipt(collaboration_baselines.rule_baseline(context.planner)),
        },
        "provider": None,
        "model_comparison": None,
    })
    if time.monotonic() >= deadline_monotonic:
        return _record("SKIPPED", "DEADLINE_EXPIRED", run_id, **fields)

    saved = _read_saved_comparison(checkpoint, operation_id=fields["operation_id"],
                                   body_hash=body_hash, expected_fields=expected_fields)
    if saved is not None:
        if saved["status"] == "UNKNOWN":
            return _record("UNKNOWN", "INPUT_BINDING_MISMATCH", run_id, **fields)
        return saved
    intent = _prior_intent(checkpoint, fields["operation_id"])
    if intent is not None:
        fields["provider"] = {"session_id": intent[0], "turn_id": None, "status": intent[1],
                              "input_tokens": None, "output_tokens": None}
        reason = ("PRIOR_INTENT_RECONCILIATION_REQUIRED" if intent[2] == body_hash
                  else "INPUT_BINDING_MISMATCH")
        return _record("UNKNOWN", reason, run_id, **fields)
    try:
        for limit in (cap_usd, upper_usd):
            if limit is not None:
                _money(limit)
        if client_factory is not None and not callable(client_factory):
            raise ValueError
    except (ValueError, ArithmeticError):
        raise ValueError("invalid catalog shadow provider configuration") from None
    if client_factory is None or cap_usd is None or upper_usd is None:
        return _record("SKIPPED", "PROVIDER_NOT_CONFIGURED", run_id, **fields)
    try:
        client = client_factory()
    except Exception:
        return _record("UNKNOWN", "PROVIDER_TRANSPORT_UNKNOWN", run_id, **fields)
    try:
        owner = CheckpointedProvider(checkpoint, cap_usd=cap_usd)
        advice = owner.initial(client, context.planner,
                               request_id=fields["operation_id"],
                               upper_usd=upper_usd,
                               deadline_monotonic=deadline_monotonic)
    except CheckpointUnavailable:
        raise
    except BudgetExceeded:
        if checkpoint.broken:
            raise CheckpointUnavailable("private checkpoint fenced; reconcile only")
        return _record("SKIPPED", "BUDGET_EXCEEDED", run_id, **fields)
    except SessionFailure:
        if checkpoint.broken:
            raise CheckpointUnavailable("private checkpoint fenced; reconcile only")
        intent = None
        try:
            intent = owner.journal.get(fields["operation_id"])
        except SessionConflict:
            pass
        fields["provider"] = {"session_id": intent.session_id if intent else None,
                              "turn_id": None,
                              "status": intent.status if intent else "UNKNOWN",
                              "input_tokens": None, "output_tokens": None}
        return _record("UNKNOWN", "PROVIDER_TRANSPORT_UNKNOWN", run_id, **fields)

    evidence = advice.evidence
    fields["provider"] = {
        "session_id": evidence.session_id,
        "turn_id": evidence.turn_id,
        "status": evidence.status,
        "input_tokens": evidence.input_tokens,
        "output_tokens": evidence.output_tokens,
    }
    if advice.advice.status == "INVALID_MODEL_OUTPUT":
        fields["model_status"] = "INVALID_MODEL_OUTPUT"
    else:
        model_receipt = advisory_receipt(advice.advice)
        fields["model_status"] = advice.advice.status
        fields["model_advice"] = model_receipt
        fields["model_comparison"] = {
            "no_action_same_decision": model_receipt["decision"] == fields["baseline"]["no_action"]["decision"],
            "rules_same_decision": model_receipt["decision"] == fields["baseline"]["rules"]["decision"],
        }
    result = _record("COMPARED_P0", "MODEL_RESPONSE_PARSED", run_id,
                     compared_at=datetime.now(timezone.utc).isoformat(), **fields)
    return _save_compared_result(checkpoint, body_hash=body_hash, result=result)


def public_catalog_shadow_summary(result: dict) -> dict:
    """Select and validate a fixed, non-authorizing public P0 projection."""
    def invalid():
        raise ValueError("invalid catalog shadow record")

    def enum(value, allowed):
        if type(value) is not str or value not in allowed:
            invalid()
        return value

    def optional_hash(value, prefix=""):
        if value is not None and (type(value) is not str or
                not re.fullmatch(prefix + r"[0-9a-f]{64}", value)):
            invalid()
        return value

    def optional_dict(value):
        if value is None:
            return {}
        if type(value) is not dict:
            invalid()
        return value

    def decision(value):
        return enum(value, {"PASS", "ASK", "PROPOSE"}) if value is not None else None

    if type(result) is not dict:
        invalid()
    if (result.get("schema") != _SCHEMA or type(result.get("schema")) is not str
            or type(result.get("run_id")) is not str
            or not re.fullmatch(r"[1-9][0-9]*", result["run_id"])
            or result.get("proof_level") != "P0"
            or type(result.get("proof_level")) is not str
            or result.get("authorized_execution") is not False
            or result.get("causal_support") is not False
            or result.get("human_outcome") != "NOT_MEASURED"
            or type(result.get("human_outcome")) is not str
            or type(result.get("action_writes")) is not int or result["action_writes"] != 0
            or result.get("settled_cost_usd") is not None):
        invalid()
    status = enum(result.get("status"), {"SKIPPED", "UNKNOWN", "COMPARED_P0"})
    reason = enum(result.get("reason"), _REASONS)
    compared_at = result.get("compared_at")
    if compared_at is not None:
        if type(compared_at) is not str:
            invalid()
        try:
            at = datetime.fromisoformat(compared_at)
            if at.tzinfo is None or at.utcoffset() is None or at.utcoffset().total_seconds() != 0:
                invalid()
        except ValueError:
            invalid()
    baseline = optional_dict(result.get("baseline"))
    baseline_decisions = {key: decision(optional_dict(baseline.get(key)).get("decision"))
                          for key in ("no_action", "rules")}
    model_status = result.get("model_status")
    if model_status is not None:
        enum(model_status, {"MODEL_ADVICE_P0", "INVALID_MODEL_OUTPUT"})
    model_decision = decision(optional_dict(result.get("model_advice")).get("decision"))
    if model_status != "MODEL_ADVICE_P0" and model_decision is not None:
        invalid()
    comparison = optional_dict(result.get("model_comparison"))
    model_comparison = {}
    for key in ("no_action_same_decision", "rules_same_decision"):
        value = comparison.get(key)
        if value is not None and type(value) is not bool:
            invalid()
        model_comparison[key] = value
    return {
        "schema": _SCHEMA, "status": status, "reason": reason,
        "run_id": result["run_id"], "compared_at": compared_at,
        "operation_id": optional_hash(result.get("operation_id"), "catalog_shadow_"),
        "context_sha256": optional_hash(result.get("context_sha256")),
        "baseline_digest": optional_hash(result.get("baseline_digest")),
        "candidate_digest": optional_hash(result.get("candidate_digest")),
        "baseline_decisions": baseline_decisions,
        "model_status": model_status, "model_decision": model_decision,
        "model_comparison": model_comparison,
        "proof_level": "P0", "authorized_execution": False, "causal_support": False,
        "human_outcome": "NOT_MEASURED", "action_writes": 0, "settled_cost_usd": None,
    }
