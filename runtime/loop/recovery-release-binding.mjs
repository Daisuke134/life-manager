import { readFile, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';

async function manifestSha(root) {
  try {
    const manifest = JSON.parse(await readFile(path.join(root, 'RELEASE.json'), 'utf8'));
    return typeof manifest?.sha === 'string' ? manifest.sha : null;
  } catch {
    return null;
  }
}

export async function resolveBoundRelease(releaseRoot, releaseSha) {
  if (await manifestSha(releaseRoot) === releaseSha) return releaseRoot;
  const releasesRoot = path.join(path.dirname(releaseRoot), 'releases');
  let base;
  let entries;
  try {
    [base, entries] = await Promise.all([
      realpath(releasesRoot), readdir(releasesRoot, { withFileTypes: true }),
    ]);
  } catch {
    return null;
  }
  const matches = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
    let candidate;
    try {
      candidate = await realpath(path.join(releasesRoot, entry.name));
    } catch {
      continue;
    }
    if (!candidate.startsWith(`${base}${path.sep}`)) continue;
    if (await manifestSha(candidate) === releaseSha) matches.push(candidate);
  }
  return matches.length === 1 ? matches[0] : null;
}
