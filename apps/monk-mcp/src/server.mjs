// Stateless Streamable-HTTP MCP server (JSON responses). Runs on Cloudflare Workers,
// Vercel/Netlify edge, Deno or Node 20+ (any runtime with fetch Request/Response).
import data from '../data/teachings.json' with { type: 'json' };

const SERVER = { name: 'anicca-monk-db', version: '0.1.0' };
const PROTOCOL = '2025-06-18';
const T = data.teachings;
const RO = { readOnlyHint: true, openWorldHint: false, destructiveHint: false };

export const tools = [
  { name: 'search_teachings', title: 'Search Buddhist teachings',
    description: 'Full-text search over source-linked public-domain Buddhist teachings (currently the full Dhammapada, 423 verses, Bhikkhu Sujato CC0 translation). Filter by collection, chapter/topic tag or teacher. Returns id, title, text and source URL.',
    inputSchema: { type: 'object', properties: {
      query: { type: 'string', description: 'Words to search for, e.g. "anger", "impermanence"' },
      tag: { type: 'string', description: 'Topic/chapter tag, e.g. "mind", "anger"' },
      teacher: { type: 'string' }, collection: { type: 'string' },
      limit: { type: 'integer', minimum: 1, maximum: 25, default: 5 } }, additionalProperties: false },
    annotations: RO },
  { name: 'get_teaching', title: 'Get one teaching',
    description: 'Get a single teaching by id (e.g. "dhp1") with full text, translator, license and source URL.',
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'], additionalProperties: false },
    annotations: RO },
  { name: 'daily_dhamma', title: 'Daily Dhamma',
    description: 'Return the teaching of the day (deterministic per UTC date, or for a given YYYY-MM-DD date).',
    inputSchema: { type: 'object', properties: { date: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' } }, additionalProperties: false },
    annotations: RO },
];

const norm = (s) => String(s ?? '').toLowerCase();
export function search({ query, tag, teacher, collection, limit = 5 } = {}) {
  const words = norm(query).split(/\W+/).filter(Boolean);
  const n = Math.min(Math.max(parseInt(limit) || 5, 1), 25);
  const scored = [];
  for (const t of T) {
    if (tag && !t.tags.some((x) => x.includes(norm(tag)))) continue;
    if (teacher && !norm(t.teacher).includes(norm(teacher))) continue;
    if (collection && !norm(t.collection).includes(norm(collection))) continue;
    const hay = norm(t.text + ' ' + t.chapter);
    const score = words.reduce((s, w) => s + (hay.includes(w) ? 1 : 0), 0);
    if (words.length && score === 0) continue;
    scored.push([score, t]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return { total: scored.length, results: scored.slice(0, n).map(([, t]) => t) };
}
export const get = ({ id }) => T.find((t) => t.id === norm(id).trim()) ?? null;
export function daily({ date } = {}) {
  const d = date ?? new Date().toISOString().slice(0, 10);
  const day = Math.floor(Date.parse(d + 'T00:00:00Z') / 86400000);
  if (Number.isNaN(day)) return null;
  return { date: d, teaching: T[((day * 7919) % T.length + T.length) % T.length] };
}

function callTool(name, args) {
  let out;
  if (name === 'search_teachings') out = search(args);
  else if (name === 'get_teaching') out = get(args) ?? { error: 'not_found' };
  else if (name === 'daily_dhamma') out = daily(args) ?? { error: 'invalid_date' };
  else return null;
  return { content: [{ type: 'text', text: JSON.stringify(out) }], structuredContent: out, isError: Boolean(out.error) };
}

export function rpc(msg) {
  const { id, method, params } = msg ?? {};
  const ok = (result) => ({ jsonrpc: '2.0', id, result });
  const err = (code, message) => ({ jsonrpc: '2.0', id: id ?? null, error: { code, message } });
  switch (method) {
    case 'initialize': return ok({ protocolVersion: params?.protocolVersion ?? PROTOCOL, capabilities: { tools: {} }, serverInfo: SERVER,
      instructions: 'Read-only Buddhist teachings database. Quote text verbatim and always cite source_url and translator.' });
    case 'ping': return ok({});
    case 'tools/list': return ok({ tools });
    case 'tools/call': { const r = callTool(params?.name, params?.arguments ?? {}); return r ? ok(r) : err(-32602, 'Unknown tool'); }
    default: return id === undefined ? null : err(-32601, 'Method not found');
  }
}

const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type, mcp-protocol-version, mcp-session-id, authorization', 'access-control-allow-methods': 'POST, OPTIONS' };
export async function handle(request) {
  const url = new URL(request.url);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (request.method === 'GET' && url.pathname === '/') return Response.json({ ...SERVER, mcp: url.origin + '/mcp', teachings: T.length, sources: data.sources }, { headers: CORS });
  if (url.pathname !== '/mcp') return new Response('Not found', { status: 404, headers: CORS });
  if (request.method !== 'POST') return new Response('Method not allowed', { status: 405, headers: { ...CORS, allow: 'POST' } });
  const body = await request.text();
  if (body.length > 65536) return new Response('Payload too large', { status: 413, headers: CORS });
  let msg; try { msg = JSON.parse(body); } catch { return Response.json({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }, { status: 400, headers: CORS }); }
  const res = Array.isArray(msg) ? msg.map(rpc).filter(Boolean) : rpc(msg);
  if (res === null || (Array.isArray(res) && !res.length)) return new Response(null, { status: 202, headers: CORS });
  return Response.json(res, { headers: CORS });
}

export default { fetch: handle };
