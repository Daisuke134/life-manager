#!/usr/bin/env node
// CLI transport only; provider decisions and durable effect fences stay in Python.
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const cli = fileURLToPath(new URL('./bin/lm', import.meta.url));
const root = fileURLToPath(new URL('../../../', import.meta.url));
const string = z.string().refine(value => value.trim().length > 0 && !value.includes('\0'), '空文字/NULは使えません');
const config = { config: string, script: string };
const operations = ['prepare', 'shadow', 'upload', 'draft', 'promote', 'route-check', 'status', 'postiz-readback', 'reconcile'];
const tools = {
  factory_plan: {
    description: '利用者の設定/台本pathから既存CLIのoffline計画を返します。providerやprivate stateを操作しません。',
    schema: z.object(config).strict(),
    command: ['factory', 'plan'], fields: ['config', 'script'], readOnly: true,
  },
  factory_render: {
    description: '既存CLIで有料HeyGen動画を生成/照合します。課金・ファイル更新が発生する場合があります。同じ要求は同じrun_idを使い、費用guardや未確定effectを迂回しません。',
    schema: z.object({ ...config, run_id: string }).strict(),
    command: ['factory', 'render'], fields: ['config', 'script', 'run_id'],
  },
  factory_publish: {
    description: '既存CLIで投稿のprepare/shadow/route-check/upload/draft/promote/status/postiz-readback/reconcileを実行します。ファイル更新や外部投稿操作があり、upload/draft/promoteにはproduction=trueが必要です。scheduledは公開成功を意味せず、既存fenceと公式照合を保持します。',
    schema: z.object({ ...config, publication: string, run_id: string, operation: z.enum(operations),
      production: z.boolean().optional(), post: string.optional(), native: string.optional() }).strict(),
    command: ['factory', 'publish'], fields: ['config', 'script', 'publication', 'run_id', 'operation', 'post', 'native'],
  },
  factory_record_review: {
    description: '実施済みの素材確認を既存publish approveで記録します。ledgerを更新しますが素材の確認自体やprovider投稿は行いません。owner_confirmationとconfirmation_refには実際の確認者と根拠を指定してください。',
    schema: z.object({ approval_id: string, asset: string, product: string, account: string,
      owner_confirmation: string, confirmation_ref: string, approved_at: string, ledger: string.optional() }).strict(),
    command: ['publish', 'approve'],
    fields: ['approval_id', 'asset', 'product', 'account', 'owner_confirmation', 'confirmation_ref', 'approved_at', 'ledger'],
  },
};

const active = new Set();

