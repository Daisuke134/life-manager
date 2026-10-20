import test from 'node:test';
import assert from 'node:assert/strict';
import * as installer from '../install.mjs';
import {validatePublication,digest} from '../package-contract.mjs';
const article=slug=>({slug,lang:'en',project:'Manager',package_path:`en/${slug}.md`,markdown:'# Fixture only',sha256:digest('# Fixture only'),word_count:3,n_papers_cited:0,canonical_url:`https://aniccaai.com/blog/${slug}`,title:'Fixture',date:'2026-10-20'});
const pkg=slug=>({articles:[article(slug)],media:[]});
function merge(a,b) {assert.equal(typeof installer.mergePublicationPackages,'function','supplement support must exist');return installer.mergePublicationPackages(a,b,validatePublication);}
test('preserves existing articles and adds the new package without mutation',()=>{let a=pkg('manager-old-en'),b=pkg('manager-new-en'),copy=JSON.stringify([a,b]);let r=merge(a,b);assert.equal(r.articles.length,2);assert.equal(JSON.stringify([a,b]),copy);assert.deepEqual(r.articles[0],a.articles[0]);});
test('rejects duplicate article replacement',()=>assert.throws(()=>merge(pkg('manager-old-en'),pkg('manager-old-en')),/Duplicate/));
test('rejects unreviewed content hash',()=>{let p=pkg('manager-new-en');p.articles[0].markdown='changed';assert.throws(()=>merge(pkg('manager-old-en'),p),/hash mismatch/);});
test('rejects path traversal',()=>{let p=pkg('manager-new-en');p.articles[0].package_path='../secret';assert.throws(()=>merge(pkg('manager-old-en'),p),/article path/);});
test('rejects unrelated product',()=>{let p=pkg('manager-new-en');p.articles[0].project='Other';assert.throws(()=>merge(pkg('manager-old-en'),p),/identity/);});
test('does not discard existing media',()=>{let a=pkg('manager-old-en'),h='a'.repeat(64);a.media=[{sha256:h,package_path:`media/${h}.png`,public_url:`https://aniccaai.com/blog/manager/media/${h}.png`}];assert.deepEqual(merge(a,pkg('manager-new-en')).media,a.media);});
test('loads supplemental Markdown from its hash-checked file rather than duplicated JSON',async()=>{let p=pkg('manager-new-en'),body=p.articles[0].markdown;delete p.articles[0].markdown;assert.equal(typeof installer.loadSupplement,'function');let seen=[];let r=await installer.loadSupplement(p,async path=>{seen.push(path);return Buffer.from(body)},validatePublication);assert.equal(r.articles[0].markdown,body);assert.deepEqual(seen,['en/manager-new-en.md']);});
test('rejects supplementary traversal before reading any file',async()=>{let p=pkg('manager-new-en');p.articles[0].package_path='../secret';let calls=0;assert.equal(typeof installer.loadSupplement,'function');await assert.rejects(()=>installer.loadSupplement(p,async()=>{calls++;return Buffer.from('')},validatePublication),/article path/);assert.equal(calls,0);});
test('rejects a fetched supplementary file with the wrong content hash',async()=>{assert.equal(typeof installer.loadSupplement,'function');await assert.rejects(()=>installer.loadSupplement(pkg('manager-new-en'),async()=>Buffer.from('bad'),validatePublication),/hash mismatch/);});
