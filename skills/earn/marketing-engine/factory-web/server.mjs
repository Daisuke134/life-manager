#!/usr/bin/env node
import http from 'node:http';
import { constants, createReadStream } from 'node:fs';
import { mkdir, open, readdir, rm, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import { createHash, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { validateProject } from './project.mjs';
import { createRunToolCaller, idPattern, readSafe, readTools, safePath, verifiedArtifact, writeJson } from './agent-mcp.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const modes = ['plan', 'render', 'publish'];
const isolationFeatureArgs = ['plugins', 'remote_plugin', 'apps', 'enable_mcp_apps', 'codex_apps_mcp_2026_07_28']
  .flatMap(feature => ['--disable', feature]);
const staticFiles = new Map([
  ['/', 'index.html'], ['/index.html', 'index.html'], ['/app.mjs', 'app.mjs'], ['/app.css', 'app.css'], ['/project.mjs', 'project.mjs'],
  ['/ai-monk-factory/', 'index.html'], ['/ai-monk-factory/index.html', 'index.html'], ['/ai-monk-factory/app.mjs', 'app.mjs'],
  ['/ai-monk-factory/app.css', 'app.css'], ['/ai-monk-factory/project.mjs', 'project.mjs'],
]);
const iso = () => new Date().toISOString();
const requireId = value => { if (typeof value !== 'string' || !idPattern.test(value)) throw new Error('Invalid ID.'); return value; };
const fields = (value, keys) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) throw new Error('Invalid request fields.');
};
const sameToken = (left, right) => typeof left === 'string' && Buffer.byteLength(left) === Buffer.byteLength(right)
  && timingSafeEqual(Buffer.from(left), Buffer.from(right));

export function agentCommand({ runRoot, workspace }, otherMcpServers = []) {
  const existing = new Set(otherMcpServers);
  const base = 'factory_run_' + createHash('sha256').update(runRoot).digest('hex').slice(0, 24);
  let name = base, suffix = 0;
  while (existing.has(name)) name = base + '_' + ++suffix;
  const disabled = [...existing].map(server => `${JSON.stringify(server)}={enabled=false}`);
  const bridge = `mcp_servers={${name}={enabled=true,command=${JSON.stringify(process.execPath)},args=${JSON.stringify([path.join(here, 'agent-mcp.mjs'), '--run-root', runRoot])},required=true,tool_timeout_sec=3600}${disabled.length ? ',' + disabled.join(',') : ''}}`;
  return { command: 'codex', args: ['exec', '--ephemeral', '--sandbox', 'workspace-write', '--json', '--skip-git-repo-check',
    ...isolationFeatureArgs,
    '-C', workspace, '-o', path.join(runRoot, 'control', 'agent.last.txt'),
    '-c', 'approval_policy="never"',
    '-c', 'sandbox_workspace_write.exclude_slash_tmp=true', '-c', 'sandbox_workspace_write.exclude_tmpdir_env_var=true',
    '-c', 'sandbox_workspace_write.writable_roots=[]',
    '-c', 'sandbox_workspace_write.network_access=false',
    '-c', bridge, '-'] };
}

export function configuredMcpNames({ execFileCommand = execFile } = {}) {
  return new Promise((resolve, reject) => execFileCommand('codex', [...isolationFeatureArgs, 'mcp', 'list', '--json'], { timeout: 15000, maxBuffer: 1048576, shell: false }, (error, stdout) => {
    if (error) { reject(new Error('mcp_inventory_unavailable')); return; }
    try {
      const rows = JSON.parse(stdout);
      if (!Array.isArray(rows) || rows.length > 128 || rows.some(row => typeof row.name !== 'string' || !row.name || row.name.length > 200)) throw new Error();
      // Discard transport URLs/env/headers here. Only names reach the exec argv.
      resolve([...new Set(rows.map(row => row.name))]);
    } catch { reject(new Error('mcp_inventory_invalid')); }
  }));
}

