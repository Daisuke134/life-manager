from __future__ import annotations

import importlib.util
import json
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "inventory_status.py"


@pytest.fixture(autouse=True)
def _isolate_draft_attempts(monkeypatch, tmp_path):
    # main() records draft attempts; never let a test write the production counter.
    monkeypatch.setenv("CAPAFY_DRAFT_ATTEMPTS_PATH", str(tmp_path / "draft-attempts.json"))


def load_module():
    spec = importlib.util.spec_from_file_location("inventory_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.CAP = 5  # fixtures below are written against a 5-slot cap
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
    # 2026-10-05 measured: Capafy accepted publish-init for a same-Agent update of an
    # ONLINE agent with 5 (then 6) unlisted agents; the cap only blocks creating agents.
    blocked_full = module.allocate_action(full, [], [fresh], updates=[update])
    assert blocked_full["action"] == "update_existing"


def test_in_progress_update_draft_resumes_before_a_different_update_starts() -> None:
    module = load_module()
    # Hook Lab's first pass already publish-init'd a draft version (agentStatus
    # flipped from online -> draft), so it no longer matches `updates` -- but it
    # must still win over starting Slide Maker's update from scratch.
    hook_lab_draft = {"agent_id": "8123079349", "feature": "catalog:hook-lab",
                       "title": "Hook Lab — Win the First 3 Seconds",
                       "update_request": {"agent_id": "8123079349", "from_version_id": "v-old",
                                          "target_model_id": "deepseek/deepseek-v4.1-flash"}}
    slide_maker_update = {"agent_id": "8828622062", "feature": "catalog:slide-maker",
                           "title": "Slide Maker",
                           "update_request": {"agent_id": "8828622062", "from_version_id": "v1",
                                               "target_model_id": "deepseek/deepseek-v4.1-flash"}}
    free = module.normalize_agents([agent("1", "under_review")])

    decision = module.allocate_action(free, [], [], resumable_drafts=[hook_lab_draft], updates=[slide_maker_update])

    assert decision["action"] == "resume_draft"
    assert decision["action_key"] == "resume:8123079349"
    assert decision["item"]["agent_id"] == "8123079349"

    # A plain resumable draft with no update_request is unaffected: `updates`
    # still outranks it (pre-existing 2026-09-28 rule).
    plain_draft = {"agent_id": "999", "feature": "catalog:plain", "title": "Plain Draft"}
    unaffected = module.allocate_action(free, [], [], resumable_drafts=[plain_draft], updates=[slide_maker_update])
    assert unaffected["action"] == "update_existing"


def test_multiple_updates_pick_highest_30d_revenue_first() -> None:
    module = load_module()
    low = {"agent_id": "1111111111", "feature": "catalog:low-revenue", "title": "Low Revenue Agent",
           "update_request": {"agent_id": "1111111111", "from_version_id": "v1",
                               "target_model_id": "deepseek/deepseek-v4.1-flash"}}
    high = {"agent_id": "2222222222", "feature": "catalog:high-revenue", "title": "High Revenue Agent",
            "update_request": {"agent_id": "2222222222", "from_version_id": "v2",
                                "target_model_id": "deepseek/deepseek-v4.1-flash"}}
    free = module.normalize_agents([agent("1", "under_review")])
    revenue_by_agent = {"1111111111": 5.0, "2222222222": 50.0}

    decision = module.allocate_action(free, [], [], updates=[low, high], revenue_by_agent=revenue_by_agent)

    assert decision["action"] == "update_existing"
    assert decision["item"]["agent_id"] == "2222222222"

    # No revenue data (or a tie) falls back to agent_id ascending, same as before.
    decision_no_data = module.allocate_action(free, [], [], updates=[low, high])
    assert decision_no_data["item"]["agent_id"] == "1111111111"


def test_multiple_retries_pick_highest_30d_revenue_first() -> None:
    module = load_module()
    # Real case 2026-10-04: agent_id-string order picked the zero-revenue
    # retry ahead of the $11.18/30d Marketing Strategist.
    low = {"agent_id": "4973250899", "title": "Customer Renewal Evidence Brief"}
    high = {"agent_id": "9563867391", "title": "Marketing Strategist"}
    free = module.normalize_agents([agent("1", "under_review")])
    revenue_by_agent = {"4973250899": 0.0, "9563867391": 11.18}

    decision = module.allocate_action(free, [low, high], [], revenue_by_agent=revenue_by_agent)

    assert decision["action"] == "retry_existing"
    assert decision["item"]["agent_id"] == "9563867391"

    # No revenue data (or a tie) falls back to agent_id ascending, same as before.
    decision_no_data = module.allocate_action(free, [low, high], [])
    assert decision_no_data["item"]["agent_id"] == "4973250899"

    decision_tied = module.allocate_action(
        free, [low, high], [], revenue_by_agent={"4973250899": 5.0, "9563867391": 5.0})
    assert decision_tied["item"]["agent_id"] == "4973250899"


def test_load_revenue_by_agent_reads_analytics_snapshot(tmp_path) -> None:
    module = load_module()
    snapshot = tmp_path / "capafy-skill-analytics.json"
    snapshot.write_text(json.dumps({"per_skill_rows": [
        {"agent_id": "9563867391", "stats_30d_revenue_usd": "13.98"},
        {"agent_id": "bad", "stats_30d_revenue_usd": "not-a-number"},
        {"not_a_dict": True},
    ]}))

    assert module.load_revenue_by_agent(str(snapshot)) == {"9563867391": 13.98}
    assert module.load_revenue_by_agent(str(tmp_path / "missing.json")) == {}


def test_repo_update_request_targets_existing_online_version(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    # Fixture catalog: a non-frozen Agent carrying an UPDATE.json (sellers in
    # FROZEN.json never get one; see test_frozen_agent_update_is_never_selected).
    import shutil
    catalog = tmp_path / "catalog"
    shutil.copytree(Path(__file__).parents[2] / "capafy/catalog/hook-lab", catalog / "hook-lab",
                    ignore=shutil.ignore_patterns("test"))
    (catalog / "hook-lab" / "UPDATE.json").write_text(json.dumps({
        "agent_id": "9999999999", "from_version_id": "2107714882678706176",
        "target_model_id": "anthropic/claude-sonnet-5",
        "icon_sha256": "71fd45e7303c4c87fa86c6ee0c532e09419a9123b0806b9e4572e34ba679176f",
        "reason": "fixture", "dais_approved_exception": "fixture"}))
    monkeypatch.setattr(module, "CATALOG", str(catalog))
    items = module.ready_inventory()
    request = next(item for item in items if item["feature"] == "catalog:hook-lab")
    assert request["update_request"]["agent_id"] == "9999999999"
    assert request["icon"].endswith("icon.webp")
    others = [item for item in items
              if item.get("update_request") and item is not request]
    rows = [agent("9999999999", "online", name=request["title"],
                  latestAgentVersionId=request["update_request"]["from_version_id"]),
            *[agent(item["update_request"]["agent_id"], "online", name=item["title"],
                    latestAgentVersionId="stale-" + item["update_request"]["from_version_id"])
              for item in others],
            agent("other", "under_review")]
    monkeypatch.setattr(module, "server_agents", lambda: rows)

    analytics = tmp_path / "analytics.json"
    analytics.write_text(json.dumps({"per_skill_rows": []}))
    monkeypatch.setattr(module, "ANALYTICS_PATH", str(analytics))
    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])
    # Dais 2026-10-08: no update of an accepted Agent is selected -- except an UPDATE.json carrying
    # dais_approved_exception (Dais 2026-10-10 price restore), which this fixture does.
    assert decision.get("action") == "update_existing", decision
    assert decision["item"]["agent_id"] == "9999999999"

    monkeypatch.setattr(module, "server_agents", lambda: [agent("other", "under_review")])
    module.main()
    missing = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert missing == {"verdict": "SERVER_UNREADABLE",
                       "reason": "same-Agent update target is missing or changed"}


