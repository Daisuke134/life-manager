import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm, symlink } from 'node:fs/promises';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { request as httpRequest } from 'node:http';

const runtime = await import('./server.mjs').catch(() => ({}));
const execFileAsync = promisify(execFile);
const project = { project_id: 'monk-demo', language: 'en', avatar_id: 'avatar_123', voice_id: 'voice_123', platform: 'tiktok',
  integration_id: 'integration-1', native_handle: 'monk.demo', product_name: 'Attention guide', product_url: 'https://example.test/guide',
  brief: 'Explain patient attention.', script: 'Attention is a practice. Pause and begin again.', cta: 'Read the guide' };
const receipt = result => ({ isError: false, structuredContent: { exit_code: 0, signal: null, result, stdout: JSON.stringify(result), stderr: '' }, content: [] });

async function fixture(t, options = {}) {
  assert.equal(typeof runtime.createFactoryWebServer, 'function', 'localhost runtime is missing');
  const root = await mkdtemp(join(tmpdir(), 'factory-web-'));
  const uiRoot = join(root, 'ui'); await mkdir(uiRoot);
  await writeFile(join(uiRoot, 'index.html'), '<meta name="factory-token" content="__FACTORY_TOKEN__">');
  const server = await runtime.createFactoryWebServer({ root: join(root, 'state'), uiRoot, token: 'test-token', ...options });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { await server.shutdown(); await rm(root, { recursive: true, force: true }); });
  const url = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { body, headers = {}, method = body === undefined ? 'GET' : 'POST' } = {}) => fetch(url + path, {
    method, headers: { 'x-factory-token': 'test-token', ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...headers },
    ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
  });
  return { root, server, url, request };
}
async function save(request, value = project) {
  const response = await request('/api/projects', { body: { project: value } });
  assert.equal(response.status, 200); return (await response.json()).project;
}
async function terminal(request, id) {
  for (let n = 0; n < 600; n++) {
    const r = (await (await request('/api/runs/' + id)).json()).run;
    if (!['queued', 'running'].includes(r.state)) return r;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  assert.fail('finite run did not terminate');
}

test('HTTP requires exact Host/Origin and action token, bounded JSON, and a known project schema', async t => {
  const { request, url } = await fixture(t);
  assert.equal((await request('/api/projects', { headers: { 'x-factory-token': '' } })).status, 403);
  assert.equal((await request('/api/projects', { headers: { origin: 'https://hostile.test' } })).status, 403);
  const hostile = await new Promise((resolve, reject) => {
    const req = httpRequest(url + '/api/projects', { headers: { host: 'hostile.test', 'x-factory-token': 'test-token' } }, response => {
      response.resume(); resolve(response.statusCode);
    }); req.on('error', reject); req.end();
  });
  assert.equal(hostile, 403);
  assert.equal((await request('/api/projects', { headers: { origin: url } })).status, 200);
  assert.equal((await request('/api/projects', { body: 'x'.repeat(65537) })).status, 413);
  assert.equal((await request('/api/projects', { body: { project: { ...project, state_root: '/tmp/escape' } } })).status, 400);
  await save(request);
  assert.equal((await (await request('/api/projects')).json()).projects[0].project_id, 'monk-demo');
  assert.equal((await request('/api/runs', { body: { project_id: '../escape', mode: 'plan' } })).status, 400);
});

test('runs snapshot project and freeze the first script/caption; plan cannot render or publish', async t => {
  let resume;
  const waiting = new Promise(resolve => { resume = resolve; });
  const calls = [];
  const { request } = await fixture(t, {
    factoryExecutor: async (name, args) => { calls.push({ name, args }); return receipt({ status: 'planned', provider_calls: 0, external_effects: [] }); },
    agentExecutor: async context => {
      await waiting;
      const denied = await context.invokeTool('factory_render', {}); assert.equal(denied.isError, true);
      const first = await context.invokeTool('factory_plan', {}); assert.equal(first.isError, false);
      await writeFile(join(context.workspace, 'script.txt'), 'A changed script must not change this run.');
      await context.invokeTool('factory_plan', {});
      return { exit_code: 0 };
    },
  });
  await save(request);
  const start = await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } });
  assert.equal(start.status, 202); const run = (await start.json()).run;
  assert.equal((await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).status, 409);
  await save(request, { ...project, brief: 'Edited project', script: 'Edited project script.' });
  resume(); const done = await terminal(request, run.run_id);
  assert.equal(done.state, 'planned'); assert.equal(done.exit_code, 0);
  assert.equal(calls.length, 2);
  assert.equal(await readFile(calls[0].args.script, 'utf8'), project.script);
  assert.equal(await readFile(calls[1].args.script, 'utf8'), project.script);
  const config = JSON.parse(await readFile(calls[0].args.config, 'utf8'));
  assert.equal(config.project_id, 'monk-demo');
  assert.ok(config.product.url.includes('utm_campaign=factory_'));
});

