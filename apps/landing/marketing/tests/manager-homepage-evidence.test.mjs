import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');
const visibleText = (html) => html.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ');

test('English Manager homepage exposes current evidence, research, and honest limits', () => {
  const html = read('pages/en.html');
  const text = visibleText(html);

  assert.match(text, /67 published articles: 38 in English and 29 in Japanese/i);
  assert.match(text, /90 existing AI evaluations/i);
  assert.match(text, /OIDC checkpoint restore/i);
  assert.match(text, /positive canary[^.]*STOP \/ rollback[^.]*native-observation/i);
  assert.match(text, /Manager has not yet demonstrated reliable human-behavior prediction or real-world effects of intervention/i);
  assert.match(text, /entity Anicca aims to build/i);
  assert.match(text, /beneficiaries should not need a dedicated app or chat/i);
  assert.match(text, /operator oversight, audit, and stop controls remain/i);
  assert.match(html, /href="https:\/\/aniccaai\.com\/blog\/manager"/);
  assert.match(html, /href="https:\/\/aniccaai\.com\/blog\/manager-eba-benchmark-landscape-en"/);
  assert.match(text, /Ampersand/);
  assert.match(text, /Persimmon/);
  assert.match(text, /Boba/);
  assert.match(text, /persuasive|persuasion/i);
  assert.match(html, /href="https:\/\/github\.com\/Daisuke134\/life-manager\/blob\/main\/products\/manager\/docs\/verification\/E16_CLOUD_EXECUTION_20261023\.md"/);
  assert.doesNotMatch(html, /blob\/docs\/manager-learning-20261017/);

  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/')?.sha256, sha256('pages/en.html'));
});

test('Japanese Manager homepage exposes the same evidence boundaries and research library', () => {
  const html = read('pages/ja.html');
  const text = visibleText(html);

  assert.match(text, /英語38本・日本語29本、計67本の記事/);
  assert.match(text, /AI評価90件/);
  assert.match(text, /GitHub OIDCによるcheckpoint restore・update・release/i);
  assert.match(text, /positive canary[^.]*STOP \/ rollback[^.]*native observation/i);
  assert.match(text, /人の行動を確かに予測し、介入によって現実の結果を改善したことは、まだ実証していません/);
  assert.match(text, /Aniccaが生み出すことを目指すAIエンティティ/);
  assert.match(text, /受益者に専用のアプリやチャット操作を求めない構想/);
  assert.match(text, /運営者の監督・監査・停止手段は保ちます/);
  assert.match(html, /href="https:\/\/aniccaai\.com\/blog\/manager"/);
  assert.match(html, /href="https:\/\/aniccaai\.com\/blog\/manager-eba-benchmark-landscape-en"/);
  assert.match(text, /Ampersand/);
  assert.match(text, /Persimmon/);
  assert.match(text, /Boba/);
  assert.match(text, /説得/);
  assert.match(html, /href="https:\/\/github\.com\/Daisuke134\/life-manager\/blob\/main\/products\/manager\/docs\/verification\/E16_CLOUD_EXECUTION_20261023\.md"/);
  assert.doesNotMatch(html, /blob\/docs\/manager-learning-20261017/);

  const manifest = JSON.parse(read('route-manifest.json'));
  assert.equal(manifest.files.find((file) => file.public_route === '/ja')?.sha256, sha256('pages/ja.html'));
});
