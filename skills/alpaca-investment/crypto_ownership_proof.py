"""Single pure contract for sealed BTC ownership and recorded close evidence.

No provider, environment, marker-file or ledger writes occur in these readers.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

from risk_policy import parse_instant
from strategy_policy import validate_policy_card


# Only these failures guarantee that the order receives no further updates.
BROKER_TERMINAL_FAILURE_STATUSES = frozenset({"canceled", "expired", "rejected"})
BROKER_RESUMABLE_STATUSES = frozenset({"done_for_day", "stopped", "suspended"})


class ReconciliationPending(ValueError):
    """An official order exists but its strategy account readback is not settled."""



def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()



def _filled_qty_positive(order: dict[str, Any]) -> bool:
    value = order.get("filled_qty")
    if value is None or value == "":
        return False
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return quantity.is_finite() and quantity > 0


def _filled_qty_is_zero(order: dict[str, Any]) -> bool:
    try:
        quantity = Decimal(str(order.get("filled_qty")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return quantity.is_finite() and quantity == 0


def _terminal_no_fill_proven(order: dict[str, Any], rows: list[dict[str, Any]], effect_id: str | None) -> bool:
    if not _filled_qty_is_zero(order):
        return False
    for row in rows:
        if row.get("effect_id") != effect_id:
            continue
        recorded = row["broker"] if isinstance(row.get("broker"), dict) else row
        if (row.get("broker_status") in {"filled", "partially_filled"}
                or recorded.get("status") in {"filled", "partially_filled"}
                or _filled_qty_positive(recorded)):
            return False
    return True


def _known_policy_metadata(row: dict[str, Any], *, owner_id: str, strategy_id: str, release_sha: str) -> None:
    for key, expected in (("owner_id", owner_id), ("strategy_id", strategy_id), ("release_sha", release_sha)):
        if row.get(key) is not None and row[key] != expected:
            raise ValueError
    if row.get("receipt_type") == "outcome" and row.get("broker_status") is not None:
        broker = row.get("broker")
        if not isinstance(broker, dict) or row["broker_status"] != broker.get("status"):
            raise ValueError


def _sealed_entry_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    """Read the sealed policy and official filled buy for one owned entry."""
    if (not isinstance(mode, str) or mode not in {"paper", "live"}
            or owner_id != f"alpaca-investment-{mode}" or not isinstance(ownership, dict)
            or ownership.get("symbol") != "BTCUSD"):
        raise ValueError("owned_entry_identity_invalid")
    effect_id, client = ownership.get("entry_effect_id"), ownership.get("entry_client_order_id")
    if (not isinstance(effect_id, str) or re.fullmatch(r"[0-9a-f]{64}", effect_id) is None
            or client != f"lm-ai-{effect_id[:24]}"):
        raise ValueError("owned_entry_identity_invalid")
    intents = [row for row in rows if row.get("receipt_type") == "effect_intent"
               and row.get("status") == "planned" and row.get("effect_id") == effect_id]
    if len(intents) != 1:
        raise ValueError("owned_entry_intent_missing" if not intents else "owned_entry_intent_conflict")
    intent = intents[0]
    if (intent.get("client_order_id") != client or intent.get("mode") != mode
            or intent.get("paper") is not (mode == "paper") or intent.get("owner_id") != owner_id):
        raise ValueError("owned_entry_identity_invalid")
    decisions = [row for row in rows if row.get("receipt_type") == "decision"
                 and row.get("decision_id") == intent.get("decision_id")]
    if len(decisions) != 1 or not isinstance(decisions[0].get("decision"), dict):
        raise ValueError("owned_entry_policy_missing")
    decision, order = decisions[0]["decision"], intent.get("order")
    if (decisions[0].get("mode") != mode or decisions[0].get("paper") is not (mode == "paper")
            or decision.get("mode") != mode or decision.get("owner_id") != owner_id
            or decision.get("action") != "ENTER" or not isinstance(decision.get("strategy_id"), str)
            or not decision["strategy_id"]
            or decision.get("strategy_id") != intent.get("strategy_id")
            or not isinstance(decision.get("policy_card"), dict) or not isinstance(order, dict)
            or order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC"
            or order.get("side") != "buy" or order.get("type") != "market"
            or order.get("time_in_force") != "gtc"):
        raise ValueError("owned_entry_policy_missing")
    if (intent.get("decision_id") != _digest({"mode": mode, "decision": decision})
            or effect_id != _digest({"decision_id": intent["decision_id"], "order": order})):
        raise ValueError("owned_entry_digest_mismatch")
    return {"intent": intent, "decision": decision, "order": order}


def owned_entry_decision_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    sealed = _sealed_entry_from_rows(rows, ownership, owner_id=owner_id, mode=mode)
    decision, order = sealed["decision"], sealed["order"]
    effect_id, client = ownership["entry_effect_id"], ownership["entry_client_order_id"]
    outcomes = [row for row in rows if row.get("receipt_type") == "outcome"
                and row.get("effect_id") == effect_id]
    if not outcomes:
        raise ValueError("owned_entry_fill_missing")
    try:
        for row in outcomes:
            _known_policy_metadata(row, owner_id=owner_id, strategy_id=decision["strategy_id"],
                                   release_sha=decision.get("release_sha"))
    except ValueError as error:
        raise ValueError("owned_entry_fill_conflict") from error
    # Enrichment may append another view of the same immutable fill. Known
    # values must agree; a later contradictory row is not an authority override.
    first_filled = next((index for index, row in enumerate(outcomes)
        if row.get("outcome") == "broker_reconciled" and isinstance(row.get("broker"), dict)
        and row["broker"].get("status") == "filled"), len(outcomes))
    # Older writers incorrectly sealed a paused zero as a terminal failure.
    # Keep its identity evidence, but a later same-order fill can supersede
    # that pre-execution snapshot. Never permit a post-fill regression.
    paused_zero = {index for index, row in enumerate(outcomes) if index < first_filled
        and row.get("outcome") == "broker_terminal_failure" and isinstance(row.get("broker"), dict)
        and row["broker"].get("status") in BROKER_RESUMABLE_STATUSES
        and _filled_qty_is_zero(row["broker"])
        and row["broker"].get("filled_at") in {None, ""}
        and row["broker"].get("filled_avg_price") in {None, ""}}
    if any(row.get("outcome") != "broker_reconciled" and index not in paused_zero
           for index, row in enumerate(outcomes)):
        raise ValueError("owned_entry_fill_conflict")
    identity_fields = ("mode", "paper", "client_order_id", "broker_receipt_id")
    if any(tuple(row.get(key) for key in identity_fields) !=
           tuple(outcomes[0].get(key) for key in identity_fields) for row in outcomes):
        raise ValueError("owned_entry_fill_conflict")
    for key in ("id", "client_order_id", "symbol", "side", "status", "type", "time_in_force",
                "filled_qty", "filled_avg_price", "submitted_at", "filled_at"):
        known = []
        for index, row in enumerate(outcomes):
            if index in paused_zero and key in {"status", "filled_qty", "filled_avg_price", "filled_at"}:
                continue
            value = row.get("broker", {}).get(key) if isinstance(row.get("broker"), dict) else None
            if value is None or value == "":
                continue
            try:
                if key in {"filled_qty", "filled_avg_price"}:
                    value = Decimal(str(value))
                    if not value.is_finite() or value <= 0:
                        raise ValueError
                elif key in {"submitted_at", "filled_at"}:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        raise ValueError
                elif key == "symbol" and isinstance(value, str):
                    value = value.replace("/", "")
            except (InvalidOperation, TypeError, ValueError, AttributeError) as error:
                raise ValueError("owned_entry_fill_invalid") from error
            known.append(value)
        if known and any(value != known[0] for value in known):
            raise ValueError("owned_entry_fill_conflict")
    outcome = outcomes[-1]
    broker = outcome.get("broker")
    if (outcome.get("outcome") != "broker_reconciled" or outcome.get("mode") != mode
            or outcome.get("paper") is not (mode == "paper")
            or outcome.get("client_order_id") != client or not isinstance(broker, dict)
            or broker.get("status") != "filled" or broker.get("side") != "buy"
            or broker.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
            or broker.get("client_order_id") != client or broker.get("type") != order["type"]
            or broker.get("time_in_force") != order["time_in_force"]
            or not isinstance(broker.get("id"), str)
            or not broker["id"] or outcome.get("broker_receipt_id") != broker["id"]):
        raise ValueError("owned_entry_fill_invalid")
    try:
        filled, marker_filled, owned, price = [Decimal(str(value)) for value in (
            broker.get("filled_qty"), ownership.get("entry_filled_qty"),
            ownership.get("owned_qty"), broker.get("filled_avg_price"))]
        if (any(not number.is_finite() or number <= 0 for number in (filled, marker_filled, owned, price))
                or filled != marker_filled or owned > filled):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("owned_entry_fill_invalid") from error
    return {"decision": decision, "broker": broker, "owned_qty": str(owned)}



def _owned_policy(proof: dict[str, Any], ownership: dict[str, Any], *, mode: str) -> dict[str, Any]:
    decision, broker = proof["decision"], proof["broker"]
    card, release_sha = validate_policy_card(decision["policy_card"], decision.get("release_sha"),
                                             strategy_id=decision.get("strategy_id"))
    if tuple(card.instruments) != ("BTC/USDC",):
        raise ValueError("owned_entry_policy_scope_invalid")
    try:
        filled_at = broker["filled_at"]
        if not (parse_instant(decision["observed_at"]) <= parse_instant(broker["submitted_at"])
                <= parse_instant(filled_at)):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("owned_entry_fill_time_invalid") from error
    return {"card": card, "release_sha": release_sha, "entry_price": broker["filled_avg_price"],
            "entry_timestamp": filled_at, "owned_qty": proof["owned_qty"],
            "entry_effect_id": ownership["entry_effect_id"], "entry_client_order_id": broker["client_order_id"],
            "entry_provider_order_id": broker["id"], "owner_id": decision["owner_id"], "mode": mode}




def _account_positions(observation: dict[str, Any], *, mode: str, not_before: datetime) -> list[dict[str, Any]]:
    if observation.get("mode") != mode or observation.get("paper") is not (mode == "paper"):
        raise ValueError
    if parse_instant(observation["clock"]["observed_at"]) < not_before:
        raise ValueError
    if any(not Decimal(str(observation["account"][key])).is_finite() for key in ("cash", "equity")):
        raise ValueError
    positions = observation["positions"]
    if not isinstance(positions, list):
        raise ValueError
    for position in positions:
        if (not isinstance(position, dict) or not isinstance(position.get("symbol"), str)
                or not position["symbol"].strip() or not Decimal(str(position.get("qty"))).is_finite()):
            raise ValueError


    return positions


def _flat_btc_account(observation: dict[str, Any], *, mode: str, not_before: datetime) -> None:
    positions = _account_positions(observation, mode=mode, not_before=not_before)
    if any(position["symbol"] in {"BTCUSD", "BTCUSDC", "BTC/USDC", "BTC/USD", "BTC"} for position in positions):
        raise ReconciliationPending("owned_close_account_pending")


def close_fill_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any], broker: dict[str, Any],
                              observation: dict[str, Any], *, mode: str, owner_id: str) -> dict[str, Any]:
    parent = _owned_policy(owned_entry_decision_from_rows(rows, ownership, owner_id=owner_id, mode=mode),
                           ownership, mode=mode)
    try:
        effect = ownership["close_effect_id"]
        client = ownership["close_client_order_id"]
        if (ownership.get("status") not in {"closing", "closed"} or not isinstance(effect, str)
                or len(effect) != 64 or any(c not in "0123456789abcdef" for c in effect)
                or client != "lm-ai-" + effect[:24]):
            raise ValueError
        intents = [r for r in rows if r.get("receipt_type") == "effect_intent"
                   and r.get("status") == "planned" and r.get("effect_id") == effect]
        if len(intents) != 1:
            raise ValueError
        intent = intents[0]
        decisions = [r for r in rows if r.get("receipt_type") == "decision"
                     and r.get("decision_id") == intent.get("decision_id")]
        if len(decisions) != 1:
            raise ValueError
        decision, order = decisions[0]["decision"], intent["order"]
        if (intent.get("client_order_id") != client or intent.get("mode") != mode
                or intent.get("paper") is not (mode == "paper")
                or intent.get("owner_id") != parent["owner_id"]
                or intent.get("strategy_id") != parent["card"].strategy_id
                or decisions[0].get("mode") != mode or decisions[0].get("paper") is not (mode == "paper")
                or decision.get("action") != "EXIT" or decision.get("mode") != mode
                or decision.get("owner_id") != parent["owner_id"]
                or decision.get("strategy_id") != parent["card"].strategy_id
                or decision.get("release_sha") != parent["release_sha"]
                or any(decision.get(key) != parent[key] for key in (
                    "entry_effect_id", "entry_client_order_id", "entry_provider_order_id"))
                or Decimal(str(decision.get("entry_price"))) != Decimal(parent["entry_price"])
                or parse_instant(decision.get("entry_timestamp")) != parse_instant(parent["entry_timestamp"])
                or intent.get("decision_id") != _digest({"mode": mode, "decision": decision})
                or effect != _digest({"decision_id": intent["decision_id"], "order": order})
                or set(order) != {"asset_class", "symbol", "side", "type", "time_in_force", "qty"}
                or order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC"
                or order.get("side") != "sell" or order.get("type") != "market"
                or order.get("time_in_force") != "gtc"):
            raise ValueError
        if (not isinstance(broker.get("id"), str) or not broker["id"].strip()
                or broker.get("client_order_id") != client or broker.get("status") != "filled"
                or broker.get("symbol") not in {"BTCUSDC", "BTC/USDC"}
                or broker.get("side") != "sell" or broker.get("type") != "market"
                or broker.get("time_in_force") != "gtc"):
            raise ValueError
        qty = Decimal(str(broker.get("filled_qty")))
        price = Decimal(str(broker.get("filled_avg_price")))
        if (not qty.is_finite() or qty <= 0 or not price.is_finite() or price <= 0
                or qty != Decimal(str(order["qty"])) or qty != Decimal(str(decision.get("position_qty")))
                or qty != Decimal(parent["owned_qty"])):
            raise ValueError
        submitted, filled, observed = (parse_instant(value) for value in (
            broker.get("submitted_at"), broker.get("filled_at"), observation["clock"]["observed_at"]))
        if not (parse_instant(parent["entry_timestamp"]) <= parse_instant(decision.get("observed_at"))
                <= submitted <= filled <= observed):
            raise ValueError
        _flat_btc_account(observation, mode=mode, not_before=filled)
        for row in rows:
            if row.get("receipt_type") != "outcome" or row.get("effect_id") != effect:
                continue
            _known_policy_metadata(row, owner_id=owner_id, strategy_id=parent["card"].strategy_id,
                                   release_sha=parent["release_sha"])
            previous = row.get("broker")
            if (row.get("mode") != mode or row.get("paper") is not (mode == "paper")
                    or row.get("client_order_id") != client or row.get("outcome") != "broker_reconciled"
                    or row.get("broker_receipt_id") != broker["id"] or not isinstance(previous, dict)):
                raise ValueError
            for key in ("id", "client_order_id", "status", "side", "type", "time_in_force",
                        "symbol", "filled_qty", "filled_avg_price", "submitted_at", "filled_at"):
                old, current = previous.get(key), broker.get(key)
                if old is None or old == "":
                    continue
                if key in {"filled_qty", "filled_avg_price"}:
                    if Decimal(str(old)) != Decimal(str(current)):
                        raise ValueError
                elif key in {"submitted_at", "filled_at"}:
                    if parse_instant(old) != parse_instant(current):
                        raise ValueError
                elif key == "symbol":
                    if old.replace("/", "") != current.replace("/", ""):
                        raise ValueError
                elif old != current:
                    raise ValueError
    except ReconciliationPending:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError("owned_close_proof_invalid") from error
    return {"account_readback": observation, "receipt": {
        "schema_version": 1, "kind": "owned_crypto_close", "owner_id": parent["owner_id"], "mode": mode,
        "strategy_id": parent["card"].strategy_id, "release_sha": parent["release_sha"],
        **{key: parent[key] for key in ("entry_effect_id", "entry_client_order_id", "entry_provider_order_id")},
        "close_effect_id": effect, "close_client_order_id": client, "close_provider_order_id": broker["id"],
        "entry_price": parent["entry_price"], "entry_timestamp": parent["entry_timestamp"],
        "exit_filled_qty": format(qty.normalize(), "f"), "exit_price": format(price.normalize(), "f"),
        "exit_timestamp": filled.isoformat(), "quote_currency": "USDC", "net_realized_pnl_usd": None}}




def _recorded_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any],
                                  broker: dict[str, Any], observation: dict[str, Any], *,
                                  mode: str, owner_id: str, reader, effect_key: str) -> dict[str, Any]:
    proof = reader(rows, ownership, broker, observation, mode=mode, owner_id=owner_id)
    matched = False
    error_prefix = {"owned_crypto_close": "owned_close", "owned_crypto_entry": "owned_entry",
                    "owned_crypto_no_fill": "owned_no_fill"}[proof["receipt"]["kind"]]
    for row in rows:
        if row.get("receipt_type") != "outcome" or row.get("effect_id") != ownership.get(effect_key):
            continue
        recorded = row.get("strategy_receipt")
        if recorded is None:
            continue
        if not isinstance(recorded, dict) or recorded.get("receipt") != proof["receipt"]:
            raise ValueError(f"{error_prefix}_receipt_conflict")
        expected = reader(rows, ownership, row.get("broker"),
            recorded.get("account_readback"), mode=mode, owner_id=owner_id)
        if recorded != expected:
            raise ValueError(f"{error_prefix}_receipt_conflict")
        matched = True
    if not matched:
        raise ValueError(f"{error_prefix}_receipt_missing")
    return proof



def no_fill_entry_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any],
                                  broker: dict[str, Any], observation: dict[str, Any], *,
                                  mode: str, owner_id: str) -> dict[str, Any]:
    sealed = _sealed_entry_from_rows(rows, ownership, owner_id=owner_id, mode=mode)
    decision, order = sealed['decision'], sealed['order']
    try:
        card, release = validate_policy_card(decision['policy_card'], decision.get('release_sha'),
                                             strategy_id=decision.get('strategy_id'))
        effect, client = ownership['entry_effect_id'], ownership['entry_client_order_id']
        if (tuple(card.instruments) != ('BTC/USDC',)
                or ownership.get('status') not in {'closed', 'entry_pending'}
                or ownership.get('close_effect_id') is not None or ownership.get('close_client_order_id') is not None
                or not isinstance(broker.get('id'), str) or not broker['id'].strip()
                or broker.get('client_order_id') != client
                or broker.get('symbol') not in {'BTCUSDC', 'BTC/USDC'}
                or broker.get('side') != 'buy' or broker.get('type') != order['type']
                or broker.get('time_in_force') != order['time_in_force']
                or broker.get('status') not in BROKER_TERMINAL_FAILURE_STATUSES
                or broker.get('filled_at') not in {None, ''}):
            raise ValueError
        for value in (broker.get('filled_qty'), ownership.get('entry_filled_qty'), ownership.get('owned_qty', '0')):
            quantity = Decimal(str(value))
            if not quantity.is_finite() or quantity != 0:
                raise ValueError
        submitted = parse_instant(broker.get('submitted_at'))
        if parse_instant(decision.get('observed_at')) > submitted:
            raise ValueError
        _flat_btc_account(observation, mode=mode, not_before=submitted)
        outcomes = []
        for row in rows:
            if row.get('effect_id') != effect:
                continue
            _known_policy_metadata(row, owner_id=owner_id, strategy_id=card.strategy_id, release_sha=release)
            if ((row.get('mode') is not None and row.get('mode') != mode)
                    or (row.get('paper') is not None and row.get('paper') is not (mode == 'paper'))
                    or (row.get('client_order_id') is not None and row.get('client_order_id') != client)
                    or (row.get('broker_receipt_id') is not None and row.get('broker_receipt_id') != broker['id'])
                    or row.get('broker_status') in {'filled', 'partially_filled'}
                    or row.get('reason') == 'partial_fill_requires_reconciliation'):
                raise ValueError
            previous = row['broker'] if isinstance(row.get('broker'), dict) else row
            if previous.get('status') in {'filled', 'partially_filled'} or previous.get('filled_at') not in {None, ''}:
                raise ValueError
            try:
                previous_qty = Decimal(str(previous.get('filled_qty')))
                if previous_qty.is_finite() and previous_qty > 0:
                    raise ValueError
            except InvalidOperation:
                pass
            if row.get('receipt_type') != 'outcome':
                continue
            if (row.get('outcome') != 'broker_terminal_failure' or not isinstance(row.get('broker'), dict)
                    or row.get('mode') != mode or row.get('paper') is not (mode == 'paper')
                    or row.get('client_order_id') != client or row.get('broker_receipt_id') != broker['id']):
                raise ValueError
            for key in ('id', 'client_order_id', 'side', 'type', 'time_in_force', 'symbol', 'submitted_at'):
                known = previous.get(key)
                if known is None or known == '':
                    continue
                current = broker.get(key)
                if key == 'symbol':
                    known, current = known.replace('/', ''), current.replace('/', '')
                elif key == 'submitted_at':
                    known, current = parse_instant(known), parse_instant(current)
                if known != current:
                    raise ValueError
            outcomes.append(row)
        if not outcomes or outcomes[-1]['broker'].get('status') != broker['status']:
            raise ValueError
        recorded_qty = Decimal(str(outcomes[-1]['broker'].get('filled_qty')))
        if not recorded_qty.is_finite() or recorded_qty != 0:
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError('owned_no_fill_proof_invalid') from error
    return {'account_readback': observation, 'receipt': {
        'schema_version': 1, 'kind': 'owned_crypto_no_fill', 'owner_id': owner_id, 'mode': mode,
        'strategy_id': card.strategy_id, 'release_sha': release, 'entry_effect_id': effect,
        'entry_client_order_id': client, 'entry_provider_order_id': broker['id'],
        'order_status': broker['status'], 'submitted_at': submitted.isoformat(),
        'filled_qty': '0', 'quote_currency': 'USDC', 'net_realized_pnl_usd': None}}


def recorded_close_proof_from_rows(rows, ownership, broker, observation, *, mode, owner_id):
    return _recorded_proof_from_rows(rows, ownership, broker, observation, mode=mode, owner_id=owner_id,
                                     reader=close_fill_proof_from_rows, effect_key="close_effect_id")


def recorded_no_fill_proof_from_rows(rows, ownership, broker, observation, *, mode, owner_id):
    return _recorded_proof_from_rows(rows, ownership, broker, observation, mode=mode, owner_id=owner_id,
                                     reader=no_fill_entry_proof_from_rows, effect_key="entry_effect_id")


def entry_fill_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any],
                               broker: dict[str, Any], observation: dict[str, Any], *,
                               mode: str, owner_id: str) -> dict[str, Any]:
    """Validate the actual GET before committing its acquisition/account receipt."""
    try:
        if ownership.get('status') not in {'entry_pending','open','closing','closed'}:
            raise ValueError
        filled = Decimal(str(broker.get('filled_qty')))
        if not filled.is_finite() or filled <= 0:
            raise ValueError
        known_fill = Decimal(str(ownership.get('entry_filled_qty')))
        if (not known_fill.is_finite() or known_fill < 0
                or (known_fill == 0 and ownership.get('status') != 'entry_pending')
                or (known_fill > 0 and known_fill != filled)):
            raise ValueError
        # This envelope contains the current official response, not a synthetic order.
        current = {'receipt_type':'outcome','outcome':'broker_reconciled',
            'effect_id':ownership['entry_effect_id'],'client_order_id':ownership['entry_client_order_id'],
            'mode':mode,'paper':mode=='paper','broker':broker,'broker_status':broker.get('status'),
            'broker_receipt_id':broker.get('id')}
        validation_owner={**ownership,'entry_filled_qty':str(filled),'owned_qty':str(filled)}
        parent=_owned_policy(owned_entry_decision_from_rows([*rows,current],validation_owner,
                             owner_id=owner_id,mode=mode),validation_owner,mode=mode)
        positions=_account_positions(observation,mode=mode,not_before=parse_instant(parent['entry_timestamp']))
        btc=[p for p in positions if p['symbol'] in {'BTCUSD','BTCUSDC','BTC/USDC'}]
        if not btc:
            raise ReconciliationPending('owned_entry_account_pending')
        if len(btc)!=1:
            raise ValueError
        held=Decimal(str(btc[0]['qty']))
        if held==0:
            raise ReconciliationPending('owned_entry_account_pending')
        if held<0 or held>filled:
            raise ValueError
        if ownership.get('owned_qty') is not None:
            known_owned=Decimal(str(ownership['owned_qty']))
            if not known_owned.is_finite() or known_owned<=0 or known_owned!=held:
                raise ValueError
    except ReconciliationPending:
        raise
    except (ValueError,KeyError,TypeError,AttributeError,InvalidOperation) as error:
        raise ValueError('owned_entry_account_invalid') from error
    return {'account_readback':observation,'receipt':{
        'schema_version':1,'kind':'owned_crypto_entry','owner_id':owner_id,'mode':mode,
        'strategy_id':parent['card'].strategy_id,'release_sha':parent['release_sha'],
        'entry_effect_id':parent['entry_effect_id'],'entry_client_order_id':parent['entry_client_order_id'],
        'entry_provider_order_id':parent['entry_provider_order_id'],
        'entry_filled_qty':format(filled.normalize(),'f'),'account_owned_qty':format(held.normalize(),'f'),
        'entry_price':format(Decimal(parent['entry_price']).normalize(),'f'),
        'entry_timestamp':parse_instant(parent['entry_timestamp']).isoformat(),
        'quote_currency':'USDC','net_realized_pnl_usd':None}}


def entry_receipt_row(rows: list[dict[str, Any]], effect: str) -> dict[str, Any]:
    candidates=[r for r in rows if r.get('receipt_type')=='outcome' and r.get('effect_id')==effect
                and r.get('strategy_receipt') is not None]
    if not candidates:
        raise ValueError('owned_entry_receipt_missing')
    return candidates[-1]


def recorded_entry_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any],
                                   broker: dict[str, Any], observation: dict[str, Any], *,
                                   mode: str, owner_id: str) -> dict[str, Any]:
    try:
        row=entry_receipt_row(rows,ownership['entry_effect_id'])
        receipt=row['strategy_receipt']['receipt']
        historical={**ownership,'entry_filled_qty':receipt['entry_filled_qty'],
                    'owned_qty':receipt['account_owned_qty']}
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise ValueError('owned_entry_receipt_missing') from error
    return _recorded_proof_from_rows(rows,historical,broker,observation,mode=mode,owner_id=owner_id,
                                    reader=entry_fill_proof_from_rows,effect_key='entry_effect_id')