export async function runFiniteAgent(context, { spawnChild = spawn, mcpInventory = configuredMcpNames, timeoutMs = 3_600_000, maxOutputBytes = 1_048_576 } = {}) {
  let names;
  try { names = await mcpInventory(); } catch { return { exit_code: null, transport_error: 'mcp_inventory_unavailable' }; }
  const spec = agentCommand(context, names);
  const files = [path.join(context.runRoot, 'control', 'agent.stdout.jsonl'), path.join(context.runRoot, 'control', 'agent.stderr.log')];
  const handles = await Promise.all(files.map(file => open(file, 'wx', 0o600)));
  const input = JSON.parse(await readSafe(context.runRoot, path.join(context.runRoot, 'input', 'project.json')));
  const url = new URL(input.project.product_url); url.searchParams.set('utm_campaign', input.attribution_token);
  const prompt = `Complete one bounded Monk Factory ${input.mode} run. Work only in this workspace.\n`
    + 'Write the real spoken script into script.txt (at most 5000 characters), and optional caption.txt containing the CTA and exact tracked product URL once. '
    + 'Call factory_plan first: this freezes those files. Never change the script after planning. Use only the run-bound Factory MCP for provider actions. '
    + 'Never use provider CLIs, credentials, browser posting, another MCP, or a shell to send a post. Do not edit input or control files. '
    + 'Keep setup_required, unknown/null costs, nonzero exits and effect fences unchanged. Do not automatically retry an uncertain provider effect. '
    + 'In publish mode, use prepare, inspect the actual rendered media, extract real frames into this workspace, observe frames/audio metadata and record your own AI review with frame_evidence and notes. '
    + 'Do not claim a human reviewed anything. Then use shadow/route-check and permitted upload/draft/promote/status/postiz-readback. '
    + 'A scheduled post or provider status alone is not native confirmation or revenue. Your final text cannot establish completion.\n'
    + `Run mode: ${input.mode}\nTracked product URL: ${url.href}\nProject facts: ${JSON.stringify(input.project)}\n`;
  return new Promise(resolve => {
    let child, timer, forceTimer, reason = null, settled = false, bytes = [0, 0];
    let writes = Promise.resolve();
    const kill = signal => { if (child?.pid) try { process.kill(-child.pid, signal); } catch {} };
    const stop = why => {
      if (forceTimer) return;
      reason ||= why; kill('SIGTERM');
      forceTimer = setTimeout(() => kill('SIGKILL'), 1000);
    };
    const abort = () => stop('interrupted');
    const finish = async (exit_code = null, signal = null) => {
      if (settled) return; settled = true; clearTimeout(timer);
      // Reclaim only this finite invocation's process group, including bridge descendants.
      kill('SIGTERM'); await new Promise(done => setTimeout(done, 600)); kill('SIGKILL');
      clearTimeout(forceTimer); context.signal?.removeEventListener('abort', abort);
      await writes.catch(() => {}); await Promise.all(handles.map(file => file.close()));
      resolve({ exit_code, signal, ...(reason ? { transport_error: reason } : {}) });
    };
    if (context.signal?.aborted) { reason = 'interrupted'; void finish(); return; }
    try { child = spawnChild(spec.command, spec.args, { cwd: context.workspace, shell: false, detached: true, stdio: ['pipe', 'pipe', 'pipe'] }); }
    catch { reason = 'spawn_error'; void finish(); return; }
    for (const [index, stream] of [child.stdout, child.stderr].entries()) stream.on('data', data => {
      const piece = Buffer.from(data), remaining = Math.max(0, maxOutputBytes - bytes[index]);
      bytes[index] += Math.min(piece.length, remaining);
      if (remaining) writes = writes.then(() => handles[index].write(piece.subarray(0, remaining))).catch(() => stop('output_write_error'));
      if (piece.length > remaining) stop('output_limit');
    });
    child.once('error', () => { reason ||= 'spawn_error'; });
    child.once('close', (code, signal) => { void finish(code, signal); });
    child.stdin.on('error', () => {}); child.stdin.end(prompt);
    timer = setTimeout(() => stop('timeout'), timeoutMs);
    context.signal?.addEventListener('abort', abort, { once: true });
  });
}

