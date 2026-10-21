/** Codex is the only supported agent brain; every other configured route fails closed. */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { think, runCodexAgentWithTimeout } from '../brain.mjs';

const baseCtx = (over) => ({
  wakeId: 'W1', walletAddress: '0xabc', balanceUsdc: 1.23, tier: 'lean',
  model: 'nvidia/llama-4-maverick', positionsSummary: '', recentSlots: [],
  recentLedgerLines: [], activeSkillSlots: [], skillCatalog: {}, ...over,
});

test('only Codex can be selected as the agent brain', async () => {
  for (const brain of ['claude-p', 'claude', 'proxy', 'glm', 'unknown-brain']) {
    await assert.rejects(
      () => think(baseCtx(), { ANICCA_BRAIN: brain }),
      /codex_only_brain_required/,
      `${brain} must not become an agent inference route`,
    );
  }
});

test('active Codex runner can be stopped and reaped before loop shutdown', async () => {
  const { stopActiveCodexRunners } = await import('../brain.mjs');
  assert.equal(typeof stopActiveCodexRunners, 'function');
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'codex-runner-stop-test-'));
  const pidPath = path.join(home, 'pid');
  const source = `require('node:fs').writeFileSync(${JSON.stringify(pidPath)}, String(process.pid)); setInterval(() => {}, 1000);`;
  const running = runCodexAgentWithTimeout(process.execPath, ['-e', source], {
    env: process.env,
    cwd: home,
    input: '',
    timeoutMs: 30_000,
  });
  try {
    const startedAt = Date.now();
    while (!(await fs.stat(pidPath).catch(() => null))) {
      if (Date.now() - startedAt > 5_000) throw new Error('Codex fixture did not start');
      await delay(10);
    }
    const pid = Number(await fs.readFile(pidPath, 'utf8'));
    await stopActiveCodexRunners();
    await assert.rejects(running, /codex_brain_interrupted/);
    assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
  } finally {
    await stopActiveCodexRunners();
    await running.catch(() => {});
    await fs.rm(home, { recursive: true, force: true });
  }
});

test('Codex brain runner enforces its timeout and returns bounded process output', async () => {
  const result = await runCodexAgentWithTimeout(
    process.execPath,
    ['-e', 'process.stdin.resume(); process.stdin.on("end", () => process.stdout.write("ok"));'],
    { env: process.env, cwd: '/tmp', input: 'prompt', timeoutMs: 1_000 },
  );
  assert.equal(result.code, 0);
  assert.equal(result.stdout, 'ok');
  await assert.rejects(
    () => runCodexAgentWithTimeout(
      process.execPath,
      ['-e', 'setTimeout(() => {}, 60_000)'],
      { env: process.env, cwd: '/tmp', input: '', timeoutMs: 25 },
    ),
    /codex_brain_timeout/,
  );
});
