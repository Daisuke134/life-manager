import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[3] / "config" / "loop-registry.json"
VALID = {"distribution", "critical_paid", "revenue", "support"}


def test_every_registry_priority_is_valid():
    # capafy-distribute-daily shipped with priority "paid" (2026-09-29) and broke
    # lm-loop status/apply for the whole fleet with "invalid priority".
    loops = json.loads(REGISTRY.read_text())
    loops = loops.get("loops", loops)
    bad = {k: v.get("priority") for k, v in loops.items()
           if isinstance(v, dict) and v.get("priority") is not None and v.get("priority") not in VALID}
    assert not bad, bad


def test_effectful_loops_carry_an_admission_contract():
    # 2026-10-24: agentmail-nudge / agentmail-replier pointed at a deleted release and could not be
    # re-applied: lm_loop._admission_rebind_guard keeps a legacy effectful queue row fenced
    # ("pending-admission") until the registry names resource_class/admission_class/priority,
    # so a release that disappears leaves such a loop dangling forever.
    loops = json.loads(REGISTRY.read_text())
    loops = loops.get("loops", loops)
    missing = {k for k, v in loops.items()
               if isinstance(v, dict) and v.get("effect_class") not in (None, "none")
               and not all(v.get(x) for x in ("resource_class", "admission_class", "priority"))}
    assert not missing, missing
