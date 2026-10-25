import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "DAILY_LOOP.md", ROOT / "CP1_AGENTIC.md", ROOT / "SKILL.md", ROOT / "scripts" / "daily_loop.sh"]


class ScriptsTheAgentRunsDirectlyAreExecutable(unittest.TestCase):
    def test_every_script_invoked_as_a_command_has_the_exec_bit(self):
        called = set()
        for doc in DOCS:
            if doc.exists():
                called |= set(re.findall(r"(?<![\w/.])scripts/([\w-]+\.(?:py|sh))\b", doc.read_text()))
        direct = [n for n in sorted(called) if (ROOT / "scripts" / n).read_text().startswith("#!")]
        self.assertTrue(direct)
        missing = [n for n in direct if not os.access(ROOT / "scripts" / n, os.X_OK)]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
