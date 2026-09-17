#!/usr/bin/env python3
"""Durable one-change article learning, application, and keep/revert control."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from publication_resume import (
    ACTIVE_PAIRS,
    LEGACY_EXACT8_PAIRS,
    PublicationStore,
)  # noqa: E402
from publication_contract_resolver import infer_publication_contract  # noqa: E402
from money_ledger import MoneyLedger  # noqa: E402


ALLOWED_AXES = frozenset(
    {
        "lead",
        "evidence",
        "structure",
        "clarity",
        "voice",
        "reader_value",
        "why_pay",
        "one_reader",
        "jargon_defined",
        "editorial",
    }
)
PROTECTED_PATTERN = re.compile(
    r"(?ix)"
    r"(exact\s*8|exact8|06:00|12:00|22:30|six[- ]hour|6[- ]hour|"
    r"schedule|launchd|cron|credential|password|api[_ -]?key|token|"
    r"safety|identity gate|publication|publish(?:ing)?|idempot|recovery|"
    r"provider priority|account identit)"
)
HEX64 = re.compile(r"[0-9a-f]{64}")


def _required_pairs_for_state(state: dict[str, Any]) -> tuple[str, ...]:
    return (
        LEGACY_EXACT8_PAIRS
        if infer_publication_contract(state) == "legacy-exact8"
        else ACTIVE_PAIRS
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _json_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _editorial_quality(payload: dict) -> dict[str, float]:
    """The composite editor returns a binary verdict, not axis scores.

    It replaced the rubric judge, and because this function only knew how to
    read rubric JSON the nightly job began exiting with "no JA/EN quality
    baseline is available" (measured 2026-07-26). A binary verdict is a
    one-axis score: PASS is 1.0, FAIL is 0.0, which is enough for the
    keep/revert comparison this module performs.
    """
    verdict = str(payload.get("verdict", "")).strip().upper()
    if verdict not in {"PASS", "FAIL"}:
        return {}
    return {"editorial": 1.0 if verdict == "PASS" else 0.0}


def _quality(run_dir: Path) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for language in ("ja", "en"):
        gates = run_dir / "gates"
        # Newest gate first; the rubric file stays readable so runs recorded
        # before the replacement still compare against runs recorded after it.
        for path, extract in (
            (gates / f"editorial-{language}.json", _editorial_quality),
            (gates / f"rubric-judge-{language}.json", None),
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if extract is not None:
                scores = extract(payload)
                if scores:
                    result[language] = scores
                    break
                continue
            raw = payload.get("scores", {})
            result[language] = {
                str(axis): float(score)
                for axis, score in raw.items()
                if isinstance(score, (int, float)) and not isinstance(score, bool)
            }
            break
        else:
            result[language] = {}
    return result


def _money_snapshot(path: Path, observed_at: datetime) -> dict[str, Any]:
    if not path.is_file():
        return {
            "status": "unavailable",
            "reason": "canonical money ledger is missing",
            "verified_revenue_event_count": 0,
            "verified_net_by_currency": {},
        }
    month_start = observed_at.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    summary = MoneyLedger(path).summary(
        start=_iso(month_start),
        end=_iso(observed_at + timedelta(microseconds=1)),
    )
    summary["status"] = (
        "verified"
        if summary["verified_revenue_event_count"] > 0
        else "insufficient"
    )
    if summary["status"] == "insufficient":
        summary["reason"] = "no verified external transaction receipt in the window"
    return summary


def collect_snapshot(
    state_path: Path,
    ledger_path: Path,
    sales_path: Path,
    funnel_path: Path,
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    """Build evidence from verified live pairs without blocking on failures."""
    store = PublicationStore(state_path, ledger_path)
    state = store.read()
    run_id = str(state["run_id"])
    topic_id = str(state["topic_id"])
    run_dir = Path(str(state["run_dir"]))
    required_pairs = _required_pairs_for_state(state)
    rows = [
        row
        for row in _json_lines(ledger_path)
        if row.get("run_id") == run_id
        and row.get("topic_id") == topic_id
        and row.get("published") is True
    ]
    by_pair = {
        f"{row.get('platform')}/{row.get('lang')}": row
        for row in rows
    }
    if (
        not rows
        or len(by_pair) != len(rows)
        or not set(by_pair).issubset(set(required_pairs))
    ):
        raise ValueError("learning input has no unambiguous live pairs")
    for pair in by_pair:
        entry = state.get("pairs", {}).get(pair, {})
        if entry.get("status") != "live" or not entry.get("receipt"):
            raise ValueError(
                f"learning pair lacks a verified receipt: {pair}"
            )
    live_pairs = [
        pair for pair in required_pairs if pair in by_pair
    ]
    pending_pairs = [
        pair for pair in required_pairs if pair not in by_pair
    ]
    exact8_complete = not pending_pairs

    sales = [
        row
        for row in _json_lines(sales_path)
        if row.get("ok") is True or row.get("reason")
    ]
    engagement = [
        row
        for row in _json_lines(funnel_path)
        if row.get("run_id") == run_id
    ]
    return {
        "schema_version": 2,
        "run_id": run_id,
        "topic_id": topic_id,
        "observed_at": _iso(observed_at),
        "exact8_complete": exact8_complete,
        "publication_contract": infer_publication_contract(state),
        "learning_eligible_pairs": live_pairs,
        "reconcile_pending_pairs": pending_pairs,
        "live_urls": {
            pair: str(by_pair[pair]["live_url"])
            for pair in live_pairs
        },
        "exact8_urls": {
            pair: str(by_pair[pair]["live_url"])
            for pair in required_pairs
            if exact8_complete
        },
        "public_ids": {
            pair: str(by_pair[pair]["public_id"])
            for pair in live_pairs
        },
        "quality": _quality(run_dir),
        "engagement": engagement,
        "sales": sales,
        "money": _money_snapshot(sales_path.parent / "money.sqlite3", observed_at),
        "source_artifacts": {
            "ja": str(state["drafts"]["ja"]["sha256"]),
            "en": str(state["drafts"]["en"]["sha256"]),
            "x-post/ja": str(state["x_post"]["sha256"]),
            "headline": str(state["media"]["headline_image"]["sha256"]),
            "body": [
                str(item["sha256"])
                for item in state["media"]["body_assets"]
            ],
        },
        "measurement_kind": {
            "revenue": "verified-external-receipt-only",
            "engagement": "proxy",
            "quality": "proxy",
        },
    }


def validate_proposal(value: dict[str, Any]) -> dict[str, str]:
    expected = {
        "axis",
        "hypothesis",
        "rule_text",
        "held_out_assertion",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("proposal must contain exactly one change contract")
    axis = value.get("axis")
    if axis not in ALLOWED_AXES:
        raise ValueError("proposal axis is not allowed")
    result: dict[str, str] = {}
    for field in expected:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"proposal {field} must be non-empty")
        result[field] = text.strip()
    joined = "\n".join(result.values())
    if len(result["rule_text"]) > 800 or PROTECTED_PATTERN.search(joined):
        raise ValueError("proposal attempts an operational or protected change")
    return result


def prepare_experiment(
    *,
    cycle_key: str,
    proposal: dict[str, str],
    baseline: dict[str, float],
    revenue_baseline: float | None,
    cut: datetime,
) -> dict[str, Any]:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", cycle_key) is None:
        raise ValueError("cycle key is invalid")
    if set(baseline) != {"ja", "en"}:
        raise ValueError("baseline must include both language lanes")
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool)
        for value in baseline.values()
    ):
        raise ValueError("baseline values must be numeric")
    cut_iso = _iso(cut)
    return {
        "schema_version": 1,
        "experiment_id": cycle_key,
        "status": "PREPARED",
        "proposal": dict(proposal),
        "target_axis": proposal["axis"],
        "baseline_quality": {
            language: float(value)
            for language, value in baseline.items()
        },
        "revenue_baseline": (
            float(revenue_baseline)
            if revenue_baseline is not None
            else None
        ),
        "cut": cut_iso,
        "evaluation_at": _iso(cut + timedelta(days=7)),
        "required_lanes": ["ja", "en"],
    }


def persist_prepared(path: Path, experiment: dict[str, Any]) -> None:
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current != experiment:
            raise ValueError("experiment record conflicts with prepared content")
        return
    if experiment.get("status") != "PREPARED":
        raise ValueError("only PREPARED experiments can be persisted")
    _atomic_json(path, experiment)


def _experiment_block(experiment: dict[str, Any]) -> str:
    proposal = experiment["proposal"]
    return (
        f"<!-- experiment:{experiment['experiment_id']}:start -->\n"
        f"## Active experiment: {experiment['experiment_id']}\n\n"
        f"- Axis: {proposal['axis']}\n"
        f"- Hypothesis: {proposal['hypothesis']}\n"
        f"- Rule: {proposal['rule_text']}\n"
        f"- Held-out assertion: {proposal['held_out_assertion']}\n"
        f"<!-- experiment:{experiment['experiment_id']}:end -->\n"
    )


def apply_prepared(record: Path, playbook: Path) -> dict[str, Any]:
    experiment = json.loads(record.read_text(encoding="utf-8"))
    if experiment.get("status") == "APPLIED":
        return experiment
    if experiment.get("status") != "PREPARED":
        raise ValueError("experiment is not PREPARED")
    block = _experiment_block(experiment)
    current = playbook.read_bytes()
    if not experiment.get("new_text"):
        if block.encode("utf-8") in current:
            raise ValueError(
                "experiment block exists without a prepared effect record"
            )
        separator = b"" if current.endswith(b"\n\n") else b"\n"
        addition = separator + block.encode("utf-8")
        planned = current + addition
        experiment.update(
            {
                "old_text": "",
                "new_text": addition.decode("utf-8"),
                "preimage_sha256": _sha256_bytes(current),
                "postimage_sha256": _sha256_bytes(planned),
            }
        )
        # Persist the exact effect and both hashes before the file mutation.
        _atomic_json(record, experiment)
    addition = str(experiment["new_text"]).encode("utf-8")
    preimage = str(experiment["preimage_sha256"])
    postimage = str(experiment["postimage_sha256"])
    current_hash = _sha256_bytes(current)
    if current_hash == preimage:
        _atomic_bytes(playbook, current + addition)
    elif current_hash != postimage:
        raise ValueError("playbook differs from prepared pre/post image")
    experiment.update(
        {
            "status": "APPLIED",
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _atomic_json(record, experiment)
    return experiment


def revert_applied(
    record: Path,
    playbook: Path,
    *,
    reason: str,
) -> dict[str, Any]:
    experiment = json.loads(record.read_text(encoding="utf-8"))
    if experiment.get("status") == "REVERTED":
        return experiment
    if experiment.get("status") not in {"APPLIED", "REVERT_PREPARED"}:
        raise ValueError("only APPLIED experiment can be reverted")
    current = playbook.read_bytes()
    block = str(experiment.get("new_text", "")).encode("utf-8")
    if not experiment.get("revert_postimage_sha256"):
        if not block or current.count(block) != 1:
            raise ValueError("exact experiment text is not uniquely reversible")
        reverted = current.replace(block, b"", 1)
        if experiment.get("old_text", ""):
            reverted += str(experiment["old_text"]).encode("utf-8")
        experiment.update(
            {
                "status": "REVERT_PREPARED",
                "decision_reason": reason,
                "revert_preimage_sha256": _sha256_bytes(current),
                "revert_postimage_sha256": _sha256_bytes(reverted),
            }
        )
        _atomic_json(record, experiment)
    preimage = str(experiment["revert_preimage_sha256"])
    postimage = str(experiment["revert_postimage_sha256"])
    current_hash = _sha256_bytes(current)
    if current_hash == preimage:
        if not block or current.count(block) != 1:
            raise ValueError("exact experiment text is not uniquely reversible")
        reverted = current.replace(block, b"", 1)
        if experiment.get("old_text", ""):
            reverted += str(experiment["old_text"]).encode("utf-8")
        _atomic_bytes(playbook, reverted)
    elif current_hash == postimage:
        reverted = current
    else:
        raise ValueError("playbook differs from prepared revert pre/post image")
    experiment.update(
        {
            "status": "REVERTED",
            "reverted_at": datetime.now(timezone.utc).isoformat(),
            "reverted_sha256": _sha256_bytes(reverted),
        }
    )
    _atomic_json(record, experiment)
    return experiment


def _real_revenue(snapshot: dict[str, Any]) -> float | None:
    money = snapshot.get("money")
    if not isinstance(money, dict) or money.get("status") != "verified":
        return None
    if not isinstance(money.get("verified_revenue_event_count"), int):
        return None
    values = money.get("verified_net_by_currency")
    if not isinstance(values, dict) or len(values) != 1:
        # No exchange-rate guesses: a multi-currency window is visible but not
        # collapsed into one optimization score.
        return None
    value = next(iter(values.values()))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def evaluate_due(
    record: Path,
    playbook: Path,
    *,
    snapshots: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    experiment = json.loads(record.read_text(encoding="utf-8"))
    if experiment.get("status") != "APPLIED":
        return experiment
    evaluation_at = datetime.fromisoformat(experiment["evaluation_at"])
    cut = datetime.fromisoformat(experiment["cut"])
    if now.tzinfo is None:
        raise ValueError("evaluation time must be timezone-aware")
    if now < evaluation_at:
        return experiment
    post = [
        snapshot
        for snapshot in snapshots
        if datetime.fromisoformat(str(snapshot["observed_at"])) > cut
    ]
    axis = str(experiment["target_axis"])
    lane_values: dict[str, list[float]] = {"ja": [], "en": []}
    for snapshot in post:
        quality = snapshot.get("quality", {})
        for language in lane_values:
            value = quality.get(language, {}).get(axis)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                lane_values[language].append(float(value))
    generalized = all(lane_values[language] for language in ("ja", "en"))
    snapshots_by_run = {
        str(snapshot.get("run_id", "")): snapshot
        for snapshot in post
    }
    applied = False
    for row in applications:
        if (
            row.get("experiment_id") != experiment["experiment_id"]
            or set(row.get("languages", [])) != {"ja", "en"}
            or not isinstance(row.get("artifact_sha256"), dict)
        ):
            continue
        matching = snapshots_by_run.get(str(row.get("run_id", "")))
        if matching is None:
            continue
        hashes = row["artifact_sha256"]
        published = matching.get("source_artifacts", {})
        if all(
            HEX64.fullmatch(str(hashes.get(language, "")))
            and hashes.get(language) == published.get(language)
            for language in ("ja", "en")
        ):
            applied = True
            break

    revenue_post_values = [
        value
        for value in (_real_revenue(snapshot) for snapshot in post)
        if value is not None
    ]
    revenue_baseline = experiment.get("revenue_baseline")
    if (
        isinstance(revenue_baseline, (int, float))
        and not isinstance(revenue_baseline, bool)
        and revenue_post_values
    ):
        decision_metric = "revenue"
        post_value = revenue_post_values[-1]
        metric_ok = post_value >= float(revenue_baseline)
        delta = post_value - float(revenue_baseline)
    else:
        decision_metric = "quality-proxy"
        metric_ok = generalized and all(
            (
                sum(lane_values[language]) / len(lane_values[language])
                >= float(experiment["baseline_quality"][language])
            )
            for language in ("ja", "en")
        )
        delta = None

    experiment.update(
        {
            "decision_metric": decision_metric,
            "revenue_delta": delta,
            "application_evidence": applied,
            "generalization_checked": generalized,
            "measurement_window": {
                "cut": experiment["cut"],
                "post": "observed_at > cut",
                "cut_excluded": True,
            },
            "post_quality": {
                language: (
                    sum(values) / len(values)
                    if values
                    else None
                )
                for language, values in lane_values.items()
            },
        }
    )
    _atomic_json(record, experiment)
    if metric_ok and applied and generalized:
        experiment["status"] = "KEPT"
        experiment["kept_at"] = _iso(now)
        _atomic_json(record, experiment)
        return experiment
    reasons = []
    if not metric_ok:
        reasons.append("metric worse or unavailable")
    if not applied:
        reasons.append("application evidence absent")
    if not generalized:
        reasons.append("both language lanes lack disjoint post evidence")
    return revert_applied(record, playbook, reason="; ".join(reasons))


def propose_and_apply(
    *,
    playbook: Path,
    record: Path,
    baseline: dict[str, Any],
    revenue_baseline: float | None,
    cut: datetime,
    propose: Callable[[str], dict[str, Any]],
    review: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    try:
        raw_proposal = propose(
            json.dumps(baseline, ensure_ascii=False, sort_keys=True)
        )
        proposal = validate_proposal(raw_proposal)
        if proposal["axis"] != baseline.get("axis"):
            raise ValueError("proposal axis does not match the measured weakest axis")
        raw_review = review(
            json.dumps(
                {"baseline": baseline, "proposal": proposal},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if (
            not isinstance(raw_review, dict)
            or set(raw_review) != {"approved", "reason"}
            or raw_review.get("approved") is not True
            or not isinstance(raw_review.get("reason"), str)
            or not raw_review["reason"].strip()
        ):
            return {"status": "REVIEW_REJECTED"}
    except Exception as error:
        return {
            "status": "PROVIDER_PENDING",
            "reason": str(error),
        }
    experiment = prepare_experiment(
        cycle_key=record.stem,
        proposal=proposal,
        baseline={
            "ja": float(baseline["ja"]),
            "en": float(baseline["en"]),
        },
        revenue_baseline=revenue_baseline,
        cut=cut,
    )
    experiment["review"] = {
        "approved": True,
        "reason": raw_review["reason"].strip(),
    }
    persist_prepared(record, experiment)
    return apply_prepared(record, playbook)


def persist_snapshot(root: Path, snapshot: dict[str, Any]) -> Path:
    destination = root / f"{snapshot['run_id']}.json"
    if destination.exists():
        current = json.loads(destination.read_text(encoding="utf-8"))
        if current != snapshot:
            raise ValueError(
                f"immutable metrics changed for {snapshot['run_id']}"
            )
        return destination
    _atomic_json(destination, snapshot)
    return destination


def load_snapshots(root: Path) -> list[dict[str, Any]]:
    values = []
    for path in sorted(root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            values.append(value)
    return sorted(
        values,
        key=lambda value: (
            str(value.get("observed_at", "")),
            str(value.get("run_id", "")),
        ),
    )


def select_baseline(
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    axes: dict[str, dict[str, list[float]]] = {}
    for snapshot in snapshots:
        for language in ("ja", "en"):
            scores = snapshot.get("quality", {}).get(language, {})
            if not isinstance(scores, dict):
                continue
            for axis, value in scores.items():
                if (
                    axis in ALLOWED_AXES
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    axes.setdefault(axis, {"ja": [], "en": []})[
                        language
                    ].append(float(value))
    candidates = []
    for axis, lanes in axes.items():
        if not lanes["ja"] or not lanes["en"]:
            continue
        averages = {
            language: sum(values) / len(values)
            for language, values in lanes.items()
        }
        candidates.append(
            (
                (averages["ja"] + averages["en"]) / 2,
                axis,
                averages,
            )
        )
    if not candidates:
        raise ValueError("no JA/EN quality baseline is available")
    _, axis, averages = min(candidates)
    return {
        "axis": axis,
        "ja": averages["ja"],
        "en": averages["en"],
        "snapshot_count": len(snapshots),
    }


def latest_revenue(
    snapshots: list[dict[str, Any]],
) -> float | None:
    for snapshot in reversed(snapshots):
        value = _real_revenue(snapshot)
        if value is not None:
            return value
    return None


def _extract_json(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    for index, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found.append(value)
    if not found:
        raise ValueError("model judge returned no JSON object")
    return found[-1]


def model_judge(
    runner: Path,
    prompt: str,
    *,
    run_id: str,
) -> dict[str, Any]:
    environment = {
        **os.environ,
        "ARTICLE_RUN_ID": run_id,
    }
    result = subprocess.run(
        [str(runner), "judge", "--prompt-file", "-"],
        input=prompt,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return _extract_json(result.stdout)


def _record_source_commit(
    record: Path,
    commit: str,
    *,
    action: str,
) -> dict[str, Any]:
    experiment = json.loads(record.read_text(encoding="utf-8"))
    history = experiment.setdefault("source_commits", [])
    item = {"action": action, "commit": commit}
    if item not in history:
        history.append(item)
    transition = experiment.get("git_transition")
    if isinstance(transition, dict) and transition.get("action") == action:
        transition.update({"status": "COMPLETE", "commit": commit})
    _atomic_json(record, experiment)
    return experiment


def source_branch(repo: Path) -> str:
    branch = os.environ.get("ARTICLE_SOURCE_BRANCH", "").strip()
    if not branch:
        upstream = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        prefix = "origin/"
        if not upstream.startswith(prefix):
            raise RuntimeError(
                f"learning source upstream must use origin: {upstream!r}"
            )
        branch = upstream[len(prefix) :]
    if (
        not branch
        or branch.startswith("-")
        or subprocess.run(
            ["git", "check-ref-format", f"refs/heads/{branch}"],
            capture_output=True,
        ).returncode
        != 0
    ):
        raise RuntimeError(f"invalid ARTICLE_SOURCE_BRANCH: {branch!r}")
    return branch


def update_deployed_commit(repo: Path, commit: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("deployed commit must be a full lowercase git object id")
    current = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != commit:
        raise RuntimeError("deployed commit does not match the runtime checkout")
    marker = repo / "skills/writer-agent/state/deployed-commit"
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(f".{marker.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(f"{commit}\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, marker)
    return marker


def commit_playbook_change(
    repo: Path,
    playbook: Path,
    record: Path,
    *,
    action: str,
) -> str:
    relative = playbook.resolve().relative_to(repo.resolve())
    experiment = json.loads(record.read_text(encoding="utf-8"))
    transition = experiment.get("git_transition")
    expected_hash = _sha256_bytes(playbook.read_bytes())
    if not isinstance(transition, dict) or transition.get("action") != action:
        experiment["git_transition"] = {
            "action": action,
            "status": "PREPARED",
            "path": str(relative),
            "expected_file_sha256": expected_hash,
        }
        _atomic_json(record, experiment)
    elif transition.get("expected_file_sha256") != expected_hash:
        raise RuntimeError("prepared git transition file hash changed")
    status = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    dirty = {
        line[3:]
        for line in status
        if len(line) > 3
    }
    writer_dirty = {
        path for path in dirty if path.startswith("skills/writer-agent/")
    }
    if writer_dirty and writer_dirty != {str(relative)}:
        raise RuntimeError(
            "tracked writer-agent files have unrelated changes: "
            f"{sorted(writer_dirty)}"
        )
    if str(relative) in dirty:
        subprocess.run(
            ["git", "-C", str(repo), "add", "--", str(relative)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "commit",
                "-m",
                (
                    f"learn(article): {action} "
                    f"{experiment['experiment_id']}"
                ),
                "--",
                str(relative),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        changed = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if changed != [str(relative)]:
            raise RuntimeError(
                "prepared git transition is not the current playbook-only commit"
            )
        subject = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        expected_subject = (
            f"learn(article): {action} {experiment['experiment_id']}"
        )
        if subject != expected_subject:
            raise RuntimeError(
                "prepared git transition commit subject does not match"
            )
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    branch = source_branch(repo)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "push",
            "origin",
            f"HEAD:refs/heads/{branch}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    update_deployed_commit(repo, commit)
    _record_source_commit(record, commit, action=action)
    return commit


def ensure_repo_synced(
    repo: Path,
    *,
    allowed_dirty: set[str] | None = None,
    allow_ahead: bool = False,
) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    branch = source_branch(repo)
    counts = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-list",
            "--left-right",
            "--count",
            f"HEAD...refs/remotes/origin/{branch}",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    if (
        len(counts) != 2
        or counts[1] != "0"
        or (counts[0] != "0" and not allow_ahead)
    ):
        raise RuntimeError(
            f"learning source is not synchronized with upstream: {counts}"
        )
    status = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    dirty = {line[3:] for line in status if len(line) > 3}
    allowed = allowed_dirty or set()
    writer_dirty = {
        path for path in dirty if path.startswith("skills/writer-agent/")
    }
    if not writer_dirty.issubset(allowed):
        raise RuntimeError(
            "learning source has unrelated tracked writer-agent changes: "
            f"{sorted(writer_dirty)}"
        )


def _latest_sales_rows(path: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _json_lines(path):
        key = (str(row.get("platform", "")), str(row.get("metric", "")))
        current = latest.get(key)
        if current is None or str(row.get("ts", "")) >= str(
            current.get("ts", "")
        ):
            latest[key] = row
    return [
        latest[key]
        for key in sorted(latest)
    ]


def _latest_engagement_rows(
    path: Path,
    run_id: str,
    required_pairs: tuple[str, ...],
) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _json_lines(path):
        if row.get("run_id") != run_id:
            continue
        pair = str(row.get("pair", ""))
        current = latest.get(pair)
        if current is None or str(row.get("measured_at", "")) >= str(
            current.get("measured_at", "")
        ):
            latest[pair] = row
    return [
        latest[pair]
        for pair in required_pairs
        if pair in latest
    ]


def _replace_snapshot_dynamic_rows(
    snapshot: dict[str, Any],
    sales_path: Path,
    funnel_path: Path,
) -> dict[str, Any]:
    snapshot["sales"] = _latest_sales_rows(sales_path)
    snapshot["engagement"] = _latest_engagement_rows(
        funnel_path,
        str(snapshot["run_id"]),
        tuple(
            LEGACY_EXACT8_PAIRS
            if infer_publication_contract(snapshot) == "legacy-exact8"
            else ACTIVE_PAIRS
        ),
    )
    snapshot["money"] = _money_snapshot(
        sales_path.parent / "money.sqlite3",
        datetime.fromisoformat(str(snapshot["observed_at"])),
    )
    return snapshot


def _complete_states(
    state_root: Path,
    ledger: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in sorted(
        state_root.glob("runs/*/gates/publication-state.json")
    ):
        store = PublicationStore(path, ledger)
        state = store.read()
        if any(
            entry.get("status") == "live"
            and isinstance(entry.get("receipt"), dict)
            for entry in state.get("pairs", {}).values()
            if isinstance(entry, dict)
        ):
            result.append((path, state))
    return result


def _measure_run(
    skill_dir: Path,
    ledger: Path,
    state: dict[str, Any],
    funnel: Path,
) -> None:
    subprocess.run(
        [
            sys.executable,
            str(skill_dir / "scripts/_shared/measure-funnel.py"),
            "--ledger",
            str(ledger),
            "--run-id",
            str(state["run_id"]),
            "--topic-id",
            str(state["topic_id"]),
            "--out",
            str(funnel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _measure_sales(skill_dir: Path, sales: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(skill_dir / "scripts/measure-sales.py"),
            "--out",
            str(sales),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _sync_money(skill_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(skill_dir / "scripts/money_sync.py"),
            "--state-dir",
            str(skill_dir / "state"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _receipt(
    receipts: Path,
    now: datetime,
    value: dict[str, Any],
) -> dict[str, Any]:
    receipts.mkdir(parents=True, exist_ok=True)
    destination = receipts / f"{now.astimezone().date().isoformat()}.json"
    payload = {
        "schema_version": 1,
        "observed_at": _iso(now),
        **value,
    }
    _atomic_json(destination, payload)
    return payload


def run_cycle(
    skill_dir: Path,
    *,
    now: datetime,
    skip_remote_measurement: bool = False,
    proposer: Callable[[str], dict[str, Any]] | None = None,
    reviewer: Callable[[str], dict[str, Any]] | None = None,
    commit_changes: bool = True,
) -> dict[str, Any]:
    state_root = skill_dir / "state"
    ledger = state_root / "articles.jsonl"
    learning = state_root / "learning"
    metrics_root = learning / "metrics"
    experiments_root = learning / "experiments"
    receipts = learning / "receipts"
    sales = state_root / "sales-ledger.jsonl"
    funnel = state_root / "funnel.jsonl"
    playbook = skill_dir / "reference/learned-playbook.md"
    runner = Path(
        os.environ.get(
            "ARTICLE_MODEL_RUNNER",
            str(skill_dir / "runtime/model-runner.sh"),
        )
    )
    repo = skill_dir.parents[1]

    states = _complete_states(state_root, ledger)
    new_states = [
        (path, state)
        for path, state in states
        if not (metrics_root / f"{state['run_id']}.json").exists()
    ]
    metric_run_ids = [
        str(state["run_id"])
        for _path, state in new_states
    ]
    if new_states and not skip_remote_measurement:
        try:
            _measure_sales(skill_dir, sales)
        except (OSError, subprocess.CalledProcessError):
            pass
        try:
            _sync_money(skill_dir)
        except (OSError, subprocess.CalledProcessError):
            pass
    for state_path, state in new_states:
        if not skip_remote_measurement:
            try:
                _measure_run(skill_dir, ledger, state, funnel)
            except (OSError, subprocess.CalledProcessError):
                pass
        snapshot = collect_snapshot(
            state_path,
            ledger,
            sales,
            funnel,
            observed_at=now,
        )
        persist_snapshot(
            metrics_root,
            _replace_snapshot_dynamic_rows(snapshot, sales, funnel),
        )

    snapshots = load_snapshots(metrics_root)
    if not snapshots:
        return _receipt(
            receipts,
            now,
            {
                "status": "NO_EXACT8_EVIDENCE",
                "new_metrics": 0,
                "metric_run_ids": metric_run_ids,
            },
        )

    applications = _json_lines(
        state_root / "playbook-applications.jsonl"
    )
    records = sorted(experiments_root.glob("*.json"))
    active = None
    for path in records:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_actions = {
            str(item.get("action"))
            for item in value.get("source_commits", [])
            if isinstance(item, dict)
        }
        if value.get("status") in {
            "PREPARED",
            "APPLIED",
            "REVERT_PREPARED",
        } or (
            value.get("status") == "REVERTED"
            and "revert" not in source_actions
        ):
            if active is not None:
                raise RuntimeError("more than one learning experiment is active")
            active = (path, value)

    if active is not None:
        record, experiment = active
        source_actions = {
            str(item.get("action"))
            for item in experiment.get("source_commits", [])
            if isinstance(item, dict)
        }
        transition = experiment.get("git_transition", {})
        allow_ahead = (
            isinstance(transition, dict)
            and transition.get("status") == "PREPARED"
        )
        if experiment["status"] == "REVERTED":
            if commit_changes:
                ensure_repo_synced(
                    repo,
                    allowed_dirty={
                        str(playbook.resolve().relative_to(repo.resolve()))
                    },
                    allow_ahead=allow_ahead,
                )
                commit_playbook_change(
                    repo,
                    playbook,
                    record,
                    action="revert",
                )
                experiment = json.loads(record.read_text(encoding="utf-8"))
            return _receipt(
                receipts,
                now,
                {
                    "status": "REVERTED",
                    "experiment_id": experiment["experiment_id"],
                    "new_metrics": len(new_states),
                    "metric_run_ids": metric_run_ids,
                    "source_commits": experiment.get("source_commits", []),
                },
            )
        if experiment["status"] == "PREPARED":
            if commit_changes:
                ensure_repo_synced(
                    repo,
                    allowed_dirty={
                        str(playbook.resolve().relative_to(repo.resolve()))
                    },
                )
            experiment = apply_prepared(record, playbook)
            if commit_changes:
                commit_playbook_change(
                    repo,
                    playbook,
                    record,
                    action="apply",
                )
                experiment = json.loads(record.read_text(encoding="utf-8"))
                source_actions.add("apply")
        elif experiment["status"] == "APPLIED" and "apply" not in source_actions:
            if commit_changes:
                ensure_repo_synced(
                    repo,
                    allowed_dirty={
                        str(playbook.resolve().relative_to(repo.resolve()))
                    },
                    allow_ahead=allow_ahead,
                )
                commit_playbook_change(
                    repo,
                    playbook,
                    record,
                    action="apply",
                )
                experiment = json.loads(record.read_text(encoding="utf-8"))
        prior_status = experiment["status"]
        if commit_changes:
            ensure_repo_synced(
                repo,
                allowed_dirty={
                    str(playbook.resolve().relative_to(repo.resolve()))
                },
            )
        experiment = (
            revert_applied(
                record,
                playbook,
                reason=str(
                    experiment.get(
                        "decision_reason",
                        "resume prepared revert",
                    )
                ),
            )
            if experiment["status"] == "REVERT_PREPARED"
            else evaluate_due(
                record,
                playbook,
                snapshots=snapshots,
                applications=applications,
                now=now,
            )
        )
        if experiment["status"] == "REVERTED" and prior_status != "REVERTED":
            if commit_changes:
                commit_playbook_change(
                    repo,
                    playbook,
                    record,
                    action="revert",
                )
        return _receipt(
            receipts,
            now,
            {
                "status": experiment["status"],
                "experiment_id": experiment["experiment_id"],
                "new_metrics": len(new_states),
                "metric_run_ids": metric_run_ids,
                "source_commits": experiment.get("source_commits", []),
            },
        )

    baseline = select_baseline(snapshots)
    cycle_key = f"learning-{now.astimezone().date().isoformat()}"
    record = experiments_root / f"{cycle_key}.json"
    proposal_prompt = (
        "Propose exactly one bounded, non-operational article-writing rule "
        "for the weakest measured axis. Never change safety, identity, "
        "accounts, exact8, schedules, credentials, provider priority, "
        "publishing, idempotency, recovery, or keep/revert criteria. "
        "Return only JSON with keys axis, hypothesis, rule_text, "
        "held_out_assertion. Baseline evidence:\n"
        + json.dumps(baseline, ensure_ascii=False, sort_keys=True)
    )
    review_prompt_prefix = (
        "Independently approve only one evidence-backed writing rule that "
        "cannot change operational invariants. Return only JSON with keys "
        "approved (boolean) and reason. Evidence:\n"
    )
    propose_call = proposer or (
        lambda prompt: model_judge(
            runner,
            prompt,
            run_id=f"{cycle_key}-proposer",
        )
    )
    review_call = reviewer or (
        lambda prompt: model_judge(
            runner,
            review_prompt_prefix + prompt,
            run_id=f"{cycle_key}-reviewer",
        )
    )
    if commit_changes:
        ensure_repo_synced(repo)
    result = propose_and_apply(
        playbook=playbook,
        record=record,
        baseline=baseline,
        revenue_baseline=latest_revenue(snapshots),
        cut=now,
        propose=lambda _baseline: propose_call(proposal_prompt),
        review=review_call,
    )
    if result["status"] == "APPLIED" and commit_changes:
        commit = commit_playbook_change(
            repo,
            playbook,
            record,
            action="apply",
        )
        result = json.loads(record.read_text(encoding="utf-8"))
        result["source_commit"] = commit
    return _receipt(
        receipts,
        now,
        {
            "status": result["status"],
            "experiment_id": result.get("experiment_id"),
            "new_metrics": len(new_states),
            "metric_run_ids": metric_run_ids,
            "source_commits": result.get("source_commits", []),
            **(
                {"reason": result["reason"]}
                if result.get("reason")
                else {}
            ),
        },
    )


def record_application(
    experiment_record: Path,
    run_dir: Path,
    evidence_path: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    experiment = json.loads(
        experiment_record.read_text(encoding="utf-8")
    )
    if experiment.get("status") != "APPLIED":
        return {"status": "NO_ACTIVE_EXPERIMENT"}
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"experiment_id", "excerpts"}
        or evidence.get("experiment_id") != experiment["experiment_id"]
        or set(evidence.get("excerpts", {})) != {"ja", "en"}
    ):
        raise ValueError("application evidence shape or identity is invalid")
    hashes = {}
    for language in ("ja", "en"):
        article = run_dir / f"article-{language}.md"
        body = article.read_text(encoding="utf-8")
        excerpt = evidence["excerpts"][language]
        if (
            not isinstance(excerpt, str)
            or len(excerpt.strip()) < 12
            or excerpt not in body
        ):
            raise ValueError(
                f"{language} experiment excerpt is not in the article"
            )
        hashes[language] = _sha256_bytes(article.read_bytes())
    row = {
        "experiment_id": experiment["experiment_id"],
        "run_id": run_dir.name,
        "languages": ["ja", "en"],
        "artifact_sha256": hashes,
        "evidence_file": str(evidence_path),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = _json_lines(ledger_path)
    matches = [
        item
        for item in existing
        if item.get("experiment_id") == row["experiment_id"]
        and item.get("run_id") == row["run_id"]
    ]
    if matches:
        comparable = {
            key: matches[0].get(key)
            for key in (
                "experiment_id",
                "run_id",
                "languages",
                "artifact_sha256",
                "evidence_file",
            )
        }
        if comparable != {
            key: row[key]
            for key in comparable
        }:
            raise ValueError("application evidence replay conflicts")
        return matches[0]
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def active_experiment(state_root: Path) -> Path | None:
    active = []
    for path in sorted((state_root / "learning/experiments").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("status") == "APPLIED":
            active.append(path)
    if len(active) > 1:
        raise ValueError("multiple active experiments")
    return active[0] if active else None


def current_experiment(skill_dir: Path) -> dict[str, Any]:
    record = active_experiment(skill_dir / "state")
    if record is None:
        return {"status": "NONE"}
    experiment = json.loads(record.read_text(encoding="utf-8"))
    return {
        "status": "APPLIED",
        "experiment_id": experiment["experiment_id"],
        "proposal": experiment["proposal"],
        "cut": experiment["cut"],
        "evaluation_at": experiment["evaluation_at"],
        "playbook": str(skill_dir / "reference/learned-playbook.md"),
        "record": str(record),
    }


def verify_latest(skill_dir: Path, state_dir: Path | None = None) -> dict[str, Any]:
    state_root = Path(state_dir) if state_dir is not None else skill_dir / "state"
    ledger = state_root / "articles.jsonl"
    states = sorted(
        state_root.glob("runs/*/gates/publication-state.json")
    )
    missing: list[str] = []
    checked_run = None
    if not states:
        missing.append("no publication-state.json exists")
    else:
        state_path = states[-1]
        store = PublicationStore(state_path, ledger)
        state = store.read()
        checked_run = str(state.get("run_id", ""))
        status = store.completion_status()
        if status != "complete":
            missing.append(
                f"{checked_run} exact8 status is {status}, not complete"
            )
        run_dir = Path(str(state.get("run_dir", "")))
        for language in ("ja", "en"):
            gate = run_dir / "gates" / f"rubric-judge-{language}.json"
            try:
                payload = json.loads(gate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                missing.append(
                    f"{checked_run} rubric-judge-{language}.json is missing"
                )
                continue
            if not isinstance(payload.get("scores"), dict):
                missing.append(
                    f"{checked_run} rubric-judge-{language}.json lacks scores"
                )

        active = active_experiment(state_root)
        if active is not None and checked_run:
            experiment = json.loads(active.read_text(encoding="utf-8"))
            cut_date = datetime.fromisoformat(experiment["cut"]).date()
            run_date_match = re.fullmatch(
                r"daily-(\d{4}-\d{2}-\d{2})",
                checked_run,
            )
            run_date = (
                datetime.fromisoformat(run_date_match.group(1)).date()
                if run_date_match
                else None
            )
            if run_date is not None and run_date > cut_date:
                applications = _json_lines(
                    state_root / "playbook-applications.jsonl"
                )
                if not any(
                    row.get("experiment_id")
                    == experiment["experiment_id"]
                    and row.get("run_id") == checked_run
                    and set(row.get("languages", [])) == {"ja", "en"}
                    for row in applications
                ):
                    missing.append(
                        f"{checked_run} lacks both-lane application evidence "
                        f"for {experiment['experiment_id']}"
                    )
    result = {
        "checked_run": checked_run,
        "missing_count": len(missing),
        "missing": missing,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(state_root / ".selfimprove-todo.json", result)
    audit = state_root / "selfimprove-audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--skill-dir", type=Path, default=SCRIPTS.parent)
    run.add_argument(
        "--now",
        help=argparse.SUPPRESS,
    )
    run.add_argument(
        "--test-skip-remote-measurement",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    run.add_argument(
        "--test-no-commit",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    application = subparsers.add_parser("record-application")
    application.add_argument("--skill-dir", type=Path, default=SCRIPTS.parent)
    application.add_argument("--run-dir", type=Path, required=True)
    application.add_argument("--evidence", type=Path, required=True)
    current = subparsers.add_parser("current")
    current.add_argument("--skill-dir", type=Path, default=SCRIPTS.parent)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--skill-dir", type=Path, default=SCRIPTS.parent)
    verify.add_argument("--state-dir", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "current":
            result = current_experiment(args.skill_dir)
        elif args.command == "verify":
            result = verify_latest(args.skill_dir, args.state_dir)
        elif args.command == "record-application":
            experiment = active_experiment(args.skill_dir / "state")
            if experiment is None:
                print('{"status":"NO_ACTIVE_EXPERIMENT"}')
                return 0
            result = record_application(
                experiment,
                args.run_dir,
                args.evidence,
                args.skill_dir / "state/playbook-applications.jsonl",
            )
        else:
            now = (
                datetime.fromisoformat(args.now)
                if args.now
                else datetime.now().astimezone()
            )
            lock_path = args.skill_dir / "state/.self-improve.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+") as lock:
                try:
                    fcntl.flock(
                        lock.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                except BlockingIOError:
                    print('{"status":"LOCKED"}')
                    return 0
                result = run_cycle(
                    args.skill_dir,
                    now=now,
                    skip_remote_measurement=(
                        args.test_skip_remote_measurement
                    ),
                    commit_changes=not args.test_no_commit,
                )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        print(f"self-improve pending: {error}", file=sys.stderr)
        return 75
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 75 if result.get("status") == "PROVIDER_PENDING" else 0


if __name__ == "__main__":
    raise SystemExit(main())
