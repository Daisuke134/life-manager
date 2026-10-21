/**
 * brain.mjs — Effectful: unified THINK step with fallback.
 *
 * Registered local owners select Codex through the shared agent-runner. It owns provider profile
 * isolation, structured output, usage accounting, and provider-unavailable reporting.
 */

import https from 'node:https';
import http from 'node:http';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { buildSystemPrompt, buildUserMessage, getToolDefinitions } from './prompt.mjs';

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;
const CODEX_BRAIN_TASK_CLASS = 'codex-brain-agent';
const CODEX_BRAIN_TIMEOUT_MS = 180_000;
const CODEX_BRAIN_SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const CODEX_BRAIN_RESULT_REASON = /^[a-z][a-z0-9_:-]{1,99}$/;
const LOOP_REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/**
 * Kept for old ledger readers; Codex-only owner routes no longer attach provider fallback metadata.
 */
export function getBrainFallback() { return null; }

/**
 * Execute the THINK step for the current wake.
 *
 * @param {object} ctx - WakeContext
 * @param {object} config - loaded config
 * @returns {Promise<object>} - raw response (OpenAI-compatible)
 * @throws only if both backends fail (caller writes wake_error)
 */
export async function think(ctx, config) {
  const brain = config.ANICCA_BRAIN || 'codex';

  if (brain === 'claude-p') throw new Error('codex_only_brain_required');

  if (brain === 'codex') return thinkCodex(ctx, config);
  return thinkProxy(ctx, config);
}

// ── Proxy brain (HTTP POST) ──────────────────────────────────────────────────

async function thinkProxy(ctx, config) {
  const baseUrl = config.OPENAI_BASE_URL || 'http://127.0.0.1:18402/v1';
  const url = baseUrl.replace(/\/+$/, '') + '/chat/completions';

  // Policy 2026-06-21 (Dais): use the survival-tier model (ctx.model from tier.mjs). For LEAN
  // and FUNDED tiers that resolves to ClawRouter `auto` — paid (kimi-k2.7 ~$0.004/call typical)
  // is OK because net-positive (earn − burn) is the real goal, not zero compute. BROKE tier
  // (balance=0) stays on `free/gpt-oss-120b` as a safety floor since an empty wallet can't pay.
  // Operator override via ANICCA_MODEL.
  const body = JSON.stringify({
    model: config.ANICCA_MODEL || ctx.model || 'auto',
    messages: [
      { role: 'system', content: buildSystemPrompt(ctx) },
      { role: 'user',   content: buildUserMessage(ctx) },
    ],
    // franklin-alwaysact-skill-router REQ-504: an always-act-engaged ctx offers ONLY the (possibly
    // reroute-narrowed) always-act menu, with sleep withheld — a non-engaged ctx (the overwhelming
    // majority of all wakes) produces the exact byte-for-byte current call.
    tools: getToolDefinitions(
      ctx.alwaysActEngaged ? ctx.alwaysActMenu : ctx.activeSkillSlots,
      { omitSleep: ctx.alwaysActEngaged === true },
    ),
    tool_choice: 'auto',
    max_tokens: 512,
  });

  let lastErr;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    if (attempt > 0) await delay(RETRY_DELAY_MS);
    try {
      const raw = await httpPost(url, body);
      return JSON.parse(raw);
    } catch (err) {
      lastErr = err;
    }
  }
  throw new Error(`proxy_down: ${lastErr?.message || 'unknown'}`);
}

// ── Codex brain (existing agent-runner, subscription-backed) ────────────────

/**
 * Run the existing Python agent-runner with bounded stdin/stdout and a process-group timeout.
 * The runner already owns Codex profile isolation, output-schema validation, token accounting, and
 * provider failover. This seam only supervises that one process; it never lets Codex execute a skill
 * or mutate the Life Manager workspace.
 */
export function runCodexAgentWithTimeout(bin, args, { env, cwd, input, timeoutMs }) {
  const limit = Number(timeoutMs);
  if (!Number.isFinite(limit) || limit < 1) {
    return Promise.reject(new Error('codex_brain_timeout_invalid'));
  }
  return new Promise((resolve, reject) => {
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let settled = false;
    let graceTimer = null;

    const append = (current, chunk) => {
      const text = String(chunk);
      const next = current + text;
      return next.length > 512_000 ? next.slice(-512_000) : next;
    };
    const proc = spawn(bin, args, {
      env,
      cwd,
      detached: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const killGroup = (signal) => {
      try { process.kill(-proc.pid, signal); } catch { try { proc.kill(signal); } catch {} }
    };
    const timer = setTimeout(() => {
      timedOut = true;
      killGroup('SIGTERM');
      graceTimer = setTimeout(() => killGroup('SIGKILL'), 2_000);
    }, limit);

    proc.stdout.on('data', (chunk) => { stdout = append(stdout, chunk); });
    proc.stderr.on('data', (chunk) => { stderr = append(stderr, chunk); });
    proc.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(graceTimer);
      reject(new Error(`codex_brain_spawn:${error.message}`));
    });
    proc.on('exit', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(graceTimer);
      if (timedOut) {
        reject(new Error('codex_brain_timeout'));
        return;
      }
      resolve({ stdout, stderr, code });
    });
    proc.stdin.end(input == null ? '' : String(input));
  });
}

