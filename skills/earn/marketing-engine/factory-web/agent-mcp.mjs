#!/usr/bin/env node
// Run-bound transport. Provider policy and durable effect fences remain in Factory Python.
import { constants } from 'node:fs';
import { lstat, mkdir, open, rename, writeFile, appendFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { validateProject } from './project.mjs';

export const idPattern = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const maxJson = 16 * 1024 * 1024;
const operations = ['prepare', 'shadow', 'route-check', 'upload', 'draft', 'promote', 'status', 'postiz-readback'];
const now = () => new Date().toISOString();

export async function safePath(root, target) {
  const base = path.resolve(root), result = path.resolve(target);
  if (result !== base && !result.startsWith(base + path.sep)) throw new Error('Unsafe workspace path.');
  let current = base;
  for (const part of ['', ...path.relative(base, result).split(path.sep).filter(Boolean)]) {
    if (part) current = path.join(current, part);
    try { if ((await lstat(current)).isSymbolicLink()) throw new Error('Symlinks are not allowed.'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return result;
}

export async function readSafe(root, target, maxBytes = maxJson) {
  await safePath(root, target);
  const file = await open(target, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size > maxBytes) throw new Error('Invalid or oversized workspace file.');
    return await file.readFile();
  } finally { await file.close(); }
}

export async function writeJson(root, target, value) {
  await safePath(root, target);
  const temporary = path.join(path.dirname(target), '.write-' + randomUUID());
  await writeFile(temporary, JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  await rename(temporary, target);
}

export async function readTools(runRoot) {
  const target = path.join(runRoot, 'control', 'tools.jsonl');
  let bytes;
  try { bytes = await readSafe(runRoot, target); } catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  return bytes.toString('utf8').split('\n').filter(Boolean).map(line => JSON.parse(line));
}

async function appendTool(runRoot, name, result) {
  const target = path.join(runRoot, 'control', 'tools.jsonl');
  await safePath(runRoot, target);
  const row = { name, created_at: now(), result: { isError: result.isError === true, structuredContent: result.structuredContent } };
  const encoded = JSON.stringify(row) + '\n';
  if (Buffer.byteLength(encoded) > 4 * 1024 * 1024) throw new Error('Factory output exceeded the run limit.');
  await appendFile(target, encoded, { mode: 0o600 });
  return result;
}

export function boundToolNames(mode) {
  return mode === 'plan' ? ['factory_plan'] : mode === 'render' ? ['factory_plan', 'factory_render']
    : ['factory_plan', 'factory_render', 'factory_publish', 'factory_record_review'];
}

export async function freezeInputs(runRoot) {
  const frozen = path.join(runRoot, 'control', 'frozen.json');
  try { return JSON.parse(await readSafe(runRoot, frozen)); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const input = JSON.parse(await readSafe(runRoot, path.join(runRoot, 'input', 'project.json')));
  const project = validateProject(input.project, { ready: true });
  const script = (await readSafe(runRoot, path.join(runRoot, 'workspace', 'script.txt'), 20000)).toString('utf8').trim();
  if (!script || script.length > 5000 || script.includes('\0')) throw new Error('Write a real script.txt before planning.');
  let caption = '';
  try { caption = (await readSafe(runRoot, path.join(runRoot, 'workspace', 'caption.txt'), 12000)).toString('utf8').trim(); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const url = new URL(project.product_url);
  url.searchParams.set('utm_campaign', input.attribution_token);
  const tracked = url.href;
  if (!caption) caption = `${project.cta}\n${tracked}`;
  if (caption.length > 4000 || caption.includes('\0') || !caption.includes(project.cta)
    || caption.split(/\s+/u).filter(word => word.includes(tracked)).join(' ') !== tracked) {
    throw new Error('caption.txt must contain the CTA and the exact tracked URL once.');
  }
  const control = path.join(runRoot, 'control');
  const stateRoot = path.join(control, 'output');
  await safePath(runRoot, stateRoot); await mkdir(stateRoot, { recursive: true, mode: 0o700 });
  const config = { schema_version: 'ai-monk-factory.config.v1', project_id: project.project_id, language: project.language,
    heygen: { avatar_id: project.avatar_id, voice_id: project.voice_id },
    postiz: { platform: project.platform, integration_id: project.integration_id },
    product: { name: project.product_name, url: tracked }, state_root: stateRoot };
  const publication = { schema_version: 'ai-monk-factory.publication.v1', native_handle: project.native_handle,
    publisher_provider: project.platform === 'tiktok' ? 'tiktok' : 'instagram-standalone',
    provider_settings: project.platform === 'tiktok' ? { __type: 'tiktok', title: project.product_name.slice(0, 90),
      privacy_level: 'PUBLIC_TO_EVERYONE', duet: false, stitch: false, comment: true, autoAddMusic: 'no',
      brand_content_toggle: false, brand_organic_toggle: true, video_made_with_ai: true, content_posting_method: 'DIRECT_POST' }
      : { __type: 'instagram-standalone', post_type: 'post', is_trial_reel: false, collaborators: [] },
    publish_enabled: input.mode === 'publish', cta: project.cta, caption, attribution_token: input.attribution_token,
    scheduled_at: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(), visual_approval_id: 'visual.accepted.' + input.run_id };
  const paths = { config: path.join(control, 'config.json'), script: path.join(control, 'script.txt'), publication: path.join(control, 'publication.json') };
  await writeJson(runRoot, paths.config, config);
  await writeFile(paths.script, script, { flag: 'wx', mode: 0o600 });
  await writeJson(runRoot, paths.publication, publication);
  const result = { ...paths, run_id: input.run_id, project_id: project.project_id, mode: input.mode, output: path.join(stateRoot, 'renders', `${project.project_id}.${input.run_id}.mp4`) };
  await writeJson(runRoot, frozen, result);
  return result;
}

export async function verifiedArtifact(runRoot) {
  const tools = await readTools(runRoot);
  const receipt = [...tools].reverse().find(row => row.name === 'factory_render' && row.result.structuredContent?.result?.output)?.result.structuredContent.result;
  return verifyReceiptArtifact(runRoot, receipt);
}

async function verifyReceiptArtifact(runRoot, receipt) {
  const frozen = JSON.parse(await readSafe(runRoot, path.join(runRoot, 'control', 'frozen.json')));
  if (!receipt || receipt.output !== frozen.output || !/^[a-f0-9]{64}$/.test(receipt.sha256 ?? '')) throw new Error('No verified run asset.');
  await safePath(runRoot, frozen.output);
  const file = await open(frozen.output, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size === 0) throw new Error('No verified run asset.');
    const hash = createHash('sha256');
    for await (const chunk of file.createReadStream({ autoClose: false })) hash.update(chunk);
    if (hash.digest('hex') !== receipt.sha256) throw new Error('Run asset hash mismatch.');
    return { path: frozen.output, sha256: receipt.sha256, size: stat.size };
  } finally { await file.close(); }
}

async function mediaCommand(command, args, signal) {
  // Reuse the existing finite child registry, output limit, abort and process-group cleanup.
  const { runCli } = await import('../factory-mcp.mjs');
  const result = await runCli([], { signal, timeoutMs: 30000, maxOutputBytes: 65536,
    spawnChild: (_command, _args, options) => spawn(command, args, { ...options,
      cwd: path.dirname(fileURLToPath(new URL('../factory-mcp.mjs', import.meta.url))),
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }) });
  if (result.exit_code !== 0 || result.transport_error) throw new Error('review_frame_extraction_unavailable');
  return result.stdout;
}

async function reviewFrames(runRoot, receipt, signal) {
  const asset = await verifyReceiptArtifact(runRoot, receipt);
  const manifestPath = path.join(runRoot, 'control', 'review-frames.json');
  let manifest;
  try { manifest = JSON.parse(await readSafe(runRoot, manifestPath)); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (!manifest) {
    // Keep the existing native binary resolution, including its absolute executable checks.
    const binaries = JSON.parse(await mediaCommand('python3', ['-c',
      'import json; from ebook_asset_pack import resolve_ffmpeg, resolve_ffprobe; print(json.dumps([resolve_ffmpeg(), resolve_ffprobe()]))'], signal));
    if (!binaries[0] || !binaries[1]) throw new Error('review_frame_extraction_unavailable');
    const probe = JSON.parse(await mediaCommand(binaries[1], ['-v', 'error', '-protocol_whitelist', 'file,pipe',
      '-show_entries', 'format=duration:stream=codec_type,codec_name,width,height', '-of', 'json', asset.path], signal));
    const video = probe.streams?.find(row => row.codec_type === 'video'), audio = probe.streams?.find(row => row.codec_type === 'audio');
    const duration = Number(probe.format?.duration);
    if (!Number.isFinite(duration) || duration < 1 || duration > 180 || !Number.isInteger(video?.width) || !Number.isInteger(video?.height)
      || video.width < 1 || video.height < 1 || video.width > 8192 || video.height > 8192) throw new Error('invalid_review_media');
    const directory = path.join(runRoot, 'control', 'review-frames');
    await safePath(runRoot, directory); await mkdir(directory, { recursive: true, mode: 0o700 });
    const files = [1, 2, 3].map(index => `frame-${String(index).padStart(2, '0')}.png`);
    for (const file of files) await safePath(runRoot, path.join(directory, file));
    const sampling = `fps=3/${duration}`;
    await mediaCommand(binaries[0], ['-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
      '-protocol_whitelist', 'file,pipe', '-i', asset.path, '-map', '0:v:0', '-an',
      '-vf', `${sampling},scale=720:1280:force_original_aspect_ratio=decrease`, '-frames:v', '3', '-threads', '1', path.join(directory, 'frame-%02d.png')], signal);
    const frames = [];
    for (const file of files) {
      const bytes = await readSafe(runRoot, path.join(directory, file), 8 * 1024 * 1024);
      if (bytes.length <= 8) throw new Error('invalid_review_frame');
      frames.push({ file: `review-frames/${file}`, sha256: createHash('sha256').update(bytes).digest('hex') });
    }
    manifest = { asset_sha256: asset.sha256, extracted_at: now(), frames,
      media: { duration_seconds: duration, width: video.width, height: video.height,
        video_codec: video.codec_name, audio_codec: audio?.codec_name ?? null, sampling } };
    await writeJson(runRoot, manifestPath, manifest);
  }
  if (manifest.asset_sha256 !== asset.sha256) throw new Error('conflicting_review_asset');
  const workspace = path.join(runRoot, 'workspace'), directory = path.join(workspace, 'review-frames');
  await safePath(workspace, directory); await mkdir(directory, { recursive: true, mode: 0o700 });
  for (const frame of manifest.frames) {
    const bytes = await readSafe(runRoot, path.join(runRoot, 'control', frame.file), 8 * 1024 * 1024);
    if (createHash('sha256').update(bytes).digest('hex') !== frame.sha256) throw new Error('conflicting_review_frame');
    const target = path.join(workspace, frame.file); await safePath(workspace, target);
    try { await writeFile(target, bytes, { flag: 'wx', mode: 0o600 }); }
    catch (error) {
      if (error.code !== 'EEXIST' || createHash('sha256').update(await readSafe(workspace, target, 8 * 1024 * 1024)).digest('hex') !== frame.sha256) throw error;
    }
  }
  return manifest;
}

function failed(reason) {
  return { isError: true, content: [{ type: 'text', text: reason }], structuredContent: {
    exit_code: null, signal: null, result: null, stdout: '', stderr: '', transport_error: reason,
  } };
}

export function createRunToolCaller({ runRoot, factoryExecutor, signal }) {
  let queue = Promise.resolve();
  const execute = async (name, args) => {
    const input = JSON.parse(await readSafe(runRoot, path.join(runRoot, 'input', 'project.json')));
    if (!boundToolNames(input.mode).includes(name)) return appendTool(runRoot, name, failed('mode_forbidden'));
    const rows = await readTools(runRoot);
    if (rows.length >= 32 || Buffer.byteLength(JSON.stringify(rows)) > 8 * 1024 * 1024) return failed('run_tool_limit');
    let invoked = false;
    try {
      if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('invalid_arguments');
      const fields = name === 'factory_publish' ? ['operation'] : name === 'factory_record_review' ? ['notes', 'frame_evidence'] : [];
      if (Object.keys(args).length !== fields.length || fields.some(field => !Object.hasOwn(args, field))) throw new Error('invalid_arguments');
      if (signal?.aborted) throw new Error('run_interrupted');
      if (name !== 'factory_plan') {
        const plan = [...rows].reverse().find(row => row.name === 'factory_plan' && row.result.structuredContent?.result?.status === 'planned'
          && row.result.structuredContent.exit_code === 0 && !row.result.isError);
        if (!plan) throw new Error('plan_required');
      }
      const frozen = await freezeInputs(runRoot);
      const fixed = { config: frozen.config, script: frozen.script };
      if (name === 'factory_render') fixed.run_id = frozen.run_id;
      if (name === 'factory_publish') {
        if (!operations.includes(args.operation)) throw new Error('invalid_operation');
        Object.assign(fixed, { publication: frozen.publication, run_id: frozen.run_id, operation: args.operation, production: input.mode === 'publish' });
      }
      if (name === 'factory_record_review') {
        if (typeof args.notes !== 'string' || !args.notes.trim() || args.notes.length > 4000 || args.notes.includes('\0')
          || !Array.isArray(args.frame_evidence) || args.frame_evidence.length < 1 || args.frame_evidence.length > 12) throw new Error('invalid_review');
        const asset = await verifiedArtifact(runRoot);
        const prepare = [...rows].reverse().find(row => row.name === 'factory_publish' && !row.result.isError
          && row.result.structuredContent?.exit_code === 0 && row.result.structuredContent.result?.approvals_path)?.result.structuredContent.result;
        if (!prepare?.account_id || !prepare?.product_id || !prepare?.approvals_path) throw new Error('prepare_required');
        const manifest = JSON.parse(await readSafe(runRoot, path.join(runRoot, 'control', 'review-frames.json')));
        if (manifest.asset_sha256 !== asset.sha256 || JSON.stringify(args.frame_evidence) !== JSON.stringify(manifest.frames.map(frame => frame.file))) throw new Error('invalid_frame');
        const frames = manifest.frames;
        for (const frame of frames) {
          for (const directory of ['workspace', 'control']) {
            const bytes = await readSafe(path.join(runRoot, directory), path.join(runRoot, directory, frame.file), 8 * 1024 * 1024);
            if (createHash('sha256').update(bytes).digest('hex') !== frame.sha256) throw new Error('invalid_frame');
          }
        }
        const evidence = path.join(runRoot, 'control', 'review.json');
        let review;
        try { review = JSON.parse(await readSafe(runRoot, evidence)); }
        catch (error) { if (error.code !== 'ENOENT') throw error; }
        if (!review) {
          review = { reviewer: 'AI agent (Codex)', notes: args.notes.trim(), frames, asset_sha256: asset.sha256, observed_at: now() };
          await writeJson(runRoot, evidence, review);
        } else if (review.notes !== args.notes.trim() || JSON.stringify(review.frames) !== JSON.stringify(frames) || review.asset_sha256 !== asset.sha256) throw new Error('conflicting_review');
        const publication = JSON.parse(await readSafe(runRoot, frozen.publication));
        for (const key of Object.keys(fixed)) delete fixed[key];
        Object.assign(fixed, { approval_id: publication.visual_approval_id, asset: asset.path, product: prepare.product_id,
          account: prepare.account_id, ledger: prepare.approvals_path, owner_confirmation: review.reviewer,
          confirmation_ref: evidence, approved_at: review.observed_at });
      }
      const invoke = factoryExecutor ?? (await import('../factory-mcp.mjs')).callFactoryTool;
      invoked = true;
      const result = await invoke(name, fixed, { signal });
      if (name === 'factory_render' && input.mode === 'publish' && result.structuredContent?.result?.output) {
        const render = result.structuredContent.result;
        try {
          const manifest = await reviewFrames(runRoot, render, signal);
          result.structuredContent.result = { ...render, review_frames: manifest.frames, review_media: manifest.media, review_state: 'frames_ready' };
        } catch {
          result.structuredContent.result = { ...render, review_frames: [], review_state: 'unavailable', review_reason: 'verified_video_frame_extraction_required' };
        }
        result.content = [{ type: 'text', text: JSON.stringify(result.structuredContent) }];
      }
      return await appendTool(runRoot, name, result);
    } catch {
      return appendTool(runRoot, name, failed(invoked ? 'factory_transport_error' : 'factory_input_or_transport_error'));
    }
  };
  return (name, args = {}) => {
    const result = queue.then(() => execute(name, args));
    queue = result.catch(() => {});
    return result;
  };
}

async function main() {
  if (process.argv.length !== 4 || process.argv[2] !== '--run-root' || !path.isAbsolute(process.argv[3])) throw new Error('Invalid bridge invocation.');
  const runRoot = process.argv[3];
  const input = JSON.parse(await readSafe(runRoot, path.join(runRoot, 'input', 'project.json')));
  const [{ McpServer }, { StdioServerTransport }, { z }] = await Promise.all([
    import('@modelcontextprotocol/sdk/server/mcp.js'), import('@modelcontextprotocol/sdk/server/stdio.js'), import('zod'),
  ]);
  const server = new McpServer({ name: 'monk-factory-run', version: '1.0.0' });
  const invoke = createRunToolCaller({ runRoot });
  for (const name of boundToolNames(input.mode)) {
    const schema = name === 'factory_publish' ? z.object({ operation: z.enum(operations) }).strict()
      : name === 'factory_record_review' ? z.object({ notes: z.string().min(1).max(4000), frame_evidence: z.array(z.string().min(1).max(200)).min(1).max(12) }).strict() : z.object({}).strict();
    server.registerTool(name, { description: name === 'factory_record_review'
      ? 'Record your actual AI observation of every server-extracted review_frame returned by factory_render. Supply those exact workspace file references and notes. Never claim a human reviewed it.'
      : `${name} for this run only. Inputs are fixed by the server; preserve the returned CLI exit code, cost unknowns and provider fences.`, inputSchema: schema,
    annotations: { readOnlyHint: name === 'factory_plan' } }, args => invoke(name, args));
  }
  let closing;
  const close = () => closing ||= (async () => {
    const { stopOwnedChildren } = await import('../factory-mcp.mjs');
    await stopOwnedChildren(); await server.close();
  })();
  process.once('SIGTERM', close); process.once('SIGINT', close);
  process.stdin.once('end', close); process.stdin.once('close', close); server.server.onclose = close;
  await server.connect(new StdioServerTransport());
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stderr.write('Factory bridge could not start.\n'); process.exitCode = 1; });
}
