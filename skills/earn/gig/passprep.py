#!/usr/bin/env python3
"""passprep.py — deterministic pass-prep helper for the gig earn-core.
Called at the START of every cron pass. Reads/repairs strategy.json,
enforces skip-floor, increments pass_count, and prints ONE JSON line
to stdout. No external dependencies (stdlib only).

Exit 0 always: on any unexpected error, falls back to safe defaults
and still prints valid JSON (with an _error field on stderr).
"""
import json
import os
import sys
import shutil
import tempfile
import time
from copy import deepcopy

HOME = os.path.expanduser("~")
GIG_DIR = os.path.join(HOME, "gig")
STRATEGY_FILE = os.path.join(GIG_DIR, "strategy.json")
# strategy.default.json lives next to this script in the skill directory
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STRATEGY = os.path.join(SKILL_DIR, "strategy.default.json")

FALLBACK = {
    "version": 1,
    "max_apply_per_pass": 7,
    "improve_cadence_passes": 4,
    "priority_categories": [
        "PPT/スライド",
        "資料作成",
        "記事/blog",
        "データ入力/Excel",
        "文字起こし",
        "コード",
        "Web制作",
        "自動化",
        "スクレイピング",
        "業務システム",
        "LP/ランディングページ",
    ],
    "skip_categories": [],
    "price_defaults": {
        "PPT/スライド": 8000,
        "資料作成": 10000,
        "記事/blog": 5000,
        "データ入力/Excel": 4000,
        "文字起こし": 4000,
        "コード": 15000,
        "LP/ランディングページ": 20000,
    },
    "proposal_templates": {},
    "profile_blurb": "AIエージェントによる高品質・迅速な作業対応。PPT・資料・記事・データ入力・コード対応。",
    "pass_count": 0,
    "improve_cycle": 0,
    "experiments": [],
    "listing_weekly_target": 2,
    "apply_skip_thresholds": {
        "max_applicants": 30,
        "min_contracted_to_skip": 1,
        "min_budget_jpy": 3000,
    },
    "notes": "Fallback defaults — strategy.default.json was not found.",
}

SETTLED = {"検収", "支払", "検収完了", "completed", "paid"}
MAX_APPLICATIONS_PER_HOUR = 7
MIN_PROPOSAL_CHARS = 200
MAX_PROPOSAL_CHARS = 3000
PROPOSAL_COMPLIANCE_SUFFIX = """

募集内容を確認したうえで、最初に成果物・対象範囲・優先順位を整理し、認識合わせを行います。着手後は途中経過を共有し、必要な修正を反映しながら納品まで進めます。ご用意いただきたい資料やアカウント権限は開始前に一覧化します。提案金額には要件確認、実作業、動作確認、納品後の軽微な修正を含みます。追加作業が必要な場合は、実施前に範囲と金額をお伝えします。納期はトークルーム開始後、実行可能な最短日で進行します。ご不明点には迅速に回答しますので、まずは詳細をお聞かせください。
""".strip()


def merge_missing_keys(existing, default):
    """Fill absent/None top-level defaults without overwriting live tuning."""
    merged = deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in (default.items() if isinstance(default, dict) else []):
        if key not in merged or merged[key] is None:
            merged[key] = deepcopy(value)
    return merged


def enforce_proposal_form_constraints(strategy):
    """Keep every live proposal inside Coconala's measured 200–3000 char range.

    This is platform form compliance, not an experiment mutation.  In particular,
    an experiment freeze must not preserve a template the live submit form rejects.
    """
    templates = strategy.get("proposal_templates")
    if not isinstance(templates, dict):
        templates = {}
    repaired = {}
    for category, value in templates.items():
        text = value.strip() if isinstance(value, str) else ""
        if len(text) < MIN_PROPOSAL_CHARS:
            text = f"{text}\n\n{PROPOSAL_COMPLIANCE_SUFFIX}".strip()
        while len(text) < MIN_PROPOSAL_CHARS:
            text += " ご依頼内容に合わせて作業範囲と納品条件を明確にし、合意した内容を誠実に実行します。"
        repaired[str(category)] = text[:MAX_PROPOSAL_CHARS]
    strategy["proposal_templates"] = repaired
    return strategy


def compute_listings_due(listing_rows, now_epoch, listing_weekly_target):
    """Return whether trailing-seven-day listing volume is below target."""
    try:
        target = max(0, int(listing_weekly_target))
        now = float(now_epoch)
    except (TypeError, ValueError):
        return True
    count = 0
    for row in listing_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            timestamp = float(row.get("ts"))
        except (TypeError, ValueError):
            continue
        if now - 7 * 86400 <= timestamp <= now:
            count += 1
    return count < target


