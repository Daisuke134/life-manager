// Build adapter: preserve the existing full export; replace only approved marketing routes.
import { createHash } from 'node:crypto';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
const revision = process.env.MANAGER_MARKETING_REVISION;
if (!/^[a-f0-9]{40}$/.test(revision || '')) throw new Error('Immutable canonical revision required');
const base = `https://raw.githubusercontent.com/Daisuke134/life-manager/${revision}/apps/landing/marketing/`;
const response = await fetch(base + 'route-manifest.json');
if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
const manifest = await response.json();
const stageOnly = process.argv.includes('--stage');
const appFiles = ['published-apps.json', 'apps/6755129214.webp', 'apps/6759667221.webp', 'apps/6759514159.png', 'apps/6757726663.webp', 'apps/6762143790.webp', 'apps/6766485903.webp'];
const allowed = new Set([...appFiles.map(path => 'assets/manager-site/' + path), 'about.html', 'about/ja.html', 'cv.pdf', 'index.html', 'en.html', 'ja.html', 'dais.html', 'dais/ja.html', 'lm.html', 'lm/ja.html', 'assets/manager-site/styles.css', 'assets/manager-site/writer-cta-url.js']);
if (manifest.files.length !== allowed.size) throw new Error('Unexpected file count');
const staged = [];
for (const file of manifest.files) {
  if (!allowed.delete(file.export_path) || file.source !== (file.export_path.startsWith('assets/manager-site/') ? file.export_path.replace('assets/manager-site/', 'assets/') : file.source) || !/^(pages\/[a-z-]+\.html|assets\/(?:public-resume\.pdf|styles\.css|writer-cta-url\.js|published-apps\.json|apps\/[0-9]+\.(?:webp|png)))$/.test(file.source)) throw new Error('Non-allowlisted path');
  const result = await fetch(base + file.source);
  if (!result.ok) throw new Error(`Source HTTP ${result.status}`);
  const bytes = Buffer.from(await result.arrayBuffer());
  if (createHash('sha256').update(bytes).digest('hex') !== file.sha256) throw new Error('Integrity mismatch');
  if (!stageOnly || appFiles.includes(file.source.replace('assets/', ''))) staged.push([resolve(stageOnly ? 'public' : 'out', file.export_path), bytes]);
}
for (const [path, bytes] of staged) {
  await mkdir(dirname(path), { recursive: true }); await writeFile(path, bytes);
  // Retired RSC payloads must not let existing Next links render the old marketing page.
  // A missing static-export payload makes Next fall back to a normal page navigation.
  if (path.endsWith('.html')) await rm(path.replace(/\.html$/, '.txt'), { force: true });
}
if (!stageOnly) await writeFile('out/manager-release.json', JSON.stringify({ source: manifest.source_authority, revision, files: manifest.files }, null, 2) + '\n');
console.log(`Verified marketing package: ${revision}; ${staged.length} files, full export preserved`);
