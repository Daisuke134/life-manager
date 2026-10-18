// Build adapter: preserve the existing full export; replace only approved marketing routes.
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
const revision = process.env.MANAGER_MARKETING_REVISION;
if (!/^[a-f0-9]{40}$/.test(revision || '')) throw new Error('Immutable canonical revision required');
const base = `https://raw.githubusercontent.com/Daisuke134/life-manager/${revision}/apps/landing/marketing/`;
const response = await fetch(base + 'route-manifest.json');
if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
const manifest = await response.json();
const allowed = new Set(['en.html', 'ja.html', 'dais.html', 'dais/ja.html', 'lm.html', 'lm/ja.html', 'assets/manager-site/styles.css', 'assets/manager-site/writer-cta-url.js']);
if (manifest.files.length !== allowed.size) throw new Error('Unexpected file count');
const staged = [];
for (const file of manifest.files) {
  if (!allowed.delete(file.export_path) || !/^(pages\/[a-z-]+\.html|assets\/(?:styles\.css|writer-cta-url\.js))$/.test(file.source)) throw new Error('Non-allowlisted path');
  const result = await fetch(base + file.source);
  if (!result.ok) throw new Error(`Source HTTP ${result.status}`);
  const bytes = Buffer.from(await result.arrayBuffer());
  if (createHash('sha256').update(bytes).digest('hex') !== file.sha256) throw new Error('Integrity mismatch');
  staged.push([resolve('out', file.export_path), bytes]);
}
for (const [path, bytes] of staged) { await mkdir(dirname(path), { recursive: true }); await writeFile(path, bytes); }
await writeFile('out/manager-release.json', JSON.stringify({ source: manifest.source_authority, revision, files: manifest.files }, null, 2) + '\n');
console.log(`Published overlay: ${revision}; ${staged.length} files, full export preserved`);
