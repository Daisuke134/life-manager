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


if __name__ == "__main__":
    unittest.main()