function resultState(run, execution) {
  const target = run.mode === 'plan' ? 'factory_plan' : run.mode === 'render' ? 'factory_render' : 'factory_publish';
  const entry = [...run.tool_results].reverse().find(row => row.name === target && row.result.structuredContent?.result);
  const envelope = entry?.result.structuredContent, result = envelope?.result;
  if (execution.transport_error === 'interrupted') return 'interrupted';
  if (result?.cost_reconciliation_required || (result?.state === 'rendered' && result.wallet_cost === null)) return 'cost_reconciliation_required';
  if (!result) return 'failed';
  const state = String(result.state ?? result.status ?? (result.dispatchable === false ? 'not_dispatchable' : 'incomplete'));
  if (/published|earned/i.test(state)) return 'native_verification_required';
  if (execution.exit_code !== 0 || execution.transport_error || envelope.exit_code !== 0 || entry.result.isError) {
    return ['rendered', 'planned', 'accepted', 'success', 'completed'].includes(state) ? 'failed' : state;
  }
  return state;
}

export async function createFactoryWebServer({ root, token = randomBytes(32).toString('base64url'), uiRoot = here,
  agentExecutor = runFiniteAgent, factoryExecutor } = {}) {
  if (typeof root !== 'string' || !path.isAbsolute(root) || typeof token !== 'string' || !/^[A-Za-z0-9_-]{8,200}$/.test(token)) throw new Error('Invalid local server configuration.');
  root = path.resolve(root); await safePath(root, root); await mkdir(root, { recursive: true, mode: 0o700 });
  for (const folder of ['projects', 'runs']) { const target = path.join(root, folder); await safePath(root, target); await mkdir(target, { recursive: true, mode: 0o700 }); }
  const lock = path.join(root, 'server-lock.json'), owner = randomUUID();
  await safePath(root, lock);
  try {
    const prior = JSON.parse(await readSafe(root, lock, 4096));
    let alive = true; try { process.kill(prior.pid, 0); } catch (error) { if (error.code === 'ESRCH') alive = false; }
    if (alive) throw new Error('This Factory workspace already has a server.');
    await rm(lock);
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await writeFile(lock, JSON.stringify({ pid: process.pid, owner }), { flag: 'wx', mode: 0o600 });
  let active = null, closing = false;
  const runRoot = id => path.join(root, 'runs', requireId(id));
  const loadRun = async id => {
    const location = runRoot(id);
    const run = JSON.parse(await readSafe(root, path.join(location, 'run.json')));
    run.tool_results = await readTools(location);
    return run;
  };
  for (const entry of await readdir(path.join(root, 'runs'), { withFileTypes: true })) {
    if (!idPattern.test(entry.name) || entry.isSymbolicLink() || !entry.isDirectory()) continue;
    const run = await loadRun(entry.name);
    if (['queued', 'running'].includes(run.state)) {
      run.state = 'interrupted'; run.summary = 'The local server stopped. No provider operation was automatically retried.';
      run.updated_at = iso(); await writeJson(root, path.join(runRoot(entry.name), 'run.json'), run);
    }
  }
  const send = (response, code, value, type = 'application/json; charset=utf-8') => {
    const body = Buffer.isBuffer(value) ? value : Buffer.from(type.startsWith('application/json') ? JSON.stringify(value) : value);
    response.writeHead(code, { 'content-type': type, 'content-length': body.length, 'cache-control': 'no-store',
      'x-content-type-options': 'nosniff', 'content-security-policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'" });
    response.end(body);
  };
  const body = async request => {
    if (!request.headers['content-type']?.startsWith('application/json')) throw new Error('JSON request required.');
    if (Number(request.headers['content-length']) > 65536) { const error = new Error('Request too large.'); error.status = 413; throw error; }
    let size = 0, parts = [];
    for await (const chunk of request) { size += chunk.length; if (size > 65536) { const error = new Error('Request too large.'); error.status = 413; throw error; } parts.push(chunk); }
    return JSON.parse(Buffer.concat(parts).toString('utf8'));
  };
  const execute = async (run, location, controller) => {
    run.state = 'running'; run.updated_at = iso(); await writeJson(root, path.join(location, 'run.json'), run);
    let execution;
    try { execution = await agentExecutor({ run: { ...run }, runRoot: location, workspace: path.join(location, 'workspace'), signal: controller.signal,
      invokeTool: createRunToolCaller({ runRoot: location, factoryExecutor, signal: controller.signal }) }); }
    catch { execution = { exit_code: null, transport_error: 'agent_executor_error' }; }
    execution ||= { exit_code: null, transport_error: 'missing_agent_result' };
    run.tool_results = await readTools(location);
    run.exit_code = Number.isInteger(execution.exit_code) ? execution.exit_code : null;
    run.state = controller.signal.aborted ? 'interrupted' : resultState(run, execution);
    run.summary = execution.transport_error ? `Agent transport: ${execution.transport_error}. Provider evidence remains authoritative.`
      : `${run.state}; agent exit ${run.exit_code ?? 'unknown'}. Native publication and revenue are not inferred.`;
    run.updated_at = iso();
    try { await verifiedArtifact(location); run.artifact_url = `/api/runs/${run.run_id}/video`; } catch { run.artifact_url = null; }
    await writeJson(root, path.join(location, 'run.json'), run);
  };
  const server = http.createServer(async (request, response) => {
    try {
      const host = `127.0.0.1:${server.address()?.port}`;
      if (request.headers.host !== host || (request.headers.origin !== undefined && request.headers.origin !== `http://${host}`)) return send(response, 403, { error: 'Local origin required.' });
      const route = request.url;
      if (route?.startsWith('/api/') && !sameToken(request.headers['x-factory-token'], token)) return send(response, 403, { error: 'Local action token required.' });
      if (request.method === 'GET' && staticFiles.has(route)) {
        const filename = staticFiles.get(route);
        const source = (await readSafe(uiRoot, path.join(uiRoot, filename), 1024 * 1024)).toString('utf8');
        return send(response, 200, filename === 'index.html' ? source.replaceAll('__FACTORY_TOKEN__', token) : source,
          filename.endsWith('.html') ? 'text/html; charset=utf-8' : filename.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/javascript; charset=utf-8');
      }
      if (route === '/api/projects' && request.method === 'GET') {
        const projects = [];
        for (const entry of await readdir(path.join(root, 'projects'), { withFileTypes: true })) {
          if (!entry.isFile() || !/^[a-z0-9][a-z0-9_-]{0,63}\.json$/.test(entry.name)) continue;
          projects.push(validateProject(JSON.parse(await readSafe(root, path.join(root, 'projects', entry.name), 65536))));
        }
        return send(response, 200, { projects });
      }
      if (route === '/api/projects' && request.method === 'POST') {
        const value = await body(request); fields(value, ['project']); const project = validateProject(value.project);
        await writeJson(root, path.join(root, 'projects', project.project_id + '.json'), project);
        return send(response, 200, { project });
      }
      if (route === '/api/runs' && request.method === 'GET') {
        const runs = [];
        for (const entry of await readdir(path.join(root, 'runs'), { withFileTypes: true })) if (entry.isDirectory() && !entry.isSymbolicLink() && idPattern.test(entry.name)) runs.push(await loadRun(entry.name));
        return send(response, 200, { runs: runs.sort((a, b) => b.created_at.localeCompare(a.created_at)) });
      }
      if (route === '/api/runs' && request.method === 'POST') {
        const value = await body(request); fields(value, ['project_id', 'mode']); requireId(value.project_id);
        if (!modes.includes(value.mode)) throw new Error('Invalid run mode.');
        if (closing || active) return send(response, 409, { error: 'A finite run is already active.' });
        const project = validateProject(JSON.parse(await readSafe(root, path.join(root, 'projects', value.project_id + '.json'), 65536)), { ready: true });
        if (closing || active) return send(response, 409, { error: 'A finite run is already active.' });
        // Reserve before any awaited writes so concurrent POSTs cannot start two agents.
        const reservation = {}; active = reservation;
        try {
          const run_id = 'run-' + randomUUID(), location = runRoot(run_id), created_at = iso();
          await safePath(root, location); await mkdir(location, { mode: 0o700 });
          for (const folder of ['input', 'workspace', 'control']) await mkdir(path.join(location, folder), { mode: 0o700 });
          await writeJson(root, path.join(location, 'input', 'project.json'), { project, run_id, mode: value.mode, attribution_token: 'factory_' + run_id.replaceAll('-', '') });
          await writeFile(path.join(location, 'workspace', 'script.txt'), project.script, { flag: 'wx', mode: 0o600 });
          const run = { run_id, project_id: project.project_id, mode: value.mode, state: 'queued', exit_code: null,
            created_at, updated_at: created_at, tool_results: [], summary: null, artifact_url: null };
          await writeJson(root, path.join(location, 'run.json'), run);
          const controller = new AbortController();
          const promise = execute(run, location, controller).catch(async () => {
            run.state = 'interrupted'; run.updated_at = iso(); run.summary = 'Run evidence could not be finalized. Do not retry uncertain provider effects.';
            await writeJson(root, path.join(location, 'run.json'), run);
          }).finally(() => { if (active === reservation) active = null; });
          Object.assign(reservation, { controller, promise });
          return send(response, 202, { run: { ...run } });
        } catch (error) { if (active === reservation) active = null; throw error; }
      }
      const match = /^\/api\/runs\/([a-z0-9][a-z0-9_-]{0,63})(\/video)?$/.exec(route ?? '');
      if (match && request.method === 'GET') {
        if (!match[2]) return send(response, 200, { run: await loadRun(match[1]) });
        let asset;
        try { asset = await verifiedArtifact(runRoot(match[1])); } catch { return send(response, 409, { error: 'Run asset is unavailable or no longer matches its receipt.' }); }
        response.writeHead(200, { 'content-type': 'video/mp4', 'content-length': asset.size, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
        const stream = createReadStream(asset.path, { flags: constants.O_RDONLY | constants.O_NOFOLLOW });
        stream.on('error', () => response.destroy()); stream.pipe(response); return;
      }
      return send(response, 404, { error: 'Not found.' });
    } catch (error) {
      if (!response.headersSent) send(response, error.status === 413 ? 413 : error.code === 'ENOENT' ? 404 : 400, { error: error.status === 413 ? 'Request too large.' : 'Invalid or unavailable workspace data.' });
      else response.destroy();
    }
  });
  let shutdown;
  server.shutdown = () => shutdown ||= (async () => {
    closing = true; active?.controller?.abort(); await active?.promise;
    if (server.listening) await new Promise(resolve => server.close(resolve));
    try {
      const current = JSON.parse(await readSafe(root, lock, 4096));
      if (current.owner === owner) await rm(lock);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  })();
  return server;
}

async function main() {
  let port = 18792, openBrowser = false;
  const args = process.argv.slice(2);
  for (let index = 0; index < args.length; index++) {
    if (args[index] === '--open') openBrowser = true;
    else if (args[index] === '--port' && /^\d+$/.test(args[index + 1] ?? '')) port = Number(args[++index]);
    else throw new Error('Use server.mjs [--port N] [--open].');
  }
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Invalid local port.');
  const hostData = process.env.LM_DATA_DIR ?? path.join(homedir(), '.local', 'state', 'life-manager');
  if (!hostData || !path.isAbsolute(hostData)) throw new Error('LM_DATA_DIR must be an absolute host path.');
  const server = await createFactoryWebServer({ root: path.join(hostData, 'marketing', 'ebook', 'factory', 'web') });
  const close = () => { void server.shutdown(); };
  process.once('SIGTERM', close); process.once('SIGINT', close);
  server.listen(port, '127.0.0.1', () => {
    const url = `http://127.0.0.1:${port}/`;
    process.stdout.write(JSON.stringify({ state: 'ready', url }) + '\n');
    if (openBrowser) {
      const command = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? null : 'xdg-open';
      if (command) { const child = spawn(command, [url], { shell: false, stdio: 'ignore' }); child.on('error', () => {}); }
    }
  });
  server.once('error', async () => { await server.shutdown(); process.stderr.write('Factory local server could not listen.\n'); process.exitCode = 1; });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stderr.write('Factory local server could not start.\n'); process.exitCode = 1; });
}
