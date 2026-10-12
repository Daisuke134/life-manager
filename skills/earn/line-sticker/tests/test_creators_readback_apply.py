import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

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



class AcquireWaitsForABusyBrowser(unittest.TestCase):
    """2026-10-12: the factory holds the LINE Creators browser for an hour at a time (it now makes
    sets back to back), so a readback that gave up on the first BUSY wrote browser_unavailable for
    every product and no review or sale was ever read. It waits its turn instead."""

    def done(self, code: int, out: str = "", err: str = ""):
        import types
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def test_it_retries_a_busy_browser_until_it_is_free(self) -> None:
        answers = iter([self.done(9, err="BUSY"), self.done(9, err="BUSY"), self.done(0, out="http://127.0.0.1:9231\n")])
        slept = []
        got = MODULE.acquire_when_free(lambda: next(answers), wait_seconds=600, poll_seconds=30,
                                       sleep=slept.append, clock=iter(range(0, 10000, 30)).__next__)
        self.assertEqual(got.returncode, 0)
        self.assertEqual(slept, [30, 30])

    def test_it_gives_up_after_the_wait_and_returns_the_busy_answer(self) -> None:
        clock = iter([0, 100, 400, 700]).__next__
        got = MODULE.acquire_when_free(lambda: self.done(9, err="BUSY"), wait_seconds=600, poll_seconds=30,
                                       sleep=lambda s: None, clock=clock)
        self.assertEqual(got.returncode, 9)

    def test_a_non_busy_failure_is_not_retried(self) -> None:
        calls = []
        got = MODULE.acquire_when_free(lambda: calls.append(1) or self.done(10, err="endpoint unavailable"),
                                       wait_seconds=600, poll_seconds=30, sleep=lambda s: None, clock=lambda: 0)
        self.assertEqual(got.returncode, 10)
        self.assertEqual(len(calls), 1)

    def test_main_returns_defer_after_browser_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item_file = root / "creators-item.json"
            item_file.write_text(json.dumps({
                "product_id": "1", "state_observed": "販売中",
                "purchase_url": "https://line.me/S/sticker/2",
            }))
            ledger = root / "readback.jsonl"
            output = io.StringIO()
            with (
                patch.object(MODULE, "LEDGER", ledger),
                patch.object(MODULE, "acquire_when_free", return_value=self.done(9, err="BUSY")),
                patch.object(sys, "argv", ["creators_readback.py", "--item-file", str(item_file)]),
                contextlib.redirect_stdout(output),
            ):
                result = MODULE.main()

            self.assertEqual(result, 75)
            self.assertEqual(json.loads(ledger.read_text().splitlines()[0])["status"], "browser_unavailable")
            self.assertEqual(json.loads(item_file.read_text())["state_observed"], "販売中")


if __name__ == "__main__":
    unittest.main()
