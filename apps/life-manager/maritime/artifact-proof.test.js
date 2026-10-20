'use strict';
const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const os=require('node:os');const path=require('node:path');
const {spawnSync}=require('node:child_process');const {createHash}=require('node:crypto');
const UID='lm_11111111-1111-4111-8111-111111111111';
const modulePath=path.join(__dirname,'artifact-proof.py');
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'lm-artifact-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const build=path.join(root,UID,'build');fs.mkdirSync(build,{recursive:true});return {root,build};}
function proof(root,ref,uid=UID){
 const code=`import sys,json,importlib.util
a=json.load(sys.stdin)
s=importlib.util.spec_from_file_location('artifact_proof',a['module']);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:print(json.dumps(m.prove_artifact(a['uid'],a['ref'],data_root=a['root'],expected_tenant=a['expected'])))
except (ValueError,OSError):print(json.dumps({'rejected':True}))`;
 const p=spawnSync('python3',['-c',code],{input:JSON.stringify({module:modulePath,root,ref,uid,expected:UID}),encoding:'utf8',env:{PATH:process.env.PATH}});
 assert.equal(p.status,0,p.stderr);return JSON.parse(p.stdout);
}
test('artifact proof reads a bound regular file and preserves raw names',t=>{
 const f=fixture(t);const name='商品 % ready\\copy.md';fs.writeFileSync(path.join(f.build,name),'original product');
 assert.deepEqual(proof(f.root,'artifact://'+name),{tenantId:UID,artifactRef:'artifact://'+name,size:16,sha256:createHash('sha256').update('original product').digest('hex')});
});
test('traversal, foreign tenant, symlink, hardlink and nonregular files are rejected',t=>{
 const f=fixture(t);const outside=path.join(f.root,'private.txt');fs.writeFileSync(outside,'fixture-private');
 fs.symlinkSync(outside,path.join(f.build,'link.txt'));fs.linkSync(outside,path.join(f.build,'hard.txt'));
 fs.symlinkSync(f.root,path.join(f.build,'dirlink'));fs.mkdirSync(path.join(f.build,'directory'));
 for(const ref of ['artifact://../private.txt','artifact://link.txt','artifact://hard.txt','artifact://dirlink/private.txt','artifact://directory','artifact://bad\0name'])assert.equal(proof(f.root,ref).rejected,true,ref);
 assert.equal(proof(f.root,'artifact://x','lm_22222222-2222-4222-8222-222222222222').rejected,true);
});
test('oversize files are rejected before reading their contents',t=>{
 const f=fixture(t);const file=path.join(f.build,'large.bin');fs.writeFileSync(file,'');fs.truncateSync(file,20*1024*1024+1);
 assert.equal(proof(f.root,'artifact://large.bin').rejected,true);
});
