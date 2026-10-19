import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { digest } from '../scripts/package-contract.mjs';
import { installManagerBlog } from '../scripts/install.mjs';
const codeRoot=new URL('../',import.meta.url);
async function setup(){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'manager-install-'));
 const fixtures=new URL('./fixtures/',import.meta.url);
 for(const [target,file] of Object.entries({'lib/blog-business.mjs':'lib__blog-business.mjs','app/blog/page.tsx':'app__blog__page.tsx','app/blog/[slug]/page.tsx':'app__blog__[slug]__page.tsx','app/blog/c/[business]/page.tsx':'app__blog__c__[business]__page.tsx','app/sitemap.ts':'app__sitemap.ts'})){
  await fs.mkdir(path.dirname(path.join(root,target)),{recursive:true});await fs.copyFile(new URL(file,fixtures),path.join(root,target));
 }
 await fs.writeFile(path.join(root,'lib/blog-business.d.mts'),'export function businessOf(slug: string, project?: string | null): string;\n');
 await fs.mkdir(path.join(root,'data/research'),{recursive:true});await fs.writeFile(path.join(root,'data/research/other.json'),'preserved');
 await fs.writeFile(path.join(root,'tailwind.config.ts'),"const config = { content: [\n    './app/**/*.{js,ts,jsx,tsx,mdx}',\n] };");
 const body='# Example\n\nContent.', article={slug:'manager-example-en',title:'Example',lang:'en',project:'Manager',date:'2026-10-19',package_path:'en/manager-example-en.md',sha256:digest(body),markdown:body,canonical_url:'https://aniccaai.com/blog/manager-example-en',n_papers_cited:0,word_count:3};
 const media=Buffer.from('image bytes'),hash=digest(media);
 const m={package_path:`media/${hash}.png`,sha256:hash,public_url:`https://aniccaai.com/blog/manager/media/${hash}.png`};
 const base='docs/research/manager/publication/2026-10-19/';
 const files=new Map([[base+'manifest.json',Buffer.from(JSON.stringify({articles:[article],media:[m]}))],[base+article.package_path,Buffer.from(body)],[base+m.package_path,media]]);
 const fetchBytes=async file=>file.startsWith('apps/landing/manager-blog/')?fs.readFile(new URL(file.replace('apps/landing/manager-blog/',''),codeRoot)):files.get(file);
 return {root,files,base,article,fetchBytes};
}
test('stages verified content before integration, preserves unrelated articles, and writes an auditable receipt',async()=>{
 const c=await setup();const receipt=await installManagerBlog({...c,revision:'a'.repeat(40)});
 assert.equal(receipt.articles.length,1);assert.equal(await fs.readFile(path.join(c.root,'data/research/other.json'),'utf8'),'preserved');
 const post=JSON.parse(await fs.readFile(path.join(c.root,'data/research/manager-example-en.json')));assert.equal(post.markdown,c.article.markdown);
 assert.match(await fs.readFile(path.join(c.root,'app/blog/manager/page.tsx'),'utf8'),/English/);
 await fs.rm(c.root,{recursive:true});
});
test('rejects tampered article bytes before any public content is staged',async()=>{
 const c=await setup();c.files.set(c.base+c.article.package_path,Buffer.from('tampered'));
 await assert.rejects(()=>installManagerBlog({...c,revision:'b'.repeat(40)}),/Article hash mismatch/);
 await assert.rejects(()=>fs.access(path.join(c.root,'data/research/manager-example-en.json')));
 await fs.rm(c.root,{recursive:true});
});
