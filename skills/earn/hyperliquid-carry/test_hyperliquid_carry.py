import json, os, stat, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wallet


class WalletTest(unittest.TestCase):
    def test_creates_once_then_reuses_with_private_modes(self):
        with tempfile.TemporaryDirectory() as d:
            ssot = Path(d) / "anicca" / "credentials.json"
            a = wallet.load_or_create(ssot)
            b = wallet.load_or_create(ssot)
            self.assertEqual(a.address, b.address)
            self.assertEqual(stat.S_IMODE(ssot.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(ssot.parent.stat().st_mode), 0o700)
            rows = json.loads(ssot.read_text())["credentials"]
            self.assertEqual([r["service"] for r in rows], [wallet.SERVICE])

    def test_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            ssot = Path(d) / "anicca" / "credentials.json"
            ssot.parent.mkdir(mode=0o700)
            ssot.write_text(json.dumps({"credentials": [{"service": "other", "password": "x"}]}))
            os.chmod(ssot, 0o600)
            wallet.load_or_create(ssot)
            services = [r["service"] for r in json.loads(ssot.read_text())["credentials"]]
            self.assertEqual(services, ["other", wallet.SERVICE])


if __name__ == "__main__":
    unittest.main()
