import fs from 'node:fs/promises';
import path from 'node:path';

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function main() {
  const evidenceDir = option('--evidence-dir');
  const config = JSON.parse(await fs.readFile(process.env.AGENT_RUNNER_CONFIG, 'utf8'));
  const url = new URL(`${String(config.base_url || '').replace(/\/+$/u, '')}/chat/completions`);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1') {
    throw new Error('mock Codex runner only permits an in-process loopback server');
  }
  const prompt = await new Promise((resolve, reject) => {
    let value = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { value += chunk; });
    process.stdin.on('end', () => resolve(value));
    process.stdin.on('error', reject);
  });
  if (config.capture_prompt_path) {
    await fs.appendFile(config.capture_prompt_path, `${JSON.stringify(prompt)}\n`, { mode: 0o600 });
  }
  if (config.hold_until_killed === true) {
    if (!path.isAbsolute(config.pid_capture_path || '')) throw new Error('mock Codex pid path must be absolute');
    await fs.writeFile(config.pid_capture_path, String(process.pid), { mode: 0o600 });
    await new Promise(() => {});
  }
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model: 'test-codex', messages: [{ role: 'user', content: prompt }] }),
  });
  if (!response.ok) {
    process.stdout.write(`${JSON.stringify({ error_class: `fixture_http_${response.status}` })}\n`);
    process.exitCode = 1;
    return;
  }
  const payload = await response.json();
  const fn = payload?.choices?.[0]?.message?.tool_calls?.[0]?.function;
  const canSleep = prompt.includes('If no action is justified, use sleep with arguments');
  const decision = fn && ['run_skill', 'sleep'].includes(fn.name) && typeof fn.arguments === 'string'
    ? { tool_calls: [{ function: { name: fn.name, arguments: fn.arguments } }] }
    : canSleep
      ? { tool_calls: [{ function: { name: 'sleep', arguments: '{}' } }] }
      : { tool_calls: [] };
  const resultPath = path.join(evidenceDir, 'decision.json');
  await fs.writeFile(resultPath, JSON.stringify(decision), { mode: 0o600 });
  process.stdout.write(`${JSON.stringify({
    status: 'success', selected_provider: 'codex', result_path: resultPath,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${String(error?.message || error)}\n`);
  process.exitCode = 1;
});
