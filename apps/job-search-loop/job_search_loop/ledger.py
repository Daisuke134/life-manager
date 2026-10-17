from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from .ats import evaluate_snapshot
from .state import (
    DEFAULT_EMPLOYER_EXCLUSIONS,
    canonical_job_id,
    canonical_url,
    is_excluded_employer,
    same_application_surface,
    validate_transition,
)


LEGACY_STRATEGY = {"capture_status": "legacy_unavailable"}
LEGACY_STRATEGY_JSON = json.dumps(
    LEGACY_STRATEGY, ensure_ascii=False, sort_keys=True, separators=(",", ":")
)
LEGACY_STRATEGY_SHA256 = hashlib.sha256(
    LEGACY_STRATEGY_JSON.encode("utf-8")
).hexdigest()
LEGACY_STRATEGY_GENERATION_ID = f"strategy-{LEGACY_STRATEGY_SHA256}"
FUNNEL_STAGES = frozenset(
    {
        "confirmed_application",
        "recruiter_response",
        "screen",
        "interview",
        "offer",
        "accepted",
        "declined",
        "started",
    }
)
FUNNEL_DISPOSITIONS = frozenset({"positive", "negative"})
AUTHORITATIVE_EVIDENCE_SOURCES = frozenset(
    {"ats", "gmail", "calendar", "employer_portal", "signed_document"}
)
WORKDAY_FIT_POLICY_VERSION = "workday-global-scope-v7"


class FenceError(RuntimeError):
    pass


class ExcludedEmployerError(ValueError):
    pass


