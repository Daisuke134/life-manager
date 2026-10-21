/**
 * brain.mjs — Effectful: unified THINK step through the shared Codex agent-runner.
 *
 * Registered local owners select Codex through the shared agent-runner. It owns provider profile
 * isolation, structured output, usage accounting, and provider-unavailable reporting.
 */

import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { buildSystemPrompt, buildUserMessage } from './prompt.mjs';

const CODEX_BRAIN_TASK_CLASS = 'codex-brain-agent';
const CODEX_BRAIN_TIMEOUT_MS = 180_000;
const CODEX_BRAIN_SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const CODEX_BRAIN_RESULT_REASON = /^[a-z][a-z0-9_:-]{1,99}$/;
const LOOP_REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const activeCodexRunnerStoppers = new Set();

export async function stopActiveCodexRunners() {
  await Promise.all([...activeCodexRunnerStoppers].map((stop) => stop()));
}

/**
 * Kept for old ledger readers; Codex-only owner routes no longer attach provider fallback metadata.
 */
export function getBrainFallback() { return null; }

/**
 * Execute the THINK step for the current wake.
 *
 * @param {object} ctx - WakeContext
 * @param {object} config - loaded config
 * @returns {Promise<object>} - validated Codex tool decision
 * @throws when the configured brain is not Codex or the Codex runner fails
 */
export async function think(ctx, config) {
  const brain = config.ANICCA_BRAIN || 'codex';

  if (brain !== 'codex') throw new Error('codex_only_brain_required');
  return thinkCodex(ctx, config);
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
    let interrupted = false;
    let resolveExited;
    let stopPromise = null;
    const exited = new Promise((resolve) => { resolveExited = resolve; });
    const stopAndWait = () => {
      if (stopPromise) return stopPromise;
      stopPromise = (async () => {
        if (settled) return;
        interrupted = true;
        clearTimeout(timer);
        clearTimeout(graceTimer);
        killGroup('SIGTERM');
        let grace;
        await Promise.race([
          exited,
          new Promise((resolve) => { grace = setTimeout(resolve, 2_000); }),
        ]);
        clearTimeout(grace);
        if (!settled) {
          killGroup('SIGKILL');
          await exited;
        }
      })();
      return stopPromise;
    };
    activeCodexRunnerStoppers.add(stopAndWait);
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
      activeCodexRunnerStoppers.delete(stopAndWait);
      resolveExited();
      reject(new Error(`codex_brain_spawn:${error.message}`));
    });
    proc.on('exit', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(graceTimer);
      activeCodexRunnerStoppers.delete(stopAndWait);
      resolveExited();
      if (interrupted) {
        reject(new Error('codex_brain_interrupted'));
        return;
      }
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

function validateCodexDecision(value, { allowNoToolCall = false } = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || !Array.isArray(value.tool_calls) || value.tool_calls.length > 1
    || (value.tool_calls.length === 0 && !allowNoToolCall)) {
    throw new Error('codex_brain_invalid_result');
  }
  // An always-act no-op must reach its existing bounded reprompt; ordinary wakes use `sleep`.
  if (value.tool_calls.length === 0) return value;
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
  return validateCodexDecision(decision, { allowNoToolCall: ctx?.alwaysActEngaged === true });
}
