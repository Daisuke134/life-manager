import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url);
const read=p=>readFileSync(new URL(p,root),'utf8');
test('founder profile is reachable from the existing English and Japanese pages',()=>{
 for(const file of ['en','products-en','life-manager-en']) assert.match(read(`pages/${file}.html`),/href="\/about"/);
 for(const file of ['ja','products','life-manager']) assert.match(read(`pages/${file}.html`),/href="\/about\/ja"/);
});
test('public profiles preserve evidence boundaries and only the public contact',()=>{
 for(const path of ['pages/about.html','pages/about-ja.html']){
  assert.ok(existsSync(new URL(path,root)),'public profile must exist');
  const html=read(path);assert.match(html,/contact@aniccaai\.com/);assert.match(html,/href="\/cv\.pdf"/);
  assert.match(html,/1,042,763/);assert.match(html,/441,570/);
  assert.doesNotMatch(html,/keiodaisuke|visa sponsorship|Three-month notice|staff members|Incorporated/i);
 }
 assert.match(read('pages/about.html'),/Solo Founder/);assert.match(read('pages/about.html'),/AI-assisted/);assert.match(read('pages/about.html'),/remain unvalidated/);
});
test('manifest includes profile and resume assets with verified integrity',()=>{
 const manifest=JSON.parse(read('route-manifest.json'));
 for(const exportPath of ['about.html','about/ja.html','cv.pdf']){
  const f=manifest.files.find(x=>x.export_path===exportPath);assert.ok(f,exportPath);
  assert.equal(createHash('sha256').update(readFileSync(new URL(f.source,root))).digest('hex'),f.sha256);
 }
});
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
function overlay(tamper=false){
 const cwd=mkdtempSync(join(tmpdir(),'founder-overlay-'));mkdirSync(join(cwd,'out/blog'),{recursive:true});writeFileSync(join(cwd,'out/blog/retained.html'),'retained');
 const code=`import {readFileSync} from 'node:fs';globalThis.fetch=async url=>{const path=String(url).split('/apps/landing/marketing/')[1];let bytes=readFileSync(${JSON.stringify(fileURLToPath(root))}+path);if(${tamper}&&path==='assets/public-resume.pdf')bytes=Buffer.from('tampered');return new Response(bytes)};await import(${JSON.stringify(new URL('../scripts/publish-overlay.mjs',import.meta.url).href)});`;
 const result=spawnSync(process.execPath,['--input-type=module','-e',code],{cwd,encoding:'utf8',env:{...process.env,MANAGER_MARKETING_REVISION:'a'.repeat(40)}});return {cwd,result};
}
test('overlay publishes byte-identical public PDF and profiles without removing existing blog content',()=>{
 const {cwd,result}=overlay();assert.equal(result.status,0,result.stderr);
 for(const [dest,src] of [['cv.pdf','assets/public-resume.pdf'],['about.html','pages/about.html'],['about/ja.html','pages/about-ja.html']])assert.deepEqual(readFileSync(join(cwd,'out',dest)),readFileSync(new URL(src,root)));
 assert.equal(readFileSync(join(cwd,'out/blog/retained.html'),'utf8'),'retained');
});
test('tampered public PDF fails atomically before marketing files are written',()=>{
 const {cwd,result}=overlay(true);assert.notEqual(result.status,0);assert.equal(existsSync(join(cwd,'out/about.html')),false);assert.equal(existsSync(join(cwd,'out/en.html')),false);
});
test('public profile retains concrete enterprise delivery and conference achievements in both languages',()=>{
 for(const file of ['about','about-ja']){
  const html=read(`pages/${file}.html`);
  for(const value of ['Agentforce','CRM','Databricks','ICLR 2026','https://www.youtube.com/watch?v=biHAQ6aSQuc'])assert.ok(html.includes(value),`${file} must retain ${value}`);
 }
 assert.match(read('pages/about.html'),/branches across Japan/);
 assert.match(read('pages/about.html'),/Rio de Janeiro/);
 assert.match(read('pages/about.html'),/contributed/i);
 assert.doesNotMatch(read('pages/about.html'),/accepted (?:ICLR )?paper|ICLR paper acceptance/i);
});

test('full public track record retains verified growth, shipped products and research initiative',()=>{
 const html=read('pages/about.html');
 for(const term of ['JPY20 million','10%','six iOS apps','self-funded','HEARTBEAM','Fourier','autoencoder','weekly'])assert.ok(html.includes(term),`must retain ${term}`);
});

test('historical founder revenue is preserved with period and attribution, not recurring profit',()=>{
 const html=read('pages/about.html');assert.match(html,/JPY200,000/);assert.match(html,/September 2026/);assert.match(html,/founder-reported/);assert.match(html,/without human intervention/);assert.doesNotMatch(html,/JPY200,000 (?:MRR|profit)/);
});
