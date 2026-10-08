import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import creators_readback as MODULE  # noqa: E402


class ApplyReading(unittest.TestCase):
    def test_a_real_status_is_recorded_with_its_purchase_url(self) -> None:
        item = {"product_id": "48067450", "state_observed": "審査待ち"}
        out = MODULE.apply_reading(item, {"status": "販売中", "purchase_url": "https://line.me/S/sticker/37142349"})
        self.assertEqual(out["state_observed"], "販売中")
        self.assertEqual(out["purchase_url"], "https://line.me/S/sticker/37142349")

    def test_an_unavailable_browser_never_overwrites_the_last_real_status(self) -> None:
        # 2026-10-09: all ten on-sale sets read browser_unavailable, so none could be promoted.
        item = {"product_id": "1", "state_observed": "販売中", "purchase_url": "https://line.me/S/sticker/2"}
        for status in ("browser_unavailable", "needs_login", "unknown", None):
            out = MODULE.apply_reading(dict(item), {"status": status, "detail": "x"})
            self.assertEqual(out["state_observed"], "販売中", status)
            self.assertEqual(out["purchase_url"], "https://line.me/S/sticker/2", status)

    def test_a_missing_purchase_url_keeps_the_known_one(self) -> None:
        item = {"product_id": "1", "state_observed": "販売中", "purchase_url": "https://line.me/S/sticker/2"}
        out = MODULE.apply_reading(dict(item), {"status": "販売中", "purchase_url": None})
        self.assertEqual(out["purchase_url"], "https://line.me/S/sticker/2")

    def test_a_built_store_url_is_never_stored(self) -> None:
        out = MODULE.apply_reading({"product_id": "1"}, {"status": "販売中", "store_url": "https://store.line.me/stickershop/product/1/ja"})
        self.assertNotIn("store_url", out)


if __name__ == "__main__":
    unittest.main()
