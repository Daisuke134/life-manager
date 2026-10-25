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
- `.cache/codex-runtimes`, `Library/Caches/camoufox`, and
  `.cache/life-manager/camofox-browser` are executable/dependency installations,
  including between runs. Preserve each root and every descendant even when
  closed; a cache directory name does not authorize deleting an installation.
- worktreeの候補判定・identity再検証・期限切れleaseの扱い・通常remove
  → `disk_cleanup.py` の `HostDiskGovernor._worktree_identity()` と `sweep()` を参照する。
  対象は `WORKTREE_REPOSITORIES`（life-manager-main/.worktrees と anicca-products → anicca-products-worktrees）。
  active lease・保護対象・不明な状態は保持し、force-remove/pruneを行わない。
- iOS Simulator runtimes, images, device data, and dyld caches remain outside
  the cleanup allow-list, including when no device is booted.
- Generic `/private/tmp` directories, including `cfo-*`, remain unknown and
  protected. Scan the active `TMPDIR` plus `/private/tmp` and `/var/tmp` for
  same-user exact Capafy npm caches, old
  `pytest-of-<user>/pytest-<number>` runs, existing exact `slide-pack-*`
  names, and TikTok `slide-pack-tiktok-{workspace,cta,cache}-<6-char-id>`
  names; only same-UID paths older than one hour with a confirmed-closed path
  probe are eligible.
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
- Release retention deletes no release unless `~/Library/LaunchAgents` exists, is
  readable and holds at least one plist. Central release GC protects a release
  named in a plist's `ProgramArguments`, `WorkingDirectory` or any
  `EnvironmentVariables` value, and appends `{ts,path,pid,argv,keep,protected_count}`
  to `~/.local/state/life-manager/release-gc.jsonl` before each removal; if that
  write fails the release stays.
- The 2 GiB recovery value is a cleanup diagnostic only; it does not determine
  cleanup pass/fail and does not pause producers. The release cutter retains its
  existing pre-export physical-capacity guard.
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
- producerの容量admission・残量floor・復旧ownerの例外・停止flag判定
  → `runtime/host/disk_admission.py` を正本として参照する。
  A real write failure remains an operation error,
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
- 自然receiptの`phase_elapsed_ms`は候補発見前・発見・cursor保存・sweep・後処理・receipt保存前合計の所要msを持つ。
  `sweep_start_remaining_ms`と`post_sweep_reserve_ms`を残し、`budget_exhaustion_stages`は時間切れ位置ごとの件数を示す。
  既存の削除判断・`preserved_reasons`・保護・予算を維持し、未計測の原因を推測で確定しない。

## Local installation

```sh
"$HOME/loops/current/skills/self/disk-cleanup/install-launchd.sh"
```

The 60-second `com.anicca.disk-watchdog` is the sole `HostDiskGovernor` owner.
Minute sweeps use fast inventory; when the one-hour inventory interval expires,
the governor runs one bounded full census. It records the attempt first, so an
incomplete census does not repeat heavy probes on every minute wake. If the
attempt marker cannot be persisted, that wake falls back to fast inventory and
records the scheduling error. Missing sizes remain unknown and never expand
deletion authorization. The wrapper tags the watchdog child so its
identity-less observations always use `last-unbound-receipt.json`; the managed
owner's `last-receipt.json` remains reserved for an exact occurrence binding.
The 5-minute `ai.anicca.life-manager-disk-cleanup` performs release/Git/Codex
and managed scratch maintenance, but never invokes the host sweeper. This keeps
it from holding the watchdog's singleton lock and making a minute pass exit 75.
This installer only manages the 60-second recovery label.
Run the installer from a complete main-derived immutable release. It pins
that release's `bin/disk-watchdog.sh` in launchd; the wrapper resolves its own
release and dispatches to that governor. The loaded plist retains its release,
and a later `current` change does not change the loaded watchdog's code. Only
this watchdog acquires the HostDiskGovernor singleton lock and writes host
inventory/cleanup receipts.

The legacy 15-day `life-manager-disk-cleanup-15d` registry row is retained as a
control record but its entrypoint only delegates to the watchdog; it does not
invoke `HostDiskGovernor` or retry the shared cleanup lock. Existing effect
fences remain untouched.

The watchdog adds no second deletion implementation. It uses the existing
`bounded_launchd_output` with the managed `life-manager-disk-cleanup` policy
and log root, including its concurrent writer lock. Native launchd
fallback streams go to `/dev/null`; legacy `watchdog.{out,err}.log` are retained.
The Python dispatcher uses -c without a temporary script. Capture startup or
import failure does not block recovery or change the governor's exit code.
The installer prepares and lints its plist before bootout, so preparation
failure retains the loaded cleanup job. RunAtLoad and the 60-second cadence trigger runs without a manual wake.

Run the tests with:

```sh
python3 -m pytest -q skills/self/disk-cleanup/tests/test_disk_cleanup.py \
  skills/self/disk-cleanup/tests/test_disk_watchdog_dispatcher.py
```

## 共通runner storage契約

管理下stdioは `runtime/host/bounded_output.py` の有限relayで保存する。raw診断は1MiB segment/backup1、structured recordは別の16MiB上限。`storage-policy.json` はowner上限と登録owner数で分割するhost上限を持つ。agent-runnerの既存次wake preflightが、summary完了・host marker・EOF receipt・positive closed proofを満たすrelay診断だけを回収する。親result・usage・JSONLは保持する。terminal保存後も生存relayのscratchは保持し、終了後の既存GCに委ねる。

cleanup実行成功と容量回復は別。receipt identityを現在のcleanup owner/run/occurrence/releaseと照合してCLIへ表示する。inventoryの増加量は観測値であり削除許可ではない。実ENOSPC/EDQUOTだけをtyped failureにし、外部処理前と証明できたscratch allocationだけ既存reconcileへ接続する。fresh cleanup・persisted failure identity・actual writeが必要で、容量admissionの停止条件 → 上記Safety contractを参照する。unknown effectは公式readbackまで再送しない。

## 削除直前の証拠

- worktreeはfresh remote mainとcached origin/mainが一致しなければ保持する。
- canonical sourceとGit registration pointerは再生成可能だが、trackedでも
  credentials、memory/state、browser identityは保持する。
- 最後のopen-path probeはfresh snapshotを使い、その後identity/status/leaseと
  時間budgetを再検査する。再検査不成立/期限切れは削除しない。
