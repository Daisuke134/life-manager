/**
 * Responses API brain adapter.
 *
 * The loop still owns scheduling, tool execution, leases, and receipts.  This module only
 * translates the existing bounded wake context into the Responses item contract and translates
 * one model function_call back into the loop's existing parseToolCall shape.
 */

import { buildSystemPrompt, buildUserMessage, getToolDefinitions } from './prompt.mjs';

const DEFAULT_BASE_URL = 'https://api.openai.com/v1';
const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_OUTPUT_TOKENS = 512;
const MAX_TIMEOUT_MS = 120_000;
const MAX_OUTPUT_TOKENS = 16_384;
const MAX_TOOLS = 32;
const HASH = /^[a-f0-9]{64}$/;

function invalid(message) {
  throw new Error(`responses adapter: ${message}`);
}

function boundedNumber(value, name, fallback, minimum, maximum) {
  const selected = value == null || value === '' ? fallback : Number(value);
  if (!Number.isInteger(selected) || selected < minimum || selected > maximum) {
    invalid(`${name} invalid`);
  }
  return selected;
}

function endpoint(config = {}) {
  const raw = String(
    config.OPENAI_RESPONSES_BASE_URL || config.OPENAI_BASE_URL || DEFAULT_BASE_URL,
  ).trim().replace(/\/+$/, '');
  let parsed;
  try { parsed = new URL(raw); } catch { invalid('base URL invalid'); }
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password
    || parsed.search || parsed.hash) {
    invalid('base URL invalid');
  }
  if (/\/responses$/i.test(parsed.pathname)) return parsed.toString();
  return `${parsed.toString()}/responses`;
}

function responsesTool(tool) {
  if (!tool || tool.type !== 'function' || !tool.function) invalid('tool definition invalid');
  const { name, description, parameters } = tool.function;
  if (typeof name !== 'string' || !name || typeof parameters !== 'object' || !parameters) {
    invalid('tool definition invalid');
  }
  return {
    type: 'function',
    name,
    ...(typeof description === 'string' && description ? { description } : {}),
    parameters,
  };
}

function contextHash(ctx) {
  const capsule = ctx && ctx.contextCapsule;
  if (capsule == null) return null;
  if (!capsule || typeof capsule !== 'object' || !HASH.test(String(capsule.content_sha256 || ''))) {
    invalid('context capsule hash invalid');
  }
  return String(capsule.content_sha256);
}

/** Build the POST /v1/responses request from one already-assembled wake context. */
export function buildResponsesRequest(ctx = {}, config = {}) {
  const slots = ctx.alwaysActEngaged ? ctx.alwaysActMenu : ctx.activeSkillSlots;
  const tools = getToolDefinitions(slots, { omitSleep: ctx.alwaysActEngaged === true })
    .map(responsesTool);
  if (tools.length > MAX_TOOLS) invalid('tool limit exceeded');
  const hash = contextHash(ctx);
  const request = {
    model: String(config.ANICCA_RESPONSES_MODEL || config.ANICCA_MODEL || ctx.model || 'gpt-6-astra'),
    instructions: buildSystemPrompt(ctx),
    input: [{ role: 'user', content: buildUserMessage(ctx) }],
    tools,
    tool_choice: 'auto',
    parallel_tool_calls: false,
    max_output_tokens: boundedNumber(
      config.RESPONSES_MAX_OUTPUT_TOKENS,
      'max output tokens',
      DEFAULT_MAX_OUTPUT_TOKENS,
      1,
      MAX_OUTPUT_TOKENS,
    ),
    // The control plane owns the capsule and ledger. Do not retain raw model responses by default.
    store: false,
    truncation: 'disabled',
  };
  if (hash) request.metadata = { context_sha256: hash };
  return request;
}

function outputText(response) {
  if (typeof response.output_text === 'string') return response.output_text;
  const output = Array.isArray(response.output) ? response.output : [];
  return output
    .filter((item) => item && item.type === 'message')
    .flatMap((item) => Array.isArray(item.content) ? item.content : [])
    .filter((item) => item && item.type === 'output_text' && typeof item.text === 'string')
    .map((item) => item.text)
    .join('');
}

