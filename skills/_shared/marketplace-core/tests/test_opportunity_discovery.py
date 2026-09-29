from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


STORE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "opportunity_observation_store.py"
RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "opportunity_discovery.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store_module = _load(STORE_PATH, "marketplace_opportunity_store_for_runner_test")
runner = _load(RUNNER_PATH, "marketplace_opportunity_discovery_test")


def _opportunity(identifier: str):
    return SimpleNamespace(
        provider="coconala",
        opportunity_id=identifier,
        source_url=f"https://coconala.com/requests/{identifier.split(':')[-1]}",
        title=f"案件 {identifier}",
        currency="JPY",
        source_hash=(identifier[-1] * 64),
        observed_at="2026-09-30T00:00:00Z",
    )


def _detail(opportunity):
    return SimpleNamespace(
        opportunity=opportunity,
        scope="募集内容\n本文",
        source_hash=opportunity.source_hash,
    )


class _ReadOnlyAdapter:
    def __init__(self, opportunities):
        self.opportunities = opportunities
        self.called = []

    def discover(self):
        self.called.append("discover")
        return self.opportunities

    def inspect(self, opportunity_id):
        self.called.append(("inspect", opportunity_id))
        return _detail(next(item for item in self.opportunities if item.opportunity_id == opportunity_id))

    def execute(self, *_args):
        raise AssertionError("runner must never execute provider effects")


def _judge(opportunity, detail):
    return {
        "decision": "eligible" if opportunity.opportunity_id.endswith("1") else "hold",
        "reasons": [] if opportunity.opportunity_id.endswith("1") else ["missing_workflow"],
        "evidence_refs": [f"snapshot://{opportunity.opportunity_id}"],
        "next_action": "plan_effect_after_authorization" if opportunity.opportunity_id.endswith("1") else "review_shared_workflow",
    }


def test_runner_inspects_and_persists_without_provider_mutation(tmp_path):
    opportunities = [_opportunity("request:1"), _opportunity("request:2")]
    adapter = _ReadOnlyAdapter(opportunities)
    store = store_module.OpportunityObservationStore(tmp_path / "observations")

    result = runner.run_opportunity_discovery(adapter, _judge, store)

    assert result["status"] == "ok"
    assert result["inspected"] == 2
    assert result["persisted"] == 2
    assert result["duplicates"] == 0
    assert result["eligible"] == 1
    assert result["held"] == 1
    assert adapter.called == ["discover", ("inspect", "request:1"), ("inspect", "request:2")]
    assert store.latest("coconala", "request:1")["decision"] == "eligible"


def test_runner_replay_is_idempotent(tmp_path):
    opportunities = [_opportunity("request:1")]
    adapter = _ReadOnlyAdapter(opportunities)
    store = store_module.OpportunityObservationStore(tmp_path / "observations")

    first = runner.run_opportunity_discovery(adapter, _judge, store)
    second = runner.run_opportunity_discovery(adapter, _judge, store)

    assert first["persisted"] == 1
    assert second["persisted"] == 0
    assert second["duplicates"] == 1
    assert len(store.read_all()) == 1


def test_runner_rejects_inspect_identity_mismatch(tmp_path):
    opportunity = _opportunity("request:1")
    adapter = _ReadOnlyAdapter([opportunity])
    adapter.inspect = lambda _identifier: _detail(_opportunity("request:9"))
    store = store_module.OpportunityObservationStore(tmp_path / "observations")

    with pytest.raises(runner.OpportunityDiscoveryError, match="inspect_identity_mismatch"):
        runner.run_opportunity_discovery(adapter, _judge, store)


def test_runner_enforces_a_bounded_batch(tmp_path):
    opportunities = [_opportunity("request:1"), _opportunity("request:2")]
    adapter = _ReadOnlyAdapter(opportunities)
    store = store_module.OpportunityObservationStore(tmp_path / "observations")

    with pytest.raises(runner.OpportunityDiscoveryError, match="discovery_bound_exceeded"):
        runner.run_opportunity_discovery(adapter, _judge, store, max_items=1)
