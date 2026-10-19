import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { integrateManagerBlog } from '../scripts/integrate.mjs';
const baseline=new URL('./fixtures/', import.meta.url);
test('integrates only Manager, preserves legacy code and is repeatable', async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'manager-blog-'));
 await fs.mkdir(path.join(root,'lib'),{recursive:true}); await fs.writeFile(path.join(root,'lib/blog-business.d.mts'),'export function businessOf(slug: string, project?: string | null): string;\n');
 const mapping={'lib/blog-business.mjs':'lib__blog-business.mjs','app/blog/page.tsx':'app__blog__page.tsx','app/blog/[slug]/page.tsx':'app__blog__[slug]__page.tsx','app/blog/c/[business]/page.tsx':'app__blog__c__[business]__page.tsx','app/sitemap.ts':'app__sitemap.ts'};
 for(const [target,source] of Object.entries(mapping)) {await fs.mkdir(path.dirname(path.join(root,target)),{recursive:true});await fs.copyFile(new URL(source,baseline),path.join(root,target));}
 await fs.writeFile(path.join(root,'tailwind.config.ts'),"const config = { content: [\n    './app/**/*.{js,ts,jsx,tsx,mdx}',\n] };");
 await integrateManagerBlog(root);
 assert.match(await fs.readFile(path.join(root,'tailwind.config.ts'),'utf8'),/render-manager-markdown/);
 const article=await fs.readFile(path.join(root,'app/blog/[slug]/page.tsx'),'utf8');
 assert.match(article,/post\.project === "Manager" \? renderManagerMarkdown/);
 assert.match(article,/WriterUnlock/);assert.match(article,/affiliatePlacement\(articleMarkdown\)/);
 const business=await fs.readFile(path.join(root,'lib/blog-business.mjs'),'utf8');
 assert.match(business,/p === 'manager'/);assert.match(business,/'line-stickers'/);
 const first=await fs.readFile(path.join(root,'app/blog/page.tsx'),'utf8');
 await integrateManagerBlog(root);assert.equal(await fs.readFile(path.join(root,'app/blog/page.tsx'),'utf8'),first);
 assert.match(await fs.readFile(path.join(root,'app/blog/manager/page.tsx'),'utf8'),/English/);
 await fs.rm(root,{recursive:true});
});
