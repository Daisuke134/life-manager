import {createHash} from 'node:crypto';
import path from 'node:path';

const keys = ['version', 'owner_id', 'occurrence_id', 'run_id', 'task_id', 'release_sha',
  'task_class', 'provider', 'model', 'effort', 'prompt', 'schema', 'workdir',
  'timeout_seconds', 'effect_mode', 'session_isolation', 'attachments', 'owned_resume_ref'];
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
function fail(field) { throw new Error(`invalid RunRequest field: ${field}`); }
function closed(value, fields) {
  if (!object(value) || Object.keys(value).length !== fields.length || fields.some(k => !Object.hasOwn(value, k))) fail('shape');
}
function safeId(value) { return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(value) && !value.includes('..'); }
export const tupleDigest = tuple => createHash('sha256').update(JSON.stringify(tuple)).digest('hex');
function jsonValue(value, ancestors = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (!value || typeof value !== 'object' || ancestors.has(value)) fail('JSON value');
  if (!Array.isArray(value) && ![Object.prototype, null].includes(Object.getPrototypeOf(value))) fail('JSON object');
  ancestors.add(value);
  const out = Array.isArray(value) ? value.map(v => jsonValue(v, ancestors)) :
    Object.fromEntries(Object.keys(value).sort().map(k => [k, jsonValue(value[k], ancestors)]));
  ancestors.delete(value); return out;
}
export function requestDigest(request) {
  const {run_id, ...content} = validateRunRequest(request);
  return createHash('sha256').update(JSON.stringify(jsonValue(content))).digest('hex');
}
function freeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
export function validateRunRequest(value) {
  closed(value, keys);
  if (value.version !== 2) fail('version');
  for (const k of ['owner_id', 'occurrence_id', 'run_id', 'task_id', 'task_class']) if (!safeId(value[k])) fail(k);
  if (!/^[a-f0-9]{40}$/.test(value.release_sha)) fail('release_sha');
  if (value.provider !== 'codex') fail('provider');
  for (const k of ['model', 'effort', 'prompt']) if (typeof value[k] !== 'string' || !value[k].trim()) fail(k);
  if (!object(value.schema)) fail('schema');
  if (typeof value.workdir !== 'string' || !path.isAbsolute(value.workdir)) fail('workdir');
  if (!Number.isSafeInteger(value.timeout_seconds) || value.timeout_seconds <= 0) fail('timeout_seconds');
  if (!['read_only', 'brokered'].includes(value.effect_mode)) fail('effect_mode');
  if (!['stable_owner', 'fresh_task'].includes(value.session_isolation)) fail('session_isolation');
  if (!Array.isArray(value.attachments)) fail('attachments');
  for (const a of value.attachments) {
    closed(a, ['path', 'mime_type', 'sha256']);
    if (typeof a.path !== 'string' || !path.isAbsolute(a.path) ||
        !['image/png', 'image/jpeg', 'image/webp'].includes(a.mime_type) || !/^[a-f0-9]{64}$/.test(a.sha256)) fail('attachments');
  }
  // Ownership is verified by the caller bridge, never inferred from a thread ID.
  if (value.owned_resume_ref !== null) {
    const r = value.owned_resume_ref;
    closed(r, ['thread_id', 'owner_id', 'proof_ref']);
    if (!safeId(r.thread_id) || r.owner_id !== value.owner_id || typeof r.proof_ref !== 'string' || !path.isAbsolute(r.proof_ref)) fail('owned_resume_ref');
  }
  return freeze(jsonValue(value));
}
export function buildRunIdentity(request, agentId) {
  if (!safeId(agentId)) fail('agentId');
  const session = [request.owner_id, request.task_class];
  if (request.session_isolation === 'fresh_task') session.push(request.occurrence_id, request.task_id);
  return Object.freeze({sessionKey: `agent:${agentId}:lm:${tupleDigest(session)}`,
    idempotencyKey: tupleDigest([request.owner_id, request.occurrence_id, request.task_id])});
}
