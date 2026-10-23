import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';

const entry = fileURLToPath(new URL('./factory-mcp.mjs', import.meta.url));
const root = fileURLToPath(new URL('../../../', import.meta.url));
const cli = fileURLToPath(new URL('./bin/lm', import.meta.url));
const base = { config: '/fixture/config.json', script: '/fixture/script.txt' };

async function adapter() {
  assert.ok(existsSync(entry), 'Factory MCP entrypoint is missing');
  return import(entry);
}

async function linked(executor) {
  const { createFactoryServer } = await adapter();
  const server = createFactoryServer({ executor });
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'factory-test', version: '1' });
  await Promise.all([server.connect(serverSide), client.connect(clientSide)]);
  return { client, close: async () => { await client.close(); await server.close(); } };
}

test('tools/list exposes only the four strict Factory tools and their effects', async () => {
  const connection = await linked(() => { throw new Error('tools/list must not execute CLI'); });
  try {
    const { tools } = await connection.client.listTools();
    assert.deepEqual(tools.map(tool => tool.name).sort(), [
      'factory_plan', 'factory_publish', 'factory_record_review', 'factory_render',
    ]);
    for (const tool of tools) {
      assert.equal(tool.inputSchema.additionalProperties, false);
      for (const forbidden of ['command', 'executable', 'environment', 'env', 'flags']) {
        assert.equal(Object.hasOwn(tool.inputSchema.properties, forbidden), false);
      }
    }
    assert.match(tools.find(tool => tool.name === 'factory_render').description, /有料|課金/);
    assert.match(tools.find(tool => tool.name === 'factory_publish').description, /投稿|公開/);
    assert.match(tools.find(tool => tool.name === 'factory_record_review').description, /記録/);
  } finally { await connection.close(); }
});

test('fixed argv treats leading dashes and shell syntax as literal values', async () => {
  const { callFactoryTool } = await adapter();
  const calls = [];
  const result = await callFactoryTool('factory_plan', {
    config: '--production', script: '$(touch /must-not-exist); script.txt',
  }, { executor: async args => {
    calls.push(args);
    return { exit_code: 0, signal: null, stdout: '{"status":"planned"}', stderr: '' };
  } });
  assert.deepEqual(calls, [[
    'factory', 'plan', '--config=--production', '--script=$(touch /must-not-exist); script.txt',
  ]]);
  assert.deepEqual(result.structuredContent.result, { status: 'planned' });
  assert.equal(result.isError, false);
});

test('unknown fields, operations, empty strings and NUL never reach the child', async () => {
  const { callFactoryTool } = await adapter();
  const invalid = [
    ['factory_plan', { ...base, executable: 'sh' }],
    ['factory_plan', { ...base, env: { HOME: '/other-user' } }],
    ['factory_plan', { ...base, config: '' }],
    ['factory_plan', { ...base, script: '  ' }],
    ['factory_plan', { ...base, script: 'bad\0path' }],
    ['factory_publish', { ...base, publication: '/p.json', run_id: 'run', operation: 'approve' }],
    ['factory_publish', { ...base, publication: '/p.json', run_id: 'run', operation: 'upload', production: 'true' }],
    ['factory_record_review', { approval_id: 'review-only' }],
    ['unknown_tool', base],
    ['constructor', base],
    ['toString', base],
  ];
  for (const [name, input] of invalid) {
    const result = await callFactoryTool(name, input, { executor: () => assert.fail('invalid input executed CLI') });
    assert.equal(result.isError, true, name);
    assert.equal(result.structuredContent.exit_code, null);
  }
  const connection = await linked(() => assert.fail('unknown field passed SDK validation'));
  try {
    const result = await connection.client.callTool({ name: 'factory_plan', arguments: { ...base, shell: true } });
    assert.equal(result.isError, true);
  } finally { await connection.close(); }
});

