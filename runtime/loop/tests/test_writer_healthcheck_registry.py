import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class WriterHealthcheckRegistryTest(unittest.TestCase):
    def test_healthcheck_declares_rebindable_admission_contract(self):
        registry = json.loads(
            (ROOT / "config" / "loop-registry.json").read_text(encoding="utf-8")
        )
        entry = registry["loops"]["article-healthcheck"]
        self.assertEqual(entry["resource_class"], "agent")
        self.assertEqual(entry["admission_class"], "borrow")
        self.assertEqual(entry["priority"], "support")


if __name__ == "__main__":
    unittest.main()
