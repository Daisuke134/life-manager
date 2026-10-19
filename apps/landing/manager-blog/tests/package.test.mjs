import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { validatePublication } from '../scripts/package-contract.mjs';
const sha=s=>createHash('sha256').update(s).digest('hex');
const article={slug:'manager-example-ja',lang:'ja',project:'Manager',title:'Example',date:'2026-10-19',package_path:'ja/manager-example-ja.md',sha256:sha('# Example'),canonical_url:'https://aniccaai.com/blog/manager-example-ja',markdown:'# Example',word_count:2,n_papers_cited:0};
const pkg=()=>({articles:[{...article}],media:[]});
test('accepts reviewed flat articles and rejects duplicate slugs and path traversal',()=>{
 assert.equal(validatePublication(pkg()).articles.length,1);
 const duplicate=pkg();duplicate.articles.push({...article});assert.throws(()=>validatePublication(duplicate),/Duplicate/);
 const escaped=pkg();escaped.articles[0].package_path='../private.md';assert.throws(()=>validatePublication(escaped),/path/);
});
test('rejects unsafe media names, mismatched embedded body and non-Manager records',()=>{
 const bad=pkg();bad.media.push({package_path:'media/x.svg',sha256:'0'.repeat(64),public_url:'https://evil.test/x.svg'});assert.throws(()=>validatePublication(bad),/media/);
 const body=pkg();body.articles[0].markdown='# Replaced';assert.throws(()=>validatePublication(body),/hash/);
 const identity=pkg();identity.articles[0].project='Writer';assert.throws(()=>validatePublication(identity),/Manager/);
});