export function runCli(args, { signal, timeoutMs = 3_600_000, maxOutputBytes = 1_048_576,
  killGraceMs = 500, spawnChild = spawn } = {}) {
  return new Promise(resolve => {
    let child;
    let timer;
    let forceTimer;
    let closed;
    let transportError = null;
    let stdoutBytes = 0;
    let stderrBytes = 0;
    const stdout = [];
    const stderr = [];
    let done;
    const entry = { stop: reason => terminate(reason), closed: new Promise(res => { done = res; }) };
    const kill = kind => {
      if (!child?.pid) return;
      try { process.kill(-child.pid, kind); } catch (error) { if (error.code !== 'ESRCH') transportError ||= 'signal_error'; }
    };
    const finish = () => {
      clearTimeout(timer);
      clearTimeout(forceTimer);
      signal?.removeEventListener('abort', abort);
      active.delete(entry);
      done();
      resolve({ exit_code: closed?.code ?? null, signal: closed?.signal ?? null,
        stdout: Buffer.concat(stdout).toString('utf8'), stderr: Buffer.concat(stderr).toString('utf8'),
        ...(transportError ? { transport_error: transportError } : {}) });
    };
    const terminate = reason => {
      if (transportError) return;
      transportError = reason;
      kill('SIGTERM');
      // Escalate even if Python exits first: its descendants may still own this group.
      forceTimer = setTimeout(() => {
        forceTimer = undefined;
        kill('SIGKILL');
        if (closed) finish();
      }, killGraceMs);
    };
    const abort = () => terminate('aborted');
    if (signal?.aborted) {
      transportError = 'aborted';
      finish();
      return;
    }
    try {
      child = spawnChild('python3', [cli, ...args], { cwd: root, shell: false, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch {
      transportError = 'spawn_error';
      finish();
      return;
    }
    active.add(entry);
    const capture = (chunks, data, used) => {
      const bytes = Buffer.from(data);
      const remaining = Math.max(0, maxOutputBytes - used);
      if (remaining) chunks.push(bytes.subarray(0, remaining));
      if (bytes.length > remaining) terminate('output_limit');
      return used + Math.min(bytes.length, remaining);
    };
    child.stdout.on('data', data => { stdoutBytes = capture(stdout, data, stdoutBytes); });
    child.stderr.on('data', data => { stderrBytes = capture(stderr, data, stderrBytes); });
    child.once('error', () => { transportError ||= 'spawn_error'; });
    child.once('close', (code, childSignal) => {
      closed = { code, signal: childSignal };
      if (!forceTimer) finish();
    });
    timer = setTimeout(() => terminate('timeout'), timeoutMs);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export async function stopOwnedChildren() {
  const pending = [...active];
  for (const child of pending) child.stop('server_closed');
  await Promise.all(pending.map(child => child.closed));
}

function mcpResult(child) {
  const envelope = { exit_code: child.exit_code ?? null, signal: child.signal ?? null,
    result: null, stdout: child.stdout ?? '', stderr: child.stderr ?? '' };
  let transportError = child.transport_error;
  try {
    envelope.result = JSON.parse(envelope.stdout.trim() ? envelope.stdout : envelope.stderr);
  } catch { transportError ||= 'invalid_json'; }
  if (transportError) envelope.transport_error = transportError;
  return { content: [{ type: 'text', text: JSON.stringify(envelope) }], structuredContent: envelope,
    isError: envelope.exit_code !== 0 || Boolean(transportError) };
}

export async function callFactoryTool(name, input, { executor = runCli, signal } = {}) {
  const tool = Object.hasOwn(tools, name) ? tools[name] : undefined;
  const parsed = tool?.schema.safeParse(input);
  if (!parsed?.success) return mcpResult({ exit_code: null, stdout: '', stderr: '', transport_error: 'invalid_arguments' });
  const args = [...tool.command];
  for (const field of tool.fields) {
    if (parsed.data[field] !== undefined) args.push(`--${field.replaceAll('_', '-')}=${parsed.data[field]}`);
  }
  if (parsed.data.production === true) args.push('--production');
  try { return mcpResult(await executor(args, { signal })); }
  catch { return mcpResult({ exit_code: null, stdout: '', stderr: '', transport_error: 'executor_error' }); }
}

export function createFactoryServer({ executor = runCli } = {}) {
  const server = new McpServer({ name: 'ai-monk-factory', version: '0.1.0' });
  for (const [name, tool] of Object.entries(tools)) {
    server.registerTool(name, { description: tool.description, inputSchema: tool.schema,
      annotations: { readOnlyHint: tool.readOnly === true } },
    (input, extra) => callFactoryTool(name, input, { executor, signal: extra.signal }));
  }
  return server;
}

async function main() {
  if (process.argv.length !== 2) throw new Error('このstdio serverはcommand引数を受け付けません。');
  const server = createFactoryServer();
  let closing;
  const close = () => closing ||= stopOwnedChildren().then(() => server.close());
  process.once('SIGINT', close);
  process.once('SIGTERM', close);
  process.stdin.once('end', close);
  server.server.onclose = close;
  await server.connect(new StdioServerTransport());
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    process.stderr.write('AI Monk Factory MCPを起動できません。\n');
    process.exitCode = 1;
  });
}
