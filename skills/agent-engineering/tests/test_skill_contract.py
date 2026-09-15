"""Contract tests for the repository-owned agent-engineering skill set."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATHS = (
    REPO_ROOT / "skills/harness-engineering/SKILL.md",
    REPO_ROOT / "skills/context-engineering/SKILL.md",
    REPO_ROOT / "skills/loop-engineering/SKILL.md",
    REPO_ROOT / "skills/graph-engineering/SKILL.md",
    REPO_ROOT / "skills/eval-engineering/SKILL.md",
    REPO_ROOT / "skills/observability-engineering/SKILL.md",
    REPO_ROOT / "skills/goal-engineering/SKILL.md",
)
REQUIRED_SECTIONS = ("## Recipe", "## Contract", "## Failure modes", "## Source map")
MASTER_CATALOG_PIN = "692a1a681c464de22a5e9b947bd081808600b0b3"


def test_every_agent_engineering_skill_has_a_discoverable_contract() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path in SKILL_PATHS if not path.is_file()]
    assert not missing, f"missing skill documents: {missing}"

    for path in SKILL_PATHS:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), path
        frontmatter = text.split("---\n", 2)[1]
        assert frontmatter.startswith("name:") or "\nname:" in frontmatter, path
        description = next(
            line.removeprefix("description:").strip()
            for line in text.splitlines()
            if line.startswith("description:")
        )
        assert description.startswith("Use when"), path
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{path}: missing {section}"
        assert "## Master catalog route" in text, f"{path}: missing catalog route"
        assert "ai-boost/awesome-harness-engineering" in text, path
        assert MASTER_CATALOG_PIN in text, f"{path}: catalog pin drift"
        assert "Read this skill first" in text, f"{path}: missing load rule"


def test_reference_map_is_present_and_names_pinned_sources() -> None:
    path = REPO_ROOT / "docs/agent-engineering/REFERENCE-REPOS.md"
    text = path.read_text(encoding="utf-8")
    assert "pinned commit" in text.lower()
    assert "license" in text.lower()
    assert "openai/symphony" in text
    assert "UKGovernmentBEIS/inspect_ai" in text
    assert "steel-dev/steel-browser" in text
    assert "firecracker-microvm/firecracker" in text
    assert "lightpanda-io/browser" in text
    assert "browserless/browserless" in text


def test_agents_instructions_route_new_agent_work_to_the_skill_set() -> None:
    path = REPO_ROOT / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    assert "Agent Engineering Skills" in text
    assert "awesome-harness-engineering" in text
    for skill in (
        "harness-engineering",
        "context-engineering",
        "loop-engineering",
        "graph-engineering",
        "eval-engineering",
        "observability-engineering",
        "goal-engineering",
    ):
        assert f"skills/{skill}/SKILL.md" in text, skill
    assert "before" in text.lower() and "wake" in text.lower()
    for token in ("Model execution boundary", "Responses API", "read-only release", "no provider"):
        assert token in text, token
    for token in ("Browser execution boundary", "headless", "Steel Browser", "human handoff"):
        assert token in text, token


def test_architecture_refinement_spec_covers_the_control_plane_gaps() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    for section in (
        "## 1. Overview",
        "## 2. Acceptance Criteria",
        "## 3. As-Is / To-Be",
        "## 4. Target Architecture",
        "## 5. Test Matrix",
        "## 6. Boundaries",
        "## 7. Execution Steps",
        "## E2E Judgment",
    ):
        assert section in text, section
    for token in ("165", "resource_admission_deferred", "human_gate_id", "held-out", "replay-zero"):
        assert token in text, token


def test_architecture_spec_covers_private_reporting_and_model_runtime_boundary() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    for token in (
        "User Communication Contract",
        "Responses API",
        "Agents SDK",
        "routine wakes",
        "human_action_required",
        "background=true",
        "trace_include_sensitive_data",
    ):
        assert token in text, token


def test_architecture_spec_distinguishes_agents_api_from_local_runtime_layers() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    for token in (
        "Agents API",
        "Codex harness",
        "hosted sandbox",
        "read-only release",
        "provider credentials",
        "sandbox boundary",
    ):
        assert token in text, token


def test_internal_first_reporting_is_part_of_the_runtime_skill_contract() -> None:
    skill = (REPO_ROOT / "skills/observability-engineering/SKILL.md").read_text(encoding="utf-8")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for token in ("Internal-first reporting", "routine wake", "human action", "stable event key"):
        assert token in skill, token
    for token in ("User-facing reporting", "routine wake", "human action", "raw logs"):
        assert token in agents, token


def test_architecture_spec_covers_local_cloud_and_browser_execution_boundaries() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    for token in (
        "Browser Execution and Deployment",
        "Steel Browser",
        "headless",
        "virtual computer",
        "local Mac",
        "cloud",
        "session memory",
        "concurrency limit",
        "Firecracker",
        "Lightpanda",
    ):
        assert token in text, token


def test_architecture_spec_requires_local_completion_before_cloud_promotion() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    for token in (
        "Two Deployment Modes",
        "local-first",
        "local completion gate",
        "cloud promotion",
        "phone-only",
        "same implementation",
        "no cloud promotion before local acceptance",
    ):
        assert token in text, token


def test_local_to_cloud_plan_has_ordered_execution_and_phone_only_gate() -> None:
    path = REPO_ROOT / "docs/superpowers/plans/2026-09-15-life-manager-local-to-cloud.md"
    text = path.read_text(encoding="utf-8")
    for token in (
        "Local-to-Cloud Implementation Plan",
        "Task 1: ローカル完了台帳を作る",
        "Task 11: ローカル版を完全受入する",
        "Task 12: クラウド版へ同じ実装を昇格する",
        "Task 13: スマホだけの本番を有効化する",
        "local completion manifest",
        "cloud promotion",
        "phone-only",
        "never start all production jobs",
    ):
        assert token in text, token


def test_parallel_workstream_boundary_protects_the_active_marketplace_todo() -> None:
    spec = (REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md").read_text(encoding="utf-8")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for token in (
        "Parallel Workstream Boundary",
        "skills/earn/gig/TODO.md",
        "shared-file overlap",
        "provider-owned files",
    ):
        assert token in spec, token
    for token in ("Parallel workstream boundary", "active marketplace TODO", "shared file"):
        assert token in agents, token


def test_architecture_spec_has_a_remediation_and_ownership_row_for_all_product_loops() -> None:
    path = REPO_ROOT / "docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md"
    text = path.read_text(encoding="utf-8")
    assert "Fourteen-Loop Remediation Matrix" in text
    for loop in (
        "Coconala", "Lancers", "CrowdWorks", "Writer", "Affiliate", "Investment",
        "Agent Economy", "Job Hunter", "Fundraiser", "Connector", "Self-Build",
        "Mobile Apps", "Capafy", "CFO",
    ):
        assert loop in text, loop
    for token in ("shared kernel", "official readback", "completion condition", "workstream owner"):
        assert token in text, token