test('nonzero unknown costs remain failures and restart interrupts without rerunning the agent', async t => {
  let invocations = 0;
  const { request, server, root } = await fixture(t, {
    factoryExecutor: async name => name === 'factory_plan' ? receipt({ status: 'planned', provider_calls: 0, external_effects: [] })
      : receipt({ state: 'rendered', wallet_cost: null, cost_reconciliation_required: true }),
    agentExecutor: async context => {
      invocations++;
      await context.invokeTool('factory_plan', {});
      await context.invokeTool('factory_render', {});
      return { exit_code: 1 };
    },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'render' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(done.exit_code, 1); assert.equal(done.state, 'cost_reconciliation_required');
  assert.equal(done.tool_results.at(-1).result.structuredContent.result.wallet_cost, null);
  await server.shutdown();
  const restarted = await runtime.createFactoryWebServer({ root: join(root, 'state'), token: 'new-token', agentExecutor: () => { invocations++; } });
  t.after(() => restarted.shutdown());
  assert.equal(invocations, 1);
  const saved = JSON.parse(await readFile(join(root, 'state', 'runs', run.run_id, 'run.json'), 'utf8'));
  assert.equal(saved.state, 'cost_reconciliation_required');
});

test('symlinked project paths are refused and only hash-matched run assets are served', async t => {
  const bytes = Buffer.from('finite video fixture');
  const { request, root } = await fixture(t, {
    factoryExecutor: async (name, args) => {
      if (name === 'factory_plan') return receipt({ status: 'planned', provider_calls: 0 });
      const config = JSON.parse(await readFile(args.config, 'utf8'));
      const output = join(config.state_root, 'renders', config.project_id + '.' + args.run_id + '.mp4');
      await mkdir(join(config.state_root, 'renders'), { recursive: true }); await writeFile(output, bytes);
      return receipt({ state: 'rendered', output, sha256: createHash('sha256').update(bytes).digest('hex'), wallet_cost: { currency: 'USD', amount: 1 } });
    },
    agentExecutor: async context => { await context.invokeTool('factory_plan', {}); await context.invokeTool('factory_render', {}); return { exit_code: 0 }; },
  });
  await symlink(join(root, 'external.json'), join(root, 'state', 'projects', 'unsafe.json'));
  assert.equal((await request('/api/projects', { body: { project: { ...project, project_id: 'unsafe' } } })).status, 400);
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'render' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(done.state, 'rendered');
  const video = await request(done.artifact_url); assert.equal(video.status, 200);
  assert.deepEqual(Buffer.from(await video.arrayBuffer()), bytes);
  const output = done.tool_results.at(-1).result.structuredContent.result.output;
  await writeFile(output, 'tampered');
  assert.equal((await request(done.artifact_url)).status, 409);
});

test('render requires a frozen offline plan and publish arguments cannot select paths or production', async t => {
  const reached = [];
  const { request } = await fixture(t, {
    factoryExecutor: async (name, args) => { reached.push({ name, args }); return receipt({ status: 'planned', provider_calls: 0 }); },
    agentExecutor: async context => {
      assert.equal((await context.invokeTool('factory_render', {})).isError, true);
      await context.invokeTool('factory_plan', {});
      assert.equal((await context.invokeTool('factory_publish', { operation: 'promote' })).isError, true);
      assert.equal((await context.invokeTool('factory_render', { config: '/other/config', production: true })).isError, true);
      await context.invokeTool('factory_render', {});
      return { exit_code: 0 };
    },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'render' } })).json()).run;
  await terminal(request, run.run_id);
  assert.deepEqual(reached.map(row => row.name), ['factory_plan', 'factory_render']);
  assert.equal(reached[1].args.run_id, run.run_id);
  assert.equal(reached[1].args.production, undefined);
});