function safeCodexBrainId(value) {
  const candidate = String(value == null ? '' : value).trim();
  return CODEX_BRAIN_SAFE_ID.test(candidate) ? candidate : 'wake';
}

function privateCodexBrainDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const stat = fs.lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('codex_brain_state_invalid');
  fs.chmodSync(directory, 0o700);
}

function lastJsonLine(text) {
  for (const line of String(text || '').split(/\r?\n/u).reverse()) {
    const candidate = line.trim();
    if (!candidate) continue;
    try {
      const value = JSON.parse(candidate);
      if (value && typeof value === 'object' && !Array.isArray(value)) return value;
    } catch { /* Codex/runner progress lines are not the summary. */ }
  }
  return null;
}

function safeResultPath(evidenceDirectory, value) {
  if (typeof value !== 'string' || !path.isAbsolute(value)) throw new Error('codex_brain_result_path_invalid');
  let root;
  let target;
  try {
    // macOS exposes /tmp as a symlink to /private/tmp. Compare real paths so the
    // existing agent-runner's Path.resolve() output remains inside our private
    // evidence directory without weakening the traversal check.
    root = fs.realpathSync(evidenceDirectory);
    target = fs.realpathSync(value);
  } catch {
    throw new Error('codex_brain_result_path_invalid');
  }
  const relative = path.relative(root, target);
  if (!relative || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error('codex_brain_result_path_invalid');
  }
  return target;
}

function validateCodexDecision(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || !Array.isArray(value.tool_calls) || value.tool_calls.length !== 1) {
    throw new Error('codex_brain_invalid_result');
  }
  const call = value.tool_calls[0];
  const name = call?.function?.name;
  const args = call?.function?.arguments;
  if (!['run_skill', 'sleep'].includes(name) || typeof args !== 'string') {
    throw new Error('codex_brain_invalid_result');
  }
  try {
    const parsed = JSON.parse(args);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('args');
    if (name === 'run_skill'
      && (typeof parsed.slot !== 'string' || !parsed.slot.trim())) throw new Error('slot');
  } catch {
    throw new Error('codex_brain_invalid_result');
  }
  return value;
}

/**
 * Use the existing Codex-first agent-runner as an optional brain backend. It receives only a
 * read-only task, writes private evidence under ANICCA_HOME, and returns the exact JSON shape that
 * parse-tool-call.mjs already accepts. No provider/browser/skill effect is executed in this function.
 */
