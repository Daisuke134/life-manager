"""Dry-run, no-network smoke tests for capafy-distribute-daily.sh.

Exercises the real script (ledger check, skill selection, run-dir setup,
dry-run receipt) with everything redirected into tmp_path so no production
state under ~/.local/state/life-manager is touched and no model/network call
is ever made (CAPAFY_DISTRIBUTE_DRY_RUN=1 short-circuits before the model
dispatch).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3].parent  # .../life-manager-main worktree root
SCRIPT = REPO_ROOT / "skills" / "earn" / "capafy-marketing" / "capafy-distribute-daily.sh"

PRODUCTS_JSON = {
    "products": {
        "anicca": {"landing_url": "https://aniccaai.com/lm"},
        "capafy-skills": {
            "skills": {
                "hook-lab": {"agent_id": "111", "buyer_problem": "hook problem"},
                "slide-maker": {"agent_id": "222", "buyer_problem": "slide problem"},
            }
        },
    }
}


def run(tmp_path: Path, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    products_config = tmp_path / "products.json"
    products_config.write_text(json.dumps(PRODUCTS_JSON))
    state_dir = tmp_path / "capafy-distribute-state"
    fence_dir = tmp_path / "owner-fence"
    env = dict(os.environ)
    env.update(
        {
            "CAPAFY_DISTRIBUTE_DRY_RUN": "1",
            "CAPAFY_DISTRIBUTE_PRODUCTS_CONFIG": str(products_config),
            "CAPAFY_DISTRIBUTE_ANALYTICS_FILE": str(tmp_path / "does-not-exist.json"),
            "CAPAFY_DISTRIBUTE_STATE_DIR": str(state_dir),
            "CAPAFY_DISTRIBUTE_OWNER_FENCE_DIR": str(fence_dir),
            "WRITER_STATE_DIR": str(state_dir),
        }
    )
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, check=False, env=env, timeout=60,
    )


def test_dry_run_exits_zero_and_writes_ledger(tmp_path: Path) -> None:
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    ledger_path = tmp_path / "capafy-distribute-state" / "ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text())
    assert len(ledger) == 1
    (entry,) = ledger.values()
    assert entry["status"] == "dry_run"
    assert entry["capafy_skill"] in {"hook-lab", "slide-maker"}
    # Capafy only attributes ct values registered as promotion links in the
    # console (2026-10-07); these are the ones issued for the sellers.
    assert entry["cta_url"].endswith(("ct=hooklab_blog", "ct=slides_blog"))


def test_second_dry_run_same_day_is_a_no_op_and_does_not_rewrite_the_pick(tmp_path: Path) -> None:
    first = run(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    ledger_path = tmp_path / "capafy-distribute-state" / "ledger.json"
    first_ledger = json.loads(ledger_path.read_text())

    second = run(tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    second_ledger = json.loads(ledger_path.read_text())

    assert first_ledger == second_ledger  # idempotent: no duplicate publish, same receipt
