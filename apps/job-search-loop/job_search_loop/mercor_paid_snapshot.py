"""Read contracts for the Paid owner without depending on Reply admission."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from .mercor_reply_snapshot import _direct_capture_expression
from .mercor_auth_readback import auth_snapshot_expression


def capture(page, *, expected_email: str, output: Path) -> None:
    """Capture on a caller-owned page; failed reads never refresh old evidence."""
    try:
        if not isinstance(expected_email, str) or not expected_email.strip():
            raise RuntimeError('mercor_paid_identity_unavailable')
        page.goto('https://work.mercor.com/home?tab=contracts',
                  wait_until='domcontentloaded', timeout=30000)
        if urlsplit(page.url).hostname != 'work.mercor.com':
            raise RuntimeError('mercor_paid_contract_capture_unavailable')
        auth = json.loads(page.evaluate(auth_snapshot_expression(expected_email=expected_email)))
        if (not isinstance(auth, dict) or auth.get('firebase_identity_matched') is not True
                or auth.get('firebase_user_present') is not True
                or auth.get('firebase_token_expired') is True
                or auth.get('firebase_token_refresh_failed') is True
                or auth.get('firebase_token_refresh_invalid') is True):
            raise RuntimeError('mercor_paid_contract_capture_unavailable')
        raw = page.evaluate(_direct_capture_expression(['contracts'], expected_email=expected_email))
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get('contracts'), list):
            raise RuntimeError('mercor_paid_contract_capture_unavailable')
        snapshot = {'version': 1, 'observed_at': datetime.now(timezone.utc).isoformat(),
                    'contracts': value['contracts']}
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.paid-snapshot-', dir=output.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(snapshot, stream, ensure_ascii=False, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        finally:
            Path(temporary).unlink(missing_ok=True)
    finally:
        page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads((Path.home()/'.config/anicca/job-search/profile.json').read_text())
        account = ((profile.get('candidate') or {}).get('application_email')
                   or profile.get('application_email') or profile.get('email'))
        if not isinstance(account, str) or not account.strip():
            raise RuntimeError('mercor_paid_identity_unavailable')
        endpoint = os.environ['CLOAK_CDP_BASE_URL']
        if urlsplit(endpoint).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise RuntimeError('mercor_paid_browser_unavailable')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser = runtime.chromium.connect_over_cdp(endpoint, timeout=10000)
            page = browser.contexts[0].new_page()
            capture(page, expected_email=account, output=args.output)
    except Exception:
        # Provider bodies, private identity and authentication material stay private.
        print('mercor_paid_contract_capture_unavailable')
        return 75
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
