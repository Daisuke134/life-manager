'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

// Translate this VM's platform-injected model access into the existing runner
// schema. No personal profile, credential value, or second model router is saved.
function prepareMaritimeRuntime({ env = process.env, baseConfig, dataRoot = '/data', releaseRoot = '/app' } = {}) {
  const tenantId = env.LM_RUNTIME_TENANT_ID;
  const releaseSha = env.LM_RELEASE_SHA;
  if (typeof tenantId !== 'string' || !/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(tenantId)
    || typeof releaseSha !== 'string' || !/^[0-9a-f]{40}$/.test(releaseSha)) throw new Error('maritime_runtime_identity_invalid');
  const child = { ...env };
  for (const name of ['AGENT_RUNNER_CONFIG', 'LM_CLOUD_MODEL_API_KEY', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR']) delete child[name];
  const key = env.OPENAI_API_KEY;
  const base = env.OPENAI_BASE_URL;
  const config = { tenantId, releaseSha, modelReady: false };
  if (!key || !base) return { config, env: child };
  if (typeof key !== 'string' || /[\r\n\0]/.test(key)) throw new Error('maritime_runtime_model_invalid');
  let url;
  try { url = new URL(base); } catch { throw new Error('maritime_runtime_model_invalid'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('maritime_runtime_model_invalid');
  const original = baseConfig || JSON.parse(fs.readFileSync(path.join(releaseRoot, 'runtime/agent-runner/config.json'), 'utf8'));
  const task = structuredClone(original.task_classes?.['application-lane-agent']);
  if (task?.candidates?.[0]?.provider !== 'codex' || typeof task.candidates[0].model !== 'string') {
    throw new Error('maritime_runtime_route_invalid');
  }
  fs.mkdirSync(dataRoot, { recursive: true, mode: 0o700 });
  const root = fs.realpathSync(dataRoot);
  const restricted = process.platform === 'linux' && process.getuid?.() === 0;
  const directoryFlags = fs.constants.O_RDONLY | fs.constants.O_DIRECTORY | fs.constants.O_NOFOLLOW;
  if (restricted) {
    const fd = fs.openSync(root, directoryFlags);
    try { fs.fchownSync(fd, 0, 0); fs.fchmodSync(fd, 0o711); } finally { fs.closeSync(fd); }
  }
  const home = path.join(root, tenantId);
  if (fs.existsSync(home) && fs.lstatSync(home).isSymbolicLink()) throw new Error('maritime_runtime_tenant_invalid');
  fs.mkdirSync(home, { recursive: true, mode: 0o700 });
  if (fs.realpathSync(home) !== home) throw new Error('maritime_runtime_tenant_invalid');
  const codexHome = path.join(home, 'agent-codex');
  if (fs.existsSync(codexHome) && fs.lstatSync(codexHome).isSymbolicLink()) throw new Error('maritime_runtime_tenant_invalid');
  if (restricted) {
    // Only fixed tenant directories change ownership, through no-follow fds.
    // Never recursively chown model-controlled paths or the immutable release.
    for (const target of [home, ...['home', 'agent-codex', 'claude', 'tmp', 'agent-ledgers', 'state', 'runtime', 'evidence', 'build'].map(name => path.join(home, name))]) {
      try { fs.mkdirSync(target, { mode: 0o700 }); } catch (error) { if (error.code !== 'EEXIST') throw error; }
      const fd = fs.openSync(target, directoryFlags);
      try { fs.fchownSync(fd, 10001, 10001); fs.fchmodSync(fd, 0o700); } finally { fs.closeSync(fd); }
    }
  }
  function atomicJson(target, value) {
    const temporary = path.join(home, `.runtime-${randomUUID()}.json`);
    try {
      const fd = fs.openSync(temporary, 'wx', 0o600);
      try {
        if (restricted) fs.fchownSync(fd, 10001, 10001);
        fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n');
      } finally { fs.closeSync(fd); }
      fs.renameSync(temporary, target);
    } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  }
  // Existing runner requires an auth-file reference even for an env-key provider.
  // This marker has no credentials; actual per-agent access remains in memory/env.
  const authFile = path.join(home, 'runner-auth-empty.json');
  atomicJson(authFile, {});
  task.candidates = [{ ...task.candidates[0], profile_alias: 'cloud' }];
  const oldProvider = original.providers?.codex || {};
  const provider = {
    executable: 'codex', executable_fallbacks: [],
    profiles: { cloud: { automation_home: codexHome, auth_file: authFile } }, account_profile_order: ['cloud'],
    model_provider: 'maritime',
    model_providers: { maritime: { name: 'Maritime', base_url: base, env_key: 'LM_CLOUD_MODEL_API_KEY', wire_api: 'responses' } },
  };
  for (const name of ['project_doc_max_bytes', 'disabled_skills', 'disabled_features', 'capabilities']) {
    if (oldProvider[name] !== undefined) provider[name] = structuredClone(oldProvider[name]);
  }
  provider.cost_tier = 'metered';
  const cert = ['/etc/ssl/certs/ca-certificates.crt', '/etc/ssl/cert.pem'].find(value => fs.existsSync(value));
  if (cert) provider.ssl_cert_file = cert;
  const filename = path.join(home, 'runner.json');
  atomicJson(filename, { version: 1, scope: 'life-manager', timeout_seconds: task.timeout_seconds,
    providers: { codex: provider }, task_classes: { 'application-lane-agent': task } });
  child.LM_CLOUD_MODEL_API_KEY = key;
  child.AGENT_RUNNER_CONFIG = filename;
  child.LM_RUNTIME_HOST = 'maritime';
  child.LIFE_MANAGER_STATE_HOME = home;
  child.LIFE_MANAGER_BUILD_WORKSPACE = path.join(home, 'build');
  child.LIFE_MANAGER_RELEASE_ROOT = releaseRoot;
  child.LIFE_MANAGER_REPO = releaseRoot;
  config.modelReady = true;
  return { config, env: child };
}
module.exports = { prepareMaritimeRuntime };
