import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');

test('English Life Manager page presents one broad product and its Cloud target', () => {
  const html = read('pages/life-manager-en.html');

  assert.match(html, /Life Manager is one proactive manager for work, money, everyday responsibilities, body, and mind\./);
  assert.match(html, /same open-source core locally/);
  assert.match(html, /dedicated cloud VM/);
  assert.match(html, /from your phone/);
  assert.match(html, /Google Calendar is optional and is not required to start/);
  assert.match(html, /Google sign-in verifies your identity only; it does not request Calendar or Gmail access/i);
  assert.match(html, /Work summaries are designed to arrive at your verified sign-in email/i);
  assert.doesNotMatch(html, /Start with the hosted Calendar assistant/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  assert.match(html, /href="\/maritime\?source=landing&amp;lang=en"/);
  assert.doesNotMatch(html, /life-call-production\.up\.railway\.app/);
  assert.doesNotMatch(html, /href="https:\/\/life-call-production\.up\.railway\.app\/lm\?start_calendar=1"/);
  assert.match(html, /Capafy/);
  assert.doesNotMatch(html, /Illustrative workflow|class="dashboard"/);
  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/lm').sha256, sha256('pages/life-manager-en.html'));
});

test('Japanese Life Manager page keeps the same broad product position', () => {
  const html = read('pages/life-manager.html');

  assert.match(html, /仕事、お金、日々の用事、体と心/);
  assert.match(html, /同じオープンソースコア/);
  assert.match(html, /専用クラウドVM/);
  assert.match(html, /スマートフォン/);
  assert.match(html, /Google Calendarの接続は任意で、初回には不要です/);
  assert.match(html, /Googleログインは本人確認だけで、CalendarやGmailの読み取り権限は求めません/);
  assert.match(html, /仕事の概要は確認済みメールアドレスへ送る設計です/);
  assert.doesNotMatch(html, /ホスト版はカレンダー管理から/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  assert.match(html, /href="\/maritime\?source=landing&amp;lang=ja"/);
  assert.doesNotMatch(html, /life-call-production\.up\.railway\.app/);
  assert.doesNotMatch(html, /href="https:\/\/life-call-production\.up\.railway\.app\/lm\?start_calendar=1"/);
  assert.match(html, /Capafy/);
  assert.doesNotMatch(html, /実際の活動記録ではありません|class="dashboard"/);
  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/lm/ja').sha256, sha256('pages/life-manager.html'));
});

test('every published overlay file matches its immutable manifest hash', () => {
  const manifest = JSON.parse(read('route-manifest.json'));

  for (const file of manifest.files) {
    assert.equal(sha256(file.source), file.sha256, `stale SHA-256 for ${file.source}`);
  }
});
