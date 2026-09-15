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


def test_reference_map_is_present_and_names_pinned_sources() -> None:
    path = REPO_ROOT / "docs/agent-engineering/REFERENCE-REPOS.md"
    text = path.read_text(encoding="utf-8")
    assert "pinned commit" in text.lower()
    assert "license" in text.lower()
    assert "openai/symphony" in text
    assert "UKGovernmentBEIS/inspect_ai" in text
