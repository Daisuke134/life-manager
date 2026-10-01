#!/usr/bin/env python3
"""Thin Coconala boundary for the shared marketplace Paid kernel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent


def _load_shared(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("coconala_paid_handoff_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PAID_HANDOFF = _load_shared(
    "coconala_shared_paid_handoff",
    HERE.parents[2] / "_shared/marketplace-core/scripts/paid_handoff.py",
)


class CoconalaPaidInventoryWait(RuntimeError):
    def __init__(self, reason: str, remaining_work: list[str]):
        super().__init__(reason)
        self.paid_wait_reason = reason
        self.paid_remaining_work = remaining_work


class CoconalaPaidAdapter:
    def __init__(
        self,
        *,
        account_id: str,
        inventory_reader: Callable[[], list[dict[str, Any]]],
        refresh_reader: Callable[[dict[str, Any]], Mapping[str, Any]],
        context_reader: Callable[[dict[str, Any]], Mapping[str, Any]],
        effect_runner: Callable[[dict[str, Any]], None],
        readback_reader: Callable[[dict[str, Any]], Mapping[str, Any]],
    ):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("coconala_account_id_invalid")
        self.account_id = account_id.strip()
        self.inventory_reader = inventory_reader
        self.refresh_reader = refresh_reader
        self.context_reader = context_reader
        self.effect_runner = effect_runner
        self.readback_reader = readback_reader
        self._items: dict[str, dict[str, Any]] = {}

    def _normalize(self, source: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "work_id": source.get("talkroom_id"),
            # The orders-only inventory is intentionally shallow.  It has no
            # buyer-message digest until the targeted readback, so use the
            # official snapshot timestamp only for the pre-targeted identity.
            # ``observe_one`` replaces it with buyer_feedback_sha256 when the
            # talkroom evidence is available.
            "latest_event_id": source.get("buyer_feedback_sha256") or source.get("snapshot_captured_at"),
            "provider_state": source.get("talkroom_state") or source.get("transaction_state") or source.get("status") or "unknown",
            "observed_at": source.get("talkroom_observed_at") or source.get("snapshot_captured_at"),
        }
        if not all(isinstance(value, str) and value.strip() for value in required.values()):
            raise RuntimeError("coconala_paid_observation_invalid")
        return {
            "provider": "coconala", "account_id": self.account_id,
            **{key: value.strip() for key, value in required.items()},
        }

    def observe_active(self) -> list[dict[str, Any]]:
        sources = self.inventory_reader()
        if not isinstance(sources, list):
            raise RuntimeError("coconala_paid_inventory_unavailable")
        items: dict[str, dict[str, Any]] = {}
        rows = []
        for source in sources:
            if not isinstance(source, Mapping):
                raise RuntimeError("coconala_paid_inventory_unavailable")
            row = self._normalize(source)
            if row["work_id"] in items:
                raise RuntimeError("coconala_paid_inventory_duplicate")
            items[row["work_id"]] = dict(source)
            rows.append(row)
        self._items = items
        return rows

    def _item(self, work_id: str) -> dict[str, Any]:
        if work_id not in self._items:
            self.observe_active()
        try:
            return dict(self._items[work_id])
        except KeyError:
            raise RuntimeError("coconala_paid_work_unavailable") from None

    def observe_one(self, work_id: str) -> dict[str, Any]:
        refreshed = self.refresh_reader(self._item(work_id))
        if not isinstance(refreshed, Mapping):
            raise RuntimeError("coconala_paid_work_unavailable")
        row = self._normalize(refreshed)
        if row["work_id"] != work_id:
            raise RuntimeError("coconala_paid_work_identity_changed")
        self._items[work_id] = dict(refreshed)
        return row

    def context(self, work_id: str) -> dict[str, Any]:
        value = self.context_reader(self._item(work_id))
        if not isinstance(value, Mapping):
            raise RuntimeError("coconala_paid_context_unavailable")
        return dict(value)

    def paid_handoff(self, work_id: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        """Map Coconala's official order readback to the shared Paid boundary.

        Coconala does not expose a separate funding object in the received-order
        snapshot.  The provider's structured order card, active transaction state,
        and targeted talkroom evidence together are the funding readback.  The
        deterministic ``order:<contract_id>`` reference preserves that mapping
        without pretending it is a second provider receipt.
        """
        if not isinstance(context, Mapping):
            raise RuntimeError("coconala_paid_handoff_unavailable")
        source = self._item(work_id)
        facts = dict(source)
        # Official refreshed fields win over derived preparation context.  Context
        # may add local, hash-bound scope/requirements that the targeted snapshot
        # does not carry, but it cannot change the provider's funding facts.
        for key, value in context.items():
            if key not in facts or facts[key] in (None, ""):
                facts[key] = value

        room = facts.get("talkroom_id")
        contract_id = facts.get("contract_id")
        state = facts.get("talkroom_state") or facts.get("transaction_state")
        price_source = facts.get("price_source")
        price = facts.get("price_jpy")
        observed_at = facts.get("talkroom_observed_at") or facts.get("observed_at")
        terms_sha256 = facts.get("talkroom_evidence_sha256")
        scope_sha256 = facts.get("scope_sha256") or facts.get("buyer_feedback_sha256")
        artifact_requirement_sha256 = (
            facts.get("artifact_requirement_sha256") or facts.get("requirements_sha256")
        )
        if (
            not isinstance(room, str) or room.strip() != work_id.strip()
            or not isinstance(contract_id, str) or not contract_id.strip()
            or state not in {"取引中", "納品確認待ち"}
            or not isinstance(price_source, str) or not price_source.startswith("structured")
            or type(price) is not int or price < 1
            or not isinstance(observed_at, str) or not observed_at.strip()
            or not isinstance(terms_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", terms_sha256)
            or not isinstance(scope_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", scope_sha256)
            or not isinstance(artifact_requirement_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", artifact_requirement_sha256)
        ):
            raise RuntimeError("coconala_paid_handoff_unavailable")

        contract_id = contract_id.strip()
        application_id = facts.get("application_external_id") or facts.get("request_id")
        if not isinstance(application_id, str) or not application_id.strip():
            application_id = f"direct-order:{contract_id}"
        funding_id = facts.get("funding_external_id")
        if not isinstance(funding_id, str) or not funding_id.strip():
            funding_id = f"order:{contract_id}"
        try:
            return _PAID_HANDOFF.build_paid_handoff(
                platform="coconala",
                application_external_id=application_id.strip(),
                work_external_id=work_id.strip(),
                contract_external_id=contract_id,
                funding_external_id=funding_id.strip(),
                thread_external_id=room.strip(),
                terms_sha256=terms_sha256,
                scope_sha256=scope_sha256,
                artifact_requirement_sha256=artifact_requirement_sha256,
                price_minor=price,
                currency="JPY",
                observed_at=observed_at.strip(),
            )
        except _PAID_HANDOFF.PaidHandoffMappingError as error:
            raise RuntimeError("coconala_paid_handoff_unavailable") from error

    @staticmethod
    def classify_observation_error(error: Exception) -> dict[str, Any] | None:
        """Classify only retryable Coconala observation boundaries."""
        if isinstance(error, CoconalaPaidInventoryWait):
            return {
                "reason": error.paid_wait_reason,
                "remaining_work": list(error.paid_remaining_work),
            }
        waits = {
            "coconala_paid_work_unavailable": (
                "provider_work_observation_unavailable",
                "retry the official Coconala work-item observation before any paid effect",
            ),
            "coconala_paid_context_unavailable": (
                "provider_context_observation_unavailable",
                "retry the official Coconala context observation before any paid effect",
            ),
            "coconala_paid_readback_unavailable": (
                "provider_readback_unavailable",
                "retry the official Coconala readback before any paid effect",
            ),
            "coconala_paid_runtime_unavailable": (
                "provider_runtime_unavailable",
                "restore the authenticated Coconala runtime and retry official observation",
            ),
        }
        value = waits.get(str(error).strip())
        if value is None:
            return None
        reason, remaining = value
        return {"reason": reason, "remaining_work": [remaining]}

    def mutate(self, intent: dict[str, Any]) -> None:
        self.effect_runner(intent)

    def readback(self, intent: dict[str, Any]) -> dict[str, Any]:
        value = self.readback_reader(intent)
        if not isinstance(value, Mapping):
            raise RuntimeError("coconala_paid_readback_unavailable")
        return dict(value)


class _CoconalaPaidBridge:
    """Translate the proven Coconala owner phases without owning their business logic."""

    def __init__(self, paid, args, root: Path):
        self.paid = paid
        self.args = args
        self.root = root
        self.prepared: dict[str, dict[str, Any]] = {}

    def inventory(self) -> list[dict[str, Any]]:
        try:
            observed = self.paid.observe_orders(self.args, self.args.evidence_dir / "orders")
        except self.paid.Failure as error:
            if (error.step == "orders_observation"
                    and "authenticated tab did not finish navigation" in error.detail):
                raise CoconalaPaidInventoryWait(
                    "provider_authentication_required",
                    ["restore the authenticated Coconala session and retry official inventory"],
                ) from error
            raise
        rows, _ = self.paid._unique_orders(observed)
        return rows

    def refresh(self, item: dict[str, Any]) -> Mapping[str, Any]:
        return self.paid._targeted(self.args, item, 0)

    def _paths(self, item: Mapping[str, Any]) -> tuple[Path, Path, Path]:
        room = self.paid._text(item.get("talkroom_id"))
        event = self.paid._text(item.get("buyer_feedback_sha256"))
        stem = f"{room}-{event}"
        return (self.root / "items" / f"{stem}.json",
                self.root / "prepared" / f"{stem}.json",
                self.root / "effects" / f"{stem}.json")

    def context(self, item: dict[str, Any]) -> Mapping[str, Any]:
        room = self.paid._text(item.get("talkroom_id"))
        reported = self.paid._reported_paid_row(self.args, item)
        if reported is not None:
            value = {**reported, "_paid_prepare_status": "no_effect"}
            self.prepared[room] = value
            return value
        if self.paid._paid_timed_retry_is_future(self.args, item):
            value = {"status": "pending", "reason": "timed_retry",
                     "remaining_work": ["resume this work item in a later wake"],
                     "_paid_prepare_status": "pending"}
            self.prepared[room] = value
            return value
        item_path, prepared_path, _ = self._paths(item)
        self.paid._write(item_path, item)
        process = self.paid._run_bounded(
            self.paid._prepare_command(self.args, item_path, prepared_path),
            env=self.paid._fresh_child_env(self.args, owner=f"paid-direct-{room}"),
            timeout=self.paid.FILE_PREPARE_TIMEOUT_SECONDS,
        )
        try:
            value = self.paid._load(prepared_path)
        except (OSError, json.JSONDecodeError):
            value = {"status": "failed", "failed_step": "remote_resume"}
        if process.returncode or value.get("status") == "failed":
            raise RuntimeError(self.paid._text(value.get("failed_step")) or "paid_prepare_failed")
        self.prepared[room] = {**value, "_bridge_prepared_path": str(prepared_path)}
        return self.prepared[room]

    def effect(self, intent: dict[str, Any]) -> None:
        payload = intent.get("payload") or {}
        prepared_path = Path(str(payload.get("prepared_path", ""))).resolve()
        expected = (self.root / "prepared").resolve()
        if prepared_path.parent != expected or not prepared_path.is_file():
            raise RuntimeError("coconala_paid_prepared_invalid")
        effect_path = (self.root / "effects" / f"{intent['effect_key']}.json").resolve()
        room = self.paid._text(intent.get("work_id"))
        process = self.paid._run_bounded(
            self.paid._effect_command(self.args, prepared_path, effect_path),
            env=self.paid._fresh_child_env(self.args, owner=f"paid-direct-{room}"),
        )
        if process.returncode:
            raise RuntimeError("coconala_paid_effect_failed")

    def readback(self, intent: dict[str, Any]) -> Mapping[str, Any]:
        path = self.root / "effects" / f"{intent['effect_key']}.json"
        try:
            value = self.paid._load(path)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {"verified": False, "authoritative_absent": True}
        item = value.get("item")
        if value.get("status") != "completed" or value.get("readback") != 1 or not isinstance(item, dict):
            return {"verified": False, "authoritative_absent": False}
        evidence = item.get("evidence_paths") or {}
        receipt_source = next((str(v) for v in evidence.values() if v), intent["effect_key"])
        return {
            "verified": True,
            "provider_receipt_id": hashlib.sha256(receipt_source.encode()).hexdigest(),
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


def _load_paid_direct():
    path = HERE / "paid_direct.py"
    spec = importlib.util.spec_from_file_location("coconala_paid_direct_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("coconala_paid_runtime_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _decision(row: Mapping[str, Any], *, allow_formal_delivery: bool = False) -> dict[str, Any]:
    context = row.get("context")
    if not isinstance(context, Mapping):
        raise RuntimeError("coconala_paid_context_unavailable")
    status = context.get("_paid_prepare_status")
    if status == "no_effect":
        classification = str(context.get("status") or "satisfied_noop")
        return {"action": "noop", "classification": classification}
    if status == "pending":
        remaining = context.get("remaining_work") or context.get("unresolved") or ["resume prepared work"]
        return {"action": "wait", "reason": str(context.get("reason") or context.get("status") or "pending"),
                "remaining_work": [str(value) for value in remaining if str(value).strip()]}
    if status != "prepared":
        raise RuntimeError("coconala_paid_prepare_invalid")
    mode = context.get("_paid_mode")
    if mode == "cancellation":
        action = "cancel"
    elif mode == "file" and context.get("delivery_action") == "formal":
        if not allow_formal_delivery:
            return {"action": "wait", "reason": "formal_delivery_disabled",
                    "remaining_work": ["retain prepared delivery until formal delivery is authorized"]}
        action = "formal_delivery"
    elif mode == "file":
        action = "submit"
    else:
        action = "answer"
    return {"action": action, "payload": {
        "prepared_path": str(context.get("_bridge_prepared_path")),
        "mode": str(mode or "answer"),
    }}


def build(argv: list[str]):
    paid = _load_paid_direct()
    bridge_parser = argparse.ArgumentParser(add_help=False)
    bridge_parser.add_argument("--account-id", default="coconala-primary")
    bridge_parser.add_argument("--bridge-root", type=Path)
    bridge_parser.add_argument("--allow-formal-delivery", action="store_true")
    bridge_args, paid_argv = bridge_parser.parse_known_args(argv)
    placeholder = str(Path(os.devnull))
    args = paid._parser().parse_args(["--output", placeholder, *paid_argv])
    for name in ("output", "evidence_dir", "projects_root", "collector", "run_with_cdp_lock",
                 "answer_browser", "formal_browser", "cancel_browser", "delivery_evidence_dir",
                 "cdp_lock_dir", "context_compiler", "dm_collector", "agent_runner",
                 "runner_schema", "artifact_schema", "decision_schema"):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    args.cdp_helper = args.cdp_helper.expanduser()
    args.lock_file = (args.lock_file.expanduser().resolve() if args.lock_file
                      else args.evidence_dir / ".paid-direct.lock")
    root = (bridge_args.bridge_root or args.evidence_dir / "shared-paid-bridge").expanduser().resolve()
    bridge = _CoconalaPaidBridge(paid, args, root)
    adapter = CoconalaPaidAdapter(
        account_id=bridge_args.account_id,
        inventory_reader=bridge.inventory,
        refresh_reader=bridge.refresh,
        context_reader=bridge.context,
        effect_runner=bridge.effect,
        readback_reader=bridge.readback,
    )
    def decide(row: Mapping[str, Any]) -> dict[str, Any]:
        return _decision(row, allow_formal_delivery=bridge_args.allow_formal_delivery)
    return adapter, decide


__all__ = ["CoconalaPaidAdapter", "build"]
