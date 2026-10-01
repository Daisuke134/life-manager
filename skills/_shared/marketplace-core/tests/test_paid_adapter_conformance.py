from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
ADAPTERS = (
    ("coconala", ROOT / "skills/earn/gig/scripts/coconala_paid_adapter.py", "CoconalaPaidAdapter"),
    ("lancers", ROOT / "skills/earn/lancers/scripts/paid_adapter.py", "LancersPaidAdapter"),
    ("crowdworks", ROOT / "skills/earn/crowdworks/scripts/paid_adapter.py", "CrowdWorksPaidAdapter"),
    ("mercor", ROOT / "skills/earn/mercor/scripts/paid_adapter.py", "MercorPaidAdapter"),
)
SURFACE = ("observe_active", "observe_one", "context", "mutate", "readback")
OBSERVATION_WAIT = "classify_observation_error"


def _load(provider: str, path: Path):
    spec = importlib.util.spec_from_file_location(
        f"paid_adapter_conformance_{provider}", path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("provider,path,class_name", ADAPTERS,
                         ids=[item[0] for item in ADAPTERS])
def test_paid_adapter_exposes_shared_kernel_contract(provider, path, class_name):
    module = _load(provider, path)
    adapter = getattr(module, class_name)

    assert callable(getattr(module, "build", None))
    assert all(callable(getattr(adapter, method, None)) for method in SURFACE)
    assert callable(getattr(adapter, OBSERVATION_WAIT, None))
