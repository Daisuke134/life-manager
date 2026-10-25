import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');

test('English Life Manager page presents one broad product and its Cloud target', () => {
  const html = read('pages/life-manager-en.html');

  assert.match(html, /Life Manager is being built as one proactive manager for work, money, everyday responsibilities, body, and mind\./);
  assert.match(html, /same open-source core locally/);
  assert.match(html, /dedicated Maritime VM/);
  assert.match(html, /from your phone/);
  assert.match(html, /Google sign-in verifies identity only/i);
  assert.match(html, /Progress and verified results are designed to go to your sign-in email/i);
  assert.match(html, /signup does not require Calendar or Gmail inbox access, a task prompt, goals, budget, or payout details/i);
  assert.match(html, /No daily instructions or user-defined goals and budgets are required/i);
  assert.match(html, /Capafy requires Publisher Certification and publisher confirmation of selected Skills and configuration before each Agent version can go live/i);
  assert.match(html, /reports listings and earnings only after Capafy confirms them/i);
  assert.match(html, /earnings are not guaranteed/i);
  assert.doesNotMatch(html, /Telegram is required|Connect Google Calendar/);
  assert.doesNotMatch(html, /Start with the hosted Calendar assistant/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  assert.match(html, /href="\/maritime\?source=landing&amp;lang=en"/);
  assert.equal((html.match(/<a[^>]*data-lm-cloud-entry/g) || []).length, 3);
  assert.doesNotMatch(html, /life-call-production\.up\.railway\.app/);
  assert.doesNotMatch(html, /href="https:\/\/life-call-production\.up\.railway\.app\/lm\?start_calendar=1"/);
  assert.match(html, /Capafy/);
  assert.doesNotMatch(html, /Illustrative workflow|class="dashboard"/);
  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/lm').sha256, sha256('pages/life-manager-en.html'));
});

test('Japanese Life Manager page keeps the same broad product position', () => {
  const html = read('pages/life-manager.html');

  assert.match(html, /仕事、お金、日々の用事、体と心をひとつで管理する自発型マネージャーとして開発中です/);
  assert.match(html, /同じオープンソースコア/);
  assert.match(html, /専用Maritime VM/);
  assert.match(html, /スマートフォン/);
  assert.match(html, /Googleログインは本人確認だけに使います/);
  assert.match(html, /確認済みの進捗・結果はログイン時のメールへ報告する設計です/);
  assert.match(html, /登録時にCalendarやGmail受信箱、タスク、目標、予算、振込先情報は求めません/);
  assert.match(html, /公開前にはPublisher Certificationと、Agentの各バージョンごとのSkill・設定内容の確認がCapafy上で必要です/);
  assert.match(html, /Capafyの確認前に公開や収益を報告しません/);
  assert.match(html, /収益は保証されません/);
  assert.doesNotMatch(html, /ホスト版はカレンダー管理から/);
  assert.doesNotMatch(html, /CLOUD · CALENDAR ASSISTANT/);
  assert.match(html, /href="\/maritime\?source=landing&amp;lang=ja"/);
  assert.equal((html.match(/<a[^>]*data-lm-cloud-entry/g) || []).length, 3);
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
