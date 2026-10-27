# Security Scan historical fixture fingerprint

## Goal

Restore the full-history Gitleaks gate without hiding current findings or broad classes of secrets.

## Finding

The Security Scan's current-tree Gitleaks step passes, while the full-history step reports one `generic-api-key` match at line 30 of a historical Maritime billing HTTP test fixture, commit `010a4f31363056b2206526187c457588c93d4c31`. The matched field is a test request's idempotency key; the current tree no longer contains that test file. TruffleHog's verified-history step passes.

## Scope

- Add only the exact commit/path/rule/line fingerprint to `.gitleaksignore`.
- Record the test-only source review in the existing security baseline evidence, without copying the matched value.
- Keep both current-tree and `--all` full-history Gitleaks scans unchanged.

## Acceptance

## Progress

- Added only the exact commit/path/rule/line fingerprint to `.gitleaksignore` and documented the test-fixture review without copying the matched value.
- `python3 scripts/security/test_sec_scan_contract.py`: 5 tests passed.
- `gitleaks dir . --config .gitleaks.toml --no-banner --redact -v`: passed (no leaks).
- Targeted `gitleaks git` scan of commit `010a4f31363056b2206526187c457588c93d4c31`: passed (1 commit scanned; no leaks).
- Remaining: PR CI including the unchanged full-history `--all` scan, merge by PR, then green Security Scan readback on main.
