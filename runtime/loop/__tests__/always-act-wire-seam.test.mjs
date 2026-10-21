// The Codex prompt must carry the bounded slot menu selected by the always-act state machine.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { think } from '../brain.mjs';
import {
  codexPromptOffersSleep,
  mockCodexRunnerEnv,
  offeredCodexSlots,
} from './helpers/mock-codex-runner-env.mjs';

function startMockBrainServer() {
  const server = http.createServer((request, response) => {
    if (request.method !== 'POST' || !request.url?.endsWith('/chat/completions')) {
      response.writeHead(404);
      response.end();
      return;
    }
    request.resume();
    request.on('end', () => {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({
        choices: [{ message: { role: 'assistant', content: 'idle' } }],
      }));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, url: `http://127.0.0.1:${server.address().port}/v1` });
    });
  });
}

function baseCtx(overrides = {}) {
  return {
    walletAddress: 'FakeWallet111',
    balanceUsdc: 42,
    positionsSummary: '',
    tier: 'lean',
    model: 'auto',
    wakeId: 'w-wire-seam-test',
    recentLedgerLines: [],
    activeSkillSlots: ['economy/gig', 'earn/clip', 'earn/sol-trade'],
    skillCatalog: {},
    genesisPrompt: '',
    avoidSlot: null,
    recentSlots: [],
    earnSteer: '',
    reserveUsdc: 5,
    ...overrides,
  };
}

async function codexPromptFor(ctx) {
  const { server, url } = await startMockBrainServer();
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'lm-codex-prompt-test-'));
  const capturePath = path.join(home, 'prompt.txt');
  const fixtureEnv = mockCodexRunnerEnv({ home, baseUrl: url, capturePromptPath: capturePath });
  const keys = ['CODEX_AGENT_RUNNER', 'CODEX_AGENT_CONFIG', 'CODEX_BRAIN_PYTHON'];
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  Object.assign(process.env, fixtureEnv);
  try {
    const decision = await think(ctx, { ANICCA_HOME: home, ANICCA_BRAIN: 'codex' });
    const prompt = JSON.parse((await fs.readFile(capturePath, 'utf8')).trim().split('\n').at(-1));
    return { prompt, decision };
  } finally {
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key];
      else process.env[key] = previous[key];
    }
    server.close();
    await fs.rm(home, { recursive: true, force: true });
  }
}

test('always-act Codex prompt contains only its narrowed menu and withholds sleep', async () => {
  const { prompt, decision } = await codexPromptFor(baseCtx({
    alwaysActEngaged: true,
    alwaysActMenu: ['economy/gig', 'earn/clip'],
  }));
  assert.deepEqual(offeredCodexSlots(prompt), ['economy/gig', 'earn/clip']);
  assert.equal(codexPromptOffersSleep(prompt), false);
  assert.deepEqual(decision.tool_calls, [], 'an always-act no-tool-call response must reach the bounded reprompt state machine');
});

test('ordinary Codex prompt keeps active slots and the sleep option', async () => {
  const { prompt, decision } = await codexPromptFor(baseCtx());
  assert.deepEqual(offeredCodexSlots(prompt), ['economy/gig', 'earn/clip', 'earn/sol-trade']);
  assert.equal(codexPromptOffersSleep(prompt), true);
  assert.equal(decision.tool_calls[0].function.name, 'sleep');
});

test('explicitly disengaged Codex prompt ignores an always-act menu', async () => {
  const ctx = baseCtx({ alwaysActEngaged: false, alwaysActMenu: ['economy/gig'] });
  const { prompt, decision } = await codexPromptFor(ctx);
  assert.deepEqual(offeredCodexSlots(prompt), ['economy/gig', 'earn/clip', 'earn/sol-trade']);
  assert.equal(codexPromptOffersSleep(prompt), true);
  assert.equal(decision.tool_calls[0].function.name, 'sleep');
});
