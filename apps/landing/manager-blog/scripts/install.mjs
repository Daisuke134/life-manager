// Run before Next build in the existing publishing repository. Source is immutable canonical Git.
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const modules=['scripts/integrate.mjs','scripts/package-contract.mjs','lib/render-manager-markdown.mjs','templates/manager-collection.tsx'];
export async function installManagerBlog({revision,root=process.cwd(),fetchBytes}) {
 if(!/^[a-f0-9]{40}$/.test(revision||'')) throw new Error('Immutable canonical revision required');
 const base=`https://raw.githubusercontent.com/Daisuke134/life-manager/${revision}/`;
 const get=fetchBytes|| (async path=>{const r=await fetch(base+path);if(!r.ok)throw new Error(`Source HTTP ${r.status}: ${path}`);return Buffer.from(await r.arrayBuffer());});
 const codeManifest=JSON.parse(await get('apps/landing/manager-blog/release-manifest.json'));
 const staged=[];
 if(!Array.isArray(codeManifest.modules)||codeManifest.modules.length!==modules.length) throw new Error('Invalid module manifest');
 const expected=new Set(modules);
 for(const file of codeManifest.modules) {
  if(!expected.delete(file.path))throw new Error('Non-allowlisted module');
  const bytes=await get('apps/landing/manager-blog/'+file.path);
  if(sha(bytes)!==file.sha256)throw new Error('Module hash mismatch');
  staged.push([resolve(root,'.manager-blog',file.path),bytes]);
 }
 // Only integrity-checked canonical modules execute. They are staged separately from public exports.
 for(const [file,bytes] of staged){await mkdir(dirname(file),{recursive:true});await writeFile(file,bytes);}
 const {validatePublication,digest}=await import(pathToFileURL(resolve(root,'.manager-blog/scripts/package-contract.mjs')).href);
 const packageRoot='docs/research/manager/publication/2026-10-19/';
 const pkg=validatePublication(JSON.parse(await get(packageRoot+'manifest.json')));
 const content=[];
 for(const a of pkg.articles) {
  const bytes=await get(packageRoot+a.package_path);
  if(digest(bytes)!==a.sha256)throw new Error(`Article hash mismatch: ${a.slug}`);
  const {slug,title,date,project,n_papers_cited,word_count,description,lang,series_order}=a;
  const target=resolve(root,'data/research',a.slug+'.json');
  try { const prior=JSON.parse(await readFile(target,'utf8')); if(prior.project!=='Manager') throw new Error('Refusing to replace unrelated article: '+a.slug); } catch(e) { if(e.code!=='ENOENT') throw e; }
  content.push([resolve(root,'data/research',a.slug+'.json'),Buffer.from(JSON.stringify({slug,title,date,project,n_papers_cited,word_count,description,lang,series_order,markdown:bytes.toString('utf8')},null,2)+'\n')]);
 }
 for(const m of pkg.media) {
  const bytes=await get(packageRoot+m.package_path);
  if(digest(bytes)!==m.sha256)throw new Error('Media hash mismatch');
  content.push([resolve(root,'public/blog/manager',m.package_path),bytes]);
 }
 for(const [file,bytes] of content){await mkdir(dirname(file),{recursive:true});await writeFile(file,bytes);}
 const {integrateManagerBlog}=await import(pathToFileURL(resolve(root,'.manager-blog/scripts/integrate.mjs')).href);
 await integrateManagerBlog(root);
 const receipt={revision,articles:pkg.articles.map(a=>({slug:a.slug,sha256:a.sha256,lang:a.lang})),media:pkg.media.map(m=>({url:m.public_url,sha256:m.sha256}))};
 await mkdir(resolve(root,'public/blog/manager'),{recursive:true});
 await writeFile(resolve(root,'public/blog/manager/release.json'),JSON.stringify(receipt,null,2)+'\n');
 console.log(`Manager blog staged: ${revision}, ${pkg.articles.length} articles, ${pkg.media.length} media`);
 return receipt;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await installManagerBlog({revision:process.env.MANAGER_BLOG_REVISION});
