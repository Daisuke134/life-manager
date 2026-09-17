#!/usr/bin/env python3
"""Immutable Writer baseline/candidate experiments and promotion receipts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
DECISIONS = {"KEEP", "REVERT", "INCONCLUSIVE"}
REPLAY_CONTRACT_KEYS = {
    "model_provider", "model_version", "evaluator_version", "trials_per_case"
}
CANARY_CONTRACT_KEYS = {
    "platform", "price", "currency", "reader_job", "window_hours"
}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(_canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_immutable(path: Path, value: Any) -> None:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"immutable receipt is unreadable: {path.name}") from error
        if existing != value:
            raise ValueError(f"immutable receipt conflicts: {path.name}")
        return
    _atomic(path, value)


def _aware_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return value.isoformat()


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _require_hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise ValueError(f"{label} must be sha256")
    return value


def _numeric_map(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty metric map")
    result: dict[str, float] = {}
    for key, raw in value.items():
        if (
            not isinstance(key, str) or not key.strip()
            or not isinstance(raw, (int, float)) or isinstance(raw, bool)
        ):
            raise ValueError(f"{label} contains an invalid metric")
        result[key] = float(raw)
    return result


class ExperimentStore:
    """Content-addressed experiment evidence with deterministic safety boundaries."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _directory(self, experiment_id: str) -> Path:
        return self.root / "experiments" / _require_id(experiment_id, "experiment_id")

    def _manifest(self, experiment_id: str) -> dict[str, Any]:
        path = self._directory(experiment_id) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("experiment manifest is unavailable") from error
        if not isinstance(value, dict):
            raise ValueError("experiment manifest is malformed")
        return value

    def create(
        self,
        *,
        experiment_id: str,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        changed_field: str,
        held_out_cases: list[dict[str, Any]],
        replay_contract: dict[str, Any],
        canary_contract: dict[str, Any],
        created_at: datetime,
    ) -> dict[str, Any]:
        experiment_id = _require_id(experiment_id, "experiment_id")
        if not isinstance(baseline, dict) or not baseline or not isinstance(candidate, dict):
            raise ValueError("baseline and candidate strategies are required")
        if not isinstance(changed_field, str) or changed_field not in baseline:
            raise ValueError("changed_field must name a baseline field")
        changed = {
            key for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        if changed != {changed_field}:
            raise ValueError("candidate must change exactly the declared field")
        if set(replay_contract) != REPLAY_CONTRACT_KEYS:
            raise ValueError("replay contract is malformed")
        trials = replay_contract.get("trials_per_case")
        if not isinstance(trials, int) or isinstance(trials, bool) or trials < 3:
            raise ValueError("replay contract requires at least three trials per case")
        for key in ("model_provider", "model_version", "evaluator_version"):
            if not isinstance(replay_contract.get(key), str) or not replay_contract[key].strip():
                raise ValueError(f"replay contract {key} is required")
        if set(canary_contract) != CANARY_CONTRACT_KEYS:
            raise ValueError("canary contract is malformed")
        if (
            not isinstance(canary_contract.get("price"), (int, float))
            or isinstance(canary_contract.get("price"), bool)
            or float(canary_contract["price"]) < 0
            or not isinstance(canary_contract.get("window_hours"), int)
            or canary_contract["window_hours"] <= 0
        ):
            raise ValueError("canary price/window is invalid")
        for key in ("platform", "currency", "reader_job"):
            if not isinstance(canary_contract.get(key), str) or not canary_contract[key].strip():
                raise ValueError(f"canary contract {key} is required")
        if not isinstance(held_out_cases, list) or len(held_out_cases) < 2:
            raise ValueError("held-out cases require both language lanes")
        cases: list[dict[str, str]] = []
        seen: set[str] = set()
        languages: set[str] = set()
        for case in held_out_cases:
            if not isinstance(case, dict) or set(case) != {"case_id", "language", "input_sha256"}:
                raise ValueError("held-out case is malformed")
            case_id = _require_id(case["case_id"], "case_id")
            if case_id in seen or case["language"] not in {"ja", "en"}:
                raise ValueError("held-out cases must be unique JA/EN cases")
            seen.add(case_id)
            languages.add(case["language"])
            cases.append({
                "case_id": case_id,
                "language": case["language"],
                "input_sha256": _require_hex(case["input_sha256"], "input_sha256"),
            })
        if languages != {"ja", "en"}:
            raise ValueError("held-out cases require both language lanes")
        baseline_hash = _sha(baseline)
        candidate_hash = _sha(candidate)
        _write_immutable(self.root / "strategies" / f"{baseline_hash}.json", baseline)
        _write_immutable(self.root / "strategies" / f"{candidate_hash}.json", candidate)
        manifest = {
            "schema_version": 2,
            "experiment_id": experiment_id,
            "status": "REPLAYING",
            "created_at": _aware_iso(created_at),
            "baseline_strategy_sha256": baseline_hash,
            "candidate_strategy_sha256": candidate_hash,
            "changed_field": changed_field,
            "text_diff": {"before": baseline[changed_field], "after": candidate[changed_field]},
            "held_out_cases": cases,
            "replay_contract": dict(replay_contract),
            "canary_contract": dict(canary_contract),
        }
        _write_immutable(self._directory(experiment_id) / "manifest.json", manifest)
        return manifest

    def record_replay(self, experiment_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        expected = {
            "case_id", "trial", "randomized_order", "baseline_output_sha256",
            "candidate_output_sha256", "scores", "guardrails", "evaluator_version",
        }
        if not isinstance(receipt, dict) or set(receipt) != expected:
            raise ValueError("replay receipt is malformed")
        cases = {item["case_id"]: item for item in manifest["held_out_cases"]}
        case_id = receipt.get("case_id")
        trial = receipt.get("trial")
        if case_id not in cases or not isinstance(trial, int) or isinstance(trial, bool):
            raise ValueError("replay case/trial is invalid")
        if not 1 <= trial <= int(manifest["replay_contract"]["trials_per_case"]):
            raise ValueError("replay trial is outside the frozen contract")
        if receipt.get("randomized_order") not in {"baseline-first", "candidate-first"}:
            raise ValueError("replay order is invalid")
        if receipt.get("evaluator_version") != manifest["replay_contract"]["evaluator_version"]:
            raise ValueError("replay evaluator differs from the frozen contract")
        scores = receipt.get("scores")
        if not isinstance(scores, dict) or not scores:
            raise ValueError("replay scores are required")
        normalized_scores: dict[str, dict[str, float]] = {}
        for dimension, pair in scores.items():
            if not isinstance(dimension, str) or not isinstance(pair, dict) or set(pair) != {"baseline", "candidate"}:
                raise ValueError("replay score pair is malformed")
            normalized_scores[dimension] = _numeric_map(pair, "replay score")
        guardrails = receipt.get("guardrails")
        if not isinstance(guardrails, dict) or set(guardrails) != {"baseline", "candidate"}:
            raise ValueError("replay guardrails are malformed")
        if any(
            not isinstance(lane, dict) or set(lane) != {"safety", "citation"}
            or any(not isinstance(value, bool) for value in lane.values())
            for lane in guardrails.values()
        ):
            raise ValueError("replay guardrails require boolean safety and citation")
        value = {
            **receipt,
            "baseline_output_sha256": _require_hex(receipt["baseline_output_sha256"], "baseline output"),
            "candidate_output_sha256": _require_hex(receipt["candidate_output_sha256"], "candidate output"),
            "scores": normalized_scores,
            "receipt_id": f"{case_id}:{trial}",
        }
        _write_immutable(
            self._directory(experiment_id) / "replays" / f"{case_id}-{trial}.json",
            value,
        )
        return value

    def record_canary(self, experiment_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        if not isinstance(receipt, dict) or set(receipt) != {
            "closed", "contract", "baseline", "candidate", "receipt_ids"
        }:
            raise ValueError("canary receipt is malformed")
        if receipt["contract"] != manifest["canary_contract"]:
            raise ValueError("canary differs from the frozen matched contract")
        if not isinstance(receipt["closed"], bool):
            raise ValueError("canary window status is invalid")
        normalized = {"closed": receipt["closed"], "contract": dict(receipt["contract"])}
        for lane in ("baseline", "candidate"):
            cohort = receipt.get(lane)
            if not isinstance(cohort, dict) or set(cohort) != {"cohort_id", "sample_size", "metrics"}:
                raise ValueError("canary cohort is malformed")
            _require_id(cohort["cohort_id"], "cohort_id")
            if not isinstance(cohort["sample_size"], int) or isinstance(cohort["sample_size"], bool) or cohort["sample_size"] <= 0:
                raise ValueError("canary sample size is invalid")
            normalized[lane] = {
                "cohort_id": cohort["cohort_id"],
                "sample_size": cohort["sample_size"],
                "metrics": _numeric_map(cohort["metrics"], "canary metrics"),
            }
        ids = receipt.get("receipt_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(item, str) or not item for item in ids):
            raise ValueError("canary requires external measurement receipt IDs")
        normalized["receipt_ids"] = list(dict.fromkeys(ids))
        _write_immutable(self._directory(experiment_id) / "canary.json", normalized)
        return normalized

    def _replays(self, experiment_id: str) -> list[dict[str, Any]]:
        rows = []
        for path in sorted((self._directory(experiment_id) / "replays").glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("replay receipt is unreadable") from error
            rows.append(value)
        return rows

    def decide(
        self,
        experiment_id: str,
        *,
        interpreter: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        directory = self._directory(experiment_id)
        decision_path = directory / "decision.json"
        if decision_path.exists():
            return json.loads(decision_path.read_text(encoding="utf-8"))
        manifest = self._manifest(experiment_id)
        replays = self._replays(experiment_id)
        required = {
            (case["case_id"], trial)
            for case in manifest["held_out_cases"]
            for trial in range(1, int(manifest["replay_contract"]["trials_per_case"]) + 1)
        }
        observed = {(row.get("case_id"), row.get("trial")) for row in replays}
        if observed != required:
            result = {
                "schema_version": 2, "experiment_id": experiment_id,
                "decision": "INCONCLUSIVE",
                "reason": "held-out repeated replay is incomplete",
                "evidence_refs": sorted(str(row.get("receipt_id")) for row in replays),
            }
            _write_immutable(decision_path, result)
            return result
        regression = any(
            any(
                row["guardrails"]["baseline"][name]
                and not row["guardrails"]["candidate"][name]
                for name in ("safety", "citation")
            )
            for row in replays
        )
        if regression:
            result = {
                "schema_version": 2, "experiment_id": experiment_id,
                "decision": "REVERT", "reason": "candidate guardrail regression",
                "evidence_refs": [
                    row["receipt_id"] for row in replays
                    if any(
                        row["guardrails"]["baseline"][name]
                        and not row["guardrails"]["candidate"][name]
                        for name in ("safety", "citation")
                    )
                ],
            }
            _write_immutable(decision_path, result)
            return result
        canary_path = directory / "canary.json"
        if not canary_path.exists():
            result = {
                "schema_version": 2, "experiment_id": experiment_id,
                "decision": "INCONCLUSIVE", "reason": "matched canary is absent",
                "evidence_refs": [row["receipt_id"] for row in replays],
            }
            _write_immutable(decision_path, result)
            return result
        canary = json.loads(canary_path.read_text(encoding="utf-8"))
        if canary.get("closed") is not True:
            result = {
                "schema_version": 2, "experiment_id": experiment_id,
                "decision": "INCONCLUSIVE", "reason": "matched canary window is open",
                "evidence_refs": list(canary.get("receipt_ids", [])),
            }
            _write_immutable(decision_path, result)
            return result
        deltas = {
            metric: canary["candidate"]["metrics"][metric] - canary["baseline"]["metrics"][metric]
            for metric in sorted(set(canary["baseline"]["metrics"]) & set(canary["candidate"]["metrics"]))
        }
        received_harm = any(
            value < 0
            for metric, value in deltas.items()
            if metric == "net_received" or metric.startswith("net_received_")
        )
        refund_harm = any(
            value > 0
            for metric, value in deltas.items()
            if metric == "refunds" or metric.startswith("refunds_")
        )
        if received_harm or refund_harm:
            result = {
                "schema_version": 2, "experiment_id": experiment_id,
                "decision": "REVERT", "reason": "matched canary shows received-money or refund harm",
                "evidence_refs": list(canary["receipt_ids"]), "canary_deltas": deltas,
            }
            _write_immutable(decision_path, result)
            return result
        evidence = {
            "experiment_id": experiment_id,
            "changed_field": manifest["changed_field"],
            "text_diff": manifest["text_diff"],
            "replays": replays,
            "canary": canary,
            "canary_deltas": deltas,
        }
        interpreted = interpreter(evidence)
        if not isinstance(interpreted, dict) or set(interpreted) not in (
            {"decision", "reason", "evidence_refs"},
            {"decision", "reason", "evidence_refs", "winner_observation"},
        ):
            raise ValueError("agent decision is malformed")
        if interpreted.get("decision") not in DECISIONS or not isinstance(interpreted.get("reason"), str) or not interpreted["reason"].strip():
            raise ValueError("agent decision is invalid")
        valid_refs = {row["receipt_id"] for row in replays} | set(canary["receipt_ids"])
        refs = interpreted.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(ref not in valid_refs for ref in refs):
            raise ValueError("agent decision cites unknown evidence")
        result = {
            "schema_version": 2,
            "experiment_id": experiment_id,
            "decision": interpreted["decision"],
            "reason": interpreted["reason"].strip(),
            "evidence_refs": list(dict.fromkeys(refs)),
            "canary_deltas": deltas,
        }
        if "winner_observation" in interpreted:
            result["winner_observation"] = interpreted["winner_observation"]
        _write_immutable(decision_path, result)
        return result

    def promote(self, experiment_id: str) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        decision_path = self._directory(experiment_id) / "decision.json"
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("experiment has no decision") from error
        if decision.get("decision") != "KEEP":
            raise ValueError("only a KEEP decision can promote a strategy")
        active = {
            "schema_version": 2,
            "experiment_id": experiment_id,
            "strategy_sha256": manifest["candidate_strategy_sha256"],
            "rollback_strategy_sha256": manifest["baseline_strategy_sha256"],
            "decision_sha256": _sha(decision),
        }
        active_path = self.root / "active-strategy.json"
        if active_path.exists():
            current = json.loads(active_path.read_text(encoding="utf-8"))
            if current != active:
                current_id = _require_id(current.get("experiment_id"), "active experiment")
                current_hash = _require_hex(
                    current.get("strategy_sha256"), "active strategy"
                )
                if not any(
                    (self._directory(current_id) / "consumptions").glob("*.json")
                ):
                    raise ValueError("active strategy has no production consumption proof")
                current_strategy_path = self.root / "strategies" / f"{current_hash}.json"
                baseline_strategy_path = (
                    self.root / "strategies"
                    / f"{manifest['baseline_strategy_sha256']}.json"
                )
                try:
                    current_strategy = json.loads(
                        current_strategy_path.read_text(encoding="utf-8")
                    )
                    baseline_strategy = json.loads(
                        baseline_strategy_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as error:
                    raise ValueError("strategy supersession inputs are unavailable") from error
                if any(
                    baseline_strategy.get(key) != value
                    for key, value in current_strategy.items()
                ):
                    raise ValueError("new baseline drops an active strategy rule")
                _write_immutable(
                    self.root / "active-history" / f"{current_id}.json", current
                )
                _atomic(active_path, active)
        else:
            _atomic(active_path, active)
        strategy_path = (
            self.root / "strategies" / f"{manifest['candidate_strategy_sha256']}.json"
        )
        runtime = {
            "version_id": manifest["candidate_strategy_sha256"],
            "status": "active",
            "learning_cycle_id": experiment_id,
            "slice": "writer-learning",
            "weight_file": str(strategy_path),
            "weight_hash": manifest["candidate_strategy_sha256"],
        }
        _atomic(self.root.parent / "strategy/active/writer-learning.json", runtime)
        _write_immutable(self._directory(experiment_id) / "promotion.json", active)
        return active

    def record_consumption(
        self,
        *,
        experiment_id: str,
        run_id: str,
        strategy_sha256: str,
        artifact_sha256: dict[str, str],
        consumed_at: datetime,
    ) -> dict[str, Any]:
        active_path = self.root / "active-strategy.json"
        try:
            active = json.loads(active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("there is no active strategy") from error
        if active.get("experiment_id") != experiment_id or active.get("strategy_sha256") != strategy_sha256:
            raise ValueError("run did not consume the active strategy")
        if set(artifact_sha256) != {"ja", "en"}:
            raise ValueError("consumption requires both frozen article hashes")
        stable = {
            "schema_version": 2,
            "experiment_id": experiment_id,
            "run_id": _require_id(run_id, "run_id"),
            "strategy_sha256": _require_hex(strategy_sha256, "strategy_sha256"),
            "artifact_sha256": {
                lang: _require_hex(artifact_sha256[lang], f"{lang} artifact")
                for lang in ("ja", "en")
            },
        }
        path = self._directory(experiment_id) / "consumptions" / f"{run_id}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("consumption receipt is unreadable") from error
            if {key: existing.get(key) for key in stable} != stable:
                raise ValueError("consumption receipt conflicts with frozen artifacts")
            _aware_iso(datetime.fromisoformat(str(existing.get("consumed_at", ""))))
            return existing
        row = {**stable, "consumed_at": _aware_iso(consumed_at)}
        _write_immutable(path, row)
        return row
