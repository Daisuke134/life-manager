import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seedance_set  # noqa: E402


class FalRetryTest(unittest.TestCase):
    def _error(self, code):
        return urllib.error.HTTPError("u", code, "x", {}, None)

    def test_read_retries_gateway_timeout_then_succeeds(self):
        ok = mock.MagicMock()
        ok.__enter__.return_value.read.return_value = b'{"status": "COMPLETED"}'
        with mock.patch.dict("os.environ", {"FAL_KEY": "k"}), \
             mock.patch("urllib.request.urlopen", side_effect=[self._error(504), ok]), \
             mock.patch("time.sleep"):
            self.assertEqual(seedance_set._fal("https://x/status"), {"status": "COMPLETED"})

    def test_submit_is_never_retried(self):
        with mock.patch.dict("os.environ", {"FAL_KEY": "k"}), \
             mock.patch("urllib.request.urlopen", side_effect=[self._error(504), AssertionError("retried")]) as urlopen:
            with self.assertRaises(urllib.error.HTTPError):
                seedance_set._fal("https://x/submit", {"prompt": "p"})
            self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
