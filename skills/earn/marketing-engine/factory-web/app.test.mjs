import assert from 'node:assert/strict';
import test from 'node:test';
import {projectFileMaxBytes,isLocalMode,encodeProjectFile,decodeProjectFile,readDrafts,saveDraft} from './app.mjs';
const project={project_id:'first-monk',language:'en',avatar_id:'',voice_id:'',platform:'tiktok',integration_id:'',native_handle:'',product_name:'',product_url:'',brief:'A gentle lesson about starting again.',script:'',cta:''};
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)};};
test('public workspace cannot mistake a host or unexpanded token for local runtime',()=>{
 assert.equal(isLocalMode('__FACTORY_TOKEN__','127.0.0.1'),false);
 assert.equal(isLocalMode('x'.repeat(43),'aniccaai.com'),false);
 assert.equal(isLocalMode('x'.repeat(43),'127.0.0.1.attacker.example'),false);
 assert.equal(isLocalMode('x'.repeat(43),'127.0.0.1'),true);
});
test('draft persists and replaces one project without dropping other projects',()=>{
 const s=storage();saveDraft(s,project);saveDraft(s,{...project,project_id:'second-monk'});saveDraft(s,{...project,brief:'A revised brief.'});
 const rows=readDrafts(s);assert.equal(rows.length,2);assert.equal(rows.find(x=>x.project_id==='first-monk').brief,'A revised brief.');
});
test('export/import preserves real project content and rejects extra fields and wrong versions',()=>{
 assert.deepEqual(decodeProjectFile(encodeProjectFile(project)),project);
 assert.throws(()=>decodeProjectFile(JSON.stringify({schema_version:'unknown',project})),/version|format/i);
 assert.throws(()=>encodeProjectFile({...project,api_key:'secret'}));
 assert.throws(()=>decodeProjectFile('{'));
});
test('corrupt stored data reports the problem instead of silently replacing drafts',()=>{
 const s=storage();s.setItem('anicca.monk-factory.drafts.v1','{');assert.throws(()=>readDrafts(s));
});

test("valid Japanese drafts round-trip using the same UTF-8 file limit",()=>{
 const large={...project,language:"ja",product_name:"僧".repeat(200),product_url:"https://example.com/"+"道".repeat(2000),brief:"あ".repeat(4000),script:"学".repeat(5000),cta:"心".repeat(500)};
 const text=encodeProjectFile(large);const bytes=new TextEncoder().encode(text).byteLength;
 assert.ok(bytes>32768);assert.ok(bytes<=projectFileMaxBytes);assert.deepEqual(decodeProjectFile(text),large);
 assert.throws(()=>decodeProjectFile("あ".repeat(Math.floor(projectFileMaxBytes/3)+1)),/too large/);
});