@dataclass(frozen=True)
class SubmitIntent:
    intent_id: str
    application_id: str
    fence: int
    payload_hash: str
    resume_path: str
    resume_sha256: str
    ats_snapshot_path: str
    ats_snapshot_sha256: str
    japan_day: str
    slot: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.connection = sqlite3.connect(
            self.path, timeout=10, isolation_level=None
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                current_state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'agent'
                    CHECK (owner IN ('agent', 'dais_manual', 'recruiter'))
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL REFERENCES applications(id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submit_intents (
                intent_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL UNIQUE REFERENCES applications(id),
                fence INTEGER NOT NULL,
                payload_hash TEXT NOT NULL,
                resume_path TEXT,
                resume_sha256 TEXT,
                ats_snapshot_path TEXT,
                ats_snapshot_sha256 TEXT,
                japan_day TEXT NOT NULL,
                slot INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS daily_slots (
                japan_day TEXT NOT NULL,
                slot INTEGER NOT NULL,
                application_id TEXT NOT NULL UNIQUE REFERENCES applications(id),
                status TEXT NOT NULL,
                PRIMARY KEY (japan_day, slot)
            );
            CREATE TABLE IF NOT EXISTS submission_attempts (
                intent_id TEXT NOT NULL REFERENCES submit_intents(intent_id),
                fence INTEGER NOT NULL,
                application_id TEXT NOT NULL REFERENCES applications(id),
                payload_hash TEXT NOT NULL,
                resume_path TEXT,
                resume_sha256 TEXT,
                ats_snapshot_path TEXT,
                ats_snapshot_sha256 TEXT,
                japan_day TEXT NOT NULL,
                slot INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                PRIMARY KEY (intent_id, fence)
            );
            CREATE TABLE IF NOT EXISTS submission_click_phases (
                intent_id TEXT NOT NULL,
                fence INTEGER NOT NULL,
                phase TEXT NOT NULL CHECK (phase IN
                    ('pre_click', 'clicked', 'confirmed')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (intent_id, fence),
                FOREIGN KEY (intent_id, fence)
                    REFERENCES submission_attempts(intent_id, fence)
            );
            CREATE TABLE IF NOT EXISTS submission_confirmations (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                intent_id TEXT NOT NULL UNIQUE
                    REFERENCES submit_intents(intent_id),
                evidence_sha256 TEXT NOT NULL,
                received_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workday_fit_decisions (
                application_id TEXT PRIMARY KEY REFERENCES applications(id),
                decision TEXT NOT NULL
                    CHECK (decision IN ('qualified', 'rejected', 'hold')),
                evidence_sha256 TEXT NOT NULL,
                policy_version TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strategy_generations (
                strategy_generation_id TEXT PRIMARY KEY,
                parent_generation_id TEXT
                    REFERENCES strategy_generations(strategy_generation_id),
                changed_field TEXT,
                strategy_json TEXT NOT NULL,
                strategy_sha256 TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS application_strategy_assignments (
                application_id TEXT PRIMARY KEY
                    REFERENCES applications(id),
                strategy_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                capture_status TEXT NOT NULL,
                source TEXT NOT NULL,
                query_family TEXT NOT NULL,
                rank_config_json TEXT,
                role_family TEXT NOT NULL,
                material_variant TEXT NOT NULL,
                message_variant TEXT NOT NULL,
                model_route TEXT NOT NULL,
                prompt_sha256 TEXT,
                material_sha256 TEXT,
                assigned_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS funnel_outcomes (
                outcome_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL
                    REFERENCES applications(id),
                funnel_stage TEXT NOT NULL,
                disposition TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                observation_policy_version TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (application_id, funnel_stage, evidence_sha256)
            );
            CREATE TABLE IF NOT EXISTS strategy_outcome_projection (
                strategy_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                funnel_stage TEXT NOT NULL,
                positive_count INTEGER NOT NULL,
                negative_count INTEGER NOT NULL,
                resolved_count INTEGER NOT NULL,
                PRIMARY KEY (strategy_generation_id, funnel_stage)
            );
            CREATE TABLE IF NOT EXISTS strategy_experiments (
                experiment_id TEXT PRIMARY KEY,
                baseline_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                candidate_generation_id TEXT NOT NULL UNIQUE
                    REFERENCES strategy_generations(strategy_generation_id),
                changed_field TEXT NOT NULL,
                metric_stage TEXT NOT NULL,
                replay_manifest_sha256 TEXT NOT NULL,
                replay_case_count INTEGER NOT NULL,
                replay_violations INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strategy_learning_control (
                scope TEXT PRIMARY KEY,
                active_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                experiment_id TEXT
                    REFERENCES strategy_experiments(experiment_id),
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_execution_events (
                event_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL
                    REFERENCES strategy_experiments(experiment_id),
                candidate_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                outcome TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (experiment_id, evidence_sha256)
            );
            CREATE TABLE IF NOT EXISTS learning_decisions (
                decision_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL
                    REFERENCES strategy_experiments(experiment_id),
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                metric_stage TEXT NOT NULL,
                active_before_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                active_after_generation_id TEXT NOT NULL
                    REFERENCES strategy_generations(strategy_generation_id),
                snapshot_sha256 TEXT NOT NULL UNIQUE,
                receipt_sha256 TEXT NOT NULL UNIQUE,
                report_json TEXT NOT NULL,
                decided_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS strategy_generations_no_update
            BEFORE UPDATE ON strategy_generations
            BEGIN
                SELECT RAISE(ABORT, 'strategy generations are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_generations_no_delete
            BEFORE DELETE ON strategy_generations
            BEGIN
                SELECT RAISE(ABORT, 'strategy generations are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_assignments_no_update
            BEFORE UPDATE ON application_strategy_assignments
            BEGIN
                SELECT RAISE(ABORT, 'strategy assignments are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_assignments_no_delete
            BEFORE DELETE ON application_strategy_assignments
            BEGIN
                SELECT RAISE(ABORT, 'strategy assignments are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS funnel_outcomes_no_update
            BEFORE UPDATE ON funnel_outcomes
            BEGIN
                SELECT RAISE(ABORT, 'funnel outcomes are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS funnel_outcomes_no_delete
            BEFORE DELETE ON funnel_outcomes
            BEGIN
                SELECT RAISE(ABORT, 'funnel outcomes are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_experiments_no_update
            BEFORE UPDATE ON strategy_experiments
            BEGIN
                SELECT RAISE(ABORT, 'strategy experiments are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_experiments_no_delete
            BEFORE DELETE ON strategy_experiments
            BEGIN
                SELECT RAISE(ABORT, 'strategy experiments are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS learning_execution_events_no_update
            BEFORE UPDATE ON learning_execution_events
            BEGIN
                SELECT RAISE(ABORT, 'learning execution events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS learning_execution_events_no_delete
            BEFORE DELETE ON learning_execution_events
            BEGIN
                SELECT RAISE(ABORT, 'learning execution events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS learning_decisions_no_update
            BEFORE UPDATE ON learning_decisions
            BEGIN
                SELECT RAISE(ABORT, 'learning decisions are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS learning_decisions_no_delete
            BEFORE DELETE ON learning_decisions
            BEGIN
                SELECT RAISE(ABORT, 'learning decisions are immutable');
            END;
            """
        )
        for table in ("submit_intents", "submission_attempts"):
            columns = {
                str(row["name"])
                for row in self.connection.execute(f"PRAGMA table_info({table})")
            }
            if "outcome_evidence_sha256" not in columns:
                self.connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN outcome_evidence_sha256 TEXT"
                )
            if "outcome_evidence_class" not in columns:
                self.connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN outcome_evidence_class TEXT"
                )
        self._migrate_funnel_outcome_evidence_constraint()
        fit_columns = {
            str(row["name"])
            for row in self.connection.execute(
                "PRAGMA table_info(workday_fit_decisions)"
            )
        }
        if "policy_version" not in fit_columns:
            self.connection.execute(
                "ALTER TABLE workday_fit_decisions ADD COLUMN policy_version TEXT"
            )
        application_columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(applications)")
        }
        if "owner" not in application_columns:
            self.connection.execute(
                "ALTER TABLE applications ADD COLUMN owner TEXT NOT NULL "
                "DEFAULT 'agent' CHECK (owner IN "
                "('agent', 'dais_manual', 'recruiter'))"
            )
        self.connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS applications_owner_no_update
            BEFORE UPDATE OF owner ON applications
            WHEN NEW.owner != OLD.owner
            BEGIN
                SELECT RAISE(ABORT, 'application owner is immutable');
            END
            """
        )
        intent_columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(submit_intents)")
        }
        if "resume_path" not in intent_columns:
            self.connection.execute(
                "ALTER TABLE submit_intents ADD COLUMN resume_path TEXT"
            )
        if "resume_sha256" not in intent_columns:
            self.connection.execute(
                "ALTER TABLE submit_intents ADD COLUMN resume_sha256 TEXT"
            )
        if "ats_snapshot_path" not in intent_columns:
            self.connection.execute(
                "ALTER TABLE submit_intents ADD COLUMN ats_snapshot_path TEXT"
            )
        if "ats_snapshot_sha256" not in intent_columns:
            self.connection.execute(
                "ALTER TABLE submit_intents ADD COLUMN ats_snapshot_sha256 TEXT"
            )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO submission_attempts
              (intent_id, fence, application_id, payload_hash, resume_path,
               resume_sha256, ats_snapshot_path, ats_snapshot_sha256,
               japan_day, slot, status, created_at, completed_at)
            SELECT
              intent_id, fence, application_id, payload_hash, resume_path,
              resume_sha256, ats_snapshot_path, ats_snapshot_sha256,
              japan_day, slot, status, created_at, completed_at
            FROM submit_intents
            """
        )
        migration_time = _now()
        self.connection.execute(
            """
            INSERT OR IGNORE INTO strategy_generations
              (strategy_generation_id, parent_generation_id, changed_field,
               strategy_json, strategy_sha256, created_at)
            VALUES (?, NULL, NULL, ?, ?, ?)
            """,
            (
                LEGACY_STRATEGY_GENERATION_ID,
                LEGACY_STRATEGY_JSON,
                LEGACY_STRATEGY_SHA256,
                migration_time,
            ),
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO application_strategy_assignments
              (application_id, strategy_generation_id, capture_status, source,
               query_family, rank_config_json, role_family, material_variant,
               message_variant, model_route, prompt_sha256, material_sha256,
               assigned_at)
            SELECT
              applications.id, ?, 'legacy_unavailable', 'legacy_unavailable',
              'legacy_unavailable', NULL, 'legacy_unavailable',
              'legacy_unavailable', 'legacy_unavailable', 'legacy_unavailable',
              NULL, NULL, applications.created_at
            FROM applications
            """,
            (LEGACY_STRATEGY_GENERATION_ID,),
        )
        if self.path.exists():
            os.chmod(self.path, 0o600)

    def _migrate_funnel_outcome_evidence_constraint(self) -> None:
        has_single_evidence_unique = False
        for index in self.connection.execute(
            "PRAGMA index_list(funnel_outcomes)"
        ).fetchall():
            if not bool(index["unique"]):
                continue
            index_name = str(index["name"]).replace("'", "''")
            columns = [
                str(row["name"])
                for row in self.connection.execute(
                    f"PRAGMA index_info('{index_name}')"
                ).fetchall()
            ]
            if columns == ["evidence_sha256"]:
                has_single_evidence_unique = True
                break
        if not has_single_evidence_unique:
            return
        self.connection.executescript(
            """
            BEGIN IMMEDIATE;
            DROP TRIGGER IF EXISTS funnel_outcomes_no_update;
            DROP TRIGGER IF EXISTS funnel_outcomes_no_delete;
            ALTER TABLE funnel_outcomes
              RENAME TO funnel_outcomes_single_evidence_unique;
            CREATE TABLE funnel_outcomes (
                outcome_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL
                    REFERENCES applications(id),
                funnel_stage TEXT NOT NULL,
                disposition TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                observation_policy_version TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (application_id, funnel_stage, evidence_sha256)
            );
            INSERT INTO funnel_outcomes
              (outcome_id, application_id, funnel_stage, disposition,
               evidence_source, evidence_sha256, occurred_at, observed_at,
               observation_policy_version, created_at)
            SELECT
              outcome_id, application_id, funnel_stage, disposition,
              evidence_source, evidence_sha256, occurred_at, observed_at,
              observation_policy_version, created_at
            FROM funnel_outcomes_single_evidence_unique;
            DROP TABLE funnel_outcomes_single_evidence_unique;
            CREATE TRIGGER funnel_outcomes_no_update
            BEFORE UPDATE ON funnel_outcomes
            BEGIN
                SELECT RAISE(ABORT, 'funnel outcomes are immutable');
            END;
            CREATE TRIGGER funnel_outcomes_no_delete
            BEFORE DELETE ON funnel_outcomes
            BEGIN
                SELECT RAISE(ABORT, 'funnel outcomes are immutable');
            END;
            COMMIT;
            """
        )

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def _append_event(
        self,
        application_id: str,
        from_state: str | None,
        to_state: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO events
              (event_id, application_id, from_state, to_state, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                application_id,
                from_state,
                to_state,
                json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                _now(),
            ),
        )

    def add_application(self, company: str, title: str, url: str) -> str:
        if is_excluded_employer(company):
            raise ExcludedEmployerError(f"employer is excluded: {company}")
        application_id = canonical_job_id(company, title, url)
        with self._transaction():
            existing = self.connection.execute(
                "SELECT id FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            if existing is None:
                created_at = _now()
                self.connection.execute(
                    """
                    INSERT INTO applications
                      (id, company, title, canonical_url, current_state, created_at)
                    VALUES (?, ?, ?, ?, 'discovered', ?)
                    """,
                    (
                        application_id,
                        company.strip(),
                        title.strip(),
                        canonical_url(url),
                        created_at,
                    ),
                )
                self._append_event(application_id, None, "discovered")
            self.connection.execute(
                """
                INSERT OR IGNORE INTO application_strategy_assignments
                  (application_id, strategy_generation_id, capture_status, source,
                   query_family, rank_config_json, role_family, material_variant,
                   message_variant, model_route, prompt_sha256, material_sha256,
                   assigned_at)
                SELECT
                  applications.id, ?, 'legacy_unavailable', 'legacy_unavailable',
                  'legacy_unavailable', NULL, 'legacy_unavailable',
                  'legacy_unavailable', 'legacy_unavailable', 'legacy_unavailable',
                  NULL, NULL, applications.created_at
                FROM applications
                WHERE applications.id = ?
                """,
                (LEGACY_STRATEGY_GENERATION_ID, application_id),
            )
        return application_id

    def add_attributed_application(
        self,
        company: str,
        title: str,
        url: str,
        *,
        strategy_generation_id: str,
        source: str,
        query_family: str,
        rank_config: Mapping[str, Any],
        role_family: str,
        material_variant: str,
        message_variant: str,
        model_route: str,
        prompt_sha256: str,
        material_sha256: str,
    ) -> str:
        if is_excluded_employer(company):
            raise ExcludedEmployerError(f"employer is excluded: {company}")
        text_values = {
            "strategy_generation_id": strategy_generation_id,
            "source": source,
            "query_family": query_family,
            "role_family": role_family,
            "material_variant": material_variant,
            "message_variant": message_variant,
            "model_route": model_route,
        }
        for name, value in text_values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(rank_config, Mapping):
            raise ValueError("rank_config must be a mapping")
        for name, value in {
            "prompt_sha256": prompt_sha256,
            "material_sha256": material_sha256,
        }.items():
            if not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256")

        application_id = canonical_job_id(company, title, url)
        rank_config_json = json.dumps(
            dict(rank_config),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._transaction():
            generation = self.connection.execute(
                """
                SELECT strategy_generation_id
                FROM strategy_generations
                WHERE strategy_generation_id = ?
                """,
                (strategy_generation_id,),
            ).fetchone()
            if generation is None:
                raise ValueError("strategy generation does not exist")
            application = self.connection.execute(
                "SELECT id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if application is None:
                created_at = _now()
                self.connection.execute(
                    """
                    INSERT INTO applications
                      (id, company, title, canonical_url, current_state, created_at)
                    VALUES (?, ?, ?, ?, 'discovered', ?)
                    """,
                    (
                        application_id,
                        company.strip(),
                        title.strip(),
                        canonical_url(url),
                        created_at,
                    ),
                )
                self._append_event(application_id, None, "discovered")
            existing_assignment = self.connection.execute(
                """
                SELECT
                  strategy_generation_id, capture_status, source, query_family,
                  rank_config_json, role_family, material_variant,
                  message_variant, model_route, prompt_sha256, material_sha256
                FROM application_strategy_assignments
                WHERE application_id = ?
                """,
                (application_id,),
            ).fetchone()
            expected_assignment = (
                strategy_generation_id,
                "captured",
                source.strip(),
                query_family.strip(),
                rank_config_json,
                role_family.strip(),
                material_variant.strip(),
                message_variant.strip(),
                model_route.strip(),
                prompt_sha256,
                material_sha256,
            )
            if existing_assignment is not None:
                if tuple(existing_assignment) == expected_assignment:
                    return application_id
                raise FenceError(
                    "application already has a different immutable strategy assignment"
                )
            self.connection.execute(
                """
                INSERT INTO application_strategy_assignments
                  (application_id, strategy_generation_id, capture_status, source,
                   query_family, rank_config_json, role_family, material_variant,
                   message_variant, model_route, prompt_sha256, material_sha256,
                   assigned_at)
                VALUES (?, ?, 'captured', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    strategy_generation_id,
                    source.strip(),
                    query_family.strip(),
                    rank_config_json,
                    role_family.strip(),
                    material_variant.strip(),
                    message_variant.strip(),
                    model_route.strip(),
                    prompt_sha256,
                    material_sha256,
                    _now(),
                ),
            )
        return application_id

    def reject_excluded_employers(
        self, exclusions: set[str] | frozenset[str] | None = None
    ) -> list[dict[str, str]]:
        """Quarantine pre-submit rows for every hard-excluded employer.

        Terminal history (``submitted`` and ``submit_unknown``) is immutable
        evidence and is deliberately not changed.  The default exclusions are
        always applied; the private profile can add aliases for this run.
        """
        names = frozenset(DEFAULT_EMPLOYER_EXCLUSIONS)
        if exclusions:
            names = names | frozenset(str(value) for value in exclusions)
        rows = self.connection.execute(
            """
            SELECT id, company, title, current_state
            FROM applications
            WHERE current_state IN ('discovered', 'qualified', 'materials_ready', 'not_submitted')
            ORDER BY created_at, rowid
            """
        ).fetchall()
        rejected: list[dict[str, str]] = []
        with self._transaction():
            for row in rows:
                company = str(row["company"])
                if not is_excluded_employer(company, names):
                    continue
                application_id = str(row["id"])
                self._transition_in_transaction(
                    application_id,
                    "rejected",
                    {"reason": "employer_excluded", "company": company},
                )
                rejected.append(
                    {
                        "application_id": application_id,
                        "company": company,
                        "title": str(row["title"]),
                        "from_state": str(row["current_state"]),
                    }
                )
        return rejected

    def strategy_assignment(self, application_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
              application_id, strategy_generation_id, capture_status, source,
              query_family, rank_config_json, role_family, material_variant,
              message_variant, model_route, prompt_sha256, material_sha256
            FROM application_strategy_assignments
            WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
        if row is None:
            raise KeyError(application_id)
        return {
            "application_id": str(row["application_id"]),
            "strategy_generation_id": str(row["strategy_generation_id"]),
            "capture_status": str(row["capture_status"]),
            "source": str(row["source"]),
            "query_family": str(row["query_family"]),
            "rank_config": (
                json.loads(str(row["rank_config_json"]))
                if row["rank_config_json"] is not None
                else None
            ),
            "role_family": str(row["role_family"]),
            "material_variant": str(row["material_variant"]),
            "message_variant": str(row["message_variant"]),
            "model_route": str(row["model_route"]),
            "prompt_sha256": (
                str(row["prompt_sha256"])
                if row["prompt_sha256"] is not None
                else None
            ),
            "material_sha256": (
                str(row["material_sha256"])
                if row["material_sha256"] is not None
                else None
            ),
        }

    def record_funnel_outcome(
        self,
        *,
        application_id: str,
        funnel_stage: str,
        disposition: str,
        evidence_source: str,
        evidence_sha256: str,
        occurred_at: str,
        observed_at: str,
        observation_policy_version: str | None = None,
    ) -> str:
        if funnel_stage not in FUNNEL_STAGES:
            raise ValueError("invalid funnel stage")
        if disposition not in FUNNEL_DISPOSITIONS:
            raise ValueError("invalid funnel disposition")
        if evidence_source not in AUTHORITATIVE_EVIDENCE_SOURCES:
            raise ValueError("outcome evidence source is not authoritative")
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256):
            raise ValueError("evidence_sha256 must be a lowercase SHA-256")
        if disposition == "negative" and (
            not isinstance(observation_policy_version, str)
            or not observation_policy_version.strip()
        ):
            raise ValueError(
                "negative outcomes require a versioned observation policy"
            )
        parsed_times: dict[str, datetime] = {}
        for name, value in {
            "occurred_at": occurred_at,
            "observed_at": observed_at,
        }.items():
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError(f"{name} must be RFC3339") from error
            if parsed.tzinfo is None:
                raise ValueError(f"{name} must include a timezone")
            parsed_times[name] = parsed
        if parsed_times["observed_at"] < parsed_times["occurred_at"]:
            raise ValueError("observed_at cannot predate occurred_at")

        identity = {
            "application_id": application_id,
            "funnel_stage": funnel_stage,
            "disposition": disposition,
            "evidence_source": evidence_source,
            "evidence_sha256": evidence_sha256,
            "occurred_at": occurred_at,
            "observed_at": observed_at,
            "observation_policy_version": observation_policy_version,
        }
        encoded = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        outcome_id = f"outcome-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
        with self._transaction():
            recorded = self._record_funnel_outcome_in_transaction(
                outcome_id=outcome_id,
                **identity,
            )
            self._rebuild_strategy_outcome_projection_in_transaction()
            return recorded

    def _record_funnel_outcome_in_transaction(
        self,
        *,
        outcome_id: str,
        application_id: str,
        funnel_stage: str,
        disposition: str,
        evidence_source: str,
        evidence_sha256: str,
        occurred_at: str,
        observed_at: str,
        observation_policy_version: str | None,
    ) -> str:
        application = self.connection.execute(
            "SELECT id FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        if application is None:
            raise KeyError(application_id)
        bound_applications = {
            str(row["application_id"])
            for row in self.connection.execute(
                """
                SELECT DISTINCT application_id
                FROM funnel_outcomes
                WHERE evidence_sha256 = ?
                """,
                (evidence_sha256,),
            ).fetchall()
        }
        if bound_applications and bound_applications != {application_id}:
            raise FenceError(
                "external evidence is already bound to a different application"
            )
        existing = self.connection.execute(
            """
            SELECT
              outcome_id, application_id, funnel_stage, disposition,
              evidence_source, evidence_sha256, occurred_at, observed_at,
              observation_policy_version
            FROM funnel_outcomes
            WHERE application_id = ?
              AND funnel_stage = ?
              AND evidence_sha256 = ?
            """,
            (application_id, funnel_stage, evidence_sha256),
        ).fetchone()
        expected = (
            outcome_id,
            application_id,
            funnel_stage,
            disposition,
            evidence_source,
            evidence_sha256,
            occurred_at,
            observed_at,
            observation_policy_version,
        )
        if existing is not None:
            if tuple(existing) == expected:
                return outcome_id
            raise FenceError(
                "external evidence is already bound to a different outcome"
            )
        self.connection.execute(
            """
            INSERT INTO funnel_outcomes
              (outcome_id, application_id, funnel_stage, disposition,
               evidence_source, evidence_sha256, occurred_at, observed_at,
               observation_policy_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*expected, _now()),
        )
        return outcome_id

    def funnel_outcomes(self, application_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
              outcome_id, application_id, funnel_stage, disposition,
              evidence_source, evidence_sha256, occurred_at, observed_at,
              observation_policy_version
            FROM funnel_outcomes
            WHERE application_id = ?
            ORDER BY occurred_at, outcome_id
            """,
            (application_id,),
        ).fetchall()
        return [
            {
                "outcome_id": str(row["outcome_id"]),
                "application_id": str(row["application_id"]),
                "funnel_stage": str(row["funnel_stage"]),
                "disposition": str(row["disposition"]),
                "evidence_source": str(row["evidence_source"]),
                "evidence_sha256": str(row["evidence_sha256"]),
                "occurred_at": str(row["occurred_at"]),
                "observed_at": str(row["observed_at"]),
                "observation_policy_version": (
                    str(row["observation_policy_version"])
                    if row["observation_policy_version"] is not None
                    else None
                ),
            }
            for row in rows
        ]

    def rebuild_strategy_outcome_projection(self) -> list[dict[str, Any]]:
        with self._transaction():
            self._rebuild_strategy_outcome_projection_in_transaction()
        return self.strategy_outcome_projection()

    def _rebuild_strategy_outcome_projection_in_transaction(self) -> None:
        self.connection.execute("DELETE FROM strategy_outcome_projection")
        self.connection.execute(
            """
            INSERT INTO strategy_outcome_projection
              (strategy_generation_id, funnel_stage, positive_count,
               negative_count, resolved_count)
            SELECT
              assignments.strategy_generation_id,
              outcomes.funnel_stage,
              SUM(CASE WHEN outcomes.disposition = 'positive' THEN 1 ELSE 0 END),
              SUM(CASE WHEN outcomes.disposition = 'negative' THEN 1 ELSE 0 END),
              COUNT(*)
            FROM funnel_outcomes AS outcomes
            JOIN application_strategy_assignments AS assignments
              ON assignments.application_id = outcomes.application_id
            GROUP BY assignments.strategy_generation_id, outcomes.funnel_stage
            """
        )

    def strategy_outcome_projection(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
              strategy_generation_id, funnel_stage, positive_count,
              negative_count, resolved_count
            FROM strategy_outcome_projection
            ORDER BY strategy_generation_id, funnel_stage
            """
        ).fetchall()
        return [
            {
                "strategy_generation_id": str(row["strategy_generation_id"]),
                "funnel_stage": str(row["funnel_stage"]),
                "positive_count": int(row["positive_count"]),
                "negative_count": int(row["negative_count"]),
                "resolved_count": int(row["resolved_count"]),
            }
            for row in rows
        ]

    def current_state(self, application_id: str) -> str:
        row = self.connection.execute(
            "SELECT current_state FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        if row is None:
            raise KeyError(application_id)
        return str(row["current_state"])

    def daily_slot_count(self, japan_day: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM daily_slots WHERE japan_day = ?",
            (japan_day,),
        ).fetchone()
        return int(row["count"])

    def _transition_in_transaction(
        self,
        application_id: str,
        to_state: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        from_state = self.current_state(application_id)
        validate_transition(from_state, to_state)
        # The applications_state_requires_event trigger validates the new state
        # against the latest event. Append first, then mutate the projection in
        # the same transaction so the trigger observes the matching event.
        self._append_event(application_id, from_state, to_state, payload)
        self.connection.execute(
            "UPDATE applications SET current_state = ? WHERE id = ?",
            (to_state, application_id),
        )

    def transition(
        self,
        application_id: str,
        to_state: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._transaction():
            self._transition_in_transaction(application_id, to_state, payload)

    def events(self, application_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT event_id, from_state, to_state, payload_json, created_at
            FROM events WHERE application_id = ? ORDER BY rowid
            """,
            (application_id,),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def record_strategy_generation(
        self,
        strategy: Mapping[str, Any],
        *,
        parent_generation_id: str | None = None,
        changed_field: str | None = None,
    ) -> str:
        if not isinstance(strategy, Mapping) or not strategy:
            raise ValueError("strategy generation must be a non-empty mapping")
        if (parent_generation_id is None) != (changed_field is None):
            raise ValueError(
                "parent_generation_id and changed_field must be provided together"
            )
        strategy_json = json.dumps(
            dict(strategy),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        strategy_sha256 = hashlib.sha256(strategy_json.encode("utf-8")).hexdigest()
        generation_id = f"strategy-{strategy_sha256}"
        with self._transaction():
            if parent_generation_id is not None:
                parent = self.connection.execute(
                    """
                    SELECT strategy_json
                    FROM strategy_generations
                    WHERE strategy_generation_id = ?
                    """,
                    (parent_generation_id,),
                ).fetchone()
                if parent is None:
                    raise ValueError("parent strategy generation does not exist")
                parent_strategy = json.loads(str(parent["strategy_json"]))
                changed = {
                    key
                    for key in set(parent_strategy) | set(strategy)
                    if parent_strategy.get(key) != strategy.get(key)
                }
                if changed != {changed_field}:
                    raise ValueError(
                        "candidate must change exactly the declared strategy field"
                    )
            self.connection.execute(
                """
                INSERT OR IGNORE INTO strategy_generations
                  (strategy_generation_id, parent_generation_id, changed_field,
                   strategy_json, strategy_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    generation_id,
                    parent_generation_id,
                    changed_field,
                    strategy_json,
                    strategy_sha256,
                    _now(),
                ),
            )
            recorded = self.connection.execute(
                """
                SELECT parent_generation_id, changed_field
                FROM strategy_generations
                WHERE strategy_generation_id = ?
                """,
                (generation_id,),
            ).fetchone()
            if (
                recorded["parent_generation_id"] != parent_generation_id
                or recorded["changed_field"] != changed_field
            ):
                raise FenceError(
                    "strategy content is already bound to different lineage"
                )
        return generation_id

    def application_summary_rows(self) -> list[dict[str, str | None]]:
        rows = self.connection.execute(
            """
            SELECT
              applications.canonical_url,
              applications.current_state,
              submit_intents.status AS submission_state
            FROM applications
            LEFT JOIN submit_intents
              ON submit_intents.application_id = applications.id
            ORDER BY applications.created_at, applications.rowid
            """
        ).fetchall()
        return [
            {
                "canonical_url": str(row["canonical_url"]),
                "current_state": str(row["current_state"]),
                "submission_state": (
                    str(row["submission_state"])
                    if row["submission_state"] is not None
                    else None
                ),
            }
            for row in rows
        ]

    def event_summary_rows(self) -> list[dict[str, Any]]:
        has_application_routes = self.connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='application_routes'"
        ).fetchone() is not None
        applications = self.connection.execute(
            "SELECT id, canonical_url, owner FROM applications ORDER BY created_at, rowid"
        ).fetchall()
        projection: list[dict[str, Any]] = []
        for application in applications:
            rows = self.connection.execute(
                "SELECT from_state, to_state, payload_json FROM events "
                "WHERE application_id = ? ORDER BY rowid",
                (application["id"],),
            ).fetchall()
            if not rows or rows[0]["from_state"] is not None:
                raise FenceError("application event chain lacks a valid origin")
            first_state = str(rows[0]["to_state"])
            first_payload = json.loads(str(rows[0]["payload_json"]))
            external_origin = first_state == "submitted" and (
                first_payload.get("external_import") is True
                and all(
                    first_payload.get(key)
                    for key in (
                        "applied_at",
                        "source",
                        "source_message_id",
                        "evidence_sha256",
                    )
                )
            )
            if first_state != "discovered" and not external_origin:
                raise FenceError("application event chain lacks a valid origin")
            previous = first_state
            previous_payload = first_payload
            ever_submitted = first_state == "submitted"
            submission_attempted = first_state in {"submitted", "submit_unknown"}
            for event in rows[1:]:
                to_state = str(event["to_state"])
                payload = json.loads(str(event["payload_json"]))
                outreach_correction = False
                if str(event["from_state"]) != previous:
                    raise FenceError("application event chain is discontinuous")
                if previous == "submit_unknown" and to_state == "submitted":
                    receipt_verified = all(
                        payload.get(key)
                        for key in (
                            "message_id",
                            "thread_id",
                            "evidence_sha256",
                            "received_at",
                        )
                    )
                    legacy_ashby_verified = False
                    if (
                        payload.get("evidence_source")
                        == "ashby_graphql_plus_visible_success"
                        and payload.get("evidence_sha256")
                        == "e73a212752d3ca020b16bae36ca19578ba437dcf434b054daff414e467cb430b"
                    ):
                        legacy_ashby_verified = self.connection.execute(
                            "SELECT 1 FROM submit_intents WHERE intent_id=? "
                            "AND application_id=? AND fence=? AND status='submitted'",
                            (
                                payload.get("intent_id"),
                                application["id"],
                                payload.get("fence"),
                            ),
                        ).fetchone() is not None
                    route_verified = False
                    if has_application_routes and all(
                        payload.get(key)
                        for key in ("route_id", "provider_id", "channel")
                    ):
                        route_verified = self.connection.execute(
                            """
                            SELECT 1
                            FROM application_routes AS routes
                            JOIN funnel_outcomes AS outcomes
                              ON outcomes.application_id = routes.application_id
                             AND outcomes.evidence_sha256 = routes.delivery_evidence_sha256
                            WHERE routes.route_id = ?
                              AND routes.application_id = ?
                              AND routes.route_kind = ?
                              AND routes.delivery_state = 'delivered'
                              AND routes.provider_id = ?
                              AND outcomes.funnel_stage = 'confirmed_application'
                              AND outcomes.disposition = 'positive'
                              AND outcomes.evidence_source IN ('ats','gmail')
                            """,
                            (
                                payload.get("route_id"),
                                application["id"],
                                payload.get("channel"),
                                payload.get("provider_id"),
                            ),
                        ).fetchone() is not None
                    if not (
                        receipt_verified
                        or legacy_ashby_verified
                        or route_verified
                    ):
                        raise FenceError("late confirmation event lacks evidence")
                elif previous == "not_submitted" and to_state == "submitted":
                    receipt_fields = (
                        "intent_id",
                        "message_id",
                        "thread_id",
                        "evidence_sha256",
                        "received_at",
                        "prior_ui_evidence_sha256",
                    )
                    prior_ui_verified = (
                        payload.get("intent_id") == previous_payload.get("intent_id")
                        and payload.get("prior_ui_evidence_class")
                        == previous_payload.get("evidence_class")
                        == "rendered_validation_rejection"
                        and payload.get("prior_ui_evidence_sha256")
                        == previous_payload.get("evidence_sha256")
                    )
                    confirmation = self.connection.execute(
                        """
                        SELECT 1
                        FROM submission_confirmations AS confirmations
                        JOIN submit_intents AS intents
                          ON intents.intent_id = confirmations.intent_id
                        WHERE confirmations.intent_id = ?
                          AND confirmations.message_id = ?
                          AND confirmations.thread_id = ?
                          AND confirmations.evidence_sha256 = ?
                          AND confirmations.received_at = ?
                          AND intents.application_id = ?
                          AND intents.status = 'submitted'
                        """,
                        (
                            payload.get("intent_id"),
                            payload.get("message_id"),
                            payload.get("thread_id"),
                            payload.get("evidence_sha256"),
                            payload.get("received_at"),
                            application["id"],
                        ),
                    ).fetchone()
                    if not (
                        all(
                            isinstance(payload.get(key), str)
                            and payload[key]
                            for key in receipt_fields
                        )
                        and re.fullmatch(
                            r"[a-f0-9]{64}", payload["evidence_sha256"]
                        )
                        and re.fullmatch(
                            r"[a-f0-9]{64}", payload["prior_ui_evidence_sha256"]
                        )
                        and prior_ui_verified
                        and confirmation is not None
                    ):
                        raise FenceError("late confirmation event lacks evidence")
                elif previous == "submitted" and to_state == "submit_unknown":
                    route_id = payload.get("route_id")
                    provider_id = payload.get("provider_id")
                    evidence_sha256 = payload.get("evidence_sha256")
                    correction_verified = (
                        payload.get("reason") == "outreach_only_delivery_correction"
                        and previous_payload.get("route_id") == route_id
                        and previous_payload.get("provider_id") == provider_id
                        and previous_payload.get("channel") == "recruiting_outreach"
                        and self.connection.execute(
                            """
                            SELECT 1 FROM application_routes
                            WHERE route_id=? AND application_id=?
                              AND route_kind='recruiting_outreach'
                              AND recipient_acceptance='outreach_only'
                              AND delivery_state='delivered'
                              AND provider_id=?
                              AND delivery_evidence_sha256=?
                            """,
                            (
                                route_id,
                                application["id"],
                                provider_id,
                                evidence_sha256,
                            ),
                        ).fetchone()
                        is not None
                    )
                    if not correction_verified:
                        raise FenceError("outreach truth correction lacks evidence")
                    outreach_correction = True
                else:
                    validate_transition(previous, to_state)
                previous = to_state
                previous_payload = payload
                ever_submitted = ever_submitted or to_state == "submitted"
                if outreach_correction:
                    ever_submitted = False
                submission_attempted = submission_attempted or to_state in {
                    "submitted",
                    "submit_unknown",
                }
            positive_query = (
                """
                    SELECT outcomes.funnel_stage
                    FROM funnel_outcomes AS outcomes
                    WHERE outcomes.application_id = ?
                      AND outcomes.disposition = 'positive'
                      AND NOT (
                        outcomes.funnel_stage = 'confirmed_application'
                        AND EXISTS (
                          SELECT 1
                          FROM application_routes AS routes
                          WHERE routes.application_id = outcomes.application_id
                            AND routes.delivery_state = 'delivered'
                            AND routes.recipient_acceptance = 'outreach_only'
                            AND routes.delivery_evidence_sha256 = outcomes.evidence_sha256
                        )
                      )
                    """
                if has_application_routes
                else "SELECT funnel_stage FROM funnel_outcomes "
                "WHERE application_id=? AND disposition='positive'"
            )
            positive_stages = {
                str(row["funnel_stage"])
                for row in self.connection.execute(
                    positive_query,
                    (application["id"],),
                ).fetchall()
            }
            projection.append(
                {
                    "application_id": str(application["id"]),
                    "canonical_url": str(application["canonical_url"]),
                    "owner": str(application["owner"]),
                    "current_state": previous,
                    "ever_submitted": ever_submitted,
                    "submission_attempted": submission_attempted,
                    "positive_funnel_stages": sorted(positive_stages),
                }
            )
        return projection

    def retryable_applications(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
              applications.id AS application_id,
              applications.company,
              applications.title,
              applications.canonical_url,
              submit_intents.intent_id,
              submit_intents.fence
            FROM submit_intents
            JOIN applications ON applications.id = submit_intents.application_id
            WHERE (
                    submit_intents.status = 'not_submitted'
                AND applications.current_state = 'not_submitted'
              ) OR (
                    submit_intents.status = 'submit_claimed'
                AND applications.current_state = 'submit_claimed'
                AND NOT EXISTS (
                    SELECT 1
                    FROM submission_click_phases
                    WHERE submission_click_phases.intent_id = submit_intents.intent_id
                      AND submission_click_phases.fence = submit_intents.fence
                      AND submission_click_phases.phase IN ('clicked', 'confirmed')
                )
              )
            ORDER BY submit_intents.completed_at, submit_intents.rowid
            """
        ).fetchall()
        return [
            {
                "application_id": str(row["application_id"]),
                "company": str(row["company"]),
                "title": str(row["title"]),
                "canonical_url": str(row["canonical_url"]),
                "intent_id": str(row["intent_id"]),
                "fence": int(row["fence"]),
            }
            for row in rows
        ]

    def pending_materials_ready_applications(self) -> list[dict[str, Any]]:
        """Return attributed jobs ready for a first submit claim.

        A materials-ready row with no submit intent is durable work left by a
        previous pass.  The resident daily owner consumes these rows before
        discovering new URLs so a recovered application cannot be stranded by
        the discovery order.
        """
        rows = self.connection.execute(
            """
            SELECT
              applications.id AS application_id,
              applications.company,
              applications.title,
              applications.canonical_url
            FROM applications
            WHERE applications.current_state = 'materials_ready'
              AND NOT EXISTS (
                SELECT 1
                FROM submit_intents
                WHERE submit_intents.application_id = applications.id
              )
            ORDER BY applications.created_at, applications.rowid
            """
        ).fetchall()
        return [
            {
                "application_id": str(row["application_id"]),
                "company": str(row["company"]),
                "title": str(row["title"]),
                "canonical_url": str(row["canonical_url"]),
            }
            for row in rows
        ]

    def superseded_workday_fit_rejections(
        self, policy_version: str
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT applications.id AS application_id, applications.company,
                   applications.title, applications.canonical_url
            FROM applications
            JOIN workday_fit_decisions
              ON workday_fit_decisions.application_id = applications.id
            WHERE applications.current_state = 'rejected'
              AND workday_fit_decisions.decision = 'rejected'
              AND COALESCE(workday_fit_decisions.policy_version, '') != ?
              AND NOT EXISTS (
                SELECT 1 FROM submit_intents
                WHERE submit_intents.application_id = applications.id
              )
            ORDER BY applications.created_at, applications.rowid
            """,
            (policy_version,),
        ).fetchall()
        return [dict(row) for row in rows]

    def workday_fit_qualified(
        self,
        application_id: str,
        policy_version: str | None = None,
    ) -> bool:
        row = self.connection.execute(
            """
            SELECT decision, policy_version
            FROM workday_fit_decisions
            WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
        return (
            row is not None
            and str(row["decision"]) == "qualified"
            and (
                policy_version is None
                or str(row["policy_version"] or "") == policy_version
            )
        )

    def record_workday_fit_decision(
        self,
        application_id: str,
        decision: str,
        evidence_sha256: str,
        *,
        policy_version: str,
    ) -> None:
        if decision not in {"qualified", "rejected", "hold"}:
            raise ValueError("invalid Workday fit decision")
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256):
            raise ValueError("Workday fit evidence must be a lowercase SHA-256")
        with self._transaction():
            self.connection.execute(
                """
                INSERT INTO workday_fit_decisions
                  (application_id, decision, evidence_sha256, policy_version, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(application_id) DO UPDATE SET
                  decision = excluded.decision,
                  evidence_sha256 = excluded.evidence_sha256,
                  policy_version = excluded.policy_version,
                  created_at = excluded.created_at
                WHERE workday_fit_decisions.decision IN ('hold', 'rejected', 'qualified')
                  AND COALESCE(workday_fit_decisions.policy_version, '') != excluded.policy_version
                """,
                (application_id, decision, evidence_sha256, policy_version, _now()),
            )
            if decision == "rejected":
                if self.current_state(application_id) != "rejected":
                    self._transition_in_transaction(
                        application_id,
                        "rejected",
                        {
                            "reason": "model_workday_fit_rejected",
                            "evidence_sha256": evidence_sha256,
                        },
                    )
            elif decision == "qualified" and self.current_state(application_id) == "rejected":
                self._transition_in_transaction(
                    application_id,
                    "materials_ready",
                    {
                        "reason": "workday_fit_policy_superseded",
                        "policy_version": policy_version,
                        "evidence_sha256": evidence_sha256,
                    },
                )

    def submission_attempts(self, application_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
              intent_id, fence, payload_hash, resume_path, resume_sha256,
              ats_snapshot_path, ats_snapshot_sha256, japan_day, slot,
              status, created_at, completed_at
            FROM submission_attempts
            WHERE application_id = ?
            ORDER BY fence
            """,
            (application_id,),
        ).fetchall()
        return [
            {
                "intent_id": str(row["intent_id"]),
                "fence": int(row["fence"]),
                "payload_hash": str(row["payload_hash"]),
                "resume_path": row["resume_path"],
                "resume_sha256": row["resume_sha256"],
                "ats_snapshot_path": row["ats_snapshot_path"],
                "ats_snapshot_sha256": row["ats_snapshot_sha256"],
                "japan_day": str(row["japan_day"]),
                "slot": int(row["slot"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
                "completed_at": row["completed_at"],
            }
            for row in rows
        ]

    def claim_submission(
        self,
        application_id: str,
        japan_day: str,
        payload_hash: str,
        *,
        resume_path: Path,
        resume_sha256: str,
        ats_snapshot_path: Path,
        ats_snapshot_sha256: str,
        final_review_receipt_sha256: str | None = None,
        observed_at: str | None = None,
    ) -> SubmitIntent | None:
        resolved_resume = Path(resume_path).expanduser().resolve()
        if not resolved_resume.is_file():
            raise ValueError(f"resume is not a file: {resolved_resume}")
        actual_resume_sha256 = hashlib.sha256(resolved_resume.read_bytes()).hexdigest()
        if actual_resume_sha256 != resume_sha256:
            raise ValueError("resume SHA-256 does not match the selected file")
        resolved_snapshot = Path(ats_snapshot_path).expanduser().resolve()
        if not resolved_snapshot.is_file():
            raise ValueError(
                f"ATS snapshot SHA-256 cannot be verified: not a file: {resolved_snapshot}"
            )
        snapshot_bytes = resolved_snapshot.read_bytes()
        actual_snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        if actual_snapshot_sha256 != ats_snapshot_sha256:
            raise ValueError("ATS snapshot SHA-256 does not match the selected file")
        try:
            snapshot = json.loads(snapshot_bytes)
            snapshot_evaluation = evaluate_snapshot(snapshot)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"ATS snapshot is invalid: {error}") from error
        final_review = final_review_receipt_sha256 is not None
        if final_review:
            if not re.fullmatch(r"[a-f0-9]{64}", final_review_receipt_sha256 or ""):
                raise ValueError("final review receipt must be a lowercase SHA-256")
            labels = [
                " ".join(str(control.get("label") or control.get("text") or "").split()).casefold()
                for frame in snapshot.get("frames", [])
                for control in frame.get("controls", [])
            ]
            if sum(label in {"submit", "submit application", "送信", "応募を送信"} for label in labels) != 1:
                raise ValueError("final review snapshot requires exactly one submit control")
        else:
            if not snapshot_evaluation["ready"]:
                blockers = ",".join(snapshot_evaluation["blockers"])
                raise ValueError(f"ATS snapshot is not ready: {blockers}")
            if not snapshot_evaluation["claim_ready"]:
                raise ValueError("ATS snapshot is not claim-ready: application form not open")
        claimed_at = _now()
        if observed_at is not None:
            if not final_review:
                raise ValueError("observed_at is only valid with a final review receipt")
            observed = datetime.fromisoformat(observed_at)
            now = datetime.now(timezone.utc)
            if observed.tzinfo is None or observed > now or (now - observed).total_seconds() > 3600:
                raise ValueError("observed_at must be a recent timezone-aware timestamp")
            claimed_at = observed.isoformat()
        with self._transaction():
            application = self.connection.execute(
                "SELECT canonical_url FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if application is None:
                raise KeyError(application_id)
            if not same_application_surface(
                snapshot["url"], str(application["canonical_url"])
            ):
                raise ValueError("ATS snapshot URL does not match the application")
            existing = self.connection.execute(
                "SELECT * FROM submit_intents WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            current_state = self.current_state(application_id)
            reopening = (
                existing is not None
                and str(existing["status"]) == "not_submitted"
                and current_state == "not_submitted"
            )
            resuming = (
                existing is not None
                and str(existing["status"]) == "submit_claimed"
                and current_state == "submit_claimed"
                and self.connection.execute(
                    """
                    SELECT 1 FROM submission_click_phases
                    WHERE intent_id = ? AND fence = ?
                      AND phase IN ('clicked', 'confirmed')
                    """,
                    (str(existing["intent_id"]), int(existing["fence"])),
                ).fetchone()
                is None
            )
            if resuming:
                if (
                    str(existing["payload_hash"]) != payload_hash
                    or str(existing["resume_sha256"]) != resume_sha256
                ):
                    return None
                return SubmitIntent(
                    str(existing["intent_id"]),
                    application_id,
                    int(existing["fence"]),
                    str(existing["payload_hash"]),
                    str(existing["resume_path"]),
                    str(existing["resume_sha256"]),
                    str(existing["ats_snapshot_path"]),
                    str(existing["ats_snapshot_sha256"]),
                    str(existing["japan_day"]),
                    int(existing["slot"]),
                )
            if existing is not None and not reopening:
                return None
            if existing is None and current_state != "materials_ready":
                return None
            # Slots are transactional per-day audit labels, not a quota.
            # A definite pre-click `not_submitted` releases its row below;
            # BEGIN IMMEDIATE still makes max+1 deterministic and collision-free
            # among all live claims while submitted/unknown claims remain held.
            row = self.connection.execute(
                "SELECT COALESCE(MAX(slot), 0) AS max_slot "
                "FROM daily_slots WHERE japan_day = ?",
                (japan_day,),
            ).fetchone()
            slot = int(row["max_slot"]) + 1
            intent = SubmitIntent(
                intent_id=(
                    str(existing["intent_id"]) if reopening else uuid.uuid4().hex
                ),
                application_id=application_id,
                fence=(int(existing["fence"]) + 1 if reopening else 1),
                payload_hash=payload_hash,
                resume_path=str(resolved_resume),
                resume_sha256=resume_sha256,
                ats_snapshot_path=str(resolved_snapshot),
                ats_snapshot_sha256=ats_snapshot_sha256,
                japan_day=japan_day,
                slot=slot,
            )
            self.connection.execute(
                """
                INSERT INTO daily_slots (japan_day, slot, application_id, status)
                VALUES (?, ?, ?, 'claimed')
                """,
                (japan_day, slot, application_id),
            )
            if reopening:
                self.connection.execute(
                    """
                    UPDATE submit_intents
                    SET fence = ?, payload_hash = ?, resume_path = ?,
                        resume_sha256 = ?, ats_snapshot_path = ?,
                        ats_snapshot_sha256 = ?, japan_day = ?, slot = ?,
                        status = 'submit_claimed', created_at = ?,
                        completed_at = NULL
                    WHERE intent_id = ? AND fence = ? AND status = 'not_submitted'
                    """,
                    (
                        intent.fence,
                        intent.payload_hash,
                        intent.resume_path,
                        intent.resume_sha256,
                        intent.ats_snapshot_path,
                        intent.ats_snapshot_sha256,
                        intent.japan_day,
                        intent.slot,
                        claimed_at,
                        intent.intent_id,
                        int(existing["fence"]),
                    ),
                )
            else:
                self.connection.execute(
                    """
                    INSERT INTO submit_intents
                      (intent_id, application_id, fence, payload_hash, resume_path,
                       resume_sha256, ats_snapshot_path, ats_snapshot_sha256,
                       japan_day, slot, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submit_claimed', ?)
                    """,
                    (
                        intent.intent_id,
                        intent.application_id,
                        intent.fence,
                        intent.payload_hash,
                        intent.resume_path,
                        intent.resume_sha256,
                        intent.ats_snapshot_path,
                        intent.ats_snapshot_sha256,
                        intent.japan_day,
                        intent.slot,
                        claimed_at,
                    ),
                )
            self.connection.execute(
                """
                INSERT INTO submission_attempts
                  (intent_id, fence, application_id, payload_hash, resume_path,
                   resume_sha256, ats_snapshot_path, ats_snapshot_sha256,
                   japan_day, slot, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submit_claimed', ?)
                """,
                (
                    intent.intent_id,
                    intent.fence,
                    intent.application_id,
                    intent.payload_hash,
                    intent.resume_path,
                    intent.resume_sha256,
                    intent.ats_snapshot_path,
                    intent.ats_snapshot_sha256,
                    intent.japan_day,
                    intent.slot,
                    claimed_at,
                ),
            )
            self._transition_in_transaction(
                application_id,
                "submit_claimed",
                {
                    "intent_id": intent.intent_id,
                    "fence": intent.fence,
                    "payload_hash": payload_hash,
                    "resume_sha256": resume_sha256,
                    "ats_snapshot_sha256": ats_snapshot_sha256,
                },
            )
            return intent

    def complete_submission(
        self, intent_id: str, fence: int, outcome: str
    ) -> None:
        if outcome != "not_submitted":
            raise ValueError(
                "submitted and submit_unknown require verifier evidence"
            )
        self.complete_submission_verified(
            intent_id,
            fence,
            outcome="not_submitted",
            evidence_sha256=hashlib.sha256(
                f"legacy-pre-submit:{intent_id}:{fence}".encode()
            ).hexdigest(),
            evidence_class="definite_pre_submit_stop",
        )

    def complete_submission_verified(
        self,
        intent_id: str,
        fence: int,
        *,
        outcome: str,
        evidence_sha256: str,
        evidence_class: str,
    ) -> None:
        allowed = {
            "submitted": "exact_completion_ui",
            "submit_unknown": "no_authoritative_completion_ui",
            "not_submitted": "rendered_validation_rejection",
        }
        if allowed.get(outcome) != evidence_class and not (
            outcome == "not_submitted" and evidence_class == "definite_pre_submit_stop"
        ) and not (
            outcome == "submit_unknown"
            and evidence_class == "exact_completion_ui_pending_receipt"
        ):
            raise ValueError("outcome does not match authoritative evidence class")
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256):
            raise ValueError("outcome evidence must be a lowercase SHA-256")
        with self._transaction():
            row = self.connection.execute(
                "SELECT * FROM submit_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            if row is None or int(row["fence"]) != fence:
                raise FenceError("submission fence does not match")
            if row["status"] != "submit_claimed":
                raise FenceError("submission intent is already completed")
            completed_at = _now()
            self.connection.execute(
                """
                UPDATE submit_intents
                SET status = ?, completed_at = ?, outcome_evidence_sha256 = ?,
                    outcome_evidence_class = ?
                WHERE intent_id = ? AND fence = ?
                """,
                (
                    outcome, completed_at, evidence_sha256, evidence_class,
                    intent_id, fence,
                ),
            )
            self.connection.execute(
                """
                UPDATE submission_attempts
                SET status = ?, completed_at = ?, outcome_evidence_sha256 = ?,
                    outcome_evidence_class = ?
                WHERE intent_id = ? AND fence = ?
                """,
                (
                    outcome, completed_at, evidence_sha256, evidence_class,
                    intent_id, fence,
                ),
            )
            self.connection.execute(
                """
                UPDATE daily_slots SET status = ?
                WHERE japan_day = ? AND slot = ? AND application_id = ?
                """,
                (outcome, row["japan_day"], row["slot"], row["application_id"]),
            )
            self._transition_in_transaction(
                str(row["application_id"]),
                outcome,
                {
                    "intent_id": intent_id,
                    "fence": fence,
                    "evidence_sha256": evidence_sha256,
                    "evidence_class": evidence_class,
                },
            )
            if outcome == "not_submitted":
                self.connection.execute(
                    """
                    DELETE FROM daily_slots
                    WHERE japan_day = ? AND slot = ? AND application_id = ?
                    """,
                    (row["japan_day"], row["slot"], row["application_id"]),
                )

    def reconcile_submission_confirmation(
        self,
        *,
        intent_id: str,
        message_id: str,
        thread_id: str,
        evidence_sha256: str,
        received_at: str,
    ) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
            raise ValueError("invalid Gmail message ID")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
            raise ValueError("invalid Gmail thread ID")
        if not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256):
            raise ValueError("invalid confirmation evidence hash")
        try:
            received = datetime.fromisoformat(received_at)
        except ValueError as error:
            raise ValueError("received_at must be RFC3339") from error
        if received.tzinfo is None:
            raise ValueError("received_at must include a timezone")

        with self._transaction():
            existing_message = self.connection.execute(
                """
                SELECT thread_id, intent_id, evidence_sha256, received_at
                FROM submission_confirmations
                WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()
            if existing_message is not None:
                expected = (
                    thread_id,
                    intent_id,
                    evidence_sha256,
                    received_at,
                )
                actual = (
                    str(existing_message["thread_id"]),
                    str(existing_message["intent_id"]),
                    str(existing_message["evidence_sha256"]),
                    str(existing_message["received_at"]),
                )
                if actual != expected:
                    raise FenceError(
                        "Gmail message ID is already bound to different evidence"
                    )
                return "duplicate"

            existing_intent = self.connection.execute(
                """
                SELECT message_id
                FROM submission_confirmations
                WHERE intent_id = ?
                """,
                (intent_id,),
            ).fetchone()
            if existing_intent is not None:
                raise FenceError(
                    "submission intent already has a different confirmation"
                )

            row = self.connection.execute(
                """
                SELECT
                  submit_intents.*,
                  applications.current_state
                FROM submit_intents
                JOIN applications
                  ON applications.id = submit_intents.application_id
                WHERE submit_intents.intent_id = ?
                """,
                (intent_id,),
            ).fetchone()
            if row is None:
                raise FenceError("submission intent does not exist")
            prior_state = str(row['current_state'])
            correction = (str(row['status']) == prior_state == 'not_submitted'
                          and row['outcome_evidence_class'] == 'rendered_validation_rejection')
            if not correction and not (str(row['status']) == prior_state == 'submit_unknown'):
                raise FenceError('only an uncertain or false-negative UI application can be reconciled')
            intent_created = datetime.fromisoformat(str(row["created_at"]))
            if received < intent_created:
                raise FenceError("confirmation predates the submission intent")

            created_at = _now()
            self.connection.execute(
                """
                INSERT INTO submission_confirmations
                  (message_id, thread_id, intent_id, evidence_sha256,
                   received_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    thread_id,
                    intent_id,
                    evidence_sha256,
                    received_at,
                    created_at,
                ),
            )
            intent_update = self.connection.execute(
                """
                UPDATE submit_intents
                SET status = 'submitted'
                WHERE intent_id = ? AND status = ?
                """,
                (intent_id, prior_state),
            )
            attempt_update = self.connection.execute(
                """
                UPDATE submission_attempts
                SET status = 'submitted'
                WHERE intent_id = ? AND fence = ? AND status = ?
                """,
                (intent_id, int(row["fence"]), prior_state),
            )
            corrected_slot = int(row['slot'])
            if correction:
                occupied = {int(r[0]) for r in self.connection.execute(
                    'SELECT slot FROM daily_slots WHERE japan_day=?', (row['japan_day'],))}
                corrected_slot = 1
                while corrected_slot in occupied:
                    corrected_slot += 1
                slot_update = self.connection.execute(
                    "INSERT INTO daily_slots(japan_day,slot,application_id,status) VALUES(?,?,?,'submitted')",
                    (row['japan_day'], corrected_slot, row['application_id']))
                self.connection.execute('UPDATE submit_intents SET slot=? WHERE intent_id=?',
                    (corrected_slot, intent_id))
            else:
                slot_update = self.connection.execute(
                    """UPDATE daily_slots SET status='submitted'
                       WHERE japan_day=? AND slot=? AND application_id=? AND status='submit_unknown'""",
                    (row['japan_day'], row['slot'], row['application_id']))
            if (
                intent_update.rowcount != 1
                or attempt_update.rowcount != 1
                or slot_update.rowcount != 1
            ):
                raise FenceError("submission confirmation state is inconsistent")
            application_id = str(row["application_id"])
            self._append_event(
                application_id,
                prior_state,
                "submitted",
                {
                    "intent_id": intent_id,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "evidence_sha256": evidence_sha256,
                    "received_at": received_at,
                    "prior_ui_evidence_class": row['outcome_evidence_class'],
                    "prior_ui_evidence_sha256": row['outcome_evidence_sha256'],
                    "original_slot": row['slot'], "corrected_slot": corrected_slot,
                },
            )
            application_update = self.connection.execute(
                """
                UPDATE applications
                SET current_state = 'submitted'
                WHERE id = ? AND current_state = ?
                """,
                (application_id, prior_state),
            )
            if application_update.rowcount != 1:
                raise FenceError("application confirmation state is inconsistent")
            outcome_identity = {
                "application_id": application_id,
                "funnel_stage": "confirmed_application",
                "disposition": "positive",
                "evidence_source": "gmail",
                "evidence_sha256": evidence_sha256,
                "occurred_at": received_at,
                "observed_at": received_at,
                "observation_policy_version": None,
            }
            encoded_outcome = json.dumps(
                outcome_identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            self._record_funnel_outcome_in_transaction(
                outcome_id=(
                    "outcome-"
                    + hashlib.sha256(
                        encoded_outcome.encode("utf-8")
                    ).hexdigest()
                ),
                **outcome_identity,
            )
            self._rebuild_strategy_outcome_projection_in_transaction()
            return "reconciled"

    def submitted_resume_reports(self) -> list[dict[str, str]]:
        rows = self.connection.execute(
            """
            SELECT
              applications.id AS application_id,
              applications.company,
              applications.title,
              applications.canonical_url,
              submit_intents.resume_path,
              submit_intents.resume_sha256
            FROM submit_intents
            JOIN applications ON applications.id = submit_intents.application_id
            WHERE submit_intents.status = 'submitted'
              AND submit_intents.resume_path IS NOT NULL
              AND submit_intents.resume_sha256 IS NOT NULL
            ORDER BY submit_intents.completed_at, submit_intents.rowid
            """
        ).fetchall()
        return [
            {
                "application_id": str(row["application_id"]),
                "company": str(row["company"]),
                "title": str(row["title"]),
                "canonical_url": str(row["canonical_url"]),
                "resume_path": str(row["resume_path"]),
                "resume_sha256": str(row["resume_sha256"]),
            }
            for row in rows
        ]
