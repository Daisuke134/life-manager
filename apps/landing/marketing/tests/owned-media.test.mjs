import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url);
const read=p=>readFileSync(new URL(p,root),'utf8');
test('six app cards use real official icon assets and no arrow CTAs',()=>{
 for(const name of ['products-en.html','products.html']){
  const cards=[...read('pages/'+name).matchAll(/<article\b[^>]*data-category="mobile"[^>]*>(.*?)<\/article>/gs)].map(m=>m[1]);
  assert.equal(cards.length,6);
  for(const card of cards){assert.match(card,/<img[^>]+src="\/assets\/manager-site\/apps\//);assert.doesNotMatch(card,/[↗↖↥↑⬆🔗]/u);}
  assert.doesNotMatch(cards.join(''),/App Storeと公式サイトはこちら/);
 }
});
test('one verified registry supplies six identities, languages, factual copy and hash-bound icons',()=>{
 assert.ok(existsSync(new URL('assets/published-apps.json',root)),'canonical app registry missing');
 const apps=JSON.parse(read('assets/published-apps.json'));
 assert.deepEqual(apps.map(a=>a.id).sort(),['6755129214','6759667221','6759514159','6757726663','6762143790','6766485903'].sort());
 for(const a of apps){assert.match(a.store,new RegExp('/id'+a.id+'$'));assert.equal(createHash('sha256').update(readFileSync(new URL('assets/apps/'+a.icon.split('/').at(-1),root))).digest('hex'),a.iconSha256);assert.ok(a.description.en.length>30);}
 assert.deepEqual(apps.find(a=>a.id==='6755129214').storeLanguages,['EN','FR','DE','JA','PT','ES']);
 assert.ok(apps.filter(a=>a.id!=='6755129214').every(a=>a.storeLanguages.join()==='EN'));
 assert.equal(apps.find(a=>a.id==='6766485903').presentationLanguage,'ja');
 assert.match(apps.find(a=>a.id==='6762143790').description.en,/subscription/);
 assert.equal(apps.find(a=>a.id==='6759514159').iconSha256,'9dc87b7f546c507f52d7794fab3e46fb2fd05f5a691395c0a969813d18393a80');
});

test('entire published marketing pages have no upward or external arrow glyphs',()=>{
 const manifest=JSON.parse(read('route-manifest.json'));
 for(const source of new Set(manifest.files.map(f=>f.source).filter(p=>p.endsWith('.html')))){
  assert.doesNotMatch(read(source),/[↗↖↥↑⬆]/u,source);
 }
});

test('published app cards lead to their dedicated introductions in both portfolio locales',()=>{
 const destinations={'6757726663':'/dailydharma','6762143790':'/sleepreset','6766485903':'/studio-cherie'};
 const apps=JSON.parse(read('assets/published-apps.json'));
 for(const [id,destination] of Object.entries(destinations)){
  const app=apps.find(a=>a.id===id);
  for(const locale of ['en','ja'])assert.equal(app.intro[locale],destination);
  for(const file of ['products-en.html','products.html']){
   const card=[...read('pages/'+file).matchAll(/<article\b[^>]*data-category="mobile"[^>]*>(.*?)<\/article>/gs)].map(m=>m[1]).find(c=>c.includes('/id'+id));
   assert.ok(card.includes(`href="${destination}"`));
  }
 }
});

test('portfolio leads with Manager then Life Manager and excludes Lookmax promotion',()=>{
 for(const file of ['products-en.html','products.html']){
  const html=read('pages/'+file);const main=html.match(/<main\b.*?<\/main>/s)[0];
  const headings=[...main.matchAll(/<h3>(.*?)<\/h3>/g)].map(m=>m[1]);
  assert.deepEqual(headings.slice(0,2),['Manager','Life Manager']);
  assert.doesNotMatch(main,/Lookmax/);
  for(const label of ['Anicca Letter','Anicca Music','Anicca Comedy'])assert.ok(headings.includes(label));
  assert.match(main,/id="creative-work"/);assert.match(main,/id="research-projects"/);
 }
});
