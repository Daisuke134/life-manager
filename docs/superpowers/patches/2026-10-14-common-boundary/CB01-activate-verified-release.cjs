// One-time operation proposal. Run only from the verified, main-derived ALL release.
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { execFileSync } = require('node:child_process');

const [destination, repository, expectedSha, guardLedger] = process.argv.slice(2);
if (!destination || !repository || !/^[a-f0-9]{40}$/.test(expectedSha || '') || !guardLedger) {
  throw new Error('exact_release_repo_sha_and_live_guard_ledger_required');
}
const release = fs.realpathSync(destination);
const loops = path.dirname(path.dirname(release));
const current = path.join(loops, 'current');
const hold = path.join(loops, '.promotion-hold');
const cutLock = path.join(loops, '.release-cut.lock');
const descriptor = JSON.parse(fs.readFileSync(path.join(release, 'RELEASE.json'), 'utf8'));
if (descriptor.sha !== expectedSha || descriptor.release_paths !== 'ALL'
    || descriptor.provenance !== 'ancestor-of-origin-main'
    || (fs.statSync(release).mode & 0o222) !== 0) {
  throw new Error('verified_all_release_required');
}
execFileSync('git', ['-C', repository, 'merge-base', '--is-ancestor', expectedSha, 'origin/main'],
             { timeout: 5000, stdio: 'pipe' });
execFileSync(path.join(release, 'bin/launchctl-safe'), ['preflight'],
             { timeout: 10000, stdio: 'pipe' });
const guard = require(path.join(release, 'apps/life-manager/lib/dev-merge-guard.js'));
const guardLock = guard.guardLockPath(guardLedger);
fs.mkdirSync(path.dirname(guardLock), { recursive: true, mode: 0o700 });
let fd;
let guardIdentity;
let cutIdentity;
const guardClaim = `${guardLock}.cb01-${process.pid}-${randomUUID()}`;
try {
  // Publish complete metadata atomically; an empty lock is stealable by legacy readers.
  fd = fs.openSync(guardClaim, 'wx', 0o600);
  guardIdentity = fs.fstatSync(fd);
  const now = new Date();
  fs.writeFileSync(fd, JSON.stringify({
    pid: process.pid, acquired_at: now.toISOString(), acquired_at_ms: now.getTime(),
  }));
  fs.fsyncSync(fd);
  fs.linkSync(guardClaim, guardLock); // EEXIST leaves the other owner's lock intact.
  fs.unlinkSync(guardClaim);
  fs.mkdirSync(cutLock, { mode: 0o700 });
  cutIdentity = fs.statSync(cutLock);
  fs.writeFileSync(path.join(cutLock, 'pid'), `${process.pid}\n`, { mode: 0o600 });
  // Any hold, including an unresolved expired/malformed hold, belongs to its owner.
  if (fs.existsSync(hold)) throw new Error('promotion_hold_present');
  const previous = JSON.parse(fs.readFileSync(path.join(current, 'RELEASE.json'), 'utf8'));
  execFileSync('git', ['-C', repository, 'merge-base', '--is-ancestor', previous.sha, expectedSha],
               { timeout: 5000, stdio: 'pipe' });
  const python = descriptor.runtime_python;
  execFileSync(python, ['-B', '-c',
    'import sys; from pathlib import Path; from runtime.host.resource_admission import durable_protocol_version; from runtime.loop.lm_loop import activate_current; activate_current(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), protocol_reader=durable_protocol_version)',
    current, release, path.join(loops, '.apply.lock')], {
      cwd: release, env: { ...process.env, PYTHONPATH: release }, timeout: 30000, stdio: 'pipe',
    });
  if (fs.realpathSync(current) !== release) throw new Error('activation_readback_mismatch');
  process.stdout.write(JSON.stringify({ status: 'verified_current', sha: expectedSha }) + '\n');
} finally {
  // Remove only this operation's exact lock identities. Unknown/replaced locks remain.
  if (cutIdentity) {
    try {
      const info = fs.statSync(cutLock);
      if (info.dev === cutIdentity.dev && info.ino === cutIdentity.ino) {
        const entries = fs.readdirSync(cutLock);
        if (entries.length === 0) fs.rmdirSync(cutLock);
        else if (entries.length === 1 && entries[0] === 'pid'
                 && fs.readFileSync(path.join(cutLock, 'pid'), 'utf8').trim() === String(process.pid)) {
          fs.unlinkSync(path.join(cutLock, 'pid'));
          fs.rmdirSync(cutLock);
        }
      }
    } catch {}
  }
  if (fd !== undefined) {
    try {
      const info = fs.lstatSync(guardClaim);
      if (info.dev === guardIdentity.dev && info.ino === guardIdentity.ino) fs.unlinkSync(guardClaim);
    } catch {}
    try {
      const info = fs.lstatSync(guardLock);
      const owner = JSON.parse(fs.readFileSync(guardLock, 'utf8'));
      if (info.dev === guardIdentity.dev && info.ino === guardIdentity.ino
          && owner.pid === process.pid) fs.unlinkSync(guardLock);
    } catch {}
    fs.closeSync(fd);
  }
}
