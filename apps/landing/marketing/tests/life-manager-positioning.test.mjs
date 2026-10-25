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
  assert.match(html, /Google sign-in is the web starting point and verifies identity only/i);
  assert.match(html, /Work and results are designed to be verified and reported to your sign-in email/i);
  assert.match(html, /No Calendar, Gmail inbox, task prompt, goal, budget, or payout details are required at signup/i);
  assert.match(html, /No task, goal, budget, or daily prompt is required to start the earning workflow/i);
  assert.match(html, /Capafy requires Publisher Certification before the first Skill can publish/i);
  assert.match(html, /confirm the selected Skills and configuration on Capafy's website for each new or updated version/i);
  assert.match(html, /will not report a live listing or earnings until Capafy confirms them/i);
  assert.match(html, /payout details can be added after certification/i);
  assert.match(html, /earnings are not guaranteed/i);
  assert.match(html, /Start on the web with Google sign-in/i);
  assert.doesNotMatch(html, /Telegram is required|Connect Google Calendar/);
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
  assert.match(html, /GoogleログインはWebで始める本人確認だけです/);
  assert.match(html, /仕事と結果を確認し、ログインで使ったメールアドレスへ報告する設計です/);
  assert.match(html, /登録時にCalendarやGmailの受信箱、タスク、目標、予算、振込先情報は求めません/);
  assert.match(html, /初回にタスク、目標、予算を入力したり、毎日指示したりする必要はありません/);
  assert.match(html, /Capafyでは最初のSkillを公開する前にPublisher Certificationが必要です/);
  assert.match(html, /新しいAgentやバージョン更新ごとに、Capafy上で選択したSkillと設定内容を確認・確定する必要があります/);
  assert.match(html, /公開や収益を確認できるまで、公開済み・収益発生とは報告しません/);
  assert.match(html, /振込先情報は認証後に追加できます/);
  assert.match(html, /収益は保証されません/);
  assert.match(html, /WebからGoogleログインで始められます/);
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
