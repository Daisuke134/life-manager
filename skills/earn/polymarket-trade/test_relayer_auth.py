import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eth_account import Account  # noqa: E402

import relayer_auth as ra  # noqa: E402


class Resp:
    def __init__(self, status, data=None):
        self.status_code, self._data, self.text = status, data, str(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, challenge):
        self.challenge, self.calls = challenge, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if url.endswith("/v1/challenge"):
            return Resp(200, self.challenge)
        return Resp(200, {"type": "metamask"})


def challenge_for(address, nonce="abc123"):
    fields = {"address": address, "chainId": 137, "domain": "polymarket.com", "nonce": nonce,
              "statement": "Welcome to Polymarket! Sign to connect.", "uri": "https://polymarket.com",
              "version": "1", "issuedAt": "2026-09-26T13:00:00.000Z"}
    message = (f"polymarket.com wants you to sign in with your Ethereum account:\n{address}\n\n"
               f"Welcome to Polymarket! Sign to connect.\n\nURI: https://polymarket.com\nVersion: 1\n"
               f"Chain ID: 137\nNonce: {nonce}\nIssued At: 2026-09-26T13:00:00.000Z")
    return {"nonce": nonce, "fields": fields, "message": message}


class SiweLoginTest(unittest.TestCase):
    def test_signs_server_challenge_and_posts_login(self):
        acct = Account.create()
        s = FakeSession(challenge_for(acct.address))
        bearer = ra.siwe_login(s, acct)
        self.assertEqual([u.rsplit("/", 2)[-1] for u, _ in s.calls], ["challenge", "login"])
        self.assertEqual(s.calls[1][1]["headers"]["Authorization"], "Bearer " + bearer)

    def test_rejects_challenge_for_other_address(self):
        acct = Account.create()
        with self.assertRaises(RuntimeError):
            ra.siwe_login(FakeSession(challenge_for(Account.create().address)), acct)

    def test_rejects_non_siwe_message(self):
        acct = Account.create()
        ch = challenge_for(acct.address)
        ch["message"] = "transfer everything"
        with self.assertRaises(RuntimeError):
            ra.siwe_login(FakeSession(ch), acct)


class LiveGateTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ("PM_DRY_RUN", "PM_LIVE_CONFIRM")}

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def _mint_without_network(self):
        called = []
        ra.siwe_login = lambda *a: called.append("login") or "x"
        try:
            ra.mint_relayer_api_key(Account.create(), cache_path="/tmp/never-used-relayer-cache", force=True)
        finally:
            ra.siwe_login = ORIGINAL_SIWE_LOGIN
        return called

    def test_dry_by_default_exits_zero_before_any_auth(self):
        with self.assertRaises(SystemExit) as cm:
            self._mint_without_network()
        self.assertEqual(cm.exception.code, 0)

    def test_single_opt_in_is_not_enough(self):
        os.environ["PM_DRY_RUN"] = "0"
        with self.assertRaises(SystemExit):
            self._mint_without_network()

    def test_double_opt_in_reaches_login(self):
        os.environ["PM_DRY_RUN"] = "0"
        os.environ["PM_LIVE_CONFIRM"] = "I_UNDERSTAND_THE_RISK"
        self.assertTrue(ra.live_confirmed())


ORIGINAL_SIWE_LOGIN = ra.siwe_login


class GateOrderTest(unittest.TestCase):
    def test_live_gate_runs_before_credential_derivation(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("bundle_arb.py", "market_maker.py"):
            with open(os.path.join(here, name)) as f:
                body = f.read().split("def main():", 1)[1]
            self.assertLess(body.index("mint()"), body.index("SecureClient._create"), name)


if __name__ == "__main__":
    unittest.main()