test('finite agent inherits model choice, bounds output, and ignores a success claim without tool evidence', async t => {
  let captured;
  const { request } = await fixture(t, {
    agentExecutor: context => runtime.runFiniteAgent(context, { maxOutputBytes: 4096, mcpInventory: async () => ['unwanted'], spawnChild: (command, args, options) => {
      captured = { command, args, options };
      return spawn(process.execPath, ['-e', 'process.stdout.write("I published and earned revenue.");'], options);
    } }),
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(captured.command, 'codex');
  assert.equal(captured.options.shell, false);
  assert.ok(!captured.args.some(arg => /^(?:-m|--model|--provider)$|model_provider|model_reasoning_effort/.test(arg)));
  assert.ok(captured.args.some(arg => arg.startsWith('mcp_servers={factory=')), 'other inherited MCP servers must not bypass run mode');
  assert.ok(captured.args.some(arg => arg.includes('"unwanted"={enabled=false}')), 'existing MCP servers must be explicitly disabled');
  assert.ok(captured.args.includes('sandbox_workspace_write.writable_roots=[]'), 'inherited writable roots must not expose control evidence');
  for (const feature of ['plugins', 'apps', 'remote_plugin', 'enable_mcp_apps', 'codex_apps_mcp_2026_07_28']) {
    assert.ok(captured.args.some((arg, index) => arg === '--disable' && captured.args[index + 1] === feature), 'inherited plugin/app execution must be disabled');
  }
  assert.equal(done.state, 'failed');
  assert.equal(done.artifact_url, null);
});

test('finite agent output is bounded and timeout reclaims only its process group', async t => {
  for (const kind of ['output', 'timeout']) {
    const { request } = await fixture(t, {
      agentExecutor: context => runtime.runFiniteAgent(context, { maxOutputBytes: 64, timeoutMs: kind === 'timeout' ? 50 : 2000,
        mcpInventory: async () => [], spawnChild: (command, args, options) => spawn(process.execPath, ['-e', kind === 'output'
          ? 'process.stdout.write("x".repeat(4096));setInterval(()=>{},1000);' : 'setInterval(()=>{},1000);'], options) }),
    });
    await save(request);
    const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).json()).run;
    const done = await terminal(request, run.run_id);
    assert.equal(done.state, 'failed');
    assert.match(done.summary, kind === 'output' ? /output_limit/ : /timeout/);
  }
});