test('render and publish preserve CLI domain JSON and nonzero exit without new decisions', async () => {
  const { callFactoryTool } = await adapter();
  const domain = { state: 'rendered', wallet_cost: null, cost_reconciliation_required: true };
  for (const exit_code of [0, 1]) {
    const result = await callFactoryTool('factory_render', { ...base, run_id: 'same-run' }, {
      executor: async args => {
        assert.deepEqual(args, ['factory', 'render', '--config=/fixture/config.json', '--script=/fixture/script.txt', '--run-id=same-run']);
        return { exit_code, signal: null, stdout: JSON.stringify(domain), stderr: '' };
      },
    });
    assert.deepEqual(result.structuredContent.result, domain);
    assert.equal(result.structuredContent.exit_code, exit_code);
    assert.equal(result.isError, exit_code !== 0);
  }
  const result = await callFactoryTool('factory_publish', {
    ...base, publication: '/p.json', run_id: 'same-run', operation: 'promote', production: true,
  }, { executor: async args => {
    assert.deepEqual(args, ['factory', 'publish', '--config=/fixture/config.json', '--script=/fixture/script.txt',
      '--publication=/p.json', '--run-id=same-run', '--operation=promote', '--production']);
    return { exit_code: 0, signal: null, stdout: '{"state":"accepted","provider_status":"scheduled"}', stderr: '' };
  } });
  assert.deepEqual(result.structuredContent.result, { state: 'accepted', provider_status: 'scheduled' });
});

test('record_review forwards every existing required approval flag without inventing a review', async () => {
  const { callFactoryTool } = await adapter();
  const input = { approval_id: 'visual.accepted.test', asset: '/asset.mp4', product: 'factory.product.test',
    account: 'factory.account.test', owner_confirmation: 'agent reviewer', confirmation_ref: '/review.json',
    approved_at: '2026-10-23T00:00:00Z', ledger: '/fixture/approvals.jsonl' };
  const result = await callFactoryTool('factory_record_review', input, { executor: async args => {
    assert.deepEqual(args, ['publish', 'approve', '--approval-id=visual.accepted.test', '--asset=/asset.mp4',
      '--product=factory.product.test', '--account=factory.account.test', '--owner-confirmation=agent reviewer',
      '--confirmation-ref=/review.json', '--approved-at=2026-10-23T00:00:00Z', '--ledger=/fixture/approvals.jsonl']);
    return { exit_code: 0, signal: null, stdout: '{"approval_id":"visual.accepted.test"}', stderr: '' };
  } });
  assert.equal(result.isError, false);
});

test('stderr JSON, malformed output and executor failure stay errors with no retry', async () => {
  const { callFactoryTool } = await adapter();
  for (const fixture of [
    { exit_code: 1, signal: null, stdout: '', stderr: '{"status":"failed","error":"explicit --production flag required"}' },
    { exit_code: 0, signal: null, stdout: 'not JSON', stderr: 'diagnostic' },
  ]) {
    let calls = 0;
    const result = await callFactoryTool('factory_plan', base, { executor: async () => { calls += 1; return fixture; } });
    assert.equal(calls, 1);
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.exit_code, fixture.exit_code);
    assert.equal(result.structuredContent.stdout, fixture.stdout);
    assert.equal(result.structuredContent.stderr, fixture.stderr);
    if (fixture.exit_code) assert.equal(result.structuredContent.result.status, 'failed');
    else assert.equal(result.structuredContent.transport_error, 'invalid_json');
  }
  const failed = await callFactoryTool('factory_plan', base, { executor: async () => { throw new Error('transport failed'); } });
  assert.equal(failed.isError, true);
  assert.equal(failed.structuredContent.exit_code, null);
});