def test_frozen_agent_update_is_never_selected(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    frozen = tmp_path / "FROZEN.json"
    frozen.write_text(json.dumps({"agent_ids": ["9999999999"]}))
    monkeypatch.setattr(module, "load_frozen_ids", lambda path=None: {"9999999999"})
    import shutil
    catalog = tmp_path / "catalog"
    shutil.copytree(Path(__file__).parents[2] / "capafy/catalog/hook-lab", catalog / "hook-lab",
                    ignore=shutil.ignore_patterns("test"))
    (catalog / "hook-lab" / "UPDATE.json").write_text(json.dumps({
        "agent_id": "9999999999", "from_version_id": "2107714882678706176", "target_model_id": "anthropic/claude-sonnet-5",
        "icon_sha256": "71fd45e7303c4c87fa86c6ee0c532e09419a9123b0806b9e4572e34ba679176f",
        "reason": "fixture", "dais_approved_exception": "fixture"}))
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(catalog))
    title = next(i for i in module.ready_inventory() if i["feature"] == "catalog:hook-lab")["title"]
    monkeypatch.setattr(module, "server_agents", lambda: [
        agent("9999999999", "online", name=title, latestAgentVersionId="2107714882678706176")])
    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert decision.get("action") != "update_existing"
    assert (decision.get("item") or {}).get("agent_id") != "9999999999"


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
        (json.dumps({"agents": {"list": []}}), 0),
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


