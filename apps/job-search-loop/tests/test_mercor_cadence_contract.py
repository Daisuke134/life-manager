import json
import unittest
from pathlib import Path


class MercorCadenceContractTests(unittest.TestCase):
    def test_admission_contention_retries_without_queue_duplication(self):
        root = Path(__file__).resolve().parents[3]
        registry = json.loads(
            (root / "config" / "loop-registry.json").read_text(encoding="utf-8")
        )
        mercor = registry["loops"]["mercor-revenue-application"]
        self.assertEqual(mercor["cadence"]["start_interval_seconds"], 300)
        self.assertIs(mercor["coalesce_queued_wakes"], True)
        self.assertIs(mercor["coalesce_reserved_wakes"], True)


if __name__ == "__main__":
    unittest.main()
