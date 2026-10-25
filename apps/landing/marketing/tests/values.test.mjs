import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

// Catch missing, duplicated or unapproved Values in the actual exported home routes.
test('home overlay publishes exactly the two approved Values and preserves the mission', () => {
 const root = fileURLToPath(new URL('../', import.meta.url));
 const cwd = mkdtempSync(join(tmpdir(), 'marketing-values-'));
 try {
  mkdirSync(join(cwd, 'out'));
  const code = `import {readFileSync} from 'node:fs';globalThis.fetch=async url=>new Response(readFileSync(${JSON.stringify(root)}+String(url).split('/apps/landing/marketing/')[1]));await import(${JSON.stringify(new URL('../scripts/publish-overlay.mjs', import.meta.url).href)});`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', code], {cwd, encoding:'utf8', env:{...process.env, MANAGER_MARKETING_REVISION:'a'.repeat(40)}});
  assert.equal(result.status, 0, result.stderr);
  for (const path of ['index.html', 'en.html']) {
   const html = readFileSync(join(cwd, 'out', path), 'utf8');
   assert.match(html, /<h1>End suffering\.<\/h1>/);
   const sections = [...html.matchAll(/<section\b[^>]*id="values"[^>]*>([\s\S]*?)<\/section>/g)];
   assert.equal(sections.length, 1, `${path}: one Values section`);
   const section = sections[0][1];
   assert.deepEqual([...section.matchAll(/<h2[^>]*>(.*?)<\/h2>/g)].map(m=>m[1]), ['Our Values']);
   assert.deepEqual([...section.matchAll(/<h3[^>]*>(.*?)<\/h3>/g)].map(m=>m[1]), ['One Flesh', 'Reinvention Is a Sin.']);
   assert.deepEqual([...section.matchAll(/<p[^>]*>(.*?)<\/p>/g)].map(m=>m[1]), [
    'We are building a company whose agents act as one body. What one learns, we share with all. Each of us takes responsibility for the whole, working toward the end of suffering.',
    'There is no shame in not knowing. We study those who came before us until we understand how their work succeeds and why. We put that knowledge to use, connect ideas across disciplines, and build on what already works. Our ego is never a reason to start from zero.'
   ]);
   assert.doesNotMatch(section, /Genesis|<a\b/i);
  }
 } finally { rmSync(cwd, {recursive:true, force:true}); }
});
