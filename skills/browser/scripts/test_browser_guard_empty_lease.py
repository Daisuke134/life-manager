#!/usr/bin/env python3
"""browser-guard.sh acquire vs an empty lease file.

2026-10-09 20:23 JST: the host disk was full, claim() created the lease with O_EXCL and the write
failed, leaving a 0-byte line-creators_dais.lease. The guard read it as an "invalid live lease"
forever, so every LINE readback after that was browser_unavailable. Fake registry and resolver,
no real browser.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

GUARD = Path(__file__).resolve().parents[1] / "browser-guard.sh"
RESOLVER = '''import json, sys
if "--all" in sys.argv:
    print(json.dumps({"identities": []}))
else:
    print(json.dumps({"endpoint": "http://127.0.0.1:1", "port": 1, "uuid": "test-uuid"}))
'''


class EmptyLease(unittest.TestCase):
    def acquire(self, lease_age_seconds: float) -> subprocess.CompletedProcess:
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tmp / "browsers.toml").write_text('[[identity]]\nid = "test:x"\nprofile = "/tmp/none"\n')
        (tmp / "resolver.py").write_text(RESOLVER)
        leases = tmp / "leases"
        leases.mkdir()
        lease = leases / "test_x.lease"
        lease.write_text("")
        stamp = time.time() - lease_age_seconds
        os.utime(lease, (stamp, stamp))
        env = {**os.environ, "AI_BROWSER_REGISTRY": str(tmp / "browsers.toml"),
               "AI_BROWSER_LEASE_DIR": str(leases), "AI_BROWSER_ENDPOINT_RESOLVER": str(tmp / "resolver.py"),
               "AI_BROWSER_HOLDER_PID": str(os.getpid()), "AI_BROWSER_HOLDER_START": "test-start"}
        return subprocess.run(["bash", str(GUARD), "acquire", "test:x"], capture_output=True, text=True,
                              env=env, timeout=60)

    def test_an_old_empty_lease_is_reclaimed(self) -> None:
        done = self.acquire(lease_age_seconds=3600)
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        self.assertEqual(done.stdout.strip(), "http://127.0.0.1:1")

    def test_a_fresh_empty_lease_is_still_respected(self) -> None:
        # It may be a claim whose write is still in flight.
        self.assertEqual(self.acquire(lease_age_seconds=5).returncode, 9)


if __name__ == "__main__":
    unittest.main()
