import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import local_loop  # noqa: E402


class XPostGateTest(unittest.TestCase):
    def test_absent_flag_blocks_and_never_calls_publisher(self):
        calls = []
        result = local_loop.gated_x_publish(
            SimpleNamespace(placement="p"), lambda a: calls.append(a), environ={})
        self.assertEqual(result["state"], "X_POST_BLOCKED")
        self.assertEqual(calls, [])

    def test_non_exact_values_block(self):
        for value in ("0", "true", "1 ", "yes", ""):
            calls = []
            local_loop.gated_x_publish(SimpleNamespace(), calls.append,
                                       environ={"AFFILIATE_X_POST_ENABLED": value})
            self.assertEqual(calls, [], value)

    def test_exact_one_allows(self):
        result = local_loop.gated_x_publish(
            SimpleNamespace(), lambda a: {"state": "LIVE", "public_url": "u"},
            environ={"AFFILIATE_X_POST_ENABLED": "1"})
        self.assertEqual(result["state"], "LIVE")

    def test_x_post_cli_publish_not_called_when_blocked(self):
        import x_post_cli
        with patch.dict("os.environ", {}, clear=True), \
                patch.object(x_post_cli, "publish") as publish:
            result = local_loop.gated_x_publish(SimpleNamespace(placement="p"))
        publish.assert_not_called()
        self.assertEqual(result["state"], "X_POST_BLOCKED")


if __name__ == "__main__":
    unittest.main()
