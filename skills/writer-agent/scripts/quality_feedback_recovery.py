#!/usr/bin/env python3
"""One bounded research recovery for an unpublished replacement quality block."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from article_generation_state import ledger_has_public_effect


# Provider/research retries are separate from the single quality assessment.
# A transient transport outage must not consume the quality iteration budget.
# Recovery/provider retries are separate from the single quality assessment.
# A bounded terminal block caused by local infrastructure must be reopenable
# without deleting its receipts or consuming a quality iteration.
MAX_INVOCATIONS = 20
MAX_PUBLICATION_HANDOFFS = 2
STATE_NAME = "quality-feedback-recovery-state.json"


class QualityFeedbackRecoveryError(ValueError):
    """The run cannot safely enter or advance feedback recovery."""


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _receipt_hash(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "receipt_sha256"}
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _quality_attempt_count_for_run(run_dir: Path) -> int:
    return sum(
        1
        for path in (run_dir / "gates").glob("quality-self-heal-attempt-*.json")
        if path.is_file() and not path.is_symlink()
    )


def _record_feedback_invocation(
    run_dir: Path,
    state: dict[str, Any],
    *,
    recovery_attempt: int,
    owner_pid: int,
) -> None:
    """Persist the wrapper's hash-bound proof that a new model call was launched."""
    quality_attempt = _quality_attempt_count_for_run(run_dir) + 1
    if quality_attempt <= 1:
        return
    prompt_sha256 = str(state.get("prompt_sha256", ""))
    feedback_plan_sha256 = str(state.get("feedback_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", prompt_sha256) or not re.fullmatch(
        r"[0-9a-f]{64}", feedback_plan_sha256
    ):
        raise QualityFeedbackRecoveryError("feedback-invocation-input-hash-invalid")
    started_at = str(state.get("started_at", ""))
    iteration_feedback_plan_sha256 = hashlib.sha256(
        json.dumps(
            {
                "quality_attempt": quality_attempt,
                "recovery_attempt": recovery_attempt,
                "prompt_sha256": prompt_sha256,
                "feedback_plan_sha256": feedback_plan_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    previous_path = run_dir / "gates" / (
        f"quality-feedback-invocation-attempt-{quality_attempt - 1}.json"
    )
    previous_receipt_sha256 = None
    if quality_attempt > 2:
        previous = _read_json(previous_path)
        if previous is None or previous.get("receipt_sha256") != _receipt_hash(previous):
            raise QualityFeedbackRecoveryError("previous-feedback-invocation-invalid")
        previous_receipt_sha256 = _sha256(previous_path)
    value = {
        "version": 1,
        "run_id": run_dir.name,
        "quality_attempt": quality_attempt,
        "recovery_attempt": recovery_attempt,
        "owner_pid": owner_pid,
        "started_at": started_at,
        "prompt_sha256": prompt_sha256,
        "feedback_plan_sha256": feedback_plan_sha256,
        "iteration_feedback_plan_sha256": iteration_feedback_plan_sha256,
        "previous_feedback_invocation_sha256": previous_receipt_sha256,
    }
    value["receipt_sha256"] = _receipt_hash(value)
    path = run_dir / "gates" / f"quality-feedback-invocation-attempt-{quality_attempt}.json"
    if path.exists() or path.is_symlink():
        existing = _read_json(path)
        if path.is_symlink() or not path.is_file() or not isinstance(existing, dict):
            raise QualityFeedbackRecoveryError("feedback-invocation-receipt-conflict")
        if existing == value and _receipt_hash(existing) == value["receipt_sha256"]:
            return
        if (
            existing.get("version") != 1
            or existing.get("run_id") != run_dir.name
            or existing.get("quality_attempt") != quality_attempt
            or not isinstance(existing.get("recovery_attempt"), int)
            or existing.get("recovery_attempt", 0) < 1
            or existing.get("receipt_sha256") != _receipt_hash(existing)
        ):
            raise QualityFeedbackRecoveryError("feedback-invocation-receipt-conflict")
        # A provider can die after rewriting drafts but before quality_self_heal
        # records the next attempt. Preserve that real invocation, then let the
        # next bounded recovery own the canonical receipt for this quality attempt.
        archived = run_dir / "gates" / (
            f"quality-feedback-invocation-attempt-{quality_attempt}-"
            f"recovery-{existing.get('recovery_attempt', 'unknown')}.json"
        )
        if archived.exists():
            if archived.is_symlink() or not archived.is_file() or _read_json(archived) != existing:
                raise QualityFeedbackRecoveryError("feedback-invocation-archive-conflict")
        else:
            shutil.copy2(path, archived)
    _atomic_write(path, value)


def _refused(reason: str) -> dict[str, str]:
    return {"status": "REFUSED", "reason": reason}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _owner_is_alive(owner_pid: Any) -> bool:
    if not isinstance(owner_pid, int) or owner_pid <= 0:
        return False
    try:
        os.kill(owner_pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _age_seconds(timestamp: Any) -> float | None:
    if not isinstance(timestamp, str):
        return None
    try:
        started = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if started.tzinfo is None:
        return None
    return (datetime.now(timezone.utc) - started).total_seconds()


def _quality_attempt_count(gates: Path) -> int:
    return sum(
        1
        for path in gates.glob("quality-self-heal-attempt-*.json")
        if path.is_file() and not path.is_symlink()
    )


def _valid_reopen_defect(run_dir: Path, gates: Path, quality_attempts: int) -> bool:
    defect_path = gates / "quality-feedback-recovery-defect.json"
    if defect_path.is_symlink() or not defect_path.is_file():
        return False
    defect = _read_json(defect_path)
    if not isinstance(defect, dict):
        return False
    try:
        drafts = {}
        for lang in ("ja", "en"):
            draft = run_dir / f"article-{lang}.md"
            if draft.is_symlink() or not draft.is_file():
                return False
            drafts[lang] = _sha256(draft)
    except OSError:
        return False
    preserved = defect.get("preserved_invariants")
    return bool(
        defect.get("version") == 2
        and defect.get("status") == "blocked"
        and defect.get("run_id") == run_dir.name
        and defect.get("scope") == "bounded-feedback-recovery"
        and defect.get("quality_attempt") == quality_attempts
        and defect.get("draft_sha256") == drafts
        and isinstance(defect.get("observations"), list)
        and defect.get("observations")
        and all(
            isinstance(observation, dict)
            and isinstance(observation.get("return_code"), int)
            and (
                observation.get("quality_action") is None
                or observation.get("quality_action") in {
                    "block_freeze",
                    "ready_to_freeze",
                    "reroute",
                    "evaluate_reroute",
                    "force_publish_advisory",
                }
            )
            for observation in defect["observations"]
        )
        and isinstance(preserved, dict)
        and preserved.get("publication_or_staging_performed") is False
        and preserved.get("feedback_consumption_verification") == "PASS"
        and preserved.get("identity") == {"ja": "PASS", "en": "PASS"}
        and isinstance(preserved.get("reader"), dict)
        and set(preserved["reader"]) == {"ja", "en"}
        and all(value in {"PASS", "FAIL"} for value in preserved["reader"].values())
        and preserved.get("cta") == {"ja": "PASS", "en": "PASS"}
        and isinstance(defect.get("required_safe_next_action"), str)
        and bool(defect["required_safe_next_action"].strip())
    )


def _is_quality_audit(row: dict[str, Any]) -> bool:
    state = row.get("state")
    return bool(
        row.get("platform") == "quality"
        and row.get("published") is False
        and isinstance(state, str)
        and state.startswith("carry-over:quality-block:")
    )


def _feedback_for_terminal(gates: Path, run_id: str) -> dict[str, Any] | None:
    quality = _read_json(gates / "quality-self-heal.json")
    if (
        quality is None
        or quality.get("version") != 2
        or quality.get("action") not in {
            "block_freeze", "ready_to_freeze", "reroute", "evaluate_reroute",
            "force_publish_advisory",
        }
        or (
            quality.get("action") == "block_freeze"
            and int(quality.get("attempt", 0)) < 1
        )
        or (
            quality.get("action") == "ready_to_freeze"
            and quality.get("quality_advisory") is not True
        )
        or (
            quality.get("action") == "force_publish_advisory"
            and (
                quality.get("quality_advisory") is not True
                or quality.get("force_publish_after_iterations") != 1
            )
        )
        or quality.get("publication_policy") != "continuous"
        or not isinstance(quality.get("quality"), dict)
    ):
        return None
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from article_daily_start_control import (  # pylint: disable=import-outside-toplevel
        _quality_failure_feedback,
    )

    feedback = _quality_failure_feedback(gates, run_id, quality["quality"])
    if feedback is None:
        return None
    for lang in ("ja", "en"):
        draft = gates.parent / f"article-{lang}.md"
        if (
            draft.is_symlink()
            or not draft.is_file()
            or feedback["article_sha256"].get(lang) != _sha256(draft)
        ):
            return None
    return feedback


def _publication_handoff_ready(run_dir: Path) -> bool:
    gates = run_dir / "gates"
    quality = _read_json(gates / "quality-self-heal.json")
    if quality is None:
        return False
    attempt = quality.get("attempt")
    attempt_path = gates / f"quality-self-heal-attempt-{attempt}.json"
    if (
        not isinstance(attempt, int)
        or isinstance(attempt, bool)
        or attempt < 1
        or attempt_path.is_symlink()
        or _read_json(attempt_path) != quality
        or quality.get("receipt_sha256") != _receipt_hash(quality)
    ):
        return False
    force = (
        quality.get("action") == "force_publish_advisory"
        and quality.get("force_publish_after_iterations") == 1
        and quality.get("quality_advisory") is True
    )
    if force:
        try:
            from quality_self_heal import validate_force_receipt

            if not validate_force_receipt(
                run_dir,
                {
                    lang: run_dir / f"article-{lang}.md"
                    for lang in ("ja", "en")
                },
            ):
                return False
        except Exception:
            return False
    if quality.get("action") != "ready_to_freeze" and not force:
        return False
    languages = quality.get("quality")
    if not isinstance(languages, dict):
        return False
    for lang in ("ja", "en"):
        draft = run_dir / f"article-{lang}.md"
        receipt = languages.get(lang)
        if (
            draft.is_symlink()
            or not draft.is_file()
            or not isinstance(receipt, dict)
            or (
                not force
                and receipt.get("ready") is not True
            )
            or receipt.get("identity") != "PASS"
            or receipt.get("article_sha256") != _sha256(draft)
        ):
            return False
    initial_ready = bool(
        quality.get("action") == "ready_to_freeze"
        and quality.get("quality_feedback_consumption_sha256") is None
        and quality.get("feedback_invocation_sha256") is None
    )
    return force or initial_ready or validate_consumption(run_dir).get("status") == "PASS"


def plan(run_dir: Path | str, ledger: Path | str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    ledger = Path(ledger).resolve()
    gates = run_dir / "gates"
    if (
        run_dir.is_symlink()
        or gates.is_symlink()
        or not run_dir.is_dir()
        or not gates.is_dir()
    ):
        return _refused("run-directory-missing")
    publication_state = gates / "publication-state.json"
    if publication_state.exists() or publication_state.is_symlink():
        return _refused("publication-state-exists")
    if ledger_has_public_effect(ledger, run_dir.name):
        return _refused("ledger-row-exists")
    replacement = _read_json(gates / "quality-replacement.json")
    quality = _read_json(gates / "quality-self-heal.json")
    advisory_candidate = bool(
        isinstance(quality, dict)
        and quality.get("version") == 2
        and quality.get("publication_policy") == "continuous"
        and quality.get("action") in {
            "ready_to_freeze", "reroute", "evaluate_reroute", "block_freeze",
            "force_publish_advisory",
        }
        and (
            quality.get("action") != "force_publish_advisory"
            or (
                quality.get("quality_advisory") is True
                and quality.get("force_publish_after_iterations") == 1
            )
        )
    )
    if not (
        (
            replacement is not None
            and replacement.get("replacement_run_id") == run_dir.name
            and isinstance(replacement.get("replaced_run_id"), str)
        )
        or advisory_candidate
    ):
        return _refused("not-a-quality-replacement")
    prior_repair = _read_json(gates / "quality-repair-state.json")
    if prior_repair is not None:
        prior_status = prior_repair.get("status")
        if prior_status not in {"terminal-blocked", "terminal-incomplete"}:
            return _refused("prior-quality-repair-not-terminal")
        if prior_status == "terminal-incomplete" and not _publication_handoff_ready(run_dir):
            return _refused("prior-quality-repair-not-terminal")

    state_path = gates / STATE_NAME
    state = _read_json(state_path)
    if state is None and _publication_handoff_ready(run_dir):
        return {
            "status": "READY",
            "reason": "terminal-quality-publication-handoff",
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "attempts": 0,
            "publication_attempts": 0,
        }
    if state is not None:
        prompt = Path(str(state.get("prompt_path", "")))
        attempts = int(state.get("attempts", 0))
        publication_attempts = int(state.get("publication_attempts", 0))
        quality_attempt_count = _quality_attempt_count(gates)
        if (
            state.get("status")
            in {"terminal-blocked", "terminal-ready-not-published"}
            and _publication_handoff_ready(run_dir)
            and publication_attempts < MAX_PUBLICATION_HANDOFFS
        ):
            return {
                "status": "READY",
                "reason": "terminal-quality-publication-handoff",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "attempts": attempts,
                "publication_attempts": publication_attempts,
            }
        if (
            state.get("status")
            in {"publication-prepared", "publication-retryable-incomplete"}
            and publication_attempts < MAX_PUBLICATION_HANDOFFS
            and prompt.is_file()
            and state.get("prompt_sha256") == _sha256(prompt)
            and _publication_handoff_ready(run_dir)
        ):
            return {
                "status": "READY",
                "reason": "prepared-quality-publication-handoff",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "prompt_path": str(prompt),
                "prompt_sha256": state["prompt_sha256"],
                "attempts": attempts,
                "publication_attempts": publication_attempts,
            }
        if (
            state.get("status") in {"prepared", "retryable-incomplete"}
            and attempts < MAX_INVOCATIONS
            and prompt.is_file()
            and state.get("prompt_sha256") == _sha256(prompt)
        ):
            return {
                "status": "READY",
                "reason": "prepared-quality-feedback-recovery",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "prompt_path": str(prompt),
                "prompt_sha256": state["prompt_sha256"],
                "attempts": attempts,
            }
        if (
            state.get("status") == "terminal-blocked"
            and attempts < MAX_INVOCATIONS
            and quality_attempt_count < 5
            and _valid_reopen_defect(run_dir, gates, quality_attempt_count)
            and prompt.is_file()
            and state.get("prompt_sha256") == _sha256(prompt)
        ):
            return {
                "status": "READY",
                "reason": "reopen-quality-feedback-recovery-after-infrastructure-block",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "prompt_path": str(prompt),
                "prompt_sha256": state["prompt_sha256"],
                "attempts": attempts,
            }
        age = _age_seconds(state.get("started_at"))
        if (
            state.get("status") == "invoking"
            and attempts < MAX_INVOCATIONS
            and not _owner_is_alive(state.get("owner_pid"))
            and age is not None
            and age >= 60
            and prompt.is_file()
            and state.get("prompt_sha256") == _sha256(prompt)
        ):
            return {
                "status": "READY",
                "reason": "orphaned-quality-feedback-recovery",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "prompt_path": str(prompt),
                "prompt_sha256": state["prompt_sha256"],
                "attempts": attempts,
            }
        if (
            state.get("status") == "publication-invoking"
            and publication_attempts < MAX_PUBLICATION_HANDOFFS
            and not _owner_is_alive(state.get("owner_pid"))
            and age is not None
            and age >= 60
            and prompt.is_file()
            and state.get("prompt_sha256") == _sha256(prompt)
            and _publication_handoff_ready(run_dir)
        ):
            return {
                "status": "READY",
                "reason": "orphaned-quality-publication-handoff",
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "prompt_path": str(prompt),
                "prompt_sha256": state["prompt_sha256"],
                "attempts": attempts,
                "publication_attempts": publication_attempts,
            }
        return _refused(
            "quality-feedback-recovery-already-"
            + str(state.get("status", "unknown"))
        )

    feedback = _feedback_for_terminal(gates, run_dir.name)
    if feedback is None:
        return _refused("terminal-quality-feedback-invalid")
    return {
        "status": "READY",
        "reason": "terminal-quality-feedback",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "feedback": feedback,
    }


def _recovery_prompt(run_dir: Path, ledger: Path, feedback: Path) -> str:
    script = Path(__file__).resolve()
    return f"""Run ONE bounded feedback research recovery for this unpublished Writer run.

RUN_DIR={run_dir}
LEDGER={ledger}
FEEDBACK_PLAN={feedback}
ORIGINAL_PROMPT={run_dir / "article-daily-prompt.txt"}

Hard boundaries:
- This call must research each feedback item before rewriting either draft.
- Do not monitor or wait for the parent owner, recovery state, or this model process. The parent waits for this call; start research immediately.
- Do not create another run, choose another topic, weaken a gate, stage, or publish early.
- Keep gates/topic-route.json immutable. Add evidence under RUN_DIR/research/feedback-recovery/.
- Use primary sources where available. Never fabricate a quote, result, price, or experience.
- Write gates/quality-feedback-consumption.json with version=1, the exact feedback_plan_sha256, current JA/EN draft SHA-256 values, and exact-one item for every feedback ID. Each item needs feedback_id, source_name, https source_url, concrete evidence, and languages. Every source_url must appear in the final Sources block of each listed language.
- Rewrite both drafts from the researched evidence and a new outline. Then run the deterministic, editorial, identity, and reader gates for both current hashes.
- The recovery wrapper records a signed invocation receipt for this quality iteration; do not reuse a previous prompt, feedback plan, or draft bytes.
- Run quality_self_heal.py assess. A missing or incomplete consumption receipt must remain block_freeze.
- Run `python3 {script} verify --run-dir "$ARTICLE_RUN_DIR"` and require status=PASS.
- Run one quality assessment. Editorial/reader failure immediately returns force_publish_advisory and must not delay shipment; identity/safety/conscience, CTA, media, duplicate, and platform guards still block. If assess returns ready_to_freeze, every language record must be ready=true. In either case, verify must return PASS before reading ORIGINAL_PROMPT and continuing STEP 4.8 through STEP 20. Note remains ¥500 and both Substack posts remain paid-only. Require authenticated and public readback.
"""


def _publication_handoff_prompt(run_dir: Path, ledger: Path) -> str:
    hashes = {
        lang: _sha256(run_dir / f"article-{lang}.md") for lang in ("ja", "en")
    }
    return f"""Continue this exact unpublished Writer run from its frozen quality boundary.

RUN_DIR={run_dir}
LEDGER={ledger}
ORIGINAL_PROMPT={run_dir / "article-daily-prompt.txt"}
JA_SHA256={hashes["ja"]}
EN_SHA256={hashes["en"]}

Hard boundaries:
- Do not rewrite either frozen draft, research again, create another run, or choose another topic.
- Recheck both draft hashes and quality-self-heal action. A valid initial ready_to_freeze or single-evaluation force_publish_advisory receipt goes directly to publication without quality-feedback verification; only ready_to_freeze produced after feedback recovery still requires quality-feedback verification PASS before any side effect.
- Read ORIGINAL_PROMPT and execute only STEP 4.8 through STEP 20 for this same run.
- Reconcile existing publication and ledger receipts before every publish action. Never duplicate a remote post.
- Note remains ¥500 and both Substack posts remain paid-only.
- Require authenticated readback and public readback. Record exact live URLs; never claim an unavailable destination as published.
"""


def prepare_publication_handoff(
    run_dir: Path | str, ledger: Path | str
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    ledger = Path(ledger).resolve()
    decision = plan(run_dir, ledger)
    if (
        decision.get("status") != "READY"
        or decision.get("reason") != "terminal-quality-publication-handoff"
    ):
        raise QualityFeedbackRecoveryError(str(decision.get("reason", "not-ready")))
    state_path = run_dir / "gates" / STATE_NAME
    state = _read_json(state_path)
    if state is None:
        state = {
            "version": 1,
            "status": "terminal-ready-not-published",
            "run_id": run_dir.name,
            "attempts": 0,
            "publication_attempts": 0,
            "route_sha256": _sha256(run_dir / "gates/topic-route.json"),
        }
    recovery_root = run_dir / "gates/quality-feedback-recovery"
    if recovery_root.exists() and (
        recovery_root.is_symlink() or not recovery_root.is_dir()
    ):
        raise QualityFeedbackRecoveryError("publication-handoff-root-invalid")
    prompt_path = recovery_root / "epoch-1/publication-handoff.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if prompt_path.parent.is_symlink():
        raise QualityFeedbackRecoveryError("publication-handoff-directory-invalid")
    prompt_text = _publication_handoff_prompt(run_dir, ledger)
    if prompt_path.exists():
        if not prompt_path.is_file() or prompt_path.read_text(encoding="utf-8") != prompt_text:
            raise QualityFeedbackRecoveryError("publication-handoff-prompt-conflicts")
    else:
        prompt_path.write_text(prompt_text, encoding="utf-8")
    state.update(
        {
            "status": "publication-prepared",
            "phase": "publication-handoff",
            "publication_attempts": int(state.get("publication_attempts", 0)),
            "prompt_path": str(prompt_path),
            "prompt_sha256": _sha256(prompt_path),
        }
    )
    _atomic_write(state_path, state)
    return state


def begin(run_dir: Path | str, ledger: Path | str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    ledger = Path(ledger).resolve()
    decision = plan(run_dir, ledger)
    if (
        decision.get("status") != "READY"
        or decision.get("reason") != "terminal-quality-feedback"
    ):
        raise QualityFeedbackRecoveryError(
            str(decision.get("reason", "not-ready"))
        )
    gates = run_dir / "gates"
    feedback = dict(decision["feedback"])
    feedback["drafts"] = dict(feedback["article_sha256"])
    plan_path = gates / "quality-feedback-plan.json"
    _atomic_write(plan_path, feedback)
    prompt_path = gates / "quality-feedback-recovery/epoch-1/prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=False)
    prompt_path.write_text(
        _recovery_prompt(run_dir, ledger, plan_path),
        encoding="utf-8",
    )
    state = {
        "version": 1,
        "status": "prepared",
        "run_id": run_dir.name,
        "attempts": 0,
        "feedback_sha256": feedback["feedback_sha256"],
        "feedback_plan_path": str(plan_path),
        "route_sha256": _sha256(gates / "topic-route.json"),
        "prompt_path": str(prompt_path),
        "prompt_sha256": _sha256(prompt_path),
    }
    _atomic_write(gates / STATE_NAME, state)
    return state


def mark_invoking(
    run_dir: Path | str,
    ledger: Path | str,
    *,
    owner_pid: int,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    decision = plan(run_dir, ledger)
    if decision.get("status") != "READY" or decision.get("reason") not in {
        "prepared-quality-feedback-recovery",
        "reopen-quality-feedback-recovery-after-infrastructure-block",
        "orphaned-quality-feedback-recovery",
        "prepared-quality-publication-handoff",
        "orphaned-quality-publication-handoff",
    }:
        raise QualityFeedbackRecoveryError(
            str(decision.get("reason", "not-prepared"))
        )
    state_path = run_dir / "gates" / STATE_NAME
    state = _read_json(state_path)
    if state is None:
        raise QualityFeedbackRecoveryError("feedback-recovery-state-missing")
    if state.get("route_sha256") != _sha256(run_dir / "gates/topic-route.json"):
        raise QualityFeedbackRecoveryError("feedback-recovery-route-changed")
    publication_phase = decision.get("reason") in {
        "prepared-quality-publication-handoff",
        "orphaned-quality-publication-handoff",
    }
    if publication_phase:
        publication_attempts = int(state.get("publication_attempts", 0)) + 1
        if publication_attempts > MAX_PUBLICATION_HANDOFFS:
            raise QualityFeedbackRecoveryError("publication-handoff-attempt-limit")
        state.update(
            {
                "status": "publication-invoking",
                "phase": "publication-handoff",
                "publication_attempts": publication_attempts,
                "owner_pid": owner_pid,
                "started_at": _utc_now(),
            }
        )
        _atomic_write(state_path, state)
        return state
    attempts = int(state.get("attempts", 0)) + 1
    if attempts > MAX_INVOCATIONS:
        raise QualityFeedbackRecoveryError("feedback-recovery-attempt-limit")
    if attempts > 1:
        old_prompt = Path(str(state.get("prompt_path", "")))
        old_hash = str(state.get("prompt_sha256", ""))
        prompt_dir = run_dir / "gates/quality-feedback-recovery/epoch-1"
        archived = prompt_dir / f"prompt-attempt-{attempts - 1}.txt"
        if archived.exists():
            if not archived.is_file() or _sha256(archived) != old_hash:
                raise QualityFeedbackRecoveryError(
                    "feedback-recovery-prompt-archive-conflicts"
                )
        else:
            shutil.copy2(old_prompt, archived)
        if _sha256(archived) != old_hash:
            raise QualityFeedbackRecoveryError(
                "feedback-recovery-prompt-archive-mismatch"
            )
        feedback_plan = Path(str(state.get("feedback_plan_path", "")))
        new_prompt = prompt_dir / f"prompt-attempt-{attempts}.txt"
        new_prompt.write_text(
            _recovery_prompt(
                run_dir,
                Path(ledger).resolve(),
                feedback_plan,
            ),
            encoding="utf-8",
        )
        state.update(
            {
                "prompt_path": str(new_prompt),
                "prompt_sha256": _sha256(new_prompt),
            }
        )
    state.update(
        {
            "status": "invoking",
            "attempts": attempts,
            "owner_pid": owner_pid,
            "started_at": _utc_now(),
        }
    )
    _atomic_write(state_path, state)
    _record_feedback_invocation(
        run_dir,
        state,
        recovery_attempt=attempts,
        owner_pid=owner_pid,
    )
    return state


def validate_consumption(run_dir: Path | str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    gates = run_dir / "gates"
    state = _read_json(gates / STATE_NAME)
    feedback = _read_json(gates / "quality-feedback-plan.json")
    consumption = _read_json(gates / "quality-feedback-consumption.json")
    if state is None or feedback is None:
        return {"status": "FAIL", "reason": "feedback-plan-missing"}
    if consumption is None:
        return {"status": "FAIL", "reason": "feedback-consumption-missing"}
    if (
        feedback.get("feedback_sha256") != state.get("feedback_sha256")
        or consumption.get("feedback_plan_sha256")
        != state.get("feedback_sha256")
        or consumption.get("version") != 1
    ):
        return {"status": "FAIL", "reason": "feedback-consumption-identity-mismatch"}

    drafts: dict[str, str] = {}
    for lang in ("ja", "en"):
        path = run_dir / f"article-{lang}.md"
        if path.is_symlink() or not path.is_file():
            return {"status": "FAIL", "reason": f"draft-{lang}-missing"}
        drafts[lang] = _sha256(path)
    if consumption.get("drafts") != drafts:
        return {"status": "FAIL", "reason": "feedback-consumption-draft-mismatch"}

    planned_items = feedback.get("items")
    consumed_items = consumption.get("items")
    if not isinstance(planned_items, list) or not isinstance(consumed_items, list):
        return {"status": "FAIL", "reason": "feedback-items-invalid"}
    planned = {
        item.get("id"): item
        for item in planned_items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    consumed: dict[str, dict[str, Any]] = {}
    for item in consumed_items:
        if not isinstance(item, dict):
            return {"status": "FAIL", "reason": "feedback-consumption-item-invalid"}
        feedback_id = item.get("feedback_id")
        if not isinstance(feedback_id, str) or feedback_id in consumed:
            return {"status": "FAIL", "reason": "feedback-consumption-id-invalid"}
        consumed[feedback_id] = item
    if set(consumed) != set(planned):
        return {"status": "FAIL", "reason": "feedback-consumption-coverage-mismatch"}

    for feedback_id, item in consumed.items():
        source_name = item.get("source_name")
        source_url = item.get("source_url")
        evidence = item.get("evidence")
        languages = item.get("languages")
        if (
            not isinstance(source_name, str)
            or not source_name.strip()
            or not isinstance(source_url, str)
            or re.fullmatch(r"https://\S+", source_url) is None
            or not isinstance(evidence, str)
            or not evidence.strip()
            or not isinstance(languages, list)
            or not languages
            or any(lang not in {"ja", "en"} for lang in languages)
            or planned[feedback_id].get("lang") not in languages
        ):
            return {"status": "FAIL", "reason": "feedback-evidence-invalid"}
        for lang in languages:
            article = (run_dir / f"article-{lang}.md").read_text(encoding="utf-8")
            if source_url not in article:
                return {
                    "status": "FAIL",
                    "reason": f"feedback-source-not-visible:{feedback_id}:{lang}",
                }
    return {
        "status": "PASS",
        "feedback_ids": [item["id"] for item in planned_items],
        "drafts": drafts,
        "feedback_plan_sha256": state["feedback_sha256"],
    }


def verify(run_dir: Path | str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    result = validate_consumption(run_dir)
    _atomic_write(
        run_dir / "gates/quality-feedback-verification.json",
        result,
    )
    return result


def record_result(
    run_dir: Path | str,
    ledger: Path | str,
    *,
    return_code: int,
    owner_pid: int,
    caller_parent_pid: int | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    ledger = Path(ledger).resolve()
    gates = run_dir / "gates"
    state_path = gates / STATE_NAME
    state = _read_json(state_path)
    if state is None or state.get("status") not in {
        "invoking",
        "publication-invoking",
    }:
        raise QualityFeedbackRecoveryError("feedback-recovery-not-invoking")
    actual_parent_pid = os.getppid() if caller_parent_pid is None else caller_parent_pid
    if state.get("owner_pid") != owner_pid or actual_parent_pid != owner_pid:
        raise QualityFeedbackRecoveryError("feedback-recovery-result-owner-mismatch")
    attempts = int(state.get("attempts", 0))
    publication_phase = state.get("status") == "publication-invoking"
    quality = _read_json(gates / "quality-self-heal.json")
    if (gates / "publication-state.json").is_file():
        status = "handed-to-publication"
    elif ledger_has_public_effect(ledger, run_dir.name):
        status = "terminal-ambiguous-ledger-without-publication-state"
    elif publication_phase and int(state.get("publication_attempts", 0)) < MAX_PUBLICATION_HANDOFFS:
        status = "publication-retryable-incomplete"
    elif not publication_phase and attempts < MAX_INVOCATIONS:
        status = "retryable-incomplete"
    elif (
        quality is not None
        and quality.get("action") in {"ready_to_freeze", "force_publish_advisory"}
        and isinstance(quality.get("quality"), dict)
        and all(
            isinstance(quality["quality"].get(lang), dict)
            and (
                quality["quality"][lang].get("ready") is True
                or (
                    quality.get("action") == "force_publish_advisory"
                    and quality["quality"][lang].get("identity") == "PASS"
                )
            )
            for lang in ("ja", "en")
        )
        and (
            quality.get("action") != "force_publish_advisory"
            or quality.get("force_publish_after_iterations") == 1
        )
        and validate_consumption(run_dir).get("status") == "PASS"
    ):
        status = "terminal-ready-not-published"
    else:
        status = "terminal-blocked"
    if status == "terminal-blocked" and not publication_phase:
        defect_path = gates / "quality-feedback-recovery-defect.json"
        existing_defect = _read_json(defect_path)
        if defect_path.is_symlink():
            raise QualityFeedbackRecoveryError("quality-recovery-defect-is-symlink")
        if defect_path.is_file():
            legacy_path = gates / "quality-feedback-recovery-defect-legacy.json"
            if legacy_path.exists() or legacy_path.is_symlink():
                if legacy_path.is_symlink() or not legacy_path.is_file():
                    raise QualityFeedbackRecoveryError("quality-recovery-legacy-defect-is-symlink")
            else:
                shutil.copy2(defect_path, legacy_path)
        current_drafts: dict[str, str] = {}
        try:
            current_drafts = {
                lang: _sha256(run_dir / f"article-{lang}.md")
                for lang in ("ja", "en")
            }
        except OSError:
            current_drafts = {}
        quality_records = (
            quality.get("quality")
            if isinstance(quality, dict) and isinstance(quality.get("quality"), dict)
            else {}
        )
        consumption_status = validate_consumption(run_dir).get("status")
        _atomic_write(
            defect_path,
            {
                "version": 2,
                "status": "blocked",
                "run_id": run_dir.name,
                "scope": "bounded-feedback-recovery",
                "quality_attempt": _quality_attempt_count(gates),
                "draft_sha256": current_drafts,
                "observations": [
                    {
                        "return_code": return_code,
                        "quality_action": quality.get("action") if isinstance(quality, dict) else None,
                        "prior_defect_sha256": (
                            _sha256(gates / "quality-feedback-recovery-defect-legacy.json")
                            if (gates / "quality-feedback-recovery-defect-legacy.json").is_file()
                            else None
                        ),
                    }
                ],
                "preserved_invariants": {
                    "publication_or_staging_performed": False,
                    "feedback_consumption_verification": consumption_status,
                    "identity": {
                        lang: quality_records.get(lang, {}).get("identity")
                        for lang in ("ja", "en")
                    },
                    "reader": {
                        lang: quality_records.get(lang, {}).get("reader")
                        for lang in ("ja", "en")
                    },
                    "cta": {
                        lang: (
                            "PASS"
                            if (
                                _read_json(gates / f"cta-{lang}.json") or {}
                            ).get("verdict") == "PASS"
                            else "FAIL"
                        )
                        for lang in ("ja", "en")
                    },
                },
                "required_safe_next_action": (
                    "Re-run the current-hash editorial and reader gates through a new signed recovery invocation."
                ),
            },
        )
    state.update(
        {
            "status": status,
            "return_code": return_code,
            "finished_at": _utc_now(),
        }
    )
    _atomic_write(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("plan", "begin", "handoff", "invoke", "verify", "result"),
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--owner-pid", type=int)
    parser.add_argument("--return-code", type=int)
    args = parser.parse_args()
    if args.command == "verify":
        value = verify(args.run_dir)
    else:
        if args.ledger is None:
            parser.error("--ledger is required")
        if args.command == "plan":
            value = plan(args.run_dir, args.ledger)
        elif args.command == "begin":
            value = begin(args.run_dir, args.ledger)
        elif args.command == "handoff":
            value = prepare_publication_handoff(args.run_dir, args.ledger)
        elif args.command == "invoke":
            if args.owner_pid is None:
                parser.error("--owner-pid is required for invoke")
            value = mark_invoking(
                args.run_dir,
                args.ledger,
                owner_pid=args.owner_pid,
            )
        else:
            if args.return_code is None:
                parser.error("--return-code is required for result")
            if args.owner_pid is None:
                parser.error("--owner-pid is required for result")
            value = record_result(
                args.run_dir,
                args.ledger,
                return_code=args.return_code,
                owner_pid=args.owner_pid,
            )
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return 0 if value.get("status") not in {"REFUSED", "FAIL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
