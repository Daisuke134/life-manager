#!/usr/bin/env python3
"""Evaluate one isolated Gig strategy experiment from fresh funnel evidence.

The historical B4 prompt created many simultaneous mutations, then compared cumulative
counts.  That cannot identify which mutation caused an outcome.  This evaluator makes
the safe boundary executable:

* overlapping active experiments are quarantined, never guessed into keep/revert;
* only code-owned strategy fields can be reverted automatically;
* the post-mutation cohort must contain enough fresh applications;
* reply/win/paid rates, not ever-growing cumulative counts, decide the verdict;
* every terminal verdict is atomically persisted and appended once to an audit ledger.

Mode "ab" runs both arms concurrently instead of before/after: each request is
assigned by a hash of (experiment id, request id), the parent prices and records the
arm, and assess_ab() compares net yen per application from official CFO receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_STATE = Path.home() / "gig"
DEFAULT_COCONALA_STATE = Path.home() / ".local/state/life-manager/coconala"
DEFAULT_EXPERIMENTS = Path(__file__).resolve().parents[1] / "config" / "experiments.json"
AB_POLICIES = {"budget_lower_bound"}
AB_RULES = (
    "min_applications_per_arm", "min_cohort_days", "max_applications_per_arm",
    "contract_margin",
)
ARMS = ("A", "B")
DAY_SECONDS = 86_400
REVERSIBLE_ROOTS = {
    "proposal_playbook",
    "proposal_templates",
    "price_defaults",
    "listing_categories",
    "priority_categories",
}
RATE_METRICS = {"replied", "won", "paid"}
TERMINAL = {"kept", "reverted", "quarantined"}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def assign_arm(experiment_id: str, request_id: str) -> str:
    """Deterministic ~50/50 split: the parity of sha256(experiment:request)."""
    digest = hashlib.sha256(f"{experiment_id}:{request_id}".encode("utf-8")).digest()
    return "B" if digest[-1] & 1 else "A"


def _experiment_id(spec: dict[str, Any]) -> str | None:
    value = str(spec.get("id") or "").strip()
    if not value or len(value) > 96 or any(
        not (ch.isalnum() or ch in "._-") for ch in value
    ):
        return None
    return value


def _active_due(experiment: Any, pass_count: int) -> bool:
    return (
        isinstance(experiment, dict)
        and experiment.get("status") == "active"
        and isinstance(experiment.get("eval_by_pass"), int)
        and experiment["eval_by_pass"] <= pass_count
    )


def _set_path(root: dict[str, Any], dotted: str, value: Any) -> bool:
    parts = [part for part in str(dotted or "").split(".") if part]
    if not parts or parts[0] not in REVERSIBLE_ROOTS:
        return False
    cursor: dict[str, Any] = root
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            return False
        cursor = child
    cursor[parts[-1]] = deepcopy(value)
    return True


def _get_path(root: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    parts = [part for part in str(dotted or "").split(".") if part]
    if not parts or parts[0] not in REVERSIBLE_ROOTS:
        return False, None
    cursor: Any = root
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return False, None
        cursor = cursor[part]
    return True, deepcopy(cursor)


def start(strategy: dict[str, Any], latest_funnel: dict[str, Any] | None,
          spec: dict[str, Any], *, category_order: list[str],
          now: int | None = None) -> dict[str, Any]:
    """Start exactly one reversible experiment and freeze its category epoch."""
    now = int(time.time()) if now is None else int(now)
    updated = deepcopy(strategy) if isinstance(strategy, dict) else {}
    experiments = updated.get("experiments")
    experiments = experiments if isinstance(experiments, list) else []
    if any(isinstance(row, dict) and row.get("status") == "active"
           for row in experiments):
        return {"ok": False, "reason": "active_experiment_exists", "strategy": updated}
    if not isinstance(spec, dict):
        return {"ok": False, "reason": "spec_invalid", "strategy": updated}
    experiment_id = _experiment_id(spec)
    if experiment_id is None:
        return {"ok": False, "reason": "experiment_id_invalid", "strategy": updated}
    if any(isinstance(row, dict) and row.get("id") == experiment_id
           for row in experiments):
        return {"ok": False, "reason": "experiment_id_duplicate", "strategy": updated}
    field = str(spec.get("field_changed") or "")
    found, old_value = _get_path(updated, field)
    if not found:
        return {"ok": False, "reason": "field_not_code_reversible", "strategy": updated}
    if "new_value" not in spec or spec.get("new_value") == old_value:
        return {"ok": False, "reason": "new_value_missing_or_unchanged", "strategy": updated}
    metric = str(spec.get("target_metric") or "")
    if metric not in RATE_METRICS:
        return {"ok": False, "reason": "target_metric_invalid", "strategy": updated}
    parsed = urlsplit(str(spec.get("source_url") or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        return {"ok": False, "reason": "source_url_invalid", "strategy": updated}
    hypothesis = str(spec.get("hypothesis") or "").strip()
    if not hypothesis:
        return {"ok": False, "reason": "hypothesis_missing", "strategy": updated}
    latest = latest_funnel if isinstance(latest_funnel, dict) else {}
    required = ("ts", "pass_id", "applied", "replied", "won", "paid")
    if any(key not in latest for key in required):
        return {"ok": False, "reason": "fresh_funnel_required", "strategy": updated}
    frozen_order = list(dict.fromkeys(
        str(value).strip() for value in category_order if str(value).strip()
    ))
    if not frozen_order:
        return {"ok": False, "reason": "category_order_required", "strategy": updated}
    if not _set_path(updated, field, spec["new_value"]):
        return {"ok": False, "reason": "field_not_code_reversible", "strategy": updated}
    pass_count = int(updated.get("pass_count") or 0)
    cadence = max(1, int(updated.get("improve_cadence_passes") or 4))
    experiment = {
        "id": experiment_id,
        "ts": now,
        "mode": "isolated",
        "hypothesis": hypothesis,
        "source_url": str(spec["source_url"]),
        "field_changed": field,
        "old_value": old_value,
        "new_value": deepcopy(spec["new_value"]),
        "target_metric": metric,
        "baseline": {key: deepcopy(latest[key]) for key in required},
        "eval_by_pass": pass_count + 2 * cadence,
        "min_post_applications": max(
            8, int(spec.get("min_post_applications") or 8)
        ),
        "frozen_category_order": frozen_order,
        "status": "active",
    }
    experiments.append(experiment)
    updated["experiments"] = experiments
    updated["last_experiment_started_at"] = now
    return {
        "ok": True,
        "reason": "started",
        "strategy": updated,
        "experiment": experiment,
    }


def _evaluation(experiment: dict[str, Any], *, status: str, reason: str,
                now: int, **details: Any) -> dict[str, Any]:
    updated = deepcopy(experiment)
    updated["status"] = status
    updated["evaluated_at"] = now
    updated["evaluation"] = {
        "reason": reason,
        "evaluated_at": now,
        **details,
    }
    return updated


def assess(strategy: dict[str, Any], latest_funnel: dict[str, Any] | None, *,
           now: int | None = None) -> dict[str, Any]:
    """Return an updated strategy and appendable evaluation events without I/O."""
    now = int(time.time()) if now is None else int(now)
    updated = deepcopy(strategy) if isinstance(strategy, dict) else {}
    experiments = updated.get("experiments")
    experiments = experiments if isinstance(experiments, list) else []
    pass_count = int(updated.get("pass_count") or 0)
    active_indexes = [
        index for index, row in enumerate(experiments)
        if isinstance(row, dict) and row.get("status") == "active"
    ]
    # A/B experiments have no pass deadline; assess_ab() owns them.  They still
    # count toward active_count, so an overlap quarantines the legacy one too.
    due_indexes = [
        index for index in active_indexes
        if experiments[index].get("mode") != "ab"
        and (not isinstance(experiments[index].get("eval_by_pass"), int)
             or _active_due(experiments[index], pass_count))
    ]
    active_count = len(active_indexes)
    summary = {
        "evaluated": 0,
        "kept": 0,
        "reverted": 0,
        "quarantined": 0,
        "deferred": 0,
    }
    events: list[dict[str, Any]] = []

    for index in due_indexes:
        experiment = experiments[index]
        assert isinstance(experiment, dict)
        terminal: dict[str, Any] | None = None

        if not isinstance(experiment.get("eval_by_pass"), int):
            terminal = _evaluation(
                experiment, status="quarantined",
                reason="evaluation_deadline_missing", now=now,
            )
        elif active_count > 1:
            terminal = _evaluation(
                experiment, status="quarantined",
                reason="overlapping_active_experiments", now=now,
                active_experiment_count=active_count,
            )
        else:
            field = str(experiment.get("field_changed") or "")
            reversible = (
                field.split(".", 1)[0] in REVERSIBLE_ROOTS
                and experiment.get("old_value") is not None
                and experiment.get("new_value") is not None
            )
            if not reversible:
                terminal = _evaluation(
                    experiment, status="quarantined",
                    reason="mutation_not_code_reversible", now=now,
                    field_changed=field,
                )
            else:
                baseline = experiment.get("baseline")
                baseline = baseline if isinstance(baseline, dict) else {}
                metric = str(experiment.get("target_metric") or "")
                baseline_applied = _number(baseline.get("applied"))
                baseline_target = _number(baseline.get(metric))
                latest = latest_funnel if isinstance(latest_funnel, dict) else {}
                latest_applied = _number(latest.get("applied"))
                latest_target = _number(latest.get(metric))
                fresh = (
                    _number(latest.get("ts")) is not None
                    and _number(experiment.get("ts")) is not None
                    and float(latest["ts"]) > float(experiment["ts"])
                    and str(latest.get("pass_id") or "")
                    != str(baseline.get("pass_id") or "")
                )
                if not fresh:
                    experiments[index] = _evaluation(
                        experiment, status="active",
                        reason="fresh_funnel_required", now=now,
                    )
                    summary["deferred"] += 1
                    continue
                if (
                    metric not in RATE_METRICS
                    or baseline_applied is None
                    or baseline_target is None
                    or latest_applied is None
                    or latest_target is None
                    or baseline_applied <= 0
                    or latest_applied < baseline_applied
                    or latest_target < baseline_target
                ):
                    terminal = _evaluation(
                        experiment, status="quarantined",
                        reason="metric_contract_invalid", now=now,
                        target_metric=metric,
                    )
                else:
                    post_applications = int(latest_applied - baseline_applied)
                    minimum = max(1, int(experiment.get("min_post_applications") or 8))
                    if post_applications < minimum:
                        experiments[index] = _evaluation(
                            experiment, status="active",
                            reason="insufficient_post_applications", now=now,
                            post_applications=post_applications,
                            required_post_applications=minimum,
                        )
                        summary["deferred"] += 1
                        continue
                    baseline_rate = baseline_target / baseline_applied
                    observed_rate = (latest_target - baseline_target) / post_applications
                    details = {
                        "target_metric": metric,
                        "baseline_rate": round(baseline_rate, 12),
                        "observed_rate": round(observed_rate, 12),
                        "post_applications": post_applications,
                        "baseline_pass_id": baseline.get("pass_id"),
                        "observed_pass_id": latest.get("pass_id"),
                    }
                    if observed_rate > baseline_rate:
                        terminal = _evaluation(
                            experiment, status="kept",
                            reason="metric_improved", now=now, **details,
                        )
                    elif _set_path(updated, field, experiment.get("old_value")):
                        terminal = _evaluation(
                            experiment, status="reverted",
                            reason="metric_did_not_improve", now=now, **details,
                        )
                    else:
                        terminal = _evaluation(
                            experiment, status="quarantined",
                            reason="revert_path_unavailable", now=now, **details,
                        )

        assert terminal is not None
        experiments[index] = terminal
        status = str(terminal["status"])
        summary["evaluated"] += 1
        summary[status] += 1
        events.append({
            "ts": now,
            "experiment_id": terminal.get("id"),
            "status": status,
            "field_changed": terminal.get("field_changed"),
            "target_metric": terminal.get("target_metric"),
            "evaluation": terminal.get("evaluation"),
        })

    updated["experiments"] = experiments
    if summary["evaluated"] or summary["deferred"]:
        updated["last_experiment_evaluation_at"] = now
    return {"strategy": updated, "events": events, "summary": summary}


def start_ab(strategy: dict[str, Any], spec: dict[str, Any], *,
             now: int | None = None) -> dict[str, Any]:
    """Start one concurrent A/B experiment; the arm policy itself lives in code."""
    now = int(time.time()) if now is None else int(now)
    updated = deepcopy(strategy) if isinstance(strategy, dict) else {}
    experiments = updated.get("experiments")
    experiments = experiments if isinstance(experiments, list) else []
    if any(isinstance(row, dict) and row.get("status") == "active"
           for row in experiments):
        return {"ok": False, "reason": "active_experiment_exists", "strategy": updated}
    if (not isinstance(spec, dict) or spec.get("mode") != "ab"
            or spec.get("policy") not in AB_POLICIES):
        return {"ok": False, "reason": "spec_invalid", "strategy": updated}
    experiment_id = _experiment_id(spec)
    if experiment_id is None:
        return {"ok": False, "reason": "experiment_id_invalid", "strategy": updated}
    if any(isinstance(row, dict) and row.get("id") == experiment_id
           for row in experiments):
        return {"ok": False, "reason": "experiment_id_duplicate", "strategy": updated}
    parsed = urlsplit(str(spec.get("source_url") or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        return {"ok": False, "reason": "source_url_invalid", "strategy": updated}
    hypothesis = str(spec.get("hypothesis") or "").strip()
    if not hypothesis:
        return {"ok": False, "reason": "hypothesis_missing", "strategy": updated}
    guardrail = spec.get("guardrail") if isinstance(spec.get("guardrail"), dict) else {}
    margin = _number(guardrail.get("send_failure_margin"))
    rules = {key: spec.get(key) for key in AB_RULES}
    if (
        any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in rules.values())
        or margin is None or not 0 < margin < 1
        or isinstance(guardrail.get("min_attempts_per_arm"), bool)
        or not isinstance(guardrail.get("min_attempts_per_arm"), int)
        or guardrail["min_attempts_per_arm"] < 1
    ):
        return {"ok": False, "reason": "decision_rule_invalid", "strategy": updated}
    experiment = {
        "id": experiment_id,
        "ts": now,
        "mode": "ab",
        "policy": spec["policy"],
        "hypothesis": hypothesis,
        "source_url": str(spec["source_url"]),
        "primary_metric": "net_jpy_per_application",
        "secondary_metric": "contracts",
        **rules,
        "guardrail": {
            "send_failure_margin": margin,
            "min_attempts_per_arm": guardrail["min_attempts_per_arm"],
        },
        "status": "active",
    }
    experiments.append(experiment)
    updated["experiments"] = experiments
    updated["last_experiment_started_at"] = now
    return {"ok": True, "reason": "started", "strategy": updated, "experiment": experiment}


def _epoch(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _title(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ab_metrics(experiment: dict[str, Any], *, applied_rows: list[Any],
                readback: Any, revenue_titles: dict[str, Any], attempts: list[Any],
                outcomes: list[Any]) -> dict[str, Any]:
    """Join CFO receipts -> revenue-history title -> applied row -> recorded arm.

    revenue_titles is the talkroom -> title map the CFO readback derives from the
    same revenue history pages with revenue_collector.parse_revenue_text().
    """
    experiment_id = experiment.get("id")
    started = float(experiment.get("ts") or 0)
    arms = {arm: {"applications": 0, "contracts": 0, "net_jpy": 0,
                  "net_jpy_per_application": None, "attempts": 0, "send_failures": 0}
            for arm in ARMS}
    cohort: dict[str, str] = {}
    by_title: dict[str, list[tuple[float, str, Any, Any]]] = defaultdict(list)
    for row in applied_rows:
        if not isinstance(row, dict):
            continue
        request_id = str(row.get("requestId") or row.get("request_id") or "")
        tag = (row.get("experiment_id"), row.get("experiment_arm"))
        if request_id and tag[0] == experiment_id and tag[1] in arms:
            cohort[request_id] = tag[1]
        title = _title(row.get("title"))
        if title:
            by_title[title].append((_number(row.get("ts")) or 0.0, request_id, *tag))
    for arm in cohort.values():
        arms[arm]["applications"] += 1

    contracts: dict[str, set[str]] = {arm: set() for arm in ARMS}
    for row in outcomes:
        request_id = str(row.get("request_id") or "") if isinstance(row, dict) else ""
        if request_id in cohort and row.get("status") == "we_won":
            contracts[cohort[request_id]].add(request_id)

    receipt_map = readback.get("receipt_map") if isinstance(readback, dict) else None
    records = receipt_map.get("records") if isinstance(receipt_map, dict) else None
    unattributed: dict[str, int] | None = None
    # A complete receipt map plus the title map, or revenue stays unknown (None).
    if (
        isinstance(receipt_map, dict) and receipt_map.get("complete") is True
        and isinstance(records, list) and revenue_titles
        and all(isinstance(record, dict) and type(record.get("net_amount_minor")) is int
                for record in records)
    ):
        unattributed = {"count": 0, "jpy": 0}
        room_titles = {str(room): _title(title) for room, title in revenue_titles.items()}
        for record in records:
            occurred = _epoch(record.get("occurred_at"))
            if occurred is not None and occurred < started:
                continue
            room = str(record.get("work_external_id") or "").removeprefix("talkroom-")
            matches = [
                match for match in by_title.get(room_titles.get(room, ""), [])
                if occurred is not None and match[0] <= occurred
            ]
            tags = {(match[2], match[3]) for match in matches}
            if len(tags) != 1:
                # No title, no application, or applications from different arms.
                unattributed["count"] += 1
                unattributed["jpy"] += record["net_amount_minor"]
                continue
            (tag_id, arm), = tags
            if tag_id != experiment_id or arm not in arms:
                continue  # sale from an application made outside this experiment
            arms[arm]["net_jpy"] += record["net_amount_minor"]
            contracts[arm].add(max(matches, key=lambda match: match[0])[1])
    for arm, values in arms.items():
        values["contracts"] = len(contracts[arm])
        if unattributed is None:
            values["net_jpy"] = None  # unknown, never zero
        elif values["applications"]:
            values["net_jpy_per_application"] = round(
                values["net_jpy"] / values["applications"], 2
            )

    latest: dict[str, tuple[str, str]] = {}
    for row in attempts:
        if (isinstance(row, dict) and row.get("experiment_id") == experiment_id
                and row.get("experiment_arm") in arms
                and row.get("outcome") in {"confirmed", "failed"}):
            latest[str(row.get("request_id") or "")] = (row["experiment_arm"], row["outcome"])
    for arm, outcome in latest.values():
        arms[arm]["attempts"] += 1
        arms[arm]["send_failures"] += outcome == "failed"
    return {"arms": arms, "unattributed": unattributed}


def _ab_verdict(experiment: dict[str, Any], metrics: dict[str, Any],
                now: int) -> tuple[str | None, str]:
    a, b = metrics["arms"]["A"], metrics["arms"]["B"]
    guardrail = experiment["guardrail"]
    if min(a["attempts"], b["attempts"]) >= guardrail["min_attempts_per_arm"]:
        a_rate = a["send_failures"] / a["attempts"]
        b_rate = b["send_failures"] / b["attempts"]
        if b_rate > a_rate + guardrail["send_failure_margin"]:
            return "reverted", "guardrail_send_failure"
    if metrics["unattributed"] is None:
        return None, "revenue_readback_unavailable"
    if now - int(experiment["ts"]) < experiment["min_cohort_days"] * DAY_SECONDS:
        return None, "cohort_too_young"
    applications = min(a["applications"], b["applications"])
    if applications < experiment["min_applications_per_arm"]:
        return None, "insufficient_applications"
    margin = experiment["contract_margin"]
    if (b["contracts"] >= a["contracts"] + margin
            and b["net_jpy_per_application"] >= a["net_jpy_per_application"]):
        return "kept", "b_won_contracts_and_yen_per_application"
    if b["contracts"] + margin <= a["contracts"]:
        return "reverted", "a_won_contracts"
    if applications >= experiment["max_applications_per_arm"]:
        return "reverted", "sample_cap_without_decision"
    return None, "no_decision_yet"


def assess_ab(strategy: dict[str, Any], *, applied_rows: list[Any], readback: Any,
              revenue_titles: dict[str, Any], attempts: list[Any], outcomes: list[Any],
              now: int | None = None) -> dict[str, Any]:
    """Evaluate the one active A/B experiment without I/O."""
    now = int(time.time()) if now is None else int(now)
    updated = deepcopy(strategy) if isinstance(strategy, dict) else {}
    experiments = updated.get("experiments")
    experiments = experiments if isinstance(experiments, list) else []
    active = [index for index, row in enumerate(experiments)
              if isinstance(row, dict) and row.get("status") == "active"]
    ab = [index for index in active if experiments[index].get("mode") == "ab"]
    if not ab:
        return {"strategy": updated, "events": [],
                "summary": {"experiment_id": None, "reason": "no_active_ab_experiment"}}
    events: list[dict[str, Any]] = []
    if len(active) > 1:
        for index in ab:
            experiments[index] = _evaluation(
                experiments[index], status="quarantined",
                reason="overlapping_active_experiments", now=now,
                active_experiment_count=len(active),
            )
        terminal = [experiments[index] for index in ab]
        summary = {"experiment_id": terminal[0].get("id"), "status": "quarantined",
                   "reason": "overlapping_active_experiments"}
    else:
        experiment = experiments[ab[0]]
        metrics = _ab_metrics(
            experiment, applied_rows=applied_rows, readback=readback,
            revenue_titles=revenue_titles, attempts=attempts, outcomes=outcomes,
        )
        verdict, reason = _ab_verdict(experiment, metrics, now)
        experiments[ab[0]] = _evaluation(
            experiment, status=verdict or "active", reason=reason, now=now, **metrics,
        )
        if verdict == "kept":
            updated["adopted_bid_policy"] = experiment["policy"]
        terminal = [experiments[ab[0]]] if verdict else []
        summary = {"experiment_id": experiment.get("id"), "status": verdict or "active",
                   "reason": reason, **metrics}
    for row in terminal:
        events.append({
            "ts": now, "experiment_id": row.get("id"), "status": row["status"],
            "mode": "ab", "policy": row.get("policy"), "evaluation": row.get("evaluation"),
        })
    updated["experiments"] = experiments
    updated["last_experiment_evaluation_at"] = now
    return {"strategy": updated, "events": events, "summary": summary}


def _jsonl(path: Path | None) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path else []
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _json(path: Path | None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path else None
    except (OSError, json.JSONDecodeError):
        return None


def _latest_jsonl(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def evaluate_files(*, strategy_path: Path, funnel_path: Path, events_path: Path,
                   now: int | None = None, applied_path: Path | None = None,
                   readback_path: Path | None = None, titles_path: Path | None = None,
                   attempts_path: Path | None = None, outcomes_path: Path | None = None,
                   experiments_path: Path | None = None) -> dict[str, Any]:
    try:
        strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        strategy = {}
    result = assess(strategy, _latest_jsonl(funnel_path), now=now)
    summary: dict[str, Any] = dict(result["summary"])
    events = list(result["events"])
    strategy = result["strategy"]
    changed = bool(summary["evaluated"] or summary["deferred"])
    if applied_path is not None:
        titles = _json(titles_path)
        titles = titles.get("titles") if isinstance(titles, dict) else None
        ab = assess_ab(
            strategy, applied_rows=_jsonl(applied_path), readback=_json(readback_path),
            revenue_titles=titles if isinstance(titles, dict) else {},
            attempts=_jsonl(attempts_path), outcomes=_jsonl(outcomes_path), now=now,
        )
        strategy, summary["ab"] = ab["strategy"], ab["summary"]
        events.extend(ab["events"])
        changed = changed or ab["summary"]["experiment_id"] is not None
    summary["started"] = None
    queue = _json(experiments_path)
    queue = queue.get("queue") if isinstance(queue, dict) else None
    known = {row.get("id") for row in strategy.get("experiments") or [] if isinstance(row, dict)}
    pending = [spec for spec in (queue if isinstance(queue, list) else [])
               if isinstance(spec, dict) and spec.get("id") not in known]
    if pending:
        started = start_ab(strategy, pending[0], now=now)
        summary["start_reason"] = started["reason"]
        if started["ok"]:
            strategy, experiment = started["strategy"], started["experiment"]
            summary["started"], changed = experiment["id"], True
            events.append({
                "ts": experiment["ts"], "experiment_id": experiment["id"], "status": "started",
                "mode": "ab", "policy": experiment["policy"],
                "source_url": experiment["source_url"],
            })
    if changed:
        # ponytail: last-writer-wins with passprep's strategy.json write, as before;
        # add a shared flock if a lost start/verdict is ever observed.
        _atomic_json(strategy_path, strategy)
    if events:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return summary


def start_files(*, strategy_path: Path, funnel_path: Path, events_path: Path,
                decisions_path: Path, spec: dict[str, Any],
                now: int | None = None) -> dict[str, Any]:
    try:
        strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        strategy = {}
    decision = _latest_jsonl(decisions_path) or {}
    order = decision.get("category_order")
    if not isinstance(order, list):
        order = [
            row.get("arm") for row in (decision.get("arms") or [])
            if isinstance(row, dict) and row.get("arm")
        ]
    if not order:
        order = strategy.get("priority_categories") or []
    result = start(
        strategy, _latest_jsonl(funnel_path), spec,
        category_order=order, now=now,
    )
    if not result["ok"]:
        return {"ok": False, "reason": result["reason"]}
    _atomic_json(strategy_path, result["strategy"])
    event = {
        "ts": result["experiment"]["ts"],
        "experiment_id": result["experiment"]["id"],
        "status": "started",
        "field_changed": result["experiment"]["field_changed"],
        "target_metric": result["experiment"]["target_metric"],
        "source_url": result["experiment"]["source_url"],
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"ok": True, "reason": "started", "experiment_id": event["experiment_id"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=("evaluate", "start"),
                        default="evaluate")
    parser.add_argument("--strategy", type=Path, default=DEFAULT_STATE / "strategy.json")
    parser.add_argument("--funnel", type=Path, default=DEFAULT_STATE / "gig-funnel.jsonl")
    parser.add_argument(
        "--events", type=Path,
        default=DEFAULT_STATE / "experiment-evaluations.jsonl",
    )
    parser.add_argument(
        "--decisions", type=Path,
        default=DEFAULT_STATE / "category-decisions.jsonl",
    )
    parser.add_argument("--spec-json")
    parser.add_argument("--applied", type=Path, default=DEFAULT_STATE / "applied.jsonl")
    parser.add_argument(
        "--readback", type=Path,
        default=DEFAULT_COCONALA_STATE / "cfo-financial-readback.json",
    )
    parser.add_argument(
        "--revenue-titles", type=Path,
        default=DEFAULT_COCONALA_STATE / "cfo-financial-readback-titles.json",
    )
    parser.add_argument(
        "--attempts", type=Path, default=DEFAULT_STATE / "experiment-attempts.jsonl",
    )
    parser.add_argument(
        "--outcomes", type=Path, default=DEFAULT_STATE / "applied-outcomes.jsonl",
    )
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    args = parser.parse_args(argv)
    if args.command == "start":
        try:
            spec = json.loads(args.spec_json or "")
        except json.JSONDecodeError:
            spec = {}
        result = start_files(
            strategy_path=args.strategy,
            funnel_path=args.funnel,
            events_path=args.events,
            decisions_path=args.decisions,
            spec=spec,
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    summary = evaluate_files(
        strategy_path=args.strategy,
        funnel_path=args.funnel,
        events_path=args.events,
        applied_path=args.applied,
        readback_path=args.readback,
        titles_path=args.revenue_titles,
        attempts_path=args.attempts,
        outcomes_path=args.outcomes,
        experiments_path=args.experiments,
    )
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
