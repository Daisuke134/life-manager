import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { validatePublication, digest } from './package-contract.mjs';
const root=resolve('docs/research/manager/publication/2026-10-19');
const pkg=validatePublication(JSON.parse(await readFile(resolve(root,'manifest.json'),'utf8')));
const knownMedia=new Set(pkg.media.map(m=>m.public_url));
for(const item of [...pkg.articles,...pkg.media]) {
 const bytes=await readFile(resolve(root,item.package_path));
 if(digest(bytes)!==item.sha256)throw new Error('Content hash mismatch: '+item.package_path);
}
for(const a of pkg.articles) {
 for(const image of a.markdown.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)) if(!knownMedia.has(image[1]))throw new Error('Unregistered image: '+image[1]);
 if(/\]\((?:\.\.?\/|\/home\/|\/workspace\/|file:|docs\/)/.test(a.markdown))throw new Error('Internal article link: '+a.slug);
}
console.log(`Verified ${pkg.articles.length} articles and ${pkg.media.length} media files`);
