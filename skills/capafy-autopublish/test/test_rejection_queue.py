from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "rejection_queue.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rejection_queue", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def rejected(agent_id: str = "1037238583") -> dict:
    return {
        "agent_id": agent_id,
        "name": "Football Match Analyst",
        "latest_version_id": "version-old",
        "latest_version_name": "1.2.0",
        "remote_status": "review_rejected",
        "lifecycle": "retry",
        "agent_type": "run_online",
        "sales": 0,
        "recent_sales": 0,
    }


def detail(reason: str | None = "OpenRouter billing error") -> dict:
    latest = {
        "agentId": "1037238583",
        "agentVersionId": "version-old",
        "versionNo": 4,
        "versionName": "1.2.0",
        "status": 2,
        "auditStatus": 3,
        "isConfirmedSkills": True,
        "isConfirmedConfigKeys": True,
    }
    if reason is not None:
        latest["rejectReason"] = reason
    return {"ok": True, "agent_id": "1037238583", "latest_version": latest}


def test_real_rejected_fixture_preserves_agent_and_targets_next_version() -> None:
    module = load_module()
    queue = module.build_queue({}, [rejected()], {"1037238583": detail()}, "2026-08-22T11:00:00Z")

    item = queue["items"][0]
    assert item["agent_id"] == "1037238583"
    assert item["source_version_id"] == "version-old"
    assert item["target_version_no"] == 5
    assert item["operation"] == "update_existing_agent"
    assert item["rejection_reason"] == "OpenRouter billing error"
    assert item["state"] == "queued"
    assert "new_agent_id" not in item


def test_missing_platform_reason_is_visible_and_not_invented() -> None:
    module = load_module()
    queue = module.build_queue({}, [rejected()], {"1037238583": detail(None)}, "2026-08-22T11:00:00Z")

    item = queue["items"][0]
    assert item["rejection_reason"] == "platform_reason_unavailable"
    assert item["reason_status"] == "unknown"
    assert item["state"] == "needs_diagnosis"


def test_replay_dedupes_same_agent_version_and_preserves_progress() -> None:
    module = load_module()
    first = module.build_queue({}, [rejected()], {"1037238583": detail()}, "2026-08-22T11:00:00Z")
    first["items"][0]["state"] = "tests_passing"
    replay = module.build_queue(first, [rejected()], {"1037238583": detail()}, "2026-08-22T12:00:00Z")

    assert len(replay["items"]) == 1
    assert replay["items"][0]["state"] == "tests_passing"
    assert replay["items"][0]["repair_id"] == "1037238583:version-old"


def test_new_rejected_version_creates_new_queue_item_same_agent() -> None:
    module = load_module()
    first = module.build_queue({}, [rejected()], {"1037238583": detail()}, "2026-08-22T11:00:00Z")
    newer = detail("Policy wording")
    newer["latest_version"]["agentVersionId"] = "version-new"
    newer["latest_version"]["versionNo"] = 5
    second = module.build_queue(first, [rejected()], {"1037238583": newer}, "2026-08-23T11:00:00Z")

    assert [item["agent_id"] for item in second["items"]] == ["1037238583", "1037238583"]
    assert second["items"][-1]["target_version_no"] == 6


def test_agent_brief_points_at_the_file_the_queue_is_actually_written_to() -> None:
    # 2026-10-23: DAILY_LOOP.md told the drainer agent to read `state/capafy-rejection-repair-queue.json`
    # (relative to CAPAFY_STATE_DIR = .../state/capafy-autopublish), but rejection_queue.py writes it one
    # level up. The agent found no file, refused a "blind" resubmission, and both rejected agents stayed
    # in the five slots.
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import rejection_queue

    brief = (Path(__file__).resolve().parents[1] / "DAILY_LOOP.md").read_text()
    written = str(rejection_queue.DEFAULT_QUEUE).replace(str(Path.home()), "~")
    assert written in brief
    assert "`state/capafy-rejection-repair-queue.json`" not in brief
