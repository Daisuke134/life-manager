import assert from 'node:assert/strict';
import test from 'node:test';
import {isLocalMode,encodeProjectFile,decodeProjectFile,readDrafts,saveDraft} from './app.mjs';
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
