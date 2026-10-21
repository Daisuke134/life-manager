// Franklin's shared loop uses the native Codex brain; the daemon does not start a provider proxy.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(HERE, '../../anicca-daemon.sh'), 'utf8');

test('Franklin daemon defaults to Codex and rejects a non-Codex brain before starting the loop', () => {
  const defaultBrain = 'ANICCA_BRAIN="' + '$' + '{ANICCA_BRAIN:-codex}"';
  const guard = source.indexOf(defaultBrain);
  const loop = source.indexOf('node "$REPO/runtime/loop/index.mjs"');
  assert.ok(guard >= 0);
  assert.ok(loop > guard);
  assert.match(source, /if \[ "\$ANICCA_BRAIN" != "codex" \]/);
  assert.match(source, /export ANICCA_BRAIN/);
});

test('Franklin daemon does not start the retired compute-proxy brain process', () => {
  assert.doesNotMatch(source, /runtime\/compute-proxy\/start-local\.sh[^\n]*--proxy-only/);
  assert.doesNotMatch(source, /BRAIN_PID=/);
  assert.doesNotMatch(source, /export OPENAI_BASE_URL=/);
  assert.doesNotMatch(source, /export OPENAI_API_KEY=/);
});
