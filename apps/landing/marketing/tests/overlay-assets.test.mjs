import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
function run(stage=false,tamper=false){
 const cwd=mkdtempSync(join(tmpdir(),'marketing-assets-'));mkdirSync(join(cwd,'out'));
 const code=`import {readFileSync} from 'node:fs';globalThis.fetch=async url=>{const path=String(url).split('/apps/landing/marketing/')[1];let bytes=readFileSync(${JSON.stringify(root)}+path);if(${tamper}&&path==='assets/published-apps.json')bytes=Buffer.from('[]');return new Response(bytes)};process.argv=${JSON.stringify(stage?['node','publish','--stage']:['node','publish'])};await import(${JSON.stringify(new URL('../scripts/publish-overlay.mjs',import.meta.url).href)});`;
 const result=spawnSync(process.execPath,['--input-type=module','-e',code],{cwd,encoding:'utf8',env:{...process.env,MANAGER_MARKETING_REVISION:'a'.repeat(40)}});return {cwd,result};
}
test('immutable bridge stages the same hash-verified registry and icons before Next build',()=>{const {cwd,result}=run(true);assert.equal(result.status,0,result.stderr);assert.equal(readFileSync(join(cwd,'public/assets/manager-site/published-apps.json'),'utf8'),readFileSync(join(root,'assets/published-apps.json'),'utf8'));});
test('full overlay accepts only its expanded app asset allowlist',()=>{const {cwd,result}=run();assert.equal(result.status,0,result.stderr);assert.ok(existsSync(join(cwd,'out/assets/manager-site/apps/6759514159.png')));});
test('tampered registry fails before any output is written',()=>{const {cwd,result}=run(true,true);assert.notEqual(result.status,0);assert.equal(existsSync(join(cwd,'public/assets/manager-site/published-apps.json')),false);});