def test_unlisted_agent_with_authoritative_approved_detail_frees_the_slot() -> None:
    # P-14: the list field agentStatus can be stale ("under_review") after Capafy
    # approves the latest version (status 3 = review passed/pending listing,
    # auditStatus 4 = passed). The authoritative detail read must free the slot.
    module = load_module()
    rows = [agent("stale-1", "under_review")]

    def fake_detail(agent_id: str):
        assert agent_id == "stale-1"
        return (3, 4)

    result = module.normalize_agents(rows, detail_fetcher=fake_detail)

    assert result["counts"]["occupied"] == 0
    assert result["counts"]["listed"] == 0
    assert result["counts"]["ready_publish"] == 1
    assert result["counts"]["free"] == 5
    assert result["agents"][0]["lifecycle"] == "ready_publish"


def test_detail_status_4_audit_4_is_listed_not_ready() -> None:
    module = load_module()
    result = module.normalize_agents([agent("live-1", "under_review")], detail_fetcher=lambda _id: (4, 4))
    assert result["counts"]["listed"] == 1
    assert result["counts"]["ready_publish"] == 0
    assert result["agents"][0]["lifecycle"] == "listed"


def test_main_selects_test_and_publish_for_stale_list_status3_even_at_full_cap(monkeypatch, capsys) -> None:
    module = load_module()
    rows = [agent(f"a{i}", "under_review") for i in range(5)] + [agent(f"b{i}", "under_review") for i in range(5)]
    detail = {f"a{i}": (3, 4) for i in range(5)} | {f"b{i}": (1, 1) for i in range(5)}
    monkeypatch.setattr(module, "server_agents", lambda: rows)
    monkeypatch.setattr(module, "fetch_agent_detail", lambda agent_id: detail[agent_id])
    monkeypatch.setattr(module, "ready_inventory", lambda: [])
    assert module.main() == 0
    out = capsys.readouterr().out.splitlines()
    verdict = json.loads(out[1])
    assert verdict["verdict"] == "PUBLISHABLE"
    assert verdict["action"] == "test_and_publish"
    assert verdict["action_key"] == "publish:a0"
    assert verdict["counts"]["occupied"] == 5
    assert verdict["counts"]["ready_publish"] == 5


def test_unlisted_agent_with_pending_audit_detail_stays_occupied() -> None:
    module = load_module()
    rows = [agent("pending-1", "under_review")]

    def fake_detail(agent_id: str):
        return (2, 2)  # manual review in progress; audit not yet passed

    result = module.normalize_agents(rows, detail_fetcher=fake_detail)

    assert result["counts"]["occupied"] == 1
    assert result["agents"][0]["lifecycle"] == "occupied"


def test_rejected_agent_is_retryable_without_a_detail_fetch() -> None:
    module = load_module()
    rows = [agent("rejected-1", "review_rejected")]
    calls: list[str] = []

    def fake_detail(agent_id: str):
        calls.append(agent_id)
        return (4, 4)

    result = module.normalize_agents(rows, detail_fetcher=fake_detail)

    assert calls == []
    assert result["agents"][0]["lifecycle"] == "retry"
    assert result["counts"]["occupied"] == 1


def test_detail_fetch_is_bounded_to_ten_gets() -> None:
    module = load_module()
    rows = [agent(f"draft-{i}", "under_review") for i in range(12)]
    calls: list[str] = []

    def fake_detail(agent_id: str):
        calls.append(agent_id)
        return None  # unreadable detail keeps the conservative classification

    result = module.normalize_agents(rows, detail_fetcher=fake_detail)

    assert len(calls) <= 10
    assert result["counts"]["occupied"] == 12


