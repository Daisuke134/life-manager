from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
ADAPTERS = (
    ("coconala", ROOT / "skills/earn/gig/scripts/coconala_reply_adapter.py",
     "CoconalaReplyAdapter"),
    ("lancers", ROOT / "skills/earn/lancers/scripts/reply_adapter.py",
     "LancersReplyAdapter"),
    ("crowdworks", ROOT / "skills/earn/crowdworks/scripts/reply_adapter.py",
     "CrowdWorksReplyAdapter"),
    ("mercor", ROOT / "skills/earn/mercor/scripts/reply_adapter.py",
     "MercorReplyAdapter"),
)
SURFACE = ("observe_threads", "observe_one", "context", "mutate", "readback")


def _load(provider: str, path: Path):
    spec = importlib.util.spec_from_file_location(
        f"reply_adapter_conformance_{provider}", path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("provider,path,class_name", ADAPTERS,
                         ids=[item[0] for item in ADAPTERS])
def test_reply_adapter_exposes_shared_kernel_contract(provider, path, class_name):
    module = _load(provider, path)
    adapter = getattr(module, class_name)

    assert callable(getattr(module, "build", None))
    assert all(callable(getattr(adapter, method, None)) for method in SURFACE)
    assert callable(getattr(adapter, "classify_observation_error", None))
    # Unknown failures must stay visible; adapters may only classify their
    # provider-owned observation boundary failures.
    assert adapter.classify_observation_error(
        RuntimeError("unexpected_programming_error")
    ) is None
