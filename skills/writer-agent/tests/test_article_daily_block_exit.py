"""2026-10-10: article-daily's start-control BLOCK exited 0. The host reads the pre-effect marker
only for a non-zero exit, so a BLOCK that never reached the model left an effect_unknown fence
(lm-loop pre-effect-reconcile: no_pre_effect_terminal) that deferred every later wake."""
from pathlib import Path

DAILY = (Path(__file__).resolve().parents[1] / "article-daily.sh").read_text(encoding="utf-8")


def test_start_control_block_exits_75_so_the_host_proves_no_effect():
    start = DAILY.index("article-daily start control BLOCK:")
    end = DAILY.index(";;", start)
    branch = DAILY[start:end]
    assert "exit 75" in branch and "exit 0" not in branch
    # The marker the host checks is only cleared right before the model pass.
    assert DAILY.index("run_model_pass()") > 0
