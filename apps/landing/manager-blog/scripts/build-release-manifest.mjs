import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const modules=['scripts/integrate.mjs','scripts/package-contract.mjs','lib/render-manager-markdown.mjs','templates/manager-collection.tsx'];
const manifest={schema_version:1,modules:await Promise.all(modules.map(async path=>({path,sha256:createHash('sha256').update(await readFile(new URL('../'+path,import.meta.url))).digest('hex')})))};
await writeFile(new URL('../release-manifest.json',import.meta.url),JSON.stringify(manifest,null,2)+'\n');
