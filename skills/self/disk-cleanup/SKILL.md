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
- Worktrees and their registrations are never automatic cleanup candidates.
  Cleanup never runs `git worktree unlock`, `remove`, or `prune`; retirement
  remains an owner operation under `../../../docs/runbooks/worktree-lifecycle.md`.
- iOS Simulator runtimes, images, device data, and dyld caches remain outside
  the cleanup allow-list, including when no device is booted.
- Generic `/private/tmp` directories, including `cfo-*`, are never candidates;
  only exact old Capafy npm cache names are eligible there.
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
- The exact `~/Library/Developer/Xcode/DerivedData` tree is a regenerable build
  cache candidate. It is reclaimed only after the path is confirmed closed;
  Xcode Archives and project source remain outside this allow-list.
- Homebrew, pip, and uv package download caches are regenerable candidates and
  are reclaimed only after the same confirmed-closed check.
- The 5-minute pass has one atomic lock and no LLM deletion authority.
- The 2 GiB recovery value describes cleanup success only; it does not pause
  producer or release loops. `disk-pressure.block` is advisory. The explicit
  `disk-writers.stop` file remains a separate hard operator control.
- The central cleanup terminal reports capacity recovery separately from
  deletion outcomes: integer `free_after` must meet the existing 2 GiB floor;
  a shortfall is `unmet`, and missing or invalid capacity is `unknown`. These
  statuses do not replace `errors` or `protected_deletions`.
- The direct governor CLI stores the same capacity status and `ok` in its pass
  receipt and exits nonzero for unmet or unknown capacity, deletion errors, or
  protected deletions. A busy singleton lock reports `cleanup_lock_busy` with
  unknown capacity and exits 75 without running cleanup.
- Candidate order rotates through `state_dir/candidate-cursor.json`. The cursor
  advances atomically under the governor's singleton lock; if disk exhaustion
  prevents that metadata write, the in-memory rotation still sweeps and retries
  the cursor once only after the sweep's fresh free-space reading meets 2 GiB.
  Cursor writes do not consume the terminal receipt reserve, and the receipt
  records cursor-write failures separately from deletion errors.
- The shared runner does not defer a wake because free bytes are below a floor.
  It still defers if filesystem measurement is unavailable and preserves the
  explicit `disk-writers.stop` control. A real write failure is recorded at the
  failing operation; it is not converted into a headroom admission result.
- After the final post-inventory capacity readback reaches 2 GiB, the governor
  removes `disk-writers.stop` only when its same-UID 0600 regular file still has
  the exact `host-disk-recovery` owner, `disk_headroom_low` reason, required
  bytes, and recovery action. Low/unknown capacity, foreign or malformed
  content, unsafe file type, and changed identity preserve the guard.
- Every pass atomically writes `host-inventory.json` with local mount sizes
  converted from `df -kP` 1 KiB block counts to bytes and bounded owner-family
  metadata. The hourly/full compatibility pass may run a
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

The 5-minute `ai.anicca.life-manager-disk-cleanup` owner remains managed by the
Life Manager runner. This installer only manages the 60-second
`com.anicca.disk-watchdog` recovery label so it cannot replace the 5-minute
owner. It installs `bin/disk-watchdog.sh` at `~/.local/bin/disk-watchdog.sh`;
the wrapper resolves `~/loops/current` and dispatches to that immutable
release's governor, so later release retirement cannot leave the watchdog
pointing at a deleted release. Both owners use the governor's singleton lock
and shared host `state_dir`.

The watchdog adds no second deletion implementation. Its output goes to
`life-manager-disk-cleanup/logs/watchdog.{out,err}.log` under the host state.

Run the tests with:

```sh
python3 -m pytest -q skills/self/disk-cleanup/tests/test_disk_cleanup.py \
  skills/self/disk-cleanup/tests/test_disk_watchdog_dispatcher.py
```
