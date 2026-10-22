import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
for(const locale of ['en','ja']) {
 test(`${locale}: mission leads, research precedes separate product destination`,()=>{
  const html=read(`pages/${locale}.html`),hero=html.match(/<section class="hero">[\s\S]*?<\/section>/)?.[0]||'';
  assert.match(html,/<body class="manager-mission">/);
  assert.equal((html.match(/<h1\b/g)||[]).length,1);
  assert.match(hero,/class="btn" href="#research"/);
  assert.doesNotMatch(hero,/apps\.apple\.com|phone|href="\/dais"/i);
  assert.match(html,/href="\/products\/"/);
  assert.match(html,new RegExp(`href="/dais${locale==='ja'?'/ja':''}"`));
  assert.ok(html.indexOf('id="research"')<html.indexOf('class="product-entry"'));
  assert.match(html,/<meta name="robots" content="index,follow">/);
  assert.match(html,new RegExp(`rel="canonical" href="https://aniccaai.com/${locale}"`));
 });
 test(`${locale}: conceptual illustration has static fallback and accessible pause`,()=>{
  const html=read(`pages/${locale}.html`);
  assert.match(html,/id="motion-pause" type="checkbox"/);
  assert.match(html,/<label for="motion-pause">/);
  assert.match(html,/aria-labelledby="scene-title scene-desc"/);
  assert.match(html,/class="scene-person"/);
  assert.doesNotMatch(html,/<animateMotion|<script[^>]+src=/);
  assert.match(html,locale==='en'?/Concept illustration, not a prediction/:/予測結果ではありません/);
 });
}
test('motion is bounded, pausable and honors reduced motion without JavaScript',()=>{
 const css=read('assets/styles.css');
 assert.match(css,/#motion-pause:checked[\s\S]*?animation-play-state:\s*paused/);
 assert.match(css,/@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.manager-mission[\s\S]*?animation:\s*none/);
 assert.match(css,/\.manager-mission[\s\S]*?:focus-visible/);
});