function usage(value) {
  if (!value || typeof value !== 'object') return null;
  const result = {};
  for (const key of ['input_tokens', 'output_tokens', 'total_tokens']) {
    if (Number.isInteger(value[key]) && value[key] >= 0) result[key] = value[key];
  }
  return Object.keys(result).length ? result : null;
}

/** Translate typed Responses output Items to the existing chat-shaped parser contract. */
export function normalizeResponsesResponse(response) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    invalid('response invalid');
  }
  if (typeof response.id !== 'string' || !response.id.trim() || response.id.length > 200) {
    invalid('response id invalid');
  }
  const output = Array.isArray(response.output) ? response.output : [];
  const calls = output.filter((item) => item && item.type === 'function_call');
  if (calls.length > 1) invalid('multiple function calls are not allowed in one wake');
  const text = outputText(response);
  const normalized = { ...response };
  if (calls.length === 1) {
    const call = calls[0];
    if (typeof call.name !== 'string' || !call.name || typeof call.call_id !== 'string' || !call.call_id) {
      invalid('function call identity invalid');
    }
    const args = typeof call.arguments === 'string'
      ? call.arguments
      : call.arguments && typeof call.arguments === 'object'
        ? JSON.stringify(call.arguments)
        : null;
    if (args == null || args.length > 32_000) invalid('function call arguments invalid');
    normalized.choices = [{
      message: {
        role: 'assistant',
        content: text || null,
        tool_calls: [{
          id: typeof call.id === 'string' ? call.id : call.call_id,
          type: 'function',
          function: { name: call.name, arguments: args },
        }],
      },
    }];
  } else {
    if (!text) invalid('response output empty');
    normalized.choices = [{ message: { role: 'assistant', content: text } }];
  }
  normalized.output_text = text;
  normalized._anicca = {
    response_id: response.id,
    ...(usage(response.usage) ? { usage: usage(response.usage) } : {}),
  };
  return normalized;
}

async function readBody(response) {
  if (!response || typeof response.text !== 'function') invalid('response body unavailable');
  const text = await response.text();
  if (typeof text !== 'string' || text.length > 2 * 1024 * 1024) invalid('response body invalid');
  return text;
}

/** Execute one bounded Responses request. The loop remains the only effect/tool executor. */
export async function thinkResponses(ctx, config = {}, { fetchImpl } = {}) {
  const request = buildResponsesRequest(ctx, config);
  const url = endpoint(config);
  const key = String(config.OPENAI_API_KEY || process.env.OPENAI_API_KEY || '').trim();
  let parsedUrl;
  try { parsedUrl = new URL(url); } catch { invalid('endpoint invalid'); }
  if (parsedUrl.hostname === 'api.openai.com' && !key) invalid('API key missing');
  const fetcher = fetchImpl || globalThis.fetch;
  if (typeof fetcher !== 'function') invalid('fetch unavailable');
  const timeoutMs = boundedNumber(
    config.RESPONSES_TIMEOUT_MS,
    'timeout',
    DEFAULT_TIMEOUT_MS,
    1,
    MAX_TIMEOUT_MS,
  );
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (key) headers.Authorization = `Bearer ${key}`;
    const response = await fetcher(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(request),
      signal: controller.signal,
    });
    if (!response || !response.ok) {
      throw new Error(`responses HTTP ${response ? response.status : 'no response'}`);
    }
    let body;
    try { body = JSON.parse(await readBody(response)); } catch { invalid('response JSON invalid'); }
    const normalized = normalizeResponsesResponse(body);
    normalized._anicca.context_sha256 = request.metadata?.context_sha256 || null;
    normalized._anicca.timeout_ms = timeoutMs;
    normalized._anicca.tool_count = request.tools.length;
    return normalized;
  } catch (error) {
    if (controller.signal.aborted) throw new Error(`responses_timeout: exceeded ${timeoutMs}ms`);
    if (error && /^responses HTTP /.test(String(error.message || ''))) throw error;
    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    clearTimeout(timer);
  }
}