def jnum(value):
    try:
        return float(str(value).replace(",", "").replace("¥", "").replace("円", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_cold_start(earnings_rows):
    """Cold start ends only after evidence-backed positive settled revenue."""
    settled = sum(
        jnum(row.get("jpy"))
        for row in earnings_rows or []
        if isinstance(row, dict)
        and row.get("status") in SETTLED
        and bool(row.get("evidence"))
        and jnum(row.get("jpy")) > 0
    )
    return settled <= 0


def read_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows


def load_default_strategy():
    try:
        with open(DEFAULT_STRATEGY, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else deepcopy(FALLBACK)
    except (OSError, ValueError, json.JSONDecodeError):
        return deepcopy(FALLBACK)


def atomic_write(path, data):
    """Write JSON atomically via temp file + os.replace."""
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_strategy():
    """Load strategy.json; on missing/corrupt, restore from default (or fallback) and load that."""
    os.makedirs(GIG_DIR, exist_ok=True)

    # Try to load existing strategy.json
    if os.path.exists(STRATEGY_FILE):
        try:
            with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return merge_missing_keys(data, load_default_strategy()), False
        except (json.JSONDecodeError, OSError, ValueError):
            # Corrupt — fall through to repair
            pass

    # Restore from strategy.default.json if available
    if os.path.exists(DEFAULT_STRATEGY):
        try:
            shutil.copy2(DEFAULT_STRATEGY, STRATEGY_FILE)
            with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, True
        except Exception:
            pass

    # Last resort: hardcoded fallback (strategy.default.json missing in this HOME)
    strategy = dict(FALLBACK)
    atomic_write(STRATEGY_FILE, strategy)
    return strategy, True


def load_category_decision(strategy_file):
    """The measured category order for this pass, via scripts/b2_objective.py.

    Loaded by path rather than by `import`, so pass-prep does not depend on how sys.path
    happens to be set when it runs, and so scripts/ cannot shadow a stdlib name here.

    Read-only and record-free on purpose: application_direct.py writes the decision row,
    because only it knows the PASS_ID the decision actually steered. Recording here too
    would put two rows per pass in the ledger and make "how many passes did the bandit
    steer?" unanswerable.
    """
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "scripts", "b2_objective.py")
    spec = importlib.util.spec_from_file_location("b2_objective_for_passprep", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(strategy_path=strategy_file)


def main():
    try:
        strategy, was_repaired = load_strategy()

        # 明示的な 0（出品拡大の凍結）を falsy で握り潰さない。未設定のときだけ既定 2。
        _listing_weekly_target = strategy.get("listing_weekly_target")
        listing_weekly_target = 2 if _listing_weekly_target is None else int(_listing_weekly_target)
        listings_due = compute_listings_due(
            read_jsonl(os.path.join(GIG_DIR, "listings.jsonl")), time.time(), listing_weekly_target
        )
        cold_start = compute_cold_start(read_jsonl(os.path.join(GIG_DIR, "earnings.jsonl")))

        # Enforce skip-floor (FIND-005):
        # If every priority_category is in skip_categories, reset skip_categories to []
        # so there are still categories available to apply to.
        priority = list(strategy.get("priority_categories") or [])
        skip = list(strategy.get("skip_categories") or [])
        if priority and all(c in skip for c in priority):
            strategy["skip_categories"] = []
            skip = []

        # G1c-S: target four, hard cap seven is an operating invariant, not an
        # experiment knob.  Persist it on every prep so the old live value (4) and
        # self-improvement drift cannot silently keep the money entrance narrow.
        strategy["max_apply_per_pass"] = MAX_APPLICATIONS_PER_HOUR
        enforce_proposal_form_constraints(strategy)

        # Increment pass_count deterministically (FIND-001)
        pass_count = int(strategy.get("pass_count") or 0) + 1
        strategy["pass_count"] = pass_count

        # Compute do_improve: true when pass_count is a multiple of improve_cadence_passes
        cadence = max(1, int(strategy.get("improve_cadence_passes") or 4))
        do_improve = (pass_count % cadence == 0)

        # 50/50 explore/exploit self-improve (gig L1-b): advance the improve_cycle
        # counter ONLY on an improve pass and alternate the mode so half of all
        # improve cycles search EXTERNAL best-practices (explore) and half tune
        # introspectively from own lessons (exploit). First improve = explore.
        # This is deterministic bookkeeping only; WHICH change to make stays the
        # agent's judgment (no hardcoded rule picks the mutation).
        improve_cycle = int(strategy.get("improve_cycle") or 0)
        if do_improve:
            improve_cycle += 1
            strategy["improve_cycle"] = improve_cycle
            improve_mode = "explore" if (improve_cycle % 2 == 1) else "exploit"
        else:
            improve_mode = None

        # Surface active experiments whose evaluation window has elapsed so the
        # improve step can keep-or-revert them against REAL funnel metrics.
        experiments = strategy.get("experiments")
        experiments = experiments if isinstance(experiments, list) else []
        experiments_due = [
            e for e in experiments
            if isinstance(e, dict)
            and e.get("status") == "active"
            and isinstance(e.get("eval_by_pass"), int)
            and pass_count >= e["eval_by_pass"]
        ]
        active_experiments = [
            e for e in experiments
            if isinstance(e, dict) and e.get("status") == "active"
        ]
        active_strategy_experiment = None
        if len(active_experiments) == 1:
            active = active_experiments[0]
            active_strategy_experiment = {
                "id": active.get("id"),
                "field_changed": active.get("field_changed"),
                "new_value": deepcopy(active.get("new_value")),
                "target_metric": active.get("target_metric"),
            }

        # Single atomic write-back (pass_count and possibly improve_cycle advanced)
        atomic_write(STRATEGY_FILE, strategy)

        # X8c: hand the pass a category order that measured reward produced, not one
        # the LLM asserted. category_bandit.py had computed this ranking since a11cc68
        # with zero callers; b2_objective.py turns it into a decision and records it.
        #
        # Isolated in its own try, deliberately. Everything above already advanced
        # pass_count and wrote strategy.json back; letting a bandit failure fall through
        # to main()'s except would emit the crash-safe fallback and lose that increment,
        # which would then re-run improve cadence off a stale counter. A ranking is worth
        # far less than the pass bookkeeping, so it is the ranking that gets dropped.
        category = {}
        try:
            category = load_category_decision(STRATEGY_FILE)
        except Exception as exc:                      # pragma: no cover - defence in depth
            print(f"passprep.py category decision unavailable: {exc}", file=sys.stderr)

        category_order = list(category.get("category_order") or [])
        if not category_order:
            category_order = list(strategy.get("priority_categories") or [])
        # The freeze is how the two learners avoid confounding each other: Thompson
        # sampling moves the CATEGORY dimension, experiments[] moves WORDING/PRICE/
        # TEMPLATES, and if both move in one window neither can read its own result.
        # may_start_experiment is the deterministic half of that -- B4-EXPLORE consumes
        # it. Evaluating experiments already running stays allowed (experiments_due is
        # untouched), because stranding them mid-flight would be worse than either.
        freeze = bool(category.get("freeze_experiments"))

        result = {
            "pass_count": pass_count,
            "do_improve": do_improve,
            "improve_mode": improve_mode,
            "experiments_due": experiments_due,
            "active_strategy_experiment": active_strategy_experiment,
            "max_apply_per_pass": int(strategy["max_apply_per_pass"]),
            "target_retainer_apply_per_pass": 1,
            "category_order": category_order,
            "category_source": category.get("decided_by") or "fallback",
            "experiment_freeze": freeze,
            "may_start_experiment": not freeze,
            "experiment_freeze_release": category.get("freeze_release_condition") or "",
            "priority_categories": list(strategy.get("priority_categories") or []),
            "skip_categories": list(strategy.get("skip_categories") or []),
            "listings_due": listings_due,
            "cold_start": cold_start,
            "apply_skip_thresholds": dict(strategy.get("apply_skip_thresholds") or FALLBACK["apply_skip_thresholds"]),
        }
        if was_repaired:
            result["_repaired"] = True
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        # Crash-safe fallback: emit valid JSON with safe defaults; do_improve=false
        fallback_result = {
            "pass_count": 0,
            "do_improve": False,
            "improve_mode": None,
            "experiments_due": [],
            "active_strategy_experiment": None,
            "max_apply_per_pass": MAX_APPLICATIONS_PER_HOUR,
            "target_retainer_apply_per_pass": 1,
            # X8c: even the crash-safe path names a category order. A pass that reaches
            # here has no measured ranking, so it says so rather than implying one.
            "category_order": list(FALLBACK["priority_categories"]),
            "category_source": "fallback",
            "experiment_freeze": False,
            "may_start_experiment": True,
            "experiment_freeze_release": "",
            "priority_categories": FALLBACK["priority_categories"],
            "skip_categories": [],
            "listings_due": True,
            "cold_start": True,
            "apply_skip_thresholds": dict(FALLBACK["apply_skip_thresholds"]),
            "_error": str(exc),
        }
        print(f"passprep.py ERROR: {exc}", file=sys.stderr)
        print(json.dumps(fallback_result, ensure_ascii=False))


if __name__ == "__main__":
    main()
