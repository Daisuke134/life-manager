"""promote_gate_run.py — close-loop Gap 3: the EFFECTFUL driver `promote_gate.sh` invokes.

Confined here (mirrors `lib/promote.py`'s own "subprocess deliberately confined to THIS module"
convention): everything that talks to a real subprocess (the fresh Codex adversary call) or
performs the actual promotion side effect. The DETERMINISTIC/pure decision logic
(`assess_candidate`/`decide_promotion`/`promote_if_approved`) lives in `lib/promote_gate.py` and is
unit-tested there (`tests/test_adversary_disapprove.py`) WITHOUT ever spending a real LLM call —
this module is instead exercised by the one real, human-zero "RUN IT ONCE" proof invocation
(evidence under `evidence/close-loop/`), never by the fast pytest suite.

REQ-RH4 order enforced end-to-end: (1)+(2) (stage2 beats_baseline + trip-wire clear) are checked by
`assess_candidate` BEFORE this module ever shells out to an LLM — an ineligible candidate never
costs a single token. Only an eligible candidate reaches step (3), the fresh adversary call.

Usage: `python3 lib/promote_gate_run.py <candidate_program_path> <run_dir> [--dry-run]`
`--dry-run` (or `PROMOTE_GATE_DRY_RUN=1`) still runs the full assessment + real adversary call, but
never actually commits the promotion (useful for smoke-testing the mechanism against a
hand-crafted candidate without mutating the committed baseline strategy file).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from difflib import unified_diff
from typing import Optional

_SELF_IMPROVE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SELF_IMPROVE_DIR not in sys.path:
    sys.path.insert(0, _SELF_IMPROVE_DIR)

import evaluator  # noqa: E402
from lib import promote_gate  # noqa: E402

ADVERSARY_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    }
)

ADVERSARY_TIMEOUT_S = 600


def _repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=_SELF_IMPROVE_DIR, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def write_realized_gate_escalation(run_dir: str, realized_gate: dict, candidate_path: str) -> None:
    """REQ-RL13: escalation record for a human/adversary reviewing a REQ-RL10/RL11 block later —
    written BEFORE `decide_promotion` is even called for that run (see `main()`'s call ordering).
    This write itself never influences the decision, which `decide_promotion` computes
    independently and identically from the SAME `realized_gate` dict (purity boundary — this
    function is the impure I/O half; `decide_promotion` stays pure)."""
    if realized_gate.get("trend_blocks"):
        reason = (
            "realized ledger trend blocks promotion: "
            f"window_net_usd={realized_gate.get('window_net_usd')}, "
            f"first_half_net_usd={realized_gate.get('first_half_net_usd')}, "
            f"second_half_net_usd={realized_gate.get('second_half_net_usd')}"
        )
    elif realized_gate.get("realism_gap_blocks"):
        reason = (
            "realized ledger data shows an implausible fixture-vs-reality gap "
            "(data_realism_gap): promotion blocked"
        )
    else:
        reason = "realized_gate escalation written without an active REQ-RL10/RL11 block"

    escalation = {**realized_gate, "candidate_path": candidate_path, "reason": reason}
    escalation_path = os.path.join(run_dir, "realized_gate_escalation.json")
    with open(escalation_path, "w", encoding="utf-8") as f:
        json.dump(escalation, f, indent=2, default=str)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _build_prompt(assessment: dict, candidate_code: str, baseline_code: str) -> str:
    diff_lines = list(
        unified_diff(
            baseline_code.splitlines(keepends=True),
            candidate_code.splitlines(keepends=True),
            fromfile="strategies/pm_backtest_strategy.py (baseline)",
            tofile="candidate (openevolve-proposed)",
        )
    )
    diff_text = "".join(diff_lines) or "(no textual diff — candidate is byte-identical to baseline)"

    return f"""You are the fresh, independent per-candidate promotion adversary for Anicca's
self-improve harness (behavioral-spec.md REQ-RH4 step 3). This is a PAPER/BACKTEST-ONLY harness —
nothing you approve executes a live trade; "promote" only means merging this diff into a committed
backtest strategy file (strategies/pm_backtest_strategy.py). No human is in this loop; your verdict
is the final gate before any promotion.

DETERMINISTIC PRE-CHECKS (already computed, before you were invoked — you do not need to
re-derive these, but you MAY spot-check anything below using Read/Bash if you want independent
verification):
- scope_guard verdict: {assessment['scope_guard_reason']} (ok={assessment['scope_guard_ok']})
- stage1_pass: {assessment['stage1_pass']}
- stage2_pass (beats_baseline): {assessment['stage2_pass']}
- combined_score (risk-adjusted, candidate): {assessment['combined_score']}
- baseline_stage2_score (risk-adjusted, baseline): {assessment['baseline_stage2_score']}
- mean_oos_net_usd: {assessment['mean_oos_net_usd']}  std_oos_net_usd: {assessment['std_oos_net_usd']}
- worst_window_oos_net_usd: {assessment['worst_window_oos_net_usd']}
- trip-wire clear (not an implausible >3x jump over population_best={assessment['population_best_used']}): {assessment['tripwire_clear']}

THE DIFF (candidate vs the frozen baseline, EVOLVE-BLOCK region only — scope_guard already
verified nothing outside it changed):
```diff
{diff_text}
```

YOUR JOB: decide whether this candidate represents a GENUINE selection/edge improvement, or is
variance-amplification / leverage / overfitting to this specific historical fixture dressed up as
one. Specifically weigh:
1. Does the candidate change WHICH trades are selected (a real selection/logic change), or does it
   only change stake SIZE on the same selection as baseline (leverage)? A pure stake multiplier on
   an unchanged selection cannot genuinely raise a risk-adjusted (mean/stddev) score except by
   floating-point noise — if you see one anyway, treat it with suspicion.
2. Is the worst individual OOS window (`worst_window_oos_net_usd` above) non-negative, or does the
   apparent improvement hide behind a good average with a hidden bad window (EDGE-5)?
3. Is std_oos_net_usd suspiciously close to zero (a near-zero-variance artifact from only 3 OOS
   data points can produce an inflated ratio that is not really "proven" by 3 points)?
4. Does the candidate's own code stay inside the single evolvable function
   (`score_candidate`), doing plausible strategy logic (thresholds, sizing, feature combination) —
   not something structurally suspicious?

Write your verdict as your ONLY structured output: {{"verdict": "PASS" or "FAIL", "reason": "<one
paragraph, concrete, citing the specific numbers/diff content that drove your decision>"}}.
"PASS" means you are willing to have this candidate promoted into the committed baseline strategy
file for future backtest runs. Default to FAIL when genuinely uncertain (fail-closed)."""


def _invoke_adversary(prompt: str, repo_root: str) -> dict:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        return {"ok": False, "error": "Codex CLI is unavailable"}

    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("ANTHROPIC_") and key != "CLAUDE_CODE_OAUTH_TOKEN"
    }
    try:
        with tempfile.TemporaryDirectory(prefix="self-improve-codex-") as temporary:
            schema_path = os.path.join(temporary, "adversary-schema.json")
            output_path = os.path.join(temporary, "adversary-output.json")
            with open(schema_path, "w", encoding="utf-8") as schema_file:
                schema_file.write(ADVERSARY_JSON_SCHEMA)
            cmd = [
                codex_bin,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "-C",
                repo_root,
                "--output-schema",
                schema_path,
                "--output-last-message",
                output_path,
                "-",
            ]
            result = subprocess.run(
                cmd, cwd=repo_root, input=prompt, capture_output=True, text=True,
                timeout=ADVERSARY_TIMEOUT_S, env=env,
            )
            if result.returncode != 0:
                return {
                    "ok": False,
                    "error": f"Codex adversary exited {result.returncode}: {result.stderr[-2000:]}",
                }
            try:
                structured = json.loads(_read_text(output_path))
            except (OSError, ValueError):
                return {"ok": False, "error": "Codex adversary response was missing or invalid JSON"}
            if (not isinstance(structured, dict)
                    or structured.get("verdict") not in {"PASS", "FAIL"}
                    or not isinstance(structured.get("reason"), str)):
                return {"ok": False, "error": "Codex adversary response did not match the verdict schema"}
            return {
                "ok": True,
                "verdict": structured["verdict"],
                "reason": structured["reason"],
                "cost_usd": None,
                "session_id": None,
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Codex adversary timed out after {ADVERSARY_TIMEOUT_S}s"}
    except FileNotFoundError:
        return {"ok": False, "error": f"Codex CLI disappeared after resolving {codex_bin}"}


def main(argv: list) -> int:
    if len(argv) < 3:
        print("usage: promote_gate_run.py <candidate_program_path> <run_dir> [--dry-run]", file=sys.stderr)
        return 2
    candidate_path = argv[1]
    run_dir = argv[2]
    dry_run = "--dry-run" in argv[3:] or os.environ.get("PROMOTE_GATE_DRY_RUN") == "1"

    os.makedirs(run_dir, exist_ok=True)
    verdict_path = os.path.join(run_dir, "verdict.json")
    log_path = os.path.join(run_dir, "promote_gate.log")

    def _log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

    if not os.path.isfile(candidate_path):
        out = {"promote": False, "reason": f"candidate program not found at {candidate_path}", "adversary_invoked": False}
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        _log(f"FATAL candidate not found: {candidate_path}")
        return 1

    repo_root = _repo_root()

    assessment = promote_gate.assess_candidate(candidate_path)
    with open(os.path.join(run_dir, "assessment.json"), "w", encoding="utf-8") as f:
        json.dump(assessment, f, indent=2, default=str)

    # REQ-RL17: compute realized_gate ONCE, pass it to EVERY decide_promotion call site below —
    # never a hardcoded literal/stub, always sourced from this instance's own resolved ledger.
    # mean_backtest_net_usd MUST be the DOLLAR-scale mean_oos_net_usd (REQ-RL11), never the
    # unitless combined_score risk-adjusted ratio (F-1, Phase-3 impl review iteration 1) — it is
    # None for a scope-guard-rejected/stage1-failed candidate, which compute_realized_gate handles
    # None-safely (realism_gap_blocks stays False; every other key still computes normally).
    realized_gate = promote_gate.compute_realized_gate(
        mean_backtest_net_usd=assessment["mean_oos_net_usd"], repo_cwd=repo_root
    )
    with open(os.path.join(run_dir, "realized_gate.json"), "w", encoding="utf-8") as f:
        json.dump(realized_gate, f, indent=2, default=str)

    if realized_gate.get("trend_blocks") or realized_gate.get("realism_gap_blocks"):
        write_realized_gate_escalation(run_dir=run_dir, realized_gate=realized_gate, candidate_path=candidate_path)

    if not assessment["eligible_for_adversary_review"]:
        decision = promote_gate.decide_promotion(assessment, adversary_verdict=None, realized_gate=realized_gate)
        out = {**decision, "adversary_invoked": False, "assessment": assessment}
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        _log(f"NOT ELIGIBLE for adversary review (no LLM call made): {decision['reason']}")
        return 0

    candidate_code = _read_text(candidate_path)
    baseline_code = _read_text(evaluator.BASELINE_PATH)
    prompt = _build_prompt(assessment, candidate_code, baseline_code)

    _log("candidate is eligible — invoking fresh Opus adversary (real call, real $ per --max-budget-usd cap)")
    adversary_result = _invoke_adversary(prompt, repo_root)

    if not adversary_result["ok"]:
        decision = promote_gate.decide_promotion(
            assessment,
            adversary_verdict=None,
            adversary_reason=f"adversary unavailable/erroring: {adversary_result['error']}",
            realized_gate=realized_gate,
        )
        out = {**decision, "adversary_invoked": True, "adversary_error": adversary_result["error"], "assessment": assessment}
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        _log(f"ADVERSARY UNAVAILABLE/ERRORED (fail-closed, not promoted): {adversary_result['error']}")
        return 0

    decision = promote_gate.decide_promotion(
        assessment,
        adversary_verdict=adversary_result["verdict"],
        adversary_reason=adversary_result["reason"],
        realized_gate=realized_gate,
    )
    _log(
        f"ADVERSARY VERDICT: {adversary_result['verdict']} — {adversary_result['reason']} "
        f"(cost_usd={adversary_result.get('cost_usd')})"
    )

    # IMPORTANT (found the hard way during this feature's own smoke test, see execution notes):
    # `lib.promote.promote(..., commit=False)` still WRITES `baseline_path` to disk unconditionally
    # — only the git-commit step is skipped, per its own documented "commit=False writes the file
    # only (for dry-run tooling)" contract. That is NOT a safe no-op for a `--dry-run` smoke test
    # against the REAL committed baseline path, so `--dry-run` here skips calling
    # `promote_if_approved`/`promote.promote` ENTIRELY (zero file writes, zero git operations) —
    # it only ever reports what the decision WOULD have been.
    if dry_run:
        promote_result = {
            "committed": False,
            "reason": "dry-run: promote_if_approved/promote.promote was never called (zero file/git side effects)",
            "would_promote": decision["promote"],
        }
    else:
        promote_result = promote_gate.promote_if_approved(
            candidate_code, evaluator.BASELINE_PATH, decision, cwd=repo_root, commit=True
        )
    out = {
        **decision,
        "adversary_invoked": True,
        "adversary_cost_usd": adversary_result.get("cost_usd"),
        "adversary_session_id": adversary_result.get("session_id"),
        "dry_run": dry_run,
        "promote_result": promote_result,
        "assessment": assessment,
    }
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    if decision["promote"] and not dry_run:
        _log(f"PROMOTED: committed={promote_result.get('committed')} commit={promote_result.get('commit')}")
    elif decision["promote"] and dry_run:
        _log("DRY-RUN: adversary said PASS but --dry-run set — NOT committed (smoke test only)")
    else:
        _log(f"NOT PROMOTED: {decision['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