test('timeout and output limit reclaim the owned group while an unrelated child survives', async () => {
  const { runCli } = await adapter();
  const unrelated = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
  try {
    for (const mode of ['timeout', 'output_limit']) {
      let owned;
      const result = await runCli(['factory', 'plan'], {
        timeoutMs: 200, maxOutputBytes: 64, killGraceMs: 25,
        spawnChild: (command, args, options) => {
          assert.equal(command, 'python3');
          assert.deepEqual(args, [cli, 'factory', 'plan']);
          assert.equal(options.shell, false);
          assert.equal(options.detached, true);
          owned = spawn(process.execPath, ['-e', mode === 'timeout'
            ? 'process.on("SIGTERM", () => {}); setInterval(() => {}, 1000)'
            : 'process.on("SIGTERM", () => {}); process.stdout.write("x".repeat(4096)); setInterval(() => {}, 1000)'], options);
          return owned;
        },
      });
      assert.equal(result.transport_error, mode);
      assert.ok(Buffer.byteLength(result.stdout) <= 64);
      assert.ok(Buffer.byteLength(result.stderr) <= 64);
      assert.throws(() => process.kill(owned.pid, 0), /ESRCH/);
      assert.doesNotThrow(() => process.kill(unrelated.pid, 0));
    }
  } finally { unrelated.kill('SIGKILL'); }
});

test('request cancellation terminates only its child and does not retry', async () => {
  const { runCli } = await adapter();
  const controller = new AbortController();
  let calls = 0;
  const promise = runCli(['factory', 'plan'], { signal: controller.signal, timeoutMs: 2000, killGraceMs: 25,
    spawnChild: (_command, _args, options) => {
      calls += 1;
      const child = spawn(process.execPath, ['-e', 'process.stdout.write("ready"); setInterval(() => {}, 1000)'], options);
      child.stdout.once('data', () => controller.abort());
      return child;
    },
  });
  const result = await promise;
  assert.equal(result.transport_error, 'aborted');
  assert.equal(calls, 1);
});

