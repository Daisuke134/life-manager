import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url);
const read=p=>readFileSync(new URL(p,root),'utf8');
const ids={'Anicca':'6755129214','Honne':'6759667221','Thankful':'6759514159','Daily Dhamma':'6757726663','Sleep Reset':'6762143790','STUDIO CHERIE':'6766485903'};
for(const file of ['products-en.html','products.html']) test(`${file}: exactly six published mobile cards with official identities`,()=>{
 const html=read(`pages/${file}`);
 const cards=[...html.matchAll(/<article\b[^>]*data-category="mobile"[^>]*>(.*?)<\/article>/gs)].map(m=>m[1]);
 assert.equal(cards.length,6);
 assert.deepEqual(cards.map(c=>c.match(/<h3>(.*?)<\/h3>/s)[1]).sort(),Object.keys(ids).sort());
 for(const card of cards){const name=card.match(/<h3>(.*?)<\/h3>/s)[1];assert.match(card,new RegExp(`https://apps\\.apple\\.com/us/app/[^" ]*/id${ids[name]}`));}
 assert.doesNotMatch(html,/BreathCalm|CalmCortisol|ImpulseLog/);
 const cherie=cards.find(c=>c.includes('STUDIO CHERIE'));
 assert.match(cherie,/アプリの紹介/);assert.match(cherie,/href="\/studio-cherie"/);
 assert.match(html,/id="mobile-apps"/);assert.match(html,/id="web-products"/);assert.match(html,/id="research-projects"/);
});
for(const [file,status] of [['products-en.html','preparing to open'],['products.html','公開準備中']]) test(`${file}: AI Monk Factory is listed with its current availability`,()=>{
 const html=read(`pages/${file}`);
 const section=html.match(/<section\b[^>]*id="web-products"[^>]*>[\s\S]*?<\/section>/)?.[0]||'';
 const card=[...section.matchAll(/<article\b[^>]*>([\s\S]*?)<\/article>/g)].map(m=>m[1]).find(c=>c.includes('<h3>AI Monk Factory</h3>'));
 assert.ok(card,'AI Monk Factory card is present in the web-products section');
 assert.ok(card.includes(status),'availability is stated in the page locale');
 assert.ok(card.includes('href="/ai-monk-factory"'),'card links to the real Factory route');
});
test('primary nav exposes Articles on all home and portfolio locales',()=>{
 for(const file of ['en.html','ja.html','products-en.html','products.html']){
  const nav=read(`pages/${file}`).match(/<nav\b.*?<\/nav>/s)[0];
  assert.match(nav,/<a href="\/blog">(?:Articles|記事)<\/a>/);
 }
});
test('route manifest verifies every shipped byte and preserves public routes',()=>{
 const manifest=JSON.parse(read('route-manifest.json'));
 for(const f of manifest.files) assert.equal(createHash('sha256').update(readFileSync(new URL(f.source,root))).digest('hex'),f.sha256,f.source);
 assert.equal(manifest.files.find(f=>f.public_route==='/dais').source,'pages/products-en.html');
 assert.equal(manifest.files.find(f=>f.public_route==='/dais/ja').source,'pages/products.html');
});
