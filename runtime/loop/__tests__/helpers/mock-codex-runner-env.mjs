import fs from 'node:fs';
import path, { dirname } from 'node:path';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MOCK_RUNNER = path.join(HERE, 'mock-codex-agent-runner.mjs');

export function mockCodexRunnerEnv({ home, baseUrl, capturePromptPath,
  holdUntilKilled = false, pidCapturePath } = {}) {
  if (!path.isAbsolute(home || '') || !/^http:\/\/127\.0\.0\.1:\d+\/v1\/?$/u.test(String(baseUrl || ''))) {
    throw new Error('mock Codex runner requires a temp home and loopback mock URL');
  }
  const configPath = path.join(home, 'state', 'mock-codex-runner.json');
  fs.mkdirSync(dirname(configPath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(configPath, JSON.stringify({
    base_url: baseUrl,
    capture_prompt_path: capturePromptPath,
    hold_until_killed: holdUntilKilled,
    pid_capture_path: pidCapturePath,
  }), {
    mode: 0o600,
  });
  return {
    ANICCA_BRAIN: 'codex',
    CODEX_AGENT_RUNNER: MOCK_RUNNER,
    CODEX_AGENT_CONFIG: configPath,
    CODEX_BRAIN_PYTHON: process.execPath,
  };
}

export function readCodexPromptCaptures(home) {
  const file = path.join(home, 'state', 'codex-prompts.jsonl');
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
}

export function offeredCodexSlots(prompt) {
  const start = prompt.indexOf('Valid slots for this wake:\n');
  if (start < 0) return [];
  const section = prompt.slice(start).split('\n\n')[0];
  return section.split('\n').slice(1).map((line) => line.replace(/^\s*-\s*/u, '').trim()).filter(Boolean);
}

export function codexPromptOffersSleep(prompt) {
  return /If no action is justified, use sleep with arguments/u.test(prompt);
}

export async function stopTestLoop(proc) {
  if (!proc || proc.exitCode !== null || proc.signalCode !== null) return;
  const exited = once(proc, 'exit');
  const forceKill = setTimeout(() => {
    if (proc.exitCode === null && proc.signalCode === null) proc.kill('SIGKILL');
  }, 10_000);
  if (proc.exitCode === null && proc.signalCode === null) proc.kill('SIGTERM');
  try { await exited; }
  finally { clearTimeout(forceKill); }
}