def test_fetch_agent_detail_reads_publish_remote_status(monkeypatch) -> None:
    module = load_module()
    payload = {"ok": True, "latest_version": {"platform_status": 3, "audit_status": 4}}

    def fake_run(args, **kwargs):
        assert args[1] == "packager.py"
        assert args[2] == "publish-remote-status"
        assert args[-1] == "9470213182"
        return SimpleNamespace(stdout=json.dumps(payload), returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.fetch_agent_detail("9470213182") == (3, 4)


def test_duplicate_gate_drops_near_duplicate_and_unknown_keeps_distinct(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"

    def listing(name: str) -> Path:
        path = tmp_path / f"{name}.md"
        path.write_text(f"## Title\n{name}\n")
        return path

    distinct = listing("distinct")
    near_dup = listing("near_dup")
    unjudged = listing("unjudged")

    sha_distinct = module.duplicate_gate.listing_content_sha(distinct)
    sha_near_dup = module.duplicate_gate.listing_content_sha(near_dup)
    cache_path.write_text(json.dumps({
        "distinct": {"content_sha256": sha_distinct, "verdict": {"verdict": "distinct", "closest": "", "why": "ok"}},
        "near_dup": {"content_sha256": sha_near_dup, "verdict": {"verdict": "near_duplicate", "closest": "X", "why": "same"}},
    }))

    items = [
        {"feature": "distinct", "title": "Distinct", "listing": str(distinct)},
        {"feature": "near_dup", "title": "Near Dup", "listing": str(near_dup)},
        {"feature": "unjudged", "title": "Unjudged", "listing": str(unjudged)},
    ]
    monkeypatch.setattr(module.duplicate_gate, "DEFAULT_VERDICTS_PATH", cache_path)

    results = {it["feature"]: module._not_near_duplicate(it) for it in items}

    assert results == {"distinct": True, "near_dup": False, "unjudged": False}


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


def test_create_fresh_prefers_lower_demand_rank_over_alphabetical_feature() -> None:
    # "Board Update Deck Builder" (alphabetically first feature) must NOT jump the queue
    # over a lower (more urgent) demand-ranked candidate like football-match-analyst.
    module = load_module()
    normalized = {"readable": True, "counts": {"occupied": 0}}
    candidates = [
        {"feature": "catalog:board-update-deck-builder", "title": "Board Update Deck Builder",
         "demand_rank": module.UNRANKED_DEMAND},
        {"feature": "catalog:football-match-analyst", "title": "Football Match Analyst",
         "demand_rank": 1},
        {"feature": "catalog:portfolio-tracker", "title": "Portfolio Tracker", "demand_rank": 2},
    ]

    decision = module.allocate_action(normalized, [], candidates)

    assert decision["action"] == "create_fresh"
    assert decision["item"]["feature"] == "catalog:football-match-analyst"


def test_create_fresh_falls_back_to_alphabetical_within_same_rank() -> None:
    module = load_module()
    normalized = {"readable": True, "counts": {"occupied": 0}}
    candidates = [
        {"feature": "catalog:zzz-skill", "title": "Zzz", "demand_rank": module.UNRANKED_DEMAND},
        {"feature": "catalog:aaa-skill", "title": "Aaa", "demand_rank": module.UNRANKED_DEMAND},
    ]

    decision = module.allocate_action(normalized, [], candidates)

    assert decision["item"]["feature"] == "catalog:aaa-skill"


def test_listing_demand_rank_parses_line_and_defaults_when_missing(tmp_path: Path) -> None:
    module = load_module()
    ranked = tmp_path / "ranked.md"
    ranked.write_text("Primary Model: Claude Sonnet 4.6\n\nDemand rank: 2\n\n| cycle |\n")
    unranked = tmp_path / "unranked.md"
    unranked.write_text("Primary Model: Claude Sonnet 4.6\n\n| cycle |\n")

    assert module.listing_demand_rank(str(ranked)) == 2
    assert module.listing_demand_rank(str(unranked)) == module.UNRANKED_DEMAND


def test_ready_inventory_reads_demand_rank_from_catalog_listing(tmp_path: Path) -> None:
    module = load_module()
    features = tmp_path / "features"
    icons = tmp_path / "icons"
    catalog = tmp_path / "catalog"
    features.mkdir()
    icons.mkdir()
    ranked = catalog / "football-match-analyst"
    ranked.mkdir(parents=True)
    (ranked / "LISTING.md").write_text("## Title\nFootball Match Analyst\n\nDemand rank: 1\n")
    (ranked / "SKILL.md").write_text("skill")
    (ranked / "icon.png").write_bytes(b"png")
    module.FEATURES = str(features)
    module.ICONS = str(icons)
    module.CATALOG = str(catalog)

    items = module.ready_inventory()

    assert items[0]["demand_rank"] == 1


def test_profit_update_outranks_draft_resume_when_a_slot_is_free() -> None:
    module = load_module()
    request = {"agent_id": "8123079349", "from_version_id": "2099413428859719680",
               "target_model_id": "deepseek/deepseek-v4.1-flash"}
    update = {"agent_id": "8123079349", "feature": "catalog:hook-lab",
              "title": "Hook Lab — Win the First 3 Seconds", "update_request": request}
    draft = {"agent_id": "9466718786", "title": "Shorts Hook Lab"}
    free = module.normalize_agents([agent("1", "under_review")])
    full = module.normalize_agents([agent(str(i), "under_review") for i in range(5)])

    assert module.allocate_action(free, [], [], resumable_drafts=[draft], updates=[update])["action"] == "update_existing"
    # Same-Agent updates are not capped (measured 2026-10-05), so a paid update outranks a draft resume at full cap too.
    assert module.allocate_action(full, [], [], resumable_drafts=[draft], updates=[update])["action"] == "update_existing"


def test_unfinished_draft_is_finished_before_a_new_skill_is_created() -> None:
    """Dais 2026-10-08: with no cap, "a slot is free" is always true, so the old rule (fresh outranks
    draft) meant a draft that already passed CP1/CP2 was never resumed and every pass started a new
    one from scratch (8580209829 stalled at CP3 while three newer drafts were created)."""
    module = load_module()
    fresh = {"feature": "catalog:ad-hook-lab", "title": "Ad Hook Lab", "demand_rank": 3}
    draft = {"agent_id": "9466718786", "title": "Shorts Hook Lab"}
    stub = {"agent_id": "4741926159", "title": "Delivery Commitment Evidence Ledger", "feature": "catalog:x"}
    free = module.normalize_agents([agent("1", "under_review")])
    full = module.normalize_agents([agent(str(i), "under_review") for i in range(5)])

    assert module.allocate_action(free, [], [fresh], resumable_drafts=[draft])["action"] == "resume_draft"
    assert module.allocate_action(full, [], [fresh], resumable_drafts=[draft])["action"] == "resume_draft"
    assert module.allocate_action(free, [], [fresh], stub_retries=[stub])["action"] == "retry_existing"
    assert module.allocate_action(free, [], [fresh])["action"] == "create_fresh"


def test_a_draft_is_attempted_at_most_three_times_then_new_skills_proceed(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    # Draft-attempt behavior only: the real catalog's Dais-approved UPDATE.json files must not decide here.
    catalog_copy = tmp_path / "catalog"
    shutil.copytree(Path(__file__).parents[2] / "capafy/catalog", catalog_copy,
                    ignore=shutil.ignore_patterns("UPDATE.json"))
    monkeypatch.setattr(module, "CATALOG", str(catalog_copy))
    monkeypatch.setattr(module, "RETIRED", str(tmp_path / "no-retired.json"))
    stub_name = "Earnings Call Brief — Pasted Results to Questions" + module.PLACEHOLDER_SUFFIX
    monkeypatch.setattr(module, "server_agents", lambda: [agent("4973250899", "draft", name=stub_name)])

    seen = []
    monkeypatch.setenv("CAPAFY_COUNT_DRAFT_ATTEMPT", "1")  # only the pass's deciding call counts
    for _ in range(5):
        module.main()
        decision = json.loads(capsys.readouterr().out.splitlines()[-1])
        seen.append((decision["action"], (decision.get("item") or {}).get("agent_id")))

    assert seen[:3] == [("retry_existing", "4973250899")] * 3, seen
    assert all(action == "create_fresh" for action, _ in seen[3:]), seen


def test_allocator_retries_lm_generated_stub_draft_at_full_cap() -> None:
    # 2026-09-29 measured: draft 4973250899 "Customer Renewal Evidence Brief (LM
    # generated -- please review and edit before saving)" sat occupied at
    # CAP_FULL forever because nothing title-matched the AI-generator's suffix.
    # stub_retries reuses the SAME agent_id, so -- like resumable_drafts -- it
    # must proceed even when all five slots are occupied.
    module = load_module()
    normalized = {"readable": True, "counts": {"occupied": 5}}
    stub = {
        "agent_id": "4973250899",
        "title": "Customer Renewal Evidence Brief",
        "feature": "catalog:customer-renewal-evidence-brief",
        "icon": "/catalog/customer-renewal-evidence-brief/icon.png",
        "listing": "/catalog/customer-renewal-evidence-brief/LISTING.md",
        "skill": "/catalog/customer-renewal-evidence-brief/SKILL.md",
        "source": "repo_catalog",
    }

    retried = module.allocate_action(normalized, [], [], stub_retries=[stub])

    assert retried["verdict"] == "PUBLISHABLE"
    assert retried["action"] == "retry_existing"
    assert retried["action_key"] == "retry:4973250899"
    assert retried["item"] == stub

    blocked = module.allocate_action(normalized, [], [])
    assert blocked == {"verdict": "CAP_FULL", "occupied": 5}


def test_lm_generated_stub_draft_is_retried_end_to_end(monkeypatch, tmp_path, capsys) -> None:
    # End-to-end via main(): a real repo_catalog title with a draft agent whose
    # name carries Capafy's AI-generator suffix must resolve to retry_existing
    # on that exact agent_id, even with all five slots occupied.
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(Path(__file__).parents[2] / "capafy/catalog"))
    # Independent of the production retired list (real agent ids get retired over time).
    monkeypatch.setattr(module, "RETIRED", str(tmp_path / "no-retired.json"))
    # Every catalog item carrying UPDATE.json needs its target Agent present and
    # unchanged, or main() fails closed with SERVER_UNREADABLE (by design: an
    # update target that vanished/moved must never be silently skipped).
    update_rows = [
        # Present and unchanged-name (so main() does not fail closed) but already on a
        # newer version, so no update is eligible and the stub retry is what is tested.
        agent(item["update_request"]["agent_id"], "online", name=item["title"],
              latestAgentVersionId="9" + item["update_request"]["from_version_id"])
        for item in module.ready_inventory() if item.get("update_request")
    ]
    stub_name = "Earnings Call Brief — Pasted Results to Questions" + module.PLACEHOLDER_SUFFIX
    rows = [agent("4973250899", "draft", name=stub_name)] + [
        agent(str(i), "under_review") for i in range(4)
    ] + update_rows
    monkeypatch.setattr(module, "server_agents", lambda: rows)

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert decision["verdict"] == "PUBLISHABLE"
    assert decision["action"] == "retry_existing"
    assert decision["item"]["agent_id"] == "4973250899"
    assert decision["item"]["title"] == "Earnings Call Brief — Pasted Results to Questions"

    # An unrelated LM-generated stub (no matching repo title) must NOT be touched.
    monkeypatch.setattr(module, "server_agents", lambda: [
        agent("999", "draft", name="Totally Unrelated Idea" + module.PLACEHOLDER_SUFFIX),
        *[agent(str(i), "under_review") for i in range(4)],
        *update_rows,
    ])
    module.main()
    untouched = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert untouched["verdict"] == "CAP_FULL"


def test_retired_offline_agent_is_not_recovered(monkeypatch, tmp_path, capsys) -> None:
    # C4 (2026-10-04): an agent we deliberately unpublished (RETIRED.json) must
    # never come back through recover_delisted just because it went offline.
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(tmp_path / "no-catalog"))
    retired_path = tmp_path / "RETIRED.json"
    retired_path.write_text(json.dumps({
        "agents": [{"agent_id": "1037005959", "title": "Retired Skill",
                    "reason": "C4", "retired_on": "2026-10-04"}]
    }), encoding="utf-8")
    monkeypatch.setattr(module, "RETIRED", str(retired_path))
    monkeypatch.setattr(module, "server_agents",
                         lambda: [agent("1037005959", "offline", name="Retired Skill")])

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert decision["verdict"] == "DRAINED"
    assert decision.get("action") != "recover_delisted"


def test_offline_agent_is_never_recovered(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(tmp_path / "no-catalog"))
    retired_path = tmp_path / "RETIRED.json"
    retired_path.write_text(json.dumps({
        "agents": [{"agent_id": "1037005959", "title": "Retired Skill",
                    "reason": "C4", "retired_on": "2026-10-04"}]
    }), encoding="utf-8")
    monkeypatch.setattr(module, "RETIRED", str(retired_path))
    monkeypatch.setattr(module, "server_agents",
                         lambda: [agent("sold-1", "offline", name="Sold Skill")])

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])

    # Dais 2026-10-08: already-submitted Agents are never recovered; new Agents only.
    assert decision.get("action") != "recover_delisted"
    assert (decision.get("item") or {}).get("agent_id") != "sold-1"