test('server shutdown reclaims its child group after the parent exits first', async () => {
  const { runCli, stopOwnedChildren } = await adapter();
  let ready;
  const started = new Promise(resolve => { ready = resolve; });
  let descendant;
  const resultPromise = runCli(['factory', 'plan'], { timeoutMs: 3000, killGraceMs: 100,
    spawnChild: (_command, _args, options) => {
      const child = spawn(process.execPath, ['-e', `
        const { spawn } = require('node:child_process');
        const grandchild = spawn(process.execPath, ['-e', 'process.on("SIGTERM", () => {}); setInterval(() => {}, 1000)'], { stdio: 'ignore' });
        process.stdout.write(String(grandchild.pid));
        setInterval(() => {}, 1000);
      `], options);
      child.stdout.once('data', bytes => { descendant = Number(bytes.toString()); ready(); });
      return child;
    },
  });
  try {
    await started;
    await stopOwnedChildren();
    const result = await resultPromise;
    assert.equal(result.transport_error, 'server_closed');
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try { process.kill(descendant, 0); }
      catch (error) { assert.equal(error.code, 'ESRCH'); return; }
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    assert.fail('owned descendant survived shutdown');
  } finally {
    try { process.kill(descendant, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
  }
});

test('normal CLI exit reclaims descendants before returning the unchanged success result', async () => {
  const { callFactoryTool, runCli } = await adapter();
  const unrelated = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
  let owned;
  try {
    const result = await callFactoryTool('factory_plan', base, { executor: args => runCli(args, {
      timeoutMs: 3000, killGraceMs: 100,
      spawnChild: (_command, _args, options) => {
        owned = spawn(process.execPath, ['-e', `
          const { spawn } = require('node:child_process');
          const grandchild = spawn(process.execPath, ['-e', 'process.on("SIGTERM", () => {}); process.send("ready"); setInterval(() => {}, 1000)'], { stdio: ['ignore', 'ignore', 'ignore', 'ipc'] });
          grandchild.once('message', () => {
            grandchild.disconnect();
            grandchild.unref();
            process.stdout.write(JSON.stringify({ descendant: grandchild.pid }));
          });
        `], options);
        return owned;
      },
    }) });
    const { descendant } = result.structuredContent.result;
    assert.equal(result.isError, false);
    assert.deepEqual(result.structuredContent, { exit_code: 0, signal: null,
      result: { descendant }, stdout: JSON.stringify({ descendant }), stderr: '' });
    let survived = true;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try { process.kill(descendant, 0); }
      catch (error) { assert.equal(error.code, 'ESRCH'); survived = false; break; }
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    assert.equal(survived, false, 'owned descendant survived normal CLI exit');
    assert.doesNotThrow(() => process.kill(unrelated.pid, 0));
  } finally {
    if (owned?.pid) {
      try { process.kill(-owned.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
    unrelated.kill('SIGKILL');
  }
});

test('real stdio lists tools, plans without communication, and preserves CLI rejection', async () => {
  await adapter();
  const home = await mkdtemp(path.join(tmpdir(), 'factory-mcp-test-'));
  const config = path.join(home, 'config.json');
  const script = path.join(home, 'script.txt');
  const publication = path.join(home, 'publication.json');
  const stateRoot = path.join(home, 'never-created');
  const fixture = JSON.parse(await readFile(new URL('./examples/ai-monk-factory.config.example.json', import.meta.url), 'utf8'));
  fixture.state_root = stateRoot;
  await writeFile(config, JSON.stringify(fixture));
  await writeFile(script, 'Breathe, and notice what changes.');
  await writeFile(publication, '{}');
  // Homebrew's sitecustomize repairs its package paths; keep it before adding test guards.
  const baseline = spawnSync('python3', ['-c', 'import importlib.util; s=importlib.util.find_spec("sitecustomize"); print(s.origin if s else "")'], {
    env: { PATH: process.env.PATH, HOME: home, PYTHONDONTWRITEBYTECODE: '1' }, encoding: 'utf8',
  });
  assert.equal(baseline.status, 0, baseline.stderr);
  const bootstrap = baseline.stdout.trim()
    ? `import runpy\nrunpy.run_path(${JSON.stringify(baseline.stdout.trim())})\n` : '';
  await writeFile(path.join(home, 'sitecustomize.py'), `${bootstrap}import socket, subprocess, sqlite3\ndef forbidden(*a, **k):\n    raise AssertionError("network/subprocess/DB is forbidden in offline plan")\nsocket.socket.connect = forbidden\nsocket.socket.connect_ex = forbidden\nsocket.getaddrinfo = forbidden\nsubprocess.run = forbidden\nsqlite3.connect = forbidden\n`);
  const transport = new StdioClientTransport({ command: process.execPath, args: [entry], cwd: root,
    env: { PATH: process.env.PATH, HOME: home, PYTHONPATH: home, PYTHONDONTWRITEBYTECODE: '1' }, stderr: 'pipe' });
  let protocolErrors = '';
  transport.stderr.on('data', data => { protocolErrors += data; });
  const client = new Client({ name: 'factory-stdio-test', version: '1' });
  try {
    await client.connect(transport);
    assert.equal((await client.listTools()).tools.length, 4);
    const planned = await client.callTool({ name: 'factory_plan', arguments: { config, script } });
    assert.equal(planned.isError, false, JSON.stringify(planned.structuredContent));
    assert.equal(planned.structuredContent.exit_code, 0);
    assert.equal(planned.structuredContent.result.status, 'planned');
    assert.equal(planned.structuredContent.result.provider_calls, 0);
    assert.deepEqual(planned.structuredContent.result.external_effects, []);
    assert.equal(existsSync(stateRoot), false);
    const rejected = await client.callTool({ name: 'factory_publish', arguments: {
      config, script, publication, run_id: 'first-video', operation: 'upload',
    } });
    assert.equal(rejected.isError, true);
    assert.equal(rejected.structuredContent.exit_code, 1);
    assert.match(rejected.structuredContent.result.error, /explicit --production flag required/);
    assert.equal(existsSync(stateRoot), false);
    assert.equal(protocolErrors, '');
  } finally { await client.close(); await rm(home, { recursive: true, force: true }); }
});
