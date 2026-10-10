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
- A registered worktree is a cleanup candidate only when its exact path still
  matches Git metadata, it has no native lock, managed lease, or `.anicca-keep`
  marker, tracked/untracked/ignored state is empty, HEAD is reachable from the
  locally cached `origin/main`, and the global open-path probe confirms no open
  file or working directory beneath it. Recheck those facts immediately before
  using ordinary `git worktree remove` and confirm the path and registration
  are gone afterward. Never unlock, force-remove, or prune; preserve on any
  missing ref, timeout, mismatch, dirty state, lease, marker, or open path.
- iOS Simulator runtimes, images, device data, and dyld caches remain outside
  the cleanup allow-list, including when no device is booted.
- Generic `/private/tmp` directories, including `cfo-*`, remain unknown and
  protected. Scan the active `TMPDIR` plus `/private/tmp` and `/var/tmp` for
  same-user exact Capafy npm caches, old
  `pytest-of-<user>/pytest-<number>` runs, and test-generated `slide-pack-*`
  names; only paths older than one hour with a confirmed-closed path probe are
  eligible.
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
- The 2 GiB recovery value is a cleanup diagnostic only; it does not determine
  cleanup pass/fail and does not pause producer or release loops.
  `disk-pressure.block` is advisory. Producer loops ignore only the exact
  cleanup-owned `host-disk-recovery` / `disk_headroom_low` signal in
  `disk-writers.stop`; other operator-authored stop records remain hard stops.
- The central cleanup terminal reports capacity recovery separately from
  cleanup success: a nonnegative integer `free_after` is compared with the
  2 GiB diagnostic target; a shortfall is `unmet`, and missing, negative, or
  invalid capacity is `unknown`.
  A measured `unmet` status alone does not fail the cleanup occurrence. These
  statuses do not replace `errors` or `protected_deletions`.
- The direct governor CLI stores capacity status separately from `ok`. It exits
  nonzero for unknown capacity, deletion errors, protected deletions, or a
  preserved or invalid `disk-writers.stop` readback; it exits zero for a clean pass whose
  measured recovery is `unmet`. A busy singleton lock reports
  `cleanup_lock_busy` with unknown capacity and exits 75 without running cleanup. When invoked by the
  managed owner it includes that occurrence identity from the immutable manifest;
  central cleanup validates it and preserves the exact lock-busy deferral as exit
  75, without running shared release/scratch cleanup. Missing/foreign identity is
  still a failure, never a successful pass.
- Candidate order rotates through `state_dir/candidate-cursor.json`. The cursor
  advances atomically under the governor's singleton lock; if disk exhaustion
  prevents that metadata write, the in-memory rotation still sweeps and retries
  the cursor once only after the sweep's fresh free-space reading meets 2 GiB.
  Cursor writes do not consume the terminal receipt reserve, and the receipt
  records cursor-write failures separately from deletion errors.
- The shared runner and producer wrappers do not defer a wake because free
  bytes are low, cannot be measured, or the exact cleanup-owned low-space
  recovery signal exists. They continue to honor other operator-authored
  `disk-writers.stop` records. A real write failure remains an operation error,
  not a threshold admission result. Structured `ENOSPC` receipts are guaranteed
  only on paths that implement them; do not assume every producer classifies a
  failed state write as `ENOSPC`.
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

The 60-second `com.anicca.disk-watchdog` is the primary cleanup cadence. The
stable wrapper sets child-only `LIFE_MANAGER_DISK_INVENTORY_FAST=1`, so an
incomplete full census cannot make every minute repeat heavy size probes.
Deletion proof, protected paths, singleton locking and receipt coverage are
unchanged; missing sizes remain unknown.
5-minute `ai.anicca.life-manager-disk-cleanup` remains a managed reporting and
full-inventory owner; both share the same cleanup lock. This installer only
manages the 60-second recovery label so it cannot replace the managed owner.
It installs `bin/disk-watchdog.sh` at `~/.local/bin/disk-watchdog.sh`;
the wrapper resolves `~/loops/current` and dispatches to that immutable
release's governor, so later release retirement cannot leave the watchdog
pointing at a deleted release. Both owners use the governor's singleton lock
and shared host `state_dir`.

The 15-day `life-manager-disk-cleanup-15d` registry row is supplemental and is
not the recurrence guarantee. It invokes the same `HostDiskGovernor`; it must
not be changed to a second 60-second deletion owner while the direct watchdog
already runs every minute.

The watchdog adds no second deletion implementation. Its output goes to
`life-manager-disk-cleanup/logs/watchdog.{out,err}.log` under the host state.

Run the tests with:

```sh
python3 -m pytest -q skills/self/disk-cleanup/tests/test_disk_cleanup.py \
  skills/self/disk-cleanup/tests/test_disk_watchdog_dispatcher.py
```

## 共通runner storage契約

管理下stdioは `runtime/host/bounded_output.py` の有限relayで保存する。raw診断は1MiB segment/backup1、structured recordは別の16MiB上限。`storage-policy.json` はowner上限と登録owner数で分割するhost上限を持つ。agent-runnerの既存次wake preflightが、summary完了・host marker・EOF receipt・positive closed proofを満たすrelay診断だけを回収する。親result・usage・JSONLは保持する。terminal保存後も生存relayのscratchは保持し、終了後の既存GCに委ねる。

cleanup実行成功と容量回復は別。receipt identityを現在のcleanup owner/run/occurrence/releaseと照合してCLIへ表示する。inventoryの増加量は観測値であり削除許可ではない。実ENOSPC/EDQUOTだけをtyped failureにし、外部処理前と証明できたscratch allocationだけ既存reconcileへ接続する。fresh cleanup・persisted failure identity・actual writeが必要で、空き容量の数値floorはproducer停止条件にしない。unknown effectは公式readbackまで再送しない。

## 削除直前の証拠

- worktreeはfresh remote mainとcached origin/mainが一致しなければ保持する。
- canonical sourceとGit registration pointerは再生成可能だが、trackedでも
  credentials、memory/state、browser identityは保持する。
- 最後のopen-path probeはfresh snapshotを使い、その後identity/status/leaseと
  時間budgetを再検査する。再検査不成立/期限切れは削除しない。
