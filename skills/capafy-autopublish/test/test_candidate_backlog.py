from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "candidate_backlog.py"
DAILY = Path(__file__).parents[1] / "scripts" / "daily_loop.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("candidate_backlog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def candidate_tree(tmp_path: Path) -> tuple[Path, Path]:
    features = tmp_path / "features"
    icons = tmp_path / "icons"
    candidate = features / "capafy-o13-interviews"
    (candidate / "test").mkdir(parents=True)
    icons.mkdir()
    (candidate / "SKILL.md").write_text("# Interview Synthesizer\n")
    (candidate / "LISTING.md").write_text("## Title\nInterview Synthesizer\n")
    (candidate / "test" / "case1.md").write_text("input -> expected output\n")
    (icons / "o13.png").write_bytes(b"png")
    return features, icons


def inventory(status: str | None = None) -> dict:
    agents = [] if status is None else [{"name": "Interview Synthesizer", "remote_status": status}]
    return {"readable": True, "agents": agents, "counts": {"occupied": 5, "free": 0}}


def test_refresh_registers_complete_offline_candidate_without_platform_agent(tmp_path: Path) -> None:
    module = load_module()
    features, icons = candidate_tree(tmp_path)

    backlog = module.refresh_backlog({}, inventory(), features, icons, "2026-08-22T12:00:00Z")

    item = backlog["items"][0]
    assert item["candidate_id"] == "capafy-o13-interviews"
    assert item["platform_state"] == "not_submitted"
    assert item["state"] == "ready"
    assert item["gates"] == {"skill": "pass", "listing": "pass", "icon": "pass", "tests": "pass"}
    assert item["content_sha256"].startswith("sha256:")
    assert "agent_id" not in item


def test_platform_match_advances_backlog_without_creating_another_candidate(tmp_path: Path) -> None:
    module = load_module()
    features, icons = candidate_tree(tmp_path)
    first = module.refresh_backlog({}, inventory(), features, icons, "2026-08-22T12:00:00Z")
    second = module.refresh_backlog(first, inventory("under_review"), features, icons, "2026-08-22T13:00:00Z")

    assert len(second["items"]) == 1
    assert second["items"][0]["platform_state"] == "under_review"
    assert second["items"][0]["state"] == "submitted"


def test_manual_publish_approval_is_not_misreported_as_listed(tmp_path: Path) -> None:
    module = load_module()
    features, icons = candidate_tree(tmp_path)

    backlog = module.refresh_backlog({}, inventory("approved"), features, icons, "2026-08-22T13:00:00Z")

    assert backlog["items"][0]["platform_state"] == "approved"
    assert backlog["items"][0]["state"] == "submitted"


def test_incomplete_candidate_is_not_ready(tmp_path: Path) -> None:
    module = load_module()
    features, icons = candidate_tree(tmp_path)
    (features / "capafy-o13-interviews" / "test" / "case1.md").unlink()

    backlog = module.refresh_backlog({}, inventory(), features, icons, "2026-08-22T12:00:00Z")

    assert backlog["items"][0]["state"] == "building"
    assert backlog["items"][0]["gates"]["tests"] == "missing"


def test_atomic_write_is_private(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "state" / "backlog.json"
    module.atomic_write(output, {"schema_version": 1, "items": []})

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text())["items"] == []


def test_daily_loop_refreshes_backlog_before_cap_full_exit() -> None:
    source = DAILY.read_text()
    refresh = source.index("candidate_backlog.py")
    cap_full = source.index("DRAINED|CAP_FULL")

    assert refresh < cap_full
    assert "--inventory-stdin" in source


def test_repo_catalog_rejected_item_keeps_same_agent_identity(tmp_path: Path) -> None:
    module = load_module()
    catalog = tmp_path / "catalog"
    candidate = catalog / "football-match-analyst"
    candidate.mkdir(parents=True)
    title = "Football Match Analyst — Weekly Fixture Read"
    (candidate / "SKILL.md").write_text("# Football\n")
    (candidate / "LISTING.md").write_text(f"## Title\n{title}\n")
    (candidate / "icon.svg").write_text("<svg/>")
    current = {
        "agents": [{"agent_id": "1037238583", "name": title,
                    "remote_status": "review_rejected"}],
        "counts": {"occupied": 5, "free": 0},
    }

    backlog = module.refresh_backlog({}, current, tmp_path / "features", tmp_path / "icons",
                                     "2026-08-22T12:00:00Z", catalog)

    assert backlog["items"] == [backlog["items"][0]]
    assert backlog["items"][0]["candidate_id"] == "catalog:football-match-analyst"
    assert backlog["items"][0]["agent_id"] == "1037238583"
    assert backlog["items"][0]["platform_state"] == "review_rejected"
    assert backlog["items"][0]["state"] == "ready_retry"
    assert backlog["counts"]["ready_retry"] == 1
