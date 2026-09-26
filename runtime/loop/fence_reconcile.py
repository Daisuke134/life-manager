#!/usr/bin/env python3
"""Close host-admission effect_unknown fences via each owner's own readback script.

This is the generic T5-G-2/T5-G-3 reconciler (see
``docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md``). It reads
the exact live fences from ``_admission_effect_unknown_occurrences`` and, for
every owner that declares ``effect_reconcile`` in ``config/loop-registry.json``,
runs that owner's existing official-readback script -- the same script a human
previously ran by hand. A script call proves either "no effect" or "effect
with a receipt" through the owner's own provider readback before closing
anything; nothing here retries or replays an effect. A non-zero exit, a
timeout, or a script that still reports the occurrence fenced simply leaves
that occurrence fenced for the next wake.

Owners with current fences but no ``effect_reconcile`` entry are reported in
``needs_readback_adapter`` (T5-G-4): a human/dev-loop task, not this loop,
must add their adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop.lm_loop import _admission_effect_unknown_occurrences  # noqa: E402
from runtime.loop.macos_loop_registry import validate_registry  # noqa: E402

DEFAULT_REGISTRY = ROOT / "config/loop-registry.json"
CALL_TIMEOUT_SECONDS = 60
MAX_CALLS_PER_WAKE = 20
STDOUT_TAIL_LIMIT = 300
DEFAULT_LOG = Path(
    "~/.local/state/life-manager/lm-fence-reconciler/reconcile-calls.jsonl"
).expanduser()


def run_call(argv: list[str]) -> tuple[int, str]:
    """Run one owner reconcile script; never raises, always (exit_code, stdout_tail)."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=CALL_TIMEOUT_SECONDS, check=False,
        )
        return result.returncode, (result.stdout or "")[-STDOUT_TAIL_LIMIT:]
    except subprocess.TimeoutExpired:
        return 124, "reconcile_call_timed_out"
    except OSError as error:
        return 127, f"reconcile_call_start_failed:{type(error).__name__}"


def build_argv(reconcile_cfg: Mapping[str, object], root: Path,
                occurrence: str | None) -> list[str]:
    """Turn one registry ``effect_reconcile`` row plus a target into a real argv.

    ``argv[0]`` is always a repository-relative script path (validated by
    ``macos_loop_registry``), never marked executable, so it is always invoked
    through the current Python interpreter.
    """
    fixed = list(reconcile_cfg.get("argv") or [])
    if not fixed:
        raise ValueError("effect_reconcile.argv is empty")
    argv = [sys.executable, str(root / fixed[0]), *fixed[1:]]
    occurrence_flag = reconcile_cfg.get("occurrence_flag")
    if occurrence_flag is not None:
        if occurrence is None:
            raise ValueError("occurrence_flag is set but no occurrence target was given")
        argv += [occurrence_flag, occurrence]
    resolve_flag = reconcile_cfg.get("resolve_flag")
    if resolve_flag is not None:
        argv.append(resolve_flag)
    return argv


def plan_targets(
    fenced: Mapping[str, tuple[str, ...]],
    loops: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, list[str | None]], list[str]]:
    """Split current fences into (per-owner call targets, owners lacking an adapter).

    An owner whose script has no ``occurrence_flag`` (it self-enumerates every
    fenced occurrence from its own admission read, e.g.
    ``reconcile_application_no_submit.py``) gets one ``None`` target: one call
    covers every currently fenced occurrence for that owner.
    """
    targets: dict[str, list[str | None]] = {}
    needs_adapter: list[str] = []
    for owner_id in sorted(fenced):
        row = loops.get(owner_id) or {}
        reconcile_cfg = row.get("effect_reconcile") if isinstance(row, Mapping) else None
        if not isinstance(reconcile_cfg, Mapping) or not reconcile_cfg.get("argv"):
            needs_adapter.append(owner_id)
            continue
        if reconcile_cfg.get("occurrence_flag") is None:
            targets[owner_id] = [None]
        else:
            targets[owner_id] = list(fenced[owner_id])
    return targets, needs_adapter


def round_robin(targets: Mapping[str, list[str | None]], cap: int) -> list[tuple[str, str | None]]:
    """Interleave owners fairly so one owner's backlog cannot starve the others."""
    owners = sorted(targets)
    queues = {owner: list(values) for owner, values in targets.items()}
    calls: list[tuple[str, str | None]] = []
    while len(calls) < cap and any(queues.values()):
        for owner in owners:
            if len(calls) >= cap:
                break
            if queues[owner]:
                calls.append((owner, queues[owner].pop(0)))
    return calls


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def reconcile(
    *,
    registry: Mapping[str, object],
    root: Path,
    cap: int = MAX_CALLS_PER_WAKE,
    run_call: Callable[[list[str]], tuple[int, str]] = run_call,
    read_fenced: Callable[[], dict[str, tuple[str, ...]]] = _admission_effect_unknown_occurrences,
    log_path: Path | None = DEFAULT_LOG,
) -> dict:
    """Run one bounded reconciliation pass and return the summary dict."""
    loops = registry.get("loops", {}) if isinstance(registry, Mapping) else {}
    fenced = read_fenced()
    checked = sum(len(occurrences) for occurrences in fenced.values())
    targets, needs_adapter = plan_targets(fenced, loops)
    calls = round_robin(targets, cap)
    closed = 0
    records: list[dict] = []
    for owner_id, occurrence in calls:
        reconcile_cfg = loops[owner_id]["effect_reconcile"]
        argv = build_argv(reconcile_cfg, root, occurrence)
        exit_code, tail = run_call(argv)
        after = read_fenced()
        still_open = set(after.get(owner_id, ()))
        if occurrence is None:
            before = set(fenced.get(owner_id, ()))
            for occ in sorted(before):
                occ_closed = occ not in still_open
                if occ_closed:
                    closed += 1
                records.append({
                    "owner_id": owner_id, "occurrence_id": occ,
                    "exit_code": exit_code, "closed": occ_closed, "stdout_tail": tail,
                })
        else:
            occ_closed = occurrence not in still_open
            if occ_closed:
                closed += 1
            records.append({
                "owner_id": owner_id, "occurrence_id": occurrence,
                "exit_code": exit_code, "closed": occ_closed, "stdout_tail": tail,
            })
    if log_path is not None:
        _append_jsonl(log_path, records)
    return {
        "checked": checked,
        "closed": closed,
        "still_fenced": checked - closed,
        "needs_readback_adapter": needs_adapter,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS_PER_WAKE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)
    if args.max_calls < 1:
        parser.error("--max-calls must be positive")
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        validate_registry(registry)
    except (OSError, ValueError) as error:
        print(json.dumps(
            {"error": "registry_unreadable_or_invalid", "detail": str(error)[:240]},
            sort_keys=True,
        ), file=sys.stderr)
        return 1
    summary = reconcile(
        registry=registry, root=args.root.resolve(), cap=args.max_calls,
        log_path=args.log.expanduser(),
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
