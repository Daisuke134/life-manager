import test from 'node:test';
import assert from 'node:assert/strict';

const module = await import('./project.mjs').catch(() => ({}));
const draft = { project_id: 'monk-demo', language: 'en', avatar_id: '', voice_id: '', platform: 'tiktok',
  integration_id: '', native_handle: '', product_name: '', product_url: '', brief: 'Explain patient attention.', script: '', cta: '' };
const ready = { ...draft, avatar_id: 'avatar_123', voice_id: 'voice_123', integration_id: 'integration-1', native_handle: 'monk.demo',
  product_name: 'Attention guide', product_url: 'https://example.test/guide', cta: 'Read the guide' };

test('brief drafts save before provider setup, but incomplete projects cannot start a run', () => {
  assert.equal(typeof module.validateProject, 'function', 'shared project validation is missing');
  assert.deepEqual(module.validateProject(draft), draft);
  assert.throws(() => module.validateProject(draft, { ready: true }));
  assert.deepEqual(module.validateProject(ready, { ready: true }), ready);
});

test('unknown or secret fields, path-like IDs, unsafe URLs, and oversized input are rejected', () => {
  assert.equal(typeof module.validateProject, 'function');
  for (const changed of [{ api_key: 'never-store' }, { schema_version: 'wrong-layer' }, { project_id: '../other' },
    { product_url: 'javascript:alert(1)' }, { product_url: 'https://user:pass@example.test/' }, { native_handle: '../bad' },
    { avatar_id: 'bad' }, { script: 'x'.repeat(5001) }, { brief: '' }, { state_root: '/tmp/other' }]) {
    assert.throws(() => module.validateProject({ ...ready, ...changed }));
  }
  assert.equal(module.validateProject({ ...ready, product_name: '  Guide  ' }).product_name, 'Guide');
});
