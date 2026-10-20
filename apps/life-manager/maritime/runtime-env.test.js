'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { prepareMaritimeRuntime } = require('./runtime-env.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const releaseRoot = path.resolve(__dirname, '../../..');
const baseConfig = JSON.parse(fs.readFileSync(path.join(releaseRoot, 'runtime/agent-runner/config.json'), 'utf8'));
function fixture(t) {
  const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'lm-cloud-env-'));
  t.after(() => fs.rmSync(dataRoot, { recursive: true, force: true }));
  const env = { LM_RUNTIME_TENANT_ID: UID, LM_RELEASE_SHA: SHA,
    OPENAI_API_KEY: 'per-agent-fixture-key', OPENAI_BASE_URL: 'https://api.maritime.sh/v1',
    AGENT_RUNNER_CONFIG: '/fixture/personal/config.json', CODEX_HOME: '/fixture/personal/codex' };
  return { dataRoot, env, baseConfig, releaseRoot };
}
test('startup reuses the existing runner schema and preserves the automation model without personal profiles', t => {
  const input = fixture(t); const result = prepareMaritimeRuntime(input);
  assert.deepEqual(result.config, { tenantId: UID, releaseSha: SHA, modelReady: true });
  assert.equal(result.env.LM_CLOUD_MODEL_API_KEY, input.env.OPENAI_API_KEY);
  const savedText = fs.readFileSync(result.env.AGENT_RUNNER_CONFIG, 'utf8');
  assert.equal(savedText.includes(input.env.OPENAI_API_KEY), false);
  assert.equal(savedText.includes('/Users/'), false);
  const saved = JSON.parse(savedText);
  assert.deepEqual(Object.keys(saved.task_classes), ['application-lane-agent']);
  assert.deepEqual(saved.task_classes['application-lane-agent'].candidates,
    [{ ...baseConfig.task_classes['application-lane-agent'].candidates[0], profile_alias: 'cloud' }]);
  assert.deepEqual(Object.keys(saved.providers), ['codex']);
  assert.equal(saved.providers.codex.model_provider, 'maritime');
  assert.equal(saved.providers.codex.cost_tier, 'metered');
  assert.equal(saved.providers.codex.quota, undefined);
  assert.deepEqual(saved.providers.codex.model_providers.maritime, {
    name: 'Maritime', base_url: input.env.OPENAI_BASE_URL, env_key: 'LM_CLOUD_MODEL_API_KEY', wire_api: 'responses',
  });
  assert.equal(saved.providers.codex.executable, 'codex');
  assert.equal(saved.providers.codex.profiles.cloud.automation_home.startsWith(path.join(fs.realpathSync(input.dataRoot), UID)), true);
  assert.equal(fs.readFileSync(saved.providers.codex.profiles.cloud.auth_file, 'utf8').trim(), '{}');
  assert.equal(fs.statSync(result.env.AGENT_RUNNER_CONFIG).mode & 0o777, 0o600);
  assert.equal(input.env.AGENT_RUNNER_CONFIG, '/fixture/personal/config.json');
});
test('missing per-agent key or base URL stays unready and never reads personal config', t => {
  for (const name of ['OPENAI_API_KEY', 'OPENAI_BASE_URL']) {
    const input = fixture(t); delete input.env[name];
    const result = prepareMaritimeRuntime(input);
    assert.equal(result.config.modelReady, false);
    assert.equal(result.env.AGENT_RUNNER_CONFIG, undefined);
    assert.equal(result.env.LM_CLOUD_MODEL_API_KEY, undefined);
    assert.deepEqual(fs.readdirSync(input.dataRoot), []);
  }
});
test('foreign tenant symlink and unsafe base URL fail before runner setup', t => {
  const input = fixture(t);
  fs.mkdirSync(path.join(input.dataRoot, 'foreign'));
  fs.symlinkSync(path.join(input.dataRoot, 'foreign'), path.join(input.dataRoot, UID));
  assert.throws(() => prepareMaritimeRuntime(input), /tenant/);
  assert.deepEqual(fs.readdirSync(path.join(input.dataRoot, 'foreign')), []);
  fs.unlinkSync(path.join(input.dataRoot, UID));
  for (const url of ['http://api.maritime.sh/v1', 'https://user:pass@api.maritime.sh/v1', 'https://api.maritime.sh/v1?key=secret']) {
    assert.throws(() => prepareMaritimeRuntime({ ...input, env: { ...input.env, OPENAI_BASE_URL: url } }), /model/);
  }
});
test('setup rejects malformed identity and an incompatible existing automation route', t => {
  const input = fixture(t);
  assert.throws(() => prepareMaritimeRuntime({ ...input, env: { ...input.env, LM_RUNTIME_TENANT_ID: '../foreign' } }), /identity/);
  const changed = structuredClone(baseConfig);
  changed.task_classes['application-lane-agent'].candidates[0].provider = 'claude-direct';
  assert.throws(() => prepareMaritimeRuntime({ ...input, baseConfig: changed }), /route/);
});

test('generated profile is consumed by the actual existing Python runner without account auth', t => {
  const input = fixture(t); const result = prepareMaritimeRuntime(input);
  const { spawnSync } = require('node:child_process');
  const probe = spawnSync('python3', ['-c', `
import sys,json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'runtime/agent-runner'))
import agent_runner as runner
request=json.load(sys.stdin)
config=request['config']
candidate=runner.resolve_provider_profiles(config['task_classes']['application-lane-agent']['candidates'],config['providers'])[0]
provider=dict(config['providers']['codex'], **candidate)
child=runner.provider_process_env('codex',provider,environ={'LM_CLOUD_MODEL_API_KEY':'fixture-key','HOME':request['home'],'PATH':'/usr/bin:/bin'},task_class='application-lane-agent')
assert child['LM_CLOUD_MODEL_API_KEY']=='fixture-key'
assert Path(child['CODEX_HOME']).is_relative_to(Path(request['home']))
assert Path(child['CODEX_HOME'],'auth.json').read_text().strip()=='{}'
assert 'LM_CLOUD_MODEL_API_KEY' in runner.codex_model_providers_toml(provider['model_providers'])
print('existing-runner-profile-contract-pass')
`], { cwd: releaseRoot, input: JSON.stringify({ config: JSON.parse(fs.readFileSync(result.env.AGENT_RUNNER_CONFIG)), home: path.join(fs.realpathSync(input.dataRoot), UID) }),
    env: { PATH: process.env.PATH, HOME: input.dataRoot, PYTHONDONTWRITEBYTECODE: '1' }, encoding: 'utf8' });
  assert.equal(probe.status, 0, probe.stderr);
  assert.equal(probe.stdout.trim(), 'existing-runner-profile-contract-pass');
});
