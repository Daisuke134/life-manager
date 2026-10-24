"""Aggregate-only, video-grouped research evaluation of AnnoMI labels.

This evaluates utterance annotation quality. It does not evaluate completed
behavior, treatment benefit, or suffering. Source rows and predictions remain
in memory and are never returned or printed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit


SOURCE_REVISION = "42936645ec3857a9c84ab296a36a3c34b779ef49"
SOURCE_SHA256 = "b178db3b0b9858a0fa4ed670dabeccd63e975ba67e141d7ae16f2e8214f78e61"
DEFAULT_SEED = 20261024
DEFAULT_FOLDS = 5
DEFAULT_BOOTSTRAPS = 2000
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_NA_LABELS = {"", "n/a", "na", "not applicable"}


class AnnoMIEvaluationError(ValueError):
    """Safe, fixed evaluation error without source text or paths."""


def _video_group(url: str) -> tuple[str, str]:
    """Return platform and a non-reversible video key, ignoring URL parameters."""
    if not isinstance(url, str):
        raise AnnoMIEvaluationError("INVALID_VIDEO_REFERENCE")
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        raise AnnoMIEvaluationError("INVALID_VIDEO_REFERENCE") from None
    host = (parsed.hostname or "").casefold()
    platform = ""
    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        platform = "youtube"
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif host in {"youtu.be", "www.youtu.be"}:
        platform = "youtube"
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"vimeo.com", "www.vimeo.com"}:
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) == 1 and re.fullmatch(r"[0-9]{6,12}", segments[0]):
            platform, video_id = "vimeo", segments[0]
    valid_id = (
        bool(_VIDEO_ID_RE.fullmatch(video_id)) if platform == "youtube"
        else bool(re.fullmatch(r"[0-9]{6,12}", video_id))
    )
    if parsed.scheme not in {"http", "https"} or not platform or not valid_id:
        raise AnnoMIEvaluationError("INVALID_VIDEO_REFERENCE")
    group = hashlib.sha256(("annomi-video\0" + platform + "\0" + video_id).encode("utf-8")).hexdigest()
    return platform, group


def _video_group_key(url: str) -> str:
    """Compatibility helper exposing only the non-reversible group key."""
    return _video_group(url)[1]


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _validated_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    required = {
        "transcript_id", "utterance_id", "video_url", "interlocutor", "utterance_text",
        "main_therapist_behaviour", "client_talk_type",
    }
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise AnnoMIEvaluationError("INVALID_ROWS")
    prepared: list[dict[str, str]] = []
    seen_utterances: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not required.issubset(row):
            raise AnnoMIEvaluationError("INVALID_SCHEMA")
        transcript = row.get("transcript_id")
        utterance = row.get("utterance_id")
        role = row.get("interlocutor")
        text = row.get("utterance_text")
        if any(not isinstance(value, str) or not value.strip() for value in (transcript, utterance, role)):
            raise AnnoMIEvaluationError("INVALID_ROW")
        if not isinstance(text, str):
            raise AnnoMIEvaluationError("INVALID_ROW")
        key = (transcript.strip(), utterance.strip())
        if key in seen_utterances:
            raise AnnoMIEvaluationError("DUPLICATE_UTTERANCE")
        seen_utterances.add(key)
        normalized_role = role.strip().casefold()
        if normalized_role not in {"therapist", "client"}:
            raise AnnoMIEvaluationError("INVALID_ROLE")
        label_field = "main_therapist_behaviour" if normalized_role == "therapist" else "client_talk_type"
        label = row.get(label_field)
        if not isinstance(label, str):
            raise AnnoMIEvaluationError("INVALID_LABEL")
        video_platform, group = _video_group(row.get("video_url"))
        prepared.append({
            "transcript": transcript.strip(),
            "group": group,
            "video_platform": video_platform,
            "role": normalized_role,
            "text": text,
            "normalized_text": _normalize_text(text),
            "label": label.strip().casefold(),
        })
    return prepared


def _classification_metrics(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]) -> dict[str, float | int | None]:
    if not y_true:
        return {"rows": 0, "accuracy": None, "macro_f1": None, "balanced_accuracy": None}
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

    return {
        "rows": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=list(labels), average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
    }


def _bootstrap_delta(
    y_true: Sequence[str],
    model_pred: Sequence[str],
    baseline_pred: Sequence[str],
    groups: Sequence[str],
    labels: Sequence[str],
    *,
    seed: int,
    resamples: int,
) -> dict[str, Any]:
    import numpy as np

    if type(resamples) is not int or resamples < 100:
        raise AnnoMIEvaluationError("INVALID_BOOTSTRAP_COUNT")
    indices_by_group: dict[str, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        indices_by_group[group].append(index)
    group_keys = sorted(indices_by_group)
    if len(group_keys) < 2:
        return {"point": None, "ci95": None, "n_groups": len(group_keys), "reason": "FEWER_THAN_TWO_GROUPS"}
    point = _classification_metrics(y_true, model_pred, labels)["macro_f1"] - _classification_metrics(y_true, baseline_pred, labels)["macro_f1"]
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    for _ in range(resamples):
        sampled = rng.choice(group_keys, size=len(group_keys), replace=True)
        indices = [index for group in sampled for index in indices_by_group[str(group)]]
        truth = [y_true[index] for index in indices]
        model = [model_pred[index] for index in indices]
        baseline = [baseline_pred[index] for index in indices]
        deltas.append(
            _classification_metrics(truth, model, labels)["macro_f1"]
            - _classification_metrics(truth, baseline, labels)["macro_f1"]
        )
    low, high = np.quantile(np.asarray(deltas), [0.025, 0.975], method="linear")
    return {"point": float(point), "ci95": [float(low), float(high)], "n_groups": len(group_keys), "method": "paired_percentile_video_group_bootstrap"}


def _evaluate_task(
    rows: Sequence[Mapping[str, str]],
    *,
    task: str,
    seed: int,
    n_splits: int,
    bootstrap_resamples: int,
) -> dict[str, Any]:
    import numpy as np
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    task_rows = [
        row for row in rows
        if row["role"] == task and row["label"] not in _NA_LABELS and row["normalized_text"]
    ]
    if not task_rows:
        raise AnnoMIEvaluationError("EMPTY_TASK")
    labels = sorted({row["label"] for row in task_rows})
    groups = np.asarray([row["group"] for row in task_rows], dtype=object)
    y = np.asarray([row["label"] for row in task_rows], dtype=object)
    texts = [row["text"] for row in task_rows]
    group_count = len(set(groups.tolist()))
    if len(labels) < 2 or group_count < n_splits:
        raise AnnoMIEvaluationError("INSUFFICIENT_GROUPS_OR_LABELS")

    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    model_predictions: list[str | None] = [None] * len(task_rows)
    majority_predictions: list[str | None] = [None] * len(task_rows)
    text_seen_by_training: list[bool | None] = [None] * len(task_rows)
    test_groups_seen: set[str] = set()
    overlap_count = 0
    for train_indices, test_indices in splitter.split(texts, y, groups):
        train_groups = set(groups[train_indices].tolist())
        test_groups = set(groups[test_indices].tolist())
        overlap_count += len(train_groups & test_groups)
        if overlap_count:
            raise AnnoMIEvaluationError("GROUP_LEAKAGE_DETECTED")
        repeated = test_groups_seen & test_groups
        if repeated:
            raise AnnoMIEvaluationError("GROUP_ASSIGNED_TO_MULTIPLE_TEST_FOLDS")
        test_groups_seen.update(test_groups)
        training_labels = Counter(y[train_indices].tolist())
        majority = min(training_labels, key=lambda label: (-training_labels[label], label))
        for index in test_indices:
            majority_predictions[int(index)] = majority
        training_texts = {_normalize_text(texts[int(index)]) for index in train_indices}
        for index in test_indices:
            text_seen_by_training[int(index)] = _normalize_text(texts[int(index)]) in training_texts
        try:
            vectorizer = TfidfVectorizer(
                lowercase=True, strip_accents="unicode", ngram_range=(1, 2),
                min_df=2, max_features=50_000, sublinear_tf=True, dtype=np.float32,
            )
            x_train = vectorizer.fit_transform([texts[int(index)] for index in train_indices])
            x_test = vectorizer.transform([texts[int(index)] for index in test_indices])
            classifier = LogisticRegression(
                C=1.0, class_weight="balanced", max_iter=500, random_state=seed,
                solver="lbfgs",
            )
            classifier.fit(x_train, y[train_indices])
            predictions = classifier.predict(x_test).tolist()
        except (ValueError, RuntimeError):
            raise AnnoMIEvaluationError("MODEL_FIT_FAILED") from None
        for index, prediction in zip(test_indices, predictions):
            model_predictions[int(index)] = str(prediction)

    if any(value is None for value in model_predictions + majority_predictions + text_seen_by_training):
        raise AnnoMIEvaluationError("INCOMPLETE_CROSS_VALIDATION")
    model_y = [str(value) for value in model_predictions]
    majority_y = [str(value) for value in majority_predictions]
    truth = y.tolist()
    seen_mask = [bool(value) for value in text_seen_by_training]
    seen_indices = [index for index, seen in enumerate(seen_mask) if seen]
    unseen_indices = [index for index, seen in enumerate(seen_mask) if not seen]

    def subset_metrics(indices: Sequence[int]) -> dict[str, Any]:
        return _classification_metrics(
            [truth[index] for index in indices],
            [model_y[index] for index in indices],
            labels,
        )

    delta = _bootstrap_delta(
        truth, model_y, majority_y, groups.tolist(), labels,
        seed=seed, resamples=bootstrap_resamples,
    )
    counts = Counter(truth)
    return {
        "assigned": len(task_rows),
        "attempted": len(task_rows),
        "valid": len(task_rows),
        "invalid": 0,
        "refused": 0,
        "not_run": 0,
        "video_groups": group_count,
        "classes": {label: counts[label] for label in labels},
        "metrics": {
            "majority_baseline": _classification_metrics(truth, majority_y, labels),
            "tfidf_logistic_regression": _classification_metrics(truth, model_y, labels),
            "macro_f1_delta_vs_majority": delta,
        },
        "exact_text_reuse": {
            "rows_seen_in_training_video_folds": len(seen_indices),
            "rows_unseen_in_training_video_folds": len(unseen_indices),
            "model_metrics_on_seen_text": subset_metrics(seen_indices),
            "model_metrics_on_unseen_text": subset_metrics(unseen_indices),
        },
        "cross_fold_group_leaks": overlap_count,
        "groups_tested_once": len(test_groups_seen),
        "sklearn_version": sklearn.__version__,
    }


def evaluate_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    *,
    n_splits: int = DEFAULT_FOLDS,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAPS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Evaluate both role-specific human-label tasks and return aggregates only."""
    if type(n_splits) is not int or n_splits < 2 or type(seed) is not int:
        raise AnnoMIEvaluationError("INVALID_EVALUATION_CONFIG")
    rows = _validated_rows(raw_rows)
    groups_by_text: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["normalized_text"]:
            groups_by_text[row["normalized_text"]].add(row["group"])
    shared_texts = {text for text, groups in groups_by_text.items() if len(groups) > 1}
    rows_with_cross_video_text = sum(row["normalized_text"] in shared_texts for row in rows)
    video_groups = {row["group"] for row in rows}
    platform_group_counts = {
        platform: len({row["group"] for row in rows if row["video_platform"] == platform})
        for platform in sorted({row["video_platform"] for row in rows})
    }
    transcripts = {row["transcript"] for row in rows}
    return {
        "schema": "manager.annomi-dialogue-evaluation.v1",
        "status": "COMPLETE",
        "claim_boundary": "human_utterance_annotation_quality_only_not_behavior_or_welfare",
        "split": {
            "grouping_unit": "normalized_source_video",
            "n_folds": n_splits,
            "seed": seed,
            "video_groups": len(video_groups),
            "video_groups_by_platform": platform_group_counts,
            "transcripts": len(transcripts),
            "cross_fold_group_leaks": 0,
            "source_texts_repeated_across_video_groups": len(shared_texts),
            "source_rows_with_text_repeated_across_video_groups": rows_with_cross_video_text,
        },
        "tasks": {
            task: _evaluate_task(
                rows, task=task, seed=seed, n_splits=n_splits,
                bootstrap_resamples=bootstrap_resamples,
            )
            for task in ("therapist", "client")
        },
    }


