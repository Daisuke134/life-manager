---
name: life-manager-disk-cleanup
description: Host-wide, fail-closed disk capacity governor for Life Manager.
---

# Life Manager disk cleanup

This skill owns the local host capacity pass. It is intentionally not a
Life-Manager-directory cleaner: it measures the Mac and only removes an
allow-listed regenerable artifact after an open-path probe confirms
`confirmed-closed`.

## Safety contract

- `.claude`, `.codex`, `.config/ai`, OpenClaw state/identity/workspace, `.git`,
  databases, credentials, cookies, source, and `state/*.jsonl` are preserved.
- Unknown paths, active leases, symlinks, open paths, and probe errors are
  preserved and recorded.
- A stale Sparkle staging blocker has one narrow recovery action: send one
  `SIGTERM` only to the same-UID updater whose executable is under an exact
  allow-listed Codex/CodexBar Sparkle `Launcher`, whose PPID is 1, whose elapsed
  time exceeds 24 hours, and whose start-time/process fingerprint still matches
  immediately before signaling. The Sparkle root, Launcher, Installation and
  PersistentDownloads paths must exist as stable real directories with no
  symlink component, and both staged paths must remain `confirmed-closed` across
  the identity check. Record `signaled`, verified `terminated`, `already_exited`,
  `preserved` and `errors` separately. Preserve on any mismatch, replacement,
  timeout or probe ambiguity. Never use `SIGKILL`, stop the parent app, or signal
  a browser or loop.
- `sweep()` accepts only candidates carrying internal allow-list discovery proof
  for the exact regenerable families; the CLI `--candidate` escape hatch is
  rejected so an arbitrary path cannot be promoted by an operator flag.
- The 5-minute pass has one atomic lock and no LLM deletion authority.
- Pressure is asserted below 11 GiB and is not cleared until the recovery floor
  is reached; the 20 GiB threshold starts preventive containment.
- Every pass atomically writes `host-inventory.json`: local `df` mounts and
  bounded owner-family metadata. The hourly/full compatibility pass may run a
  timeout-bounded `du` probe for allow-listed families; gaps are recorded as
  unknown and never become deletion candidates. The fallback adapter keeps a
  separate `cleanup-full-pass.at` marker so one bounded full cleanup occurs at
  most once per hour; a missing or stale marker is fail-closed toward
  observation/probe bounds, never toward deleting unknown paths.
- The host adapter bounds the governor, runtime-manifest, and sweep subprocesses;
  timeout is a preserve/error result and never advances the full-pass marker.
- Receipts are bounded and the high-volume cleanup ledger is rotated before it
  can consume the reserve.

## Local installation

```sh
skills/self/disk-cleanup/install-launchd.sh
```

The installer renders the user-specific plist, validates it with `plutil`, and
registers `ai.anicca.life-manager-disk-cleanup` at a 300-second interval. If
the macOS launchd user domain is temporarily unavailable, the existing
emergency guard invokes `disk_cleanup.py` as its single fallback owner. The
legacy hourly label is only a compatibility trigger: the guard's
`cleanup-full-pass.at` marker (or explicit `EMERGENCY_GUARD_FULL_PASS=1`) opts
into the bounded full pass so deferred worktree inspection is not permanently
skipped.

Run the tests with:

```sh
python3 -m pytest -q skills/self/disk-cleanup/tests/test_disk_cleanup.py
```