export async function thinkCodex(ctx, config = {}) {
  const stateHome = String(config.ANICCA_HOME || process.env.ANICCA_HOME || '').trim();
  if (!path.isAbsolute(stateHome) || stateHome === path.parse(stateHome).root) {
    throw new Error('codex_brain_state_invalid');
  }
  const wakeId = safeCodexBrainId(ctx && (ctx.wakeId || ctx.wake_id));
  const evidenceDirectory = path.join(stateHome, 'state', 'codex-brain', wakeId);
  privateCodexBrainDirectory(path.dirname(evidenceDirectory));
  privateCodexBrainDirectory(evidenceDirectory);

  const schemaPath = path.resolve(
    String(process.env.CODEX_BRAIN_SCHEMA || path.join(LOOP_REPO_ROOT, 'runtime/loop/codex-brain.schema.json')),
  );
  if (!fs.existsSync(schemaPath) || !fs.statSync(schemaPath).isFile()) {
    throw new Error('codex_brain_schema_missing');
  }
  const runnerPath = path.resolve(
    String(process.env.CODEX_AGENT_RUNNER || path.join(LOOP_REPO_ROOT, 'runtime/agent-runner/agent_runner.py')),
  );
  const runnerConfig = path.resolve(
    String(process.env.CODEX_AGENT_CONFIG || path.join(LOOP_REPO_ROOT, 'runtime/agent-runner/config.json')),
  );
  if (!fs.existsSync(runnerPath) || !fs.statSync(runnerPath).isFile()
    || !fs.existsSync(runnerConfig) || !fs.statSync(runnerConfig).isFile()) {
    throw new Error('codex_brain_runner_missing');
  }

  const menuSlots = (ctx && (ctx.alwaysActEngaged ? ctx.alwaysActMenu : ctx.activeSkillSlots)) || [];
  const slotList = Array.isArray(menuSlots) && menuSlots.length
    ? menuSlots.map((slot) => `  - ${slot}`).join('\n')
    : '  (no slots available this wake)';
  const canSleep = !(ctx && ctx.alwaysActEngaged === true);
  const prompt = [
    buildSystemPrompt(ctx),
    '',
    buildUserMessage(ctx),
    '',
    'Return exactly one JSON object and nothing else. It must match the supplied output schema.',
    'The only valid function names are run_skill and sleep.',
    'function.arguments MUST be a JSON-encoded string, not an object.',
    '',
    '{"tool_calls":[{"function":{"name":"run_skill","arguments":"{\\"slot\\":\\"<slot>\\",\\"args\\":{}}"}}]}',
    '',
    'Valid slots for this wake:',
    slotList,
    ...(canSleep ? ['', 'If no action is justified, use sleep with arguments "{}".'] : []),
  ].join('\n');

  const timeoutSecondsRaw = Number(process.env.CODEX_BRAIN_TIMEOUT_S || 180);
  const timeoutSeconds = Number.isInteger(timeoutSecondsRaw) && timeoutSecondsRaw > 0
    ? timeoutSecondsRaw : 180;
  const python = String(
    process.env.CODEX_BRAIN_PYTHON || process.env.LIFE_MANAGER_RUNTIME_PYTHON || 'python3',
  );
  const args = [
    runnerPath,
    '--task-class', CODEX_BRAIN_TASK_CLASS,
    '--prompt-stdin',
    '--schema', schemaPath,
    '--evidence-dir', evidenceDirectory,
    '--task-label', `codex-brain-${wakeId}`,
    '--loop', 'codex-brain',
    '--workdir', os.tmpdir(),
    '--timeout-seconds', String(timeoutSeconds),
    '--read-only',
  ];
  const childEnv = {
    HOME: process.env.HOME || os.homedir(),
    PATH: process.env.PATH || '/usr/bin:/bin',
    USER: process.env.USER || 'anicca',
    ANICCA_HOME: stateHome,
    LIFE_MANAGER_REPO: LOOP_REPO_ROOT,
    AGENT_RUNNER_CONFIG: runnerConfig,
    PYTHONPATH: [LOOP_REPO_ROOT, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };
  const result = await runCodexAgentWithTimeout(python, args, {
    env: childEnv,
    cwd: os.tmpdir(),
    input: prompt,
    timeoutMs: timeoutSeconds * 1000,
  });
  if (result.code !== 0) {
    const summary = lastJsonLine(result.stdout);
    const reason = summary && typeof summary.error_class === 'string' && CODEX_BRAIN_RESULT_REASON.test(summary.error_class)
      ? summary.error_class : `exit_${result.code}`;
    throw new Error(`codex_brain_failed:${reason}`);
  }
  const summary = lastJsonLine(result.stdout);
  if (!summary || summary.status !== 'success' || summary.selected_provider !== 'codex') {
    throw new Error('codex_brain_not_codex');
  }
  const resultFile = safeResultPath(evidenceDirectory, summary.result_path);
  let decision;
  try {
    decision = JSON.parse(fs.readFileSync(resultFile, 'utf8'));
  } catch {
    throw new Error('codex_brain_result_unreadable');
  }
  return validateCodexDecision(decision);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function httpPost(url, body) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === 'https:' ? https : http;
    const options = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        'Authorization': `Bearer ${process.env.OPENAI_API_KEY || 'x402-local'}`,
      },
      timeout: 30000,
    };
    const req = lib.request(options, (res) => {
      let data = '';
      res.on('data', c => { data += c; });
      res.on('end', () => {
        // #F1 (2026-07-06): a non-2xx here is a real upstream failure (observed live:
        // sol.blockrun.ai's free-model NVIDIA passthrough intermittently 403/429s —
        // transient: retrying the identical request succeeds within a few attempts).
        // Resolving unconditionally let that error BODY get JSON.parse'd and returned
        // as if it were a real completion, so the retry loop above never fired and
        // every failure silently surfaced as a harmless "narrate" wake instead of
        // wake_error (confirmed live 2026-07-07: a real 429 body parses as valid JSON
        // with no `choices` array, so parseToolCall sees null and index.mjs treats it
        // as text-only). Reject instead so the existing attempt/back-off loop actually
        // retries transient gateway errors.
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0, 300)}`));
          return;
        }
        resolve(data);
      });
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('HTTP timeout')); });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}
