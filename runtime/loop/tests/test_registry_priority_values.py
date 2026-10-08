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
