"""set-012 (2026-10-08) packaged ChatGPT sprite-sheet clips and crashed on receipt['request_id']."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seedance_set as MODULE  # noqa: E402


class ClipReceipt(unittest.TestCase):
    def test_chatgpt_sheet_receipt_maps_to_validator_keys(self) -> None:
        row = MODULE._clip_receipt({"id": "angry", "provider": "chatgpt-imagegen",
                                    "sheet_sha256": "0d64c36226638ef3" + "a" * 48, "estimated_usd": 0})
        self.assertEqual(row, {"id": "angry", "request_id": "chatgpt:0d64c36226638ef3",
                               "sha256": "0d64c36226638ef3" + "a" * 48, "estimated_usd": "0"})

    def test_fal_receipt_unchanged(self) -> None:
        row = MODULE._clip_receipt({"id": "x", "request_id": "r1", "sha256": "s", "estimated_usd": 0.07})
        self.assertEqual(row, {"id": "x", "request_id": "r1", "sha256": "s", "estimated_usd": "0.07"})


if __name__ == "__main__":
    unittest.main()
