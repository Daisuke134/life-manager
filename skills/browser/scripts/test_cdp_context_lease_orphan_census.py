"""The browser census must expose unknown contexts without closing them."""

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parent / "cdp_context_lease.py"
    spec = importlib.util.spec_from_file_location("cdp_context_lease_orphan_census", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_context_inventory_marks_unleased_blank_context_unknown(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_leases", lambda: {
        "owned-task": {"context_id": "ctx-owned", "target_id": "target-owned"},
    })

    async def read_inventory(pairs, timeout=None):
        assert [method for method, _params in pairs] == [
            "Target.getBrowserContexts",
            "Target.getTargets",
        ]
        return [
            {"browserContextIds": ["ctx-owned", "ctx-orphan"]},
            {"targetInfos": [
                {"targetId": "target-owned", "type": "page", "url": "https://example.test/", "browserContextId": "ctx-owned"},
                {"targetId": "target-orphan", "type": "page", "url": "about:blank", "browserContextId": "ctx-orphan"},
            ]},
        ]

    monkeypatch.setattr(module, "_calls", read_inventory)

    result = module.context_inventory()

    assert result["ok"] is True
    assert result["context_count"] == 2
    assert result["leased_context_ids"] == ["ctx-owned"]
    assert result["unknown_owner_contexts"] == [{
        "context_id": "ctx-orphan",
        "page_count": 1,
        "blank_page_count": 1,
        "page_urls": ["about:blank"],
    }]


def test_context_inventory_never_disposes_or_closes_targets(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_leases", lambda: {})
    calls = []

    async def read_inventory(pairs, timeout=None):
        calls.extend(method for method, _params in pairs)
        return [
            {"browserContextIds": ["ctx-orphan"]},
            {"targetInfos": [{
                "targetId": "target-orphan", "type": "page", "url": "about:blank", "browserContextId": "ctx-orphan",
            }]},
        ]

    monkeypatch.setattr(module, "_calls", read_inventory)
    result = module.context_inventory()

    assert result["unknown_owner_contexts"][0]["context_id"] == "ctx-orphan"
    assert calls == ["Target.getBrowserContexts", "Target.getTargets"]