def evaluate_csv(
    path: str | Path,
    *,
    expected_sha256: str = SOURCE_SHA256,
    n_splits: int = DEFAULT_FOLDS,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAPS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Read the pinned public artifact without exposing its path or source rows."""
    try:
        payload = Path(path).read_bytes()
    except OSError:
        raise AnnoMIEvaluationError("SOURCE_UNAVAILABLE") from None
    actual_sha = hashlib.sha256(payload).hexdigest()
    if not isinstance(expected_sha256, str) or actual_sha != expected_sha256:
        raise AnnoMIEvaluationError("SOURCE_HASH_MISMATCH")
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig", errors="strict")))
        required = {
            "transcript_id", "utterance_id", "video_url", "interlocutor", "utterance_text",
            "main_therapist_behaviour", "client_talk_type",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AnnoMIEvaluationError("INVALID_SCHEMA")
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise AnnoMIEvaluationError("SOURCE_PARSE_FAILED") from None
    result = evaluate_rows(
        rows, n_splits=n_splits, bootstrap_resamples=bootstrap_resamples, seed=seed,
    )
    result["source"] = {
        "repository": "uccollab/AnnoMI",
        "revision": SOURCE_REVISION,
        "artifact": "AnnoMI-simple.csv",
        "sha256": actual_sha,
        "label_source": "released_human_utterance_annotations",
        "rights_scope": "bounded_local_research; no source rows or weights published",
    }
    return result
