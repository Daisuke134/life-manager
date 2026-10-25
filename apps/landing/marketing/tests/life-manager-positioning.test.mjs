import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');

test('English Life Manager page presents one broad product and its Cloud target', () => {
  const html = read('pages/life-manager-en.html');

  assert.match(html, /Life Manager is being built as one proactive manager for work, income, everyday responsibilities, body, and mind\./);
  assert.match(html, /same open-source core locally/);
  assert.match(html, /dedicated Maritime VM/);
  assert.match(html, /phone-first/);
  assert.match(html, /Calendar travel-time planning is one workflow, not the product\./);
  assert.doesNotMatch(html, /Start with the hosted Calendar assistant/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/lm').sha256, sha256('pages/life-manager-en.html'));
});

test('Japanese Life Manager page keeps the same broad product position', () => {
  const html = read('pages/life-manager.html');

  assert.match(html, /仕事、収入、日々の用事、体、心/);
  assert.match(html, /同じオープンソースコア/);
  assert.match(html, /Maritime上の専用VM/);
  assert.match(html, /スマートフォン/);
  assert.match(html, /移動時間の計画は、Life Managerのひとつの機能です/);
  assert.doesNotMatch(html, /ホスト版はカレンダー管理から/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/lm/ja').sha256, sha256('pages/life-manager.html'));
});
