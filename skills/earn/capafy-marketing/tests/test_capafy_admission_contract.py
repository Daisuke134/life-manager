import json
from pathlib import Path


def test_capafy_marketing_declares_finite_host_admission_contract():
    root = Path(__file__).resolve().parents[4]
    entry = json.loads((root / "config/loop-registry.json").read_text())["loops"][
        "capafy-ig-marketing-daily"
    ]

    assert entry["resource_class"] == "agent"
    assert entry["admission_class"] == "borrow"
    assert entry["priority"] == "support"
