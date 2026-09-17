from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from .experiments import ExperimentResult, evaluate_candidate
from .ledger import FUNNEL_STAGES, Ledger
from .telegram import send_once


LEARNING_SCOPE = "default"
METRIC_STAGE = "interview"
EXECUTION_OUTCOMES = frozenset({"success", "failure", "safety_violation"})
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_SAFE_AUTO_APPLY_THRESHOLD = 90
THRESHOLD_STEP = 5


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _strategy_row(ledger: Ledger, generation_id: str) -> dict[str, Any]:
    row = ledger.connection.execute(
        """
        SELECT strategy_json
        FROM strategy_generations
        WHERE strategy_generation_id = ?
        """,
        (generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError("strategy generation does not exist")
    value = json.loads(str(row["strategy_json"]))
    if not isinstance(value, dict):
        raise ValueError("strategy generation is not an object")
    return value


def _aware_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("occurred_at must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("occurred_at must include a timezone")
    return parsed.isoformat()


def replay_strategy_pair(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    replay_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    cases = [dict(case) for case in replay_cases]
    if not cases:
        raise ValueError("replay requires at least one held-out case")
    case_ids = [case.get("case_id") for case in cases]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
        raise ValueError("each replay case needs a case_id")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("replay case IDs must be unique")

    changed = sorted(
        key
        for key in set(baseline) | set(candidate)
        if baseline.get(key) != candidate.get(key)
    )
    violations: list[str] = []
    if changed != ["auto_apply_threshold"]:
        violations.append("candidate_must_change_auto_apply_threshold_only")
    baseline_threshold = baseline.get("auto_apply_threshold")
    candidate_threshold = candidate.get("auto_apply_threshold")
    if (
        not isinstance(baseline_threshold, int)
        or not isinstance(candidate_threshold, int)
        or candidate_threshold <= baseline_threshold
        or candidate_threshold > MAX_SAFE_AUTO_APPLY_THRESHOLD
    ):
        violations.append("candidate_threshold_outside_safe_range")

    replay_rows = []
    for case in sorted(cases, key=lambda item: str(item["case_id"])):
        score = case.get("score")
        hard_eligible = case.get("hard_eligible")
        if not isinstance(score, int) or not isinstance(hard_eligible, bool):
            raise ValueError("replay cases require integer score and boolean hard_eligible")
        baseline_applies = bool(
            hard_eligible
            and isinstance(baseline_threshold, int)
            and score >= baseline_threshold
        )
        candidate_applies = bool(
            hard_eligible
            and isinstance(candidate_threshold, int)
            and score >= candidate_threshold
        )
        if not hard_eligible and (baseline_applies or candidate_applies):
            violations.append(f"hard_filter_regression:{case['case_id']}")
        replay_rows.append(
            {
                "case_id": case["case_id"],
                "baseline_applies": baseline_applies,
                "candidate_applies": candidate_applies,
            }
        )

    manifest = {
        "version": 1,
        "baseline_sha256": _sha256(dict(baseline)),
        "candidate_sha256": _sha256(dict(candidate)),
        "cases": replay_rows,
        "violations": sorted(set(violations)),
    }
    return {
        "manifest_sha256": _sha256(manifest),
        "case_count": len(replay_rows),
        "violations": len(manifest["violations"]),
    }


class LearningDriver:
    def __init__(
        self,
        ledger: Ledger,
        *,
        baseline_strategy: Mapping[str, Any],
        replay_cases: Sequence[Mapping[str, Any]],
        metric_stage: str = METRIC_STAGE,
    ):
        if not isinstance(baseline_strategy, Mapping) or not baseline_strategy:
            raise ValueError("baseline strategy must be a non-empty object")
        if metric_stage not in FUNNEL_STAGES:
            raise ValueError("metric_stage is not a supported funnel stage")
        self.ledger = ledger
        self.baseline_strategy = dict(baseline_strategy)
        self.replay_cases = tuple(dict(case) for case in replay_cases)
        self.metric_stage = metric_stage

    def _control(self):
        return self.ledger.connection.execute(
            """
            SELECT active_generation_id, experiment_id
            FROM strategy_learning_control
            WHERE scope = ?
            """,
            (LEARNING_SCOPE,),
        ).fetchone()

    def _bootstrap_control(self) -> None:
        if self._control() is not None:
            return
        generation_id = self.ledger.record_strategy_generation(
            self.baseline_strategy
        )
        with self.ledger._transaction():
            self.ledger.connection.execute(
                """
                INSERT OR IGNORE INTO strategy_learning_control
                  (scope, active_generation_id, experiment_id, updated_at)
                VALUES (?, ?, NULL, datetime('now'))
                """,
                (LEARNING_SCOPE, generation_id),
            )

    def _propose_candidate(
        self,
        baseline: Mapping[str, Any],
        baseline_generation_id: str,
    ) -> dict[str, Any]:
        threshold = baseline.get("auto_apply_threshold")
        if not isinstance(threshold, int):
            raise ValueError("active strategy has no integer auto_apply_threshold")
        tested_thresholds = set()
        rows = self.ledger.connection.execute(
            """
            SELECT generations.strategy_json
            FROM strategy_experiments AS experiments
            JOIN strategy_generations AS generations
              ON generations.strategy_generation_id =
                 experiments.candidate_generation_id
            WHERE experiments.baseline_generation_id = ?
              AND experiments.changed_field = 'auto_apply_threshold'
            """,
            (baseline_generation_id,),
        ).fetchall()
        for row in rows:
            value = json.loads(str(row["strategy_json"])).get(
                "auto_apply_threshold"
            )
            if isinstance(value, int):
                tested_thresholds.add(value)
        candidate_threshold = threshold + THRESHOLD_STEP
        while (
            candidate_threshold in tested_thresholds
            and candidate_threshold <= MAX_SAFE_AUTO_APPLY_THRESHOLD
        ):
            candidate_threshold += THRESHOLD_STEP
        if candidate_threshold > MAX_SAFE_AUTO_APPLY_THRESHOLD:
            raise ValueError("no bounded threshold candidate remains")
        return {**dict(baseline), "auto_apply_threshold": candidate_threshold}

    def _ensure_experiment(self) -> None:
        self._bootstrap_control()
        control = self._control()
        if control["experiment_id"] is not None:
            return
        baseline_id = str(control["active_generation_id"])
        baseline = _strategy_row(self.ledger, baseline_id)
        candidate = self._propose_candidate(baseline, baseline_id)
        candidate_id = self.ledger.record_strategy_generation(
            candidate,
            parent_generation_id=baseline_id,
            changed_field="auto_apply_threshold",
        )
        replay = replay_strategy_pair(baseline, candidate, self.replay_cases)
        experiment_payload = {
            "version": 1,
            "baseline_generation_id": baseline_id,
            "candidate_generation_id": candidate_id,
            "changed_field": "auto_apply_threshold",
            "metric_stage": self.metric_stage,
            "replay": replay,
        }
        experiment_id = f"experiment-{_sha256(experiment_payload)}"
        with self.ledger._transaction():
            self.ledger.connection.execute(
                """
                INSERT OR IGNORE INTO strategy_experiments
                  (experiment_id, baseline_generation_id,
                   candidate_generation_id, changed_field, metric_stage,
                   replay_manifest_sha256, replay_case_count,
                   replay_violations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    experiment_id,
                    baseline_id,
                    candidate_id,
                    "auto_apply_threshold",
                    self.metric_stage,
                    replay["manifest_sha256"],
                    replay["case_count"],
                    replay["violations"],
                ),
            )
            current = self.ledger.connection.execute(
                """
                SELECT active_generation_id, experiment_id
                FROM strategy_learning_control
                WHERE scope = ?
                """,
                (LEARNING_SCOPE,),
            ).fetchone()
            if (
                str(current["active_generation_id"]) != baseline_id
                or current["experiment_id"] is not None
            ):
                raise RuntimeError("learning control changed during proposal")
            self.ledger.connection.execute(
                """
                UPDATE strategy_learning_control
                SET experiment_id = ?, updated_at = datetime('now')
                WHERE scope = ?
                """,
                (experiment_id, LEARNING_SCOPE),
            )

    def _experiment(self):
        control = self._control()
        if control is None or control["experiment_id"] is None:
            return None
        return self.ledger.connection.execute(
            """
            SELECT *
            FROM strategy_experiments
            WHERE experiment_id = ?
            """,
            (control["experiment_id"],),
        ).fetchone()

    def _counts(self, generation_id: str, stage: str) -> tuple[int, int]:
        row = self.ledger.connection.execute(
            """
            SELECT positive_count, resolved_count
            FROM strategy_outcome_projection
            WHERE strategy_generation_id = ? AND funnel_stage = ?
            """,
            (generation_id, stage),
        ).fetchone()
        if row is None:
            return (0, 0)
        return (int(row["positive_count"]), int(row["resolved_count"]))

    def _execution_state(self, experiment_id: str) -> tuple[int, int]:
        rows = self.ledger.connection.execute(
            """
            SELECT outcome
            FROM learning_execution_events
            WHERE experiment_id = ?
            ORDER BY occurred_at, event_id
            """,
            (experiment_id,),
        ).fetchall()
        safety_violations = sum(
            1 for row in rows if row["outcome"] == "safety_violation"
        )
        failure_streak = 0
        for row in reversed(rows):
            if row["outcome"] != "failure":
                break
            failure_streak += 1
        return safety_violations, failure_streak

    def status(self) -> dict[str, Any]:
        self._bootstrap_control()
        control = self._control()
        active_id = str(control["active_generation_id"])
        experiment = self._experiment()
        result: dict[str, Any] = {
            "active_generation_id": active_id,
            "active_strategy": _strategy_row(self.ledger, active_id),
            "experiment_id": None,
            "candidate_generation_id": None,
            "candidate_strategy": None,
            "changed_field": None,
            "replay": None,
            "candidate_failure_streak": 0,
        }
        if experiment is None:
            return result
        safety_violations, failure_streak = self._execution_state(
            str(experiment["experiment_id"])
        )
        candidate_id = str(experiment["candidate_generation_id"])
        return {
            **result,
            "experiment_id": str(experiment["experiment_id"]),
            "candidate_generation_id": candidate_id,
            "candidate_strategy": _strategy_row(self.ledger, candidate_id),
            "changed_field": str(experiment["changed_field"]),
            "replay": {
                "manifest_sha256": str(experiment["replay_manifest_sha256"]),
                "case_count": int(experiment["replay_case_count"]),
                "violations": int(experiment["replay_violations"]),
                "safety_events": safety_violations,
            },
            "candidate_failure_streak": failure_streak,
        }

    def assign(self, assignment_key: str) -> dict[str, Any]:
        if not isinstance(assignment_key, str) or not assignment_key:
            raise ValueError("assignment_key is required")
        self._ensure_experiment()
        experiment = self._experiment()
        digest = hashlib.sha256(
            f"{experiment['experiment_id']}\0{assignment_key}".encode("utf-8")
        ).digest()
        arm = "candidate" if digest[0] & 1 else "baseline"
        generation_id = str(
            experiment[
                "candidate_generation_id"
                if arm == "candidate"
                else "baseline_generation_id"
            ]
        )
        return {
            "experiment_id": str(experiment["experiment_id"]),
            "arm": arm,
            "strategy_generation_id": generation_id,
            "strategy": _strategy_row(self.ledger, generation_id),
        }

    def record_candidate_execution(
        self,
        *,
        outcome: str,
        evidence_sha256: str,
        occurred_at: str,
    ) -> str:
        if outcome not in EXECUTION_OUTCOMES:
            raise ValueError("unsupported candidate execution outcome")
        if not SHA256_PATTERN.fullmatch(evidence_sha256):
            raise ValueError("evidence_sha256 must be a lowercase SHA-256")
        occurred = _aware_timestamp(occurred_at)
        self._ensure_experiment()
        experiment = self._experiment()
        event_payload = {
            "version": 1,
            "experiment_id": str(experiment["experiment_id"]),
            "candidate_generation_id": str(experiment["candidate_generation_id"]),
            "outcome": outcome,
            "evidence_sha256": evidence_sha256,
            "occurred_at": occurred,
        }
        event_id = f"learning-event-{_sha256(event_payload)}"
        with self.ledger._transaction():
            self.ledger.connection.execute(
                """
                INSERT OR IGNORE INTO learning_execution_events
                  (event_id, experiment_id, candidate_generation_id, outcome,
                   evidence_sha256, occurred_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    event_id,
                    event_payload["experiment_id"],
                    event_payload["candidate_generation_id"],
                    outcome,
                    evidence_sha256,
                    occurred,
                ),
            )
            recorded = self.ledger.connection.execute(
                """
                SELECT outcome, occurred_at
                FROM learning_execution_events
                WHERE experiment_id = ? AND evidence_sha256 = ?
                """,
                (event_payload["experiment_id"], evidence_sha256),
            ).fetchone()
            if (
                str(recorded["outcome"]) != outcome
                or str(recorded["occurred_at"]) != occurred
            ):
                raise RuntimeError("execution evidence is already bound")
        return event_id

    def run(self) -> dict[str, Any]:
        self._ensure_experiment()
        experiment = self._experiment()
        baseline_id = str(experiment["baseline_generation_id"])
        candidate_id = str(experiment["candidate_generation_id"])
        self.ledger.rebuild_strategy_outcome_projection()
        baseline_positive, baseline_resolved = self._counts(
            baseline_id, str(experiment["metric_stage"])
        )
        candidate_positive, candidate_resolved = self._counts(
            candidate_id, str(experiment["metric_stage"])
        )
        evaluated = evaluate_candidate(
            _strategy_row(self.ledger, baseline_id),
            _strategy_row(self.ledger, candidate_id),
            baseline_resolved=baseline_resolved,
            baseline_positive=baseline_positive,
            candidate_resolved=candidate_resolved,
            candidate_positive=candidate_positive,
            replay_violations=int(experiment["replay_violations"]),
        )
        safety_violations, failure_streak = self._execution_state(
            str(experiment["experiment_id"])
        )
        if safety_violations:
            decision, reason = "rollback", "verified_safety_violation"
        elif failure_streak >= 3:
            decision, reason = (
                "rollback",
                "three_consecutive_candidate_failures",
            )
        elif evaluated.decision == "rejected":
            decision, reason = "rollback", evaluated.reason
        else:
            decision, reason = evaluated.decision, evaluated.reason

        terminal = (
            decision in {"promote", "rollback"}
            or (
                decision == "inconclusive"
                and reason != "insufficient_resolved_applications"
            )
        )
        active_after = candidate_id if decision == "promote" else baseline_id
        report_base = {
            "version": 1,
            "experiment_id": str(experiment["experiment_id"]),
            "decision": decision,
            "reason": reason,
            "changed_field": str(experiment["changed_field"]),
            "metric_stage": str(experiment["metric_stage"]),
            "baseline_generation_id": baseline_id,
            "candidate_generation_id": candidate_id,
            "baseline": {
                "positive": baseline_positive,
                "resolved": baseline_resolved,
                "interval": list(evaluated.baseline_interval),
            },
            "candidate": {
                "positive": candidate_positive,
                "resolved": candidate_resolved,
                "interval": list(evaluated.candidate_interval),
            },
            "replay": {
                "manifest_sha256": str(experiment["replay_manifest_sha256"]),
                "case_count": int(experiment["replay_case_count"]),
                "violations": int(experiment["replay_violations"]),
                "safety_events": safety_violations,
            },
            "candidate_failure_streak": failure_streak,
            "active_generation_id": active_after,
            "experiment_open": not terminal,
        }
        receipt_sha256 = _sha256(report_base)
        report = {
            **report_base,
            "decision_id": f"learning-{receipt_sha256}",
            "receipt_sha256": receipt_sha256,
        }
        report_json = _canonical_json(report)
        with self.ledger._transaction():
            cursor = self.ledger.connection.execute(
                """
                INSERT OR IGNORE INTO learning_decisions
                  (decision_id, experiment_id, decision, reason, metric_stage,
                   active_before_generation_id, active_after_generation_id,
                   snapshot_sha256, receipt_sha256, report_json, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    report["decision_id"],
                    report["experiment_id"],
                    decision,
                    reason,
                    report["metric_stage"],
                    baseline_id,
                    active_after,
                    receipt_sha256,
                    receipt_sha256,
                    report_json,
                ),
            )
            if cursor.rowcount:
                control_update = self.ledger.connection.execute(
                    """
                    UPDATE strategy_learning_control
                    SET active_generation_id = ?,
                        experiment_id = ?,
                        updated_at = datetime('now')
                    WHERE scope = ?
                      AND active_generation_id = ?
                      AND experiment_id = ?
                    """,
                    (
                        active_after,
                        None if terminal else report["experiment_id"],
                        LEARNING_SCOPE,
                        baseline_id,
                        report["experiment_id"],
                    ),
                )
                if control_update.rowcount != 1:
                    raise RuntimeError(
                        "learning control changed during decision"
                    )
            stored = self.ledger.connection.execute(
                """
                SELECT report_json
                FROM learning_decisions
                WHERE decision_id = ?
                """,
                (report["decision_id"],),
            ).fetchone()
        return json.loads(str(stored["report_json"]))


def deliver_learning_report(
    report: Mapping[str, Any],
    *,
    database: Path,
    requester: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, str | None]:
    message = (
        "🧠 Job-search learning pass\n"
        f"Decision: {report['decision']} ({report['reason']})\n"
        f"Field: {report['changed_field']}\n"
        f"Resolved: baseline {report['baseline']['resolved']}, "
        f"candidate {report['candidate']['resolved']}\n"
        f"Receipt: {report['receipt_sha256'][:16]}"
    )
    arguments: dict[str, Any] = {
        "database": database,
        "event_key": f"job-search-learning:{report['decision_id']}",
        "message": message,
    }
    if requester is not None:
        arguments["requester"] = requester
    return send_once(**arguments)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def summarize_mercor_sources(path: Path | None) -> dict[str, Any]:
    """Attach validated source provenance to a private learning report."""
    unavailable_context = {
        "resolved": 0,
        "stage_counts": {},
        "loss_stage": "unknown",
        "source": "unavailable",
    }
    if path is None or not Path(path).is_file():
        return {
            "status": "unavailable",
            "reason": "source_receipt_missing",
            "source_count": 0,
            "income_receipts_promoted": 0,
            "sources": [],
            "funnel_context": unavailable_context,
        }
    try:
        value = _read_object(Path(path))
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "status": "unavailable",
            "reason": "source_receipt_invalid",
            "source_count": 0,
            "income_receipts_promoted": 0,
            "sources": [],
            "funnel_context": unavailable_context,
        }
    rows = value.get("sources")
    if not isinstance(rows, list):
        return {
            "status": "unavailable",
            "reason": "source_receipt_sources_missing",
            "source_count": 0,
            "income_receipts_promoted": 0,
            "sources": [],
            "funnel_context": unavailable_context,
        }
    raw_context = value.get("funnel_context")
    funnel_context = unavailable_context
    if isinstance(raw_context, Mapping):
        raw_counts = raw_context.get("stage_counts")
        counts = {
            str(stage): number
            for stage, number in (raw_counts.items() if isinstance(raw_counts, Mapping) else [])
            if isinstance(stage, str)
            and isinstance(number, int)
            and not isinstance(number, bool)
            and number >= 0
        }
        raw_resolved = raw_context.get("resolved")
        funnel_context = {
            "resolved": raw_resolved if isinstance(raw_resolved, int) and not isinstance(raw_resolved, bool) and raw_resolved >= 0 else 0,
            "stage_counts": counts,
            "loss_stage": str(raw_context.get("loss_stage") or "unknown")[:80],
            "source": str(raw_context.get("source") or "unknown")[:80],
        }
    accepted: list[dict[str, Any]] = []
    allowed_kinds = {"official_guidance", "first_person", "marketing", "code", "official_receipt"}
    allowed_grades = {"official", "first_person", "marketing", "code", "official_receipt", "unavailable"}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        url = row.get("source_url")
        parsed = urlsplit(url.strip()) if isinstance(url, str) else None
        kind = row.get("source_kind")
        grade = row.get("evidence_grade")
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.netloc
            or kind not in allowed_kinds
            or grade not in allowed_grades
            or not isinstance(row.get("source_unavailable"), bool)
        ):
            continue
        accepted_row = {
            "source_url": url.strip(),
            "source_kind": kind,
            "evidence_grade": grade,
            "source_unavailable": row["source_unavailable"],
            "published_at": row.get("published_at") if isinstance(row.get("published_at"), (str, type(None))) else None,
            "observed_at": str(row.get("observed_at") or ""),
            "author": str(row.get("author") or "")[:200],
            "claimed_outcome": str(row.get("claimed_outcome") or "")[:1000],
        }
        for key in ("target_stage", "one_variable", "strategy_version"):
            if isinstance(row.get(key), str) and row[key].strip():
                accepted_row[key] = row[key].strip()[:120]
        if isinstance(row.get("baseline_cohort"), Mapping):
            accepted_row["baseline_cohort"] = {
                "resolved": row["baseline_cohort"].get("resolved", 0),
                "stage_counts": row["baseline_cohort"].get("stage_counts", {}),
                "loss_stage": str(row["baseline_cohort"].get("loss_stage") or "unknown")[:80],
            }
        if isinstance(row.get("proposed_change"), Mapping) and len(row["proposed_change"]) == 1:
            accepted_row["proposed_change"] = dict(row["proposed_change"])
        accepted.append(accepted_row)
    return {
        "status": "loaded",
        "source_count": len(accepted),
        "income_receipts_promoted": 0,
        "sources": accepted,
        "funnel_context": funnel_context,
    }


def _read_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("replay file must be a version-1 object")
    cases = value.get("cases")
    if not isinstance(cases, list):
        raise ValueError("replay file needs a cases array")
    return [dict(case) for case in cases]


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "assign", "status", "execution"))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--key")
    parser.add_argument("--outcome", choices=sorted(EXECUTION_OUTCOMES))
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--occurred-at")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--outbox", type=Path)
    parser.add_argument("--mercor-sources", type=Path)
    parsed = parser.parse_args(argv)

    ledger = Ledger(parsed.ledger)
    try:
        driver = LearningDriver(
            ledger,
            baseline_strategy=_read_object(parsed.strategy),
            replay_cases=_read_cases(parsed.replay),
        )
        if parsed.command == "run":
            if parsed.report is None or parsed.outbox is None:
                parser.error("run requires --report and --outbox")
            result = driver.run()
            result["mercor_sources"] = summarize_mercor_sources(parsed.mercor_sources)
            _write_private_json(parsed.report, result)
            delivery = deliver_learning_report(
                result,
                database=parsed.outbox,
            )
            output = {
                "status": "success",
                "decision_id": result["decision_id"],
                "decision": result["decision"],
                "reason": result["reason"],
                "receipt_sha256": result["receipt_sha256"],
                "telegram_status": delivery["status"],
                "telegram_message_id": delivery["message_id"],
            }
        elif parsed.command == "assign":
            if parsed.key is None:
                parser.error("assign requires --key")
            output = driver.assign(parsed.key)
        elif parsed.command == "execution":
            if not all(
                (parsed.outcome, parsed.evidence_sha256, parsed.occurred_at)
            ):
                parser.error(
                    "execution requires --outcome, --evidence-sha256 and --occurred-at"
                )
            output = {
                "event_id": driver.record_candidate_execution(
                    outcome=parsed.outcome,
                    evidence_sha256=parsed.evidence_sha256,
                    occurred_at=parsed.occurred_at,
                )
            }
        else:
            output = driver.status()
    finally:
        ledger.close()
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
