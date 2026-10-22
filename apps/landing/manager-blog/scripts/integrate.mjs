// Canonical, scoped build adapter. Refuse changed legacy interfaces instead of silently dropping integration.
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
async function patch(root, file, changes) {
 const target=join(root,file);let text=await readFile(target,'utf8');
 for(const [before,after] of changes) {
  if(text.includes(after)) continue;
  if(!text.includes(before)) throw new Error(`Legacy contract changed: ${file}: ${before.slice(0,60)}`);
  text=text.replaceAll(before,after);
 }
 await writeFile(target,text);
}
export async function integrateManagerBlog(root) {
 await patch(root,'lib/blog-business.mjs',[
  ['export const BUSINESSES = {',`export const BUSINESSES = {\n  manager: {\n    label: 'Manager',\n    intro: 'Research and working experiments toward Manager: synthetic populations, behavior models and interventions. Our mission is End suffering.',\n  },`],
  ["  const p = String(project || '').toLowerCase();", "  const p = String(project || '').toLowerCase();\n  if (p === 'manager') return 'manager';"],
 ]);
 const businessPath=join(root,'lib/blog-business.mjs');let business=await readFile(businessPath,'utf8');
 if(!business.includes('export function businessHubPath')) await writeFile(businessPath,business+"\nexport function businessHubPath(key) { return key === 'manager' ? '/blog/manager' : `/blog/c/${key}`; }\n");
 await patch(root,'lib/blog-business.d.mts',[[
  'export function businessOf(slug: string, project?: string | null): string;',
  'export function businessOf(slug: string, project?: string | null): string;\nexport function businessHubPath(key: string): string;',
 ]]);
 await patch(root,'tailwind.config.ts',[[
  "'./app/**/*.{js,ts,jsx,tsx,mdx}',",
  "'./app/**/*.{js,ts,jsx,tsx,mdx}',\n    './lib/render-manager-markdown.mjs',",
 ]]);
 await patch(root,'app/blog/page.tsx',[
  ['import { BUSINESSES }','import { BUSINESSES, businessHubPath }'],
  ['href={`/blog/c/${key}`}','href={businessHubPath(key)}'],
  ["import {MediaNav,MediaFooter,ArticleList}", "import {MediaNav,MediaFooter}"],
 ]);
 // Topic-first index: remove the standalone latest feed, not the article corpus.
 const indexPath=join(root,'app/blog/page.tsx');let index=await readFile(indexPath,'utf8');
 const latest=' <section aria-labelledby="latest-heading"><h2 id="latest-heading">Latest articles</h2><ArticleList posts={posts}/><Link href="/blog/archive/1">All articles</Link></section>';
 index=index.replace(latest,'')
  .replace(" const posts=corpus.filter(p=>editorialOf(p.slug,p.project) !== 'Research').slice(0,6);",'')
  .replace(' const posts=corpus.slice(0,24);','')
  .replace('<h1>Latest articles.</h1>','<h1>Explore by topic.</h1>')
  .replace('Newest first, across every topic. Explore the work behind Anicca.','Choose an area to explore the work behind Anicca.');
 if(!index.includes(' {groups.map(')||!index.includes('<h1>Explore by topic.</h1>')||/latest-heading|const posts=|ArticleList/.test(index))throw new Error('Legacy blog topic-directory contract changed');
 await writeFile(indexPath,index);
 await patch(root,'app/blog/[slug]/page.tsx',[
  ['import { BUSINESSES, businessOf }','import { BUSINESSES, businessOf, businessHubPath }'],
  ['import { affiliatePlacement, renderMarkdown }', 'import { renderManagerMarkdown } from "../../../lib/render-manager-markdown.mjs";\nimport { affiliatePlacement, renderMarkdown }'],
  ['const html = renderMarkdown(articleMarkdown);','const html = post.project === "Manager" ? renderManagerMarkdown(articleMarkdown) : renderMarkdown(articleMarkdown);'],
  ['`https://aniccaai.com/blog/c/${business}`','`https://aniccaai.com${businessHubPath(business)}`'],
  ['href={`/blog/c/${business}`}','href={businessHubPath(business)}'],
 ]);
 await patch(root,'app/blog/c/[business]/page.tsx',[
  ['import { BUSINESSES, businessOf }','import { BUSINESSES, businessOf, businessHubPath }'],
  ['`${SITE}/blog/c/${params.business}`','`${SITE}${businessHubPath(params.business)}`'],
 ]);
 await patch(root,'app/sitemap.ts',[
  ['import { BUSINESSES }','import { BUSINESSES, businessHubPath }'],
  ['`${BASE_URL}/blog/c/${key}`','`${BASE_URL}${businessHubPath(key)}`'],
 ]);
 const route=join(root,'app/blog/manager/page.tsx');await mkdir(dirname(route),{recursive:true});
 await copyFile(new URL('../templates/manager-collection.tsx',import.meta.url),route);
 await copyFile(new URL('../lib/render-manager-markdown.mjs',import.meta.url),join(root,'lib/render-manager-markdown.mjs'));
 await writeFile(join(root,'lib/render-manager-markdown.d.mts'),'export function renderManagerMarkdown(markdown: string): string;\n');
}
