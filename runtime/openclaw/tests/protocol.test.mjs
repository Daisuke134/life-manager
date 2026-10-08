import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveHarnessPaths } from '../paths.mjs';
import { validateRunRequest, buildRunIdentity } from '../protocol.mjs';

export const fixture = () => ({
  version: 2, owner_id: 'writer', occurrence_id: 'wake:001', run_id: 'attempt-1',
  task_id: 'draft', release_sha: 'a'.repeat(40), task_class: 'writer-agent',
  provider: 'codex', model: 'account-default', effort: 'medium', prompt: 'Write a draft',
  schema: {type: 'object'}, workdir: '/srv/lm/work', timeout_seconds: 60,
  effect_mode: 'read_only', session_isolation: 'stable_owner',
  attachments: [], owned_resume_ref: null,
});
test('portable paths retain the existing LM data root and never global OpenClaw', () => {
  for (const home of ['/home/alice', '/Users/bob', '/srv/lm']) {
    const p = resolveHarnessPaths({}, home);
    assert.equal(p.stateRoot, `${home}/.local/state/life-manager/openclaw`);
    assert.equal(p.credentialFile, `${home}/.local/share/anicca/credentials.json`);
  }
  assert.throws(() => resolveHarnessPaths({LM_DATA_DIR: 'relative'}, '/home/alice'));
  assert.throws(() => resolveHarnessPaths({LM_CREDENTIALS_FILE: 'relative'}, '/home/alice'));
});
test('request validation rejects ambiguous and non-native routes without modifying input', () => {
  const input = fixture(); const copy = structuredClone(input);
  const out = validateRunRequest(input);
  assert.deepEqual(input, copy);
  assert.ok(Object.isFrozen(out.schema));
  for (const patch of [{prompt: ''}, {timeout_seconds: true}, {owner_id: '../writer'},
    {provider: 'openai'}, {workdir: 'relative'}, {unexpected: 1}, {schema: []},
    {attachments: [{path: '/tmp/a.png', mime_type: 'image/png', sha256: 'bad'}]}]) {
    assert.throws(() => validateRunRequest({...input, ...patch}));
  }
});
test('a retry keeps its key across caller restarts and releases, while logical tasks differ', () => {
  const a = buildRunIdentity(validateRunRequest(fixture()), 'manager');
  const b = buildRunIdentity(validateRunRequest({...fixture(), run_id: 'attempt-2', release_sha: 'b'.repeat(40)}), 'manager');
  assert.deepEqual(a, b);
  const c = buildRunIdentity(validateRunRequest({...fixture(), task_id: 'review'}), 'manager');
  assert.notEqual(a.idempotencyKey, c.idempotencyKey);
  assert.equal(a.sessionKey, c.sessionKey);
  const fresh = patch => buildRunIdentity(validateRunRequest({...fixture(), session_isolation: 'fresh_task', ...patch}), 'manager');
  assert.notEqual(fresh({}).sessionKey, fresh({task_id: 'review'}).sessionKey);
  assert.throws(() => buildRunIdentity(validateRunRequest(fixture()), '../manager'));
});
test('request digest catches changed content and release while ignoring caller restart',async()=>{
 const {requestDigest}=await import('../protocol.mjs');
 const a=fixture();
 assert.equal(requestDigest(a),requestDigest({...a,run_id:'attempt-2'}));
 for(const patch of [{prompt:'new prompt'},{schema:{type:'array'}},{release_sha:'b'.repeat(40)}])assert.notEqual(requestDigest(a),requestDigest({...a,...patch}));
 assert.equal(requestDigest({...a,schema:{type:'object',properties:{a:{type:'string'}}}}),requestDigest({...a,schema:{properties:{a:{type:'string'}},type:'object'}}));
});
test('non-JSON schemas cannot silently change during request cloning',()=>{
 for(const schema of [{value:NaN},{value:undefined},{value:()=>1},new Date()])assert.throws(()=>validateRunRequest({...fixture(),schema}));
});
test('JSON arrays cannot impersonate typed SHA strings through regex coercion',()=>{
 assert.throws(()=>validateRunRequest({...fixture(),release_sha:['a'.repeat(40)]}));
 assert.throws(()=>validateRunRequest({...fixture(),attachments:[{path:'/srv/lm/image.png',mime_type:'image/png',sha256:['a'.repeat(64)]}]}));
});