def test_malformed_retired_json_fails_closed(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(tmp_path / "no-catalog"))
    retired_path = tmp_path / "RETIRED.json"
    retired_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(module, "RETIRED", str(retired_path))
    monkeypatch.setattr(module, "server_agents",
                         lambda: [agent("sold-1", "offline", name="Sold Skill")])

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert decision["verdict"] == "SERVER_UNREADABLE"


def test_retired_draft_is_not_resumed(monkeypatch, tmp_path, capsys) -> None:
    # 2026-10-05: Shorts Hook Lab (retired, $0 lifetime) kept being resumed as a
    # draft every pass and blocked at CP1; retired agents must not be resumed.
    module = load_module()
    catalog = tmp_path / "catalog" / "shorts"
    catalog.mkdir(parents=True)
    (catalog / "LISTING.md").write_text("## Title\nShorts Skill\n", encoding="utf-8")
    (catalog / "SKILL.md").write_text("x", encoding="utf-8")
    (catalog / "icon.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(tmp_path / "catalog"))
    retired_path = tmp_path / "RETIRED.json"
    retired_path.write_text(json.dumps({"agents": [
        {"agent_id": "9466718786", "title": "Shorts Skill", "reason": "C3", "retired_on": "2026-10-05"}]}), encoding="utf-8")
    monkeypatch.setattr(module, "RETIRED", str(retired_path))
    monkeypatch.setattr(module, "server_agents", lambda: [agent("9466718786", "draft", name="Shorts Skill")])

    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert decision.get("action") != "resume_draft"


def test_profitable_sellers_are_never_updated(tmp_path) -> None:
    # Dais 2026-10-07: never touch an Agent that is selling at a profit.
    module = load_module()
    analytics = tmp_path / "analytics.json"
    analytics.write_text(json.dumps({"per_skill_rows": [
        {"agent_id": "hook", "stats_30d_orders": 9, "profit_30d_actual_usd": "13.90"},
        {"agent_id": "bleed", "stats_30d_orders": 2, "profit_30d_actual_usd": "-16.45"},
        {"agent_id": "zero", "stats_30d_orders": 0, "profit_30d_actual_usd": "0.00"},
    ]}))
    updates = [{"agent_id": a, "update_request": {"from_version_id": "v"}} for a in ("hook", "bleed", "zero")]

    kept = module.drop_profitable_updates(updates, path=analytics)

    # Dais 2026-10-07: no change to any published Agent, selling or not.
    assert kept == []


def test_dais_approved_exception_lets_one_profitable_update_through(tmp_path) -> None:
    module = load_module()
    analytics = tmp_path / "analytics.json"
    analytics.write_text(json.dumps({"per_skill_rows": [
        {"agent_id": "hook", "stats_30d_orders": 9, "profit_30d_actual_usd": "13.90"},
    ]}))
    approved = {"agent_id": "hook", "update_request": {"from_version_id": "v", "dais_approved_exception": "2026-10-07"}}
    plain = {"agent_id": "hook", "update_request": {"from_version_id": "v"}}

    assert module.drop_profitable_updates([approved, plain], path=analytics) == [approved]


def test_frozen_agents_are_never_updated_without_exception(tmp_path) -> None:
    module = load_module()
    analytics = tmp_path / "analytics.json"
    analytics.write_text(json.dumps({"per_skill_rows": []}))
    frozen = tmp_path / "FROZEN.json"
    frozen.write_text(json.dumps({"agent_ids": ["hook"]}))
    plain = {"agent_id": "hook", "update_request": {"from_version_id": "v"}}
    approved = {"agent_id": "hook", "update_request": {"from_version_id": "v", "dais_approved_exception": "x"}}

    assert module.drop_profitable_updates([plain, approved], path=analytics, frozen_path=frozen) == [approved]


def test_only_the_deciding_call_counts_a_draft_attempt(monkeypatch, tmp_path, capsys) -> None:
    """A pass calls inventory_status.py three times (pre-check, decision, post-verdict). Counting every
    call burned a draft's three attempts inside one pass (10/08: 3257394572 showed 3 after one pass)."""
    module = load_module()
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    # Draft-attempt behavior only: the real catalog's Dais-approved UPDATE.json files must not decide here.
    catalog_copy = tmp_path / "catalog"
    shutil.copytree(Path(__file__).parents[2] / "capafy/catalog", catalog_copy,
                    ignore=shutil.ignore_patterns("UPDATE.json"))
    monkeypatch.setattr(module, "CATALOG", str(catalog_copy))
    monkeypatch.setattr(module, "RETIRED", str(tmp_path / "no-retired.json"))
    stub_name = "Earnings Call Brief — Pasted Results to Questions" + module.PLACEHOLDER_SUFFIX
    monkeypatch.setattr(module, "server_agents", lambda: [agent("4973250899", "draft", name=stub_name)])
    monkeypatch.delenv("CAPAFY_COUNT_DRAFT_ATTEMPT", raising=False)
    for _ in range(4):
        module.main(); capsys.readouterr()
    assert module.load_draft_attempts() == {}, "non-deciding calls must not count"
    monkeypatch.setenv("CAPAFY_COUNT_DRAFT_ATTEMPT", "1")
    module.main(); capsys.readouterr()
    assert module.load_draft_attempts() == {"4973250899": 1}


def test_unlisted_cap_defaults_to_the_servers_five_and_is_overridable():
    """2026-10-09: 4 under review + 1 rejected = 5 and the server refused every create."""
    import importlib, os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    os.environ.pop("CAPAFY_UNLISTED_CAP", None)
    import inventory_status
    assert importlib.reload(inventory_status).CAP == 5
    os.environ["CAPAFY_UNLISTED_CAP"] = "9"
    try:
        assert importlib.reload(inventory_status).CAP == 9
    finally:
        os.environ.pop("CAPAFY_UNLISTED_CAP", None)
        importlib.reload(inventory_status)


def test_dais_approved_update_ships_even_when_review_slots_are_full(monkeypatch, tmp_path, capsys) -> None:
    """2026-10-10: main() passed updates=[] unconditionally, so the Dais-approved price restore
    UPDATE.json files for Hook Lab / TikTok Script Pro / YouTube Script Writer never shipped and
    the factory kept answering CAP_FULL. Only updates carrying dais_approved_exception may pass."""
    module = load_module()
    catalog = tmp_path / "catalog" / "hook-lab"
    catalog.mkdir(parents=True)
    (catalog / "LISTING.md").write_text("## Title\nHook Lab\n", encoding="utf-8")
    (catalog / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (catalog / "icon.png").write_bytes(b"png")
    (catalog / "UPDATE.json").write_text(json.dumps({
        "agent_id": "8123079349", "from_version_id": "111", "target_model_id": "anthropic/claude-sonnet-5",
        "dais_approved_exception": "Dais 2026-10-10: restore the September prices"}), encoding="utf-8")
    analytics = tmp_path / "analytics.json"
    analytics.write_text(json.dumps({"per_skill_rows": []}), encoding="utf-8")
    monkeypatch.setattr(module, "FEATURES", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(module, "CATALOG", str(tmp_path / "catalog"))
    monkeypatch.setattr(module, "RETIRED", str(tmp_path / "no-retired.json"))
    monkeypatch.setattr(module, "ANALYTICS_PATH", str(analytics))
    full = [agent(str(i), "under_review") for i in range(5)]
    hook_lab = agent("8123079349", "online", name="Hook Lab", latestAgentVersionId="111")
    monkeypatch.setattr(module, "server_agents", lambda: full + [hook_lab])
    module.main()
    decision = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert decision["action"] == "update_existing", decision
    assert decision["item"]["agent_id"] == "8123079349"


def test_refund_draft_attempt_undoes_one_count_and_never_goes_negative(monkeypatch, tmp_path) -> None:
    """2026-10-11: the CP1 agent was deferred (disk_headroom_low, rc 75) on every pass, yet each pass
    still charged a draft attempt. Hook Lab and TikTok's Dais-approved price-restore drafts hit
    MAX_DRAFT_ATTEMPTS without the agent ever running and were dropped from the resume queue."""
    module = load_module()
    module.record_draft_attempt("8123079349", module.load_draft_attempts())
    module.record_draft_attempt("8123079349", module.load_draft_attempts())
    module.refund_draft_attempt("8123079349")
    assert module.load_draft_attempts() == {"8123079349": 1}
    module.refund_draft_attempt("8123079349")
    module.refund_draft_attempt("8123079349")
    assert module.load_draft_attempts().get("8123079349", 0) == 0


def test_refund_cli_entry(monkeypatch, tmp_path) -> None:
    import subprocess, sys as _sys
    module = load_module()
    module.record_draft_attempt("2844813315", module.load_draft_attempts())
    proc = subprocess.run([_sys.executable, str(SCRIPT), "--refund-draft-attempt", "2844813315"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert module.load_draft_attempts().get("2844813315", 0) == 0