test('publish binds approval to the actual asset and prepare metadata, with real frame references and an AI reviewer', async t => {
  let reviewArguments, reviewEvidence, promoted;
  const video = Buffer.from('run-owned video');
  const frame = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1QAAAAASUVORK5CYII=', 'base64');
  const { request } = await fixture(t, {
    factoryExecutor: async (name, args) => {
      if (name === 'factory_plan') return receipt({ status: 'planned', provider_calls: 0 });
      if (name === 'factory_render') {
        const config = JSON.parse(await readFile(args.config, 'utf8'));
        const output = join(config.state_root, 'renders', config.project_id + '.' + args.run_id + '.mp4');
        await mkdir(join(config.state_root, 'renders')); await writeFile(output, video);
        return receipt({ state: 'rendered', output, sha256: createHash('sha256').update(video).digest('hex'), wallet_cost: { currency: 'USD', amount: 1 } });
      }
      if (name === 'factory_publish') {
        if (args.operation === 'promote') promoted = args;
        return receipt({ state: args.operation === 'promote' ? 'PUBLISHED' : 'prepared', account_id: 'factory-account', product_id: 'factory-product', approvals_path: '/fixed/host/factory/visual-approvals.jsonl' });
      }
      reviewArguments = args; reviewEvidence = JSON.parse(await readFile(args.confirmation_ref, 'utf8'));
      return receipt({ created: true, approval: { status: 'accepted', owner_confirmation: args.owner_confirmation } });
    },
    agentExecutor: async context => {
      await context.invokeTool('factory_plan', {}); await context.invokeTool('factory_render', {});
      await context.invokeTool('factory_publish', { operation: 'prepare' });
      assert.equal((await context.invokeTool('factory_record_review', { notes: 'A claim with no actual image', frame_evidence: ['missing.png'] })).isError, true);
      await writeFile(join(context.workspace, 'frame.png'), frame);
      const approval = await context.invokeTool('factory_record_review', { notes: 'I inspected the produced frame and checked its visible layout.', frame_evidence: ['frame.png'] });
      assert.equal(approval.isError, false);
      await context.invokeTool('factory_publish', { operation: 'promote' });
      return { exit_code: 0 };
    },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'publish' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(reviewArguments.account, 'factory-account'); assert.equal(reviewArguments.product, 'factory-product');
  assert.equal(reviewArguments.ledger, '/fixed/host/factory/visual-approvals.jsonl');
  assert.equal(reviewArguments.owner_confirmation, 'AI agent (Codex)');
  assert.equal(reviewEvidence.frames[0].sha256, createHash('sha256').update(frame).digest('hex'));
  assert.equal(promoted.production, true); assert.equal(promoted.run_id, run.run_id);
  assert.equal(done.state, 'native_verification_required');
});

test('restart preserves an interrupted run and never starts an agent from saved running state', async t => {
  const { server, root } = await fixture(t);
  await server.shutdown();
  const location = join(root, 'state', 'runs', 'run-interrupted');
  await mkdir(join(location, 'control'), { recursive: true });
  await writeFile(join(location, 'run.json'), JSON.stringify({ run_id: 'run-interrupted', project_id: 'monk-demo', mode: 'publish', state: 'running',
    exit_code: null, created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z', tool_results: [], summary: null, artifact_url: null }));
  let starts = 0;
  const restarted = await runtime.createFactoryWebServer({ root: join(root, 'state'), token: 'test-token', agentExecutor: () => { starts++; } });
  await restarted.shutdown();
  const saved = JSON.parse(await readFile(join(location, 'run.json'), 'utf8'));
  assert.equal(saved.state, 'interrupted'); assert.equal(saved.exit_code, null); assert.equal(starts, 0);
});

test('real Python CLI receives server-frozen inputs and produces an offline zero-effect plan', async t => {
  const { request } = await fixture(t, {
    factoryExecutor: async (name, args) => {
      assert.equal(name, 'factory_plan');
      const { stdout } = await execFileAsync('python3', [new URL('../bin/lm', import.meta.url).pathname, 'factory', 'plan', '--config', args.config, '--script', args.script],
        { encoding: 'utf8', env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: '1' } });
      return receipt(JSON.parse(stdout));
    },
    agentExecutor: async context => { const result = await context.invokeTool('factory_plan', {}); return { exit_code: result.isError ? 1 : 0 }; },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(done.state, 'planned');
  const planned = done.tool_results[0].result.structuredContent.result;
  assert.equal(planned.provider_calls, 0); assert.deepEqual(planned.external_effects, []);
  assert.equal(planned.render_request.script, project.script);
});

let sdkPresent = false;
try { await import('@modelcontextprotocol/sdk/client/index.js'); sdkPresent = true; } catch {}
test('real stdio bridge lists only plan and calls the existing Factory zero-effect CLI', { skip: !sdkPresent && !process.env.CI }, async t => {
  // CI installs the existing root dependencies and must exercise this boundary.
  const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js');
  const { request } = await fixture(t, {
    agentExecutor: async context => {
      const client = new Client({ name: 'factory-web-stdio-acceptance', version: '1' });
      try {
        await client.connect(new StdioClientTransport({ command: process.execPath,
          args: [new URL('./agent-mcp.mjs', import.meta.url).pathname, '--run-root', context.runRoot], stderr: 'pipe' }));
        assert.deepEqual((await client.listTools()).tools.map(tool => tool.name), ['factory_plan']);
        const planned = await client.callTool({ name: 'factory_plan', arguments: {} });
        assert.equal(planned.isError, false);
        assert.equal(planned.structuredContent.result.provider_calls, 0);
        assert.deepEqual(planned.structuredContent.result.external_effects, []);
        return { exit_code: 0 };
      } finally { await client.close(); }
    },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).json()).run;
  assert.equal((await terminal(request, run.run_id)).state, 'planned');
});

test('stdio EOF reclaims a CLI process group owned by the bridge', { skip: !sdkPresent && !process.env.CI }, async t => {
  const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js');
  let cleaned = false;
  let cleanupFailure = null;
  const { request, root } = await fixture(t, {
    agentExecutor: async context => {
      const stub = join(root, 'stub'), pids = join(root, 'cli-pids.json');
      await mkdir(stub);
      await writeFile(join(stub, 'python3'), '#!' + process.execPath + '\n' +
        'const fs=require("node:fs"),{spawn}=require("node:child_process");' +
        'const child=spawn(process.execPath,["-e","setInterval(()=>{},1000)"],{stdio:"ignore"});' +
        'fs.writeFileSync(process.env.PID_FILE,JSON.stringify([process.pid,child.pid]));setInterval(()=>{},1000);', { mode: 0o700 });
      const client = new Client({ name: 'factory-bridge-eof', version: '1' });
      let owned = [];
      try {
        await client.connect(new StdioClientTransport({ command: process.execPath,
          args: [new URL('./agent-mcp.mjs', import.meta.url).pathname, '--run-root', context.runRoot], stderr: 'pipe',
          env: { ...process.env, PATH: stub + ':' + process.env.PATH, PID_FILE: pids } }));
        const pending = client.callTool({ name: 'factory_plan', arguments: {} }).catch(() => null);
        for (let n = 0; n < 200; n++) {
          try { owned = JSON.parse(await readFile(pids, 'utf8')); break; } catch {}
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.equal(owned.length, 2, 'owned CLI fixture did not start');
        await client.close(); await pending;
        for (let n = 0; n < 200; n++) {
          const living = owned.filter(pid => { try { process.kill(pid, 0); return true; } catch { return false; } });
          if (!living.length) break;
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.ok(owned.every(pid => { try { process.kill(pid, 0); return false; } catch { return true; } }), 'bridge leaked an owned CLI descendant');
        cleaned = true;
        return { exit_code: 1 };
      } catch (error) {
        let processes = '';
        if (owned.length) try { processes = (await execFileAsync('ps', ['-p', owned.join(','), '-o', 'pid,ppid,stat,command'])).stdout; } catch {}
        cleanupFailure = new Error(`${error.message}\n${processes}`);
        throw error;
      } finally {
        await client.close();
        if (owned[0]) try { process.kill(-owned[0], 'SIGKILL'); } catch {}
      }
    },
  });
  await save(request);
  const run = (await (await request('/api/runs', { body: { project_id: project.project_id, mode: 'plan' } })).json()).run;
  const done = await terminal(request, run.run_id);
  assert.equal(done.state, 'failed');
  assert.ifError(cleanupFailure);
  assert.equal(cleaned, true);
});
