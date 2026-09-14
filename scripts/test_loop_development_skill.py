import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/loop-development/SKILL.md"


class LoopDevelopmentSkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text()
        cls.prose = " ".join(cls.text.split())

    def test_reuses_goal_named_same_task_worktree_before_creating_one(self):
        self.assertIn("active persistent goal", self.prose)
        self.assertIn("goal-named worktree takes priority", self.prose)
        self.assertIn("Never create a duplicate worktree for the same task", self.prose)

    def test_parallel_sessions_have_disjoint_owners(self):
        self.assertIn("One independent workstream owns one worktree, branch, and lease", self.prose)
        self.assertIn("same worktree, branch, mutable state, browser profile, or CDP port", self.prose)
        self.assertIn("serialize the exact shared effect", self.prose)

    def test_development_and_runtime_skills_are_not_conflated(self):
        self.assertIn("applicable Superpowers process skill", self.prose)
        self.assertIn("Codex plugin skills are development-time tools", self.prose)
        self.assertIn("Life Manager runtime loads only repository-owned skills", self.prose)

    def test_code_first_research_reuses_existing_sources(self):
        self.assertIn("inspect the existing implementation and local clones before prose documentation", self.prose)
        self.assertIn("Do not clone a duplicate repository", self.prose)


if __name__ == "__main__":
    unittest.main()
