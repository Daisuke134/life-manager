from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "inventory_status.py"


def load_module():
    spec = importlib.util.spec_from_file_location("inventory_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def agent(agent_id: str, status: str, **extra) -> dict:
    return {
        "agentId": agent_id,
        "name": f"Skill {agent_id}",
        "agentStatus": status,
        "agentType": "run_online",
        "latestAgentVersionId": f"v-{agent_id}",
        "latestVersionName": "1.0.0",
        "sales": 2,
        "recentSales": 1,
    } | extra


def test_normalize_agents_returns_exact_slot_and_retry_counts() -> None:
    module = load_module()
    rows = [
        agent("1", "online"),
        agent("2", "online"),
        agent("3", "draft"),
        agent("4", "under_review"),
        agent("5", "review_rejected"),
        agent("6", "banned"),
    ]

    result = module.normalize_agents(rows)

    assert result["readable"] is True
    assert result["counts"] == {
        "total": 6,
        "listed": 2,
        "occupied": 3,
        "free": 2,
        "retry": 1,
        "recover": 0,
        "ready_publish": 0,
        "blocked": 1,
        "unknown": 0,
    }
    assert result["agents"][2] == {
        "agent_id": "3",
        "name": "Skill 3",
        "latest_version_id": "v-3",
        "latest_version_name": "1.0.0",
        "remote_status": "draft",
        "lifecycle": "occupied",
        "agent_type": "run_online",
        "sales": 2,
        "recent_sales": 1,
    }
    assert result["agents"][4]["lifecycle"] == "retry"


def test_rejections_consume_the_live_unlisted_cap() -> None:
    module = load_module()
    rows = [
        agent("under-review", "under_review"),
        agent("rejected-1", "review_rejected"),
        agent("rejected-2", "review_rejected"),
        agent("rejected-3", "review_rejected"),
        agent("rejected-4", "review_rejected"),
    ]

    normalized = module.normalize_agents(rows)
    decision = module.allocate_action(
        normalized, [], [{"feature": "catalog:fresh", "title": "Fresh Skill"}]
    )

    assert normalized["counts"]["occupied"] == 5
    assert normalized["counts"]["retry"] == 4
    assert decision == {"verdict": "CAP_FULL", "occupied": 5}


def test_paid_same_agent_update_precedes_fresh_only_with_a_free_slot() -> None:
    module = load_module()
    request = {"agent_id": "9563867391", "from_version_id": "2070737929294868480",
               "target_model_id": "deepseek/deepseek-v4.1-flash"}
    update = {"agent_id": "9563867391", "feature": "catalog:marketing-strategist",
              "title": "Marketing Strategist — The One Move to Make", "update_request": request}
    fresh = {"feature": "catalog:fresh", "title": "Fresh Skill"}
    free = module.normalize_agents([agent("1", "under_review")])
    full = module.normalize_agents([agent(str(i), "under_review") for i in range(5)])

    selected = module.allocate_action(free, [], [fresh], updates=[update])

    assert selected["action"] == "update_existing"
    assert selected["action_key"] == "update:9563867391:2070737929294868480"
    assert module.allocate_action(full, [], [fresh], updates=[update])["verdict"] == "CAP_FULL"


def test_repo_update_request_targets_existing_online_version(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(Path(__file__).parents[2] / "capafy/catalog"))
    items = module.ready_inventory()
    request = next(item for item in items if item["feature"] == "catalog:marketing-strategist")
    assert request["update_request"]["agent_id"] == "9563867391"
    assert request["icon"].endswith("icon.webp")
    rows = [agent("9563867391", "online", name=request["title"],
                  latestAgentVersionId="2070737929294868480"),
            agent("other", "under_review")]
    monkeypatch.setattr(module, "server_agents", lambda: rows)

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert decision["action"] == "update_existing"
    assert decision["item"]["agent_id"] == "9563867391"

    monkeypatch.setattr(module, "server_agents", lambda: [agent("other", "under_review")])
    module.main()
    missing = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert missing == {"verdict": "SERVER_UNREADABLE",
                       "reason": "same-Agent update target is missing or changed"}


def test_unknown_status_fails_closed_without_free_slot_claim() -> None:
    module = load_module()

    result = module.normalize_agents([agent("1", "platform_new_state")])

    assert result["readable"] is False
    assert result["counts"]["occupied"] is None
    assert result["counts"]["free"] is None
    assert result["counts"]["unknown"] == 1


def test_offline_is_recoverable_not_server_unreadable() -> None:
    module = load_module()

    normalized = module.normalize_agents([agent("sold-1", "offline", name="Sold Skill")])
    decision = module.allocate_action(
        normalized,
        [],
        [],
        recoveries=[{"agent_id": "sold-1", "title": "Sold Skill"}],
    )

    assert normalized["readable"] is True
    assert normalized["counts"]["recover"] == 1
    assert normalized["counts"]["occupied"] == 0
    assert decision == {
        "verdict": "PUBLISHABLE",
        "reason": "offline Agent needs copied replacement version",
        "action": "recover_delisted",
        "action_key": "recover:sold-1",
        "item": {"agent_id": "sold-1", "title": "Sold Skill"},
    }


def test_offline_recovery_bypasses_full_new_agent_cap() -> None:
    module = load_module()
    rows = [agent(f"draft-{i}", "draft") for i in range(5)] + [agent("sold-1", "offline")]
    normalized = module.normalize_agents(rows)

    decision = module.allocate_action(
        normalized,
        [],
        [{"feature": "catalog:fresh", "title": "Fresh Skill"}],
        recoveries=[{"agent_id": "sold-1", "title": "Skill sold-1"}],
    )

    assert decision["action"] == "recover_delisted"


def test_approved_version_requires_test_run_and_manual_publish() -> None:
    module = load_module()
    normalized = module.normalize_agents([agent("sold-1", "pending_online", name="Sold Skill")])

    decision = module.allocate_action(
        normalized,
        [],
        [],
        ready_to_publish=[{"agent_id": "sold-1", "title": "Sold Skill"}],
    )

    assert normalized["readable"] is True
    assert normalized["counts"]["ready_publish"] == 1
    assert decision["action"] == "test_and_publish"
    assert decision["action_key"] == "publish:sold-1"


def test_missing_identity_fails_closed() -> None:
    module = load_module()
    row = agent("1", "online")
    row.pop("agentId")

    result = module.normalize_agents([row])

    assert result["readable"] is False
    assert result["counts"]["free"] is None


def test_server_agents_adapts_official_0911_snake_case_shape(monkeypatch) -> None:
    module = load_module()
    payload = {
        "agents": [
            {
                "agent_id": "agent-1",
                "name": "Skill agent-1",
                "description": "A published skill",
                "agent_type": "run_online",
                "agent_status": "online",
                "latest_agent_version_id": "version-1",
                "updated_at": 1735689600000,
            }
        ]
    }

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps(payload), returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rows = module.server_agents()

    assert rows == [
        {
            "agentId": "agent-1",
            "name": "Skill agent-1",
            "description": "A published skill",
            "agentType": "run_online",
            "agentStatus": "online",
            "latestAgentVersionId": "version-1",
            "updatedAt": 1735689600000,
        }
    ]
    assert module.normalize_agents(rows)["readable"] is True


def test_server_agents_malformed_shape_or_nonzero_is_unreadable(monkeypatch) -> None:
    module = load_module()

    cases = [
        ("not-json", 0),
        (json.dumps({"agents": {}}), 0),
        (json.dumps({"agents": ["not-an-object"]}), 0),
        (json.dumps({"agents": []}), 1),
    ]

    for stdout, returncode in cases:
        monkeypatch.setattr(
            module.subprocess,
            "run",
            lambda *args, _stdout=stdout, _returncode=returncode, **kwargs: SimpleNamespace(
                stdout=_stdout, returncode=_returncode
            ),
        )
        assert module.server_agents() is None


def test_allocator_contract_is_bounded_and_replay_stable() -> None:
    module = load_module()
    retry = {"agent_id": "rejected-1", "title": "Fix Me"}
    fresh = {"feature": "capafy-o1-fresh", "title": "Fresh Skill"}
    cases = [
        ({"readable": False, "counts": {"occupied": None}}, [retry], [fresh], "SERVER_UNREADABLE", None),
        ({"readable": True, "counts": {"occupied": 5}}, [retry], [fresh], "CAP_FULL", None),
        ({"readable": True, "counts": {"occupied": 4}}, [retry], [fresh], "PUBLISHABLE", "retry_existing"),
        ({"readable": True, "counts": {"occupied": 5}}, [], [fresh], "CAP_FULL", None),
        ({"readable": True, "counts": {"occupied": 4}}, [], [fresh], "PUBLISHABLE", "create_fresh"),
        ({"readable": True, "counts": {"occupied": 4}}, [], [], "DRAINED", None),
    ]

    for normalized, retries, publishable, verdict, action in cases:
        first = module.allocate_action(normalized, retries, publishable)
        replay = module.allocate_action(normalized, retries, publishable)
        assert first == replay
        assert first["verdict"] == verdict
        assert first.get("action") == action
        assert int(first.get("action") is not None) <= 1


def test_allocator_selects_only_one_deterministic_candidate() -> None:
    module = load_module()
    normalized = {"readable": True, "counts": {"occupied": 0}}
    candidates = [
        {"feature": "capafy-o2", "title": "Second"},
        {"feature": "capafy-o1", "title": "First"},
    ]

    decision = module.allocate_action(normalized, [], candidates)

    assert decision["action"] == "create_fresh"
    assert decision["action_key"] == "create:capafy-o1"
    assert decision["item"]["feature"] == "capafy-o1"


def test_allocator_resumes_matching_draft_at_full_cap_but_blocks_without_one() -> None:
    module = load_module()
    normalized = {"readable": True, "counts": {"occupied": 5}}
    draft = {
        "agent_id": "draft-42",
        "title": "Portfolio Tracker — Daily Position Review",
        "feature": "catalog:portfolio-tracker",
        "icon": "/catalog/portfolio-tracker/icon.svg",
        "listing": "/catalog/portfolio-tracker/LISTING.md",
        "skill": "/catalog/portfolio-tracker/SKILL.md",
        "source": "repo_catalog",
    }
    retry = {"agent_id": "rejected-1", "title": "Retry Me"}
    fresh = {"feature": "catalog:fresh", "title": "Fresh Skill"}

    resumed = module.allocate_action(normalized, [retry], [fresh], [draft])

    assert resumed["verdict"] == "PUBLISHABLE"
    assert resumed["action"] == "resume_draft"
    assert resumed["action_key"] == "resume:draft-42"
    assert resumed["item"] == draft

    blocked = module.allocate_action(normalized, [retry], [fresh], [])

    assert blocked == {"verdict": "CAP_FULL", "occupied": 5}


def test_repo_catalog_is_ready_and_overrides_same_title_legacy_item(tmp_path: Path) -> None:
    module = load_module()
    features = tmp_path / "features"
    icons = tmp_path / "icons"
    catalog = tmp_path / "catalog"
    legacy = features / "capafy-o1-football"
    canonical = catalog / "football-match-analyst"
    legacy.mkdir(parents=True)
    icons.mkdir()
    canonical.mkdir(parents=True)
    title = "Football Match Analyst — Weekly Fixture Read"
    (legacy / "LISTING.md").write_text(f"## Title\n{title}\n")
    (legacy / "SKILL.md").write_text("legacy")
    (icons / "o1.png").write_bytes(b"png")
    (canonical / "LISTING.md").write_text(f"## Title\n{title}\n")
    (canonical / "SKILL.md").write_text("canonical")
    (canonical / "icon.svg").write_text("<svg/>")
    module.FEATURES = str(features)
    module.ICONS = str(icons)
    module.CATALOG = str(catalog)

    items = module.ready_inventory()

    assert len(items) == 1
    assert items[0]["feature"] == "catalog:football-match-analyst"
    assert items[0]["source"] == "repo_catalog"
