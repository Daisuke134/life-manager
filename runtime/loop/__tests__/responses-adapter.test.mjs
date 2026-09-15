import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildResponsesRequest,
  normalizeResponsesResponse,
  thinkResponses,
} from '../responses-adapter.mjs';
import { think } from '../brain.mjs';
import { parseToolCall } from '../parse-tool-call.mjs';

const capsule = Object.freeze({
  capsule_id: 'capsule-1',
  content_sha256: 'a'.repeat(64),
});

const context = {
  walletAddress: 'wallet-public',
  balanceUsdc: 1,
  tier: 'lean',
  model: 'free/glm-4.7',
  wakeId: 'wake-1',
  recentLedgerLines: [],
  activeSkillSlots: ['earn/gig', 'cook'],
  skillCatalog: { 'earn/gig': 'earn', cook: 'discover' },
  recentSlots: [],
  positionsSummary: '',
  genesisPrompt: '',
  contextCapsule: capsule,
};

test('buildResponsesRequest uses Responses item/tool shapes and binds the capsule hash', () => {
  const request = buildResponsesRequest(context, {
    ANICCA_RESPONSES_MODEL: 'gpt-6-astra',
    RESPONSES_MAX_OUTPUT_TOKENS: 300,
  });

  assert.equal(request.model, 'gpt-6-astra');
  assert.equal(request.store, false);
  assert.equal(request.max_output_tokens, 300);
  assert.deepEqual(request.metadata, { context_sha256: 'a'.repeat(64) });
  assert.equal(request.parallel_tool_calls, false);
  assert.equal(request.instructions.includes('Wake ID: wake-1'), true);
  assert.equal(Array.isArray(request.input), true);
  assert.equal(request.input[0].role, 'user');
  assert.equal(request.tools[0].type, 'function');
  assert.equal(request.tools[0].name, 'run_skill');
  assert.equal(request.tools[0].parameters.type, 'object');
  assert.equal('function' in request.tools[0], false);
});

test('normalizeResponsesResponse converts one function_call into the loop tool-call contract', () => {
  const normalized = normalizeResponsesResponse({
    id: 'resp-1',
    output: [{
      type: 'function_call',
      id: 'fc-1',
      call_id: 'call-1',
      name: 'run_skill',
      arguments: JSON.stringify({ slot: 'cook', args: { query: 'new earner' } }),
    }],
    usage: { input_tokens: 12, output_tokens: 4, total_tokens: 16 },
  });

  assert.deepEqual(normalized.choices[0].message.tool_calls, [{
    id: 'fc-1',
    type: 'function',
    function: {
      name: 'run_skill',
      arguments: JSON.stringify({ slot: 'cook', args: { query: 'new earner' } }),
    },
  }]);
  assert.equal(normalized._anicca.response_id, 'resp-1');
  assert.deepEqual(normalized._anicca.usage, { input_tokens: 12, output_tokens: 4, total_tokens: 16 });
});

test('thinkResponses posts a redacted, bounded request and returns Responses output text', async () => {
  const calls = [];
  const response = await thinkResponses(context, {
    OPENAI_RESPONSES_BASE_URL: 'http://127.0.0.1:9999/v1',
    OPENAI_API_KEY: 'test-key',
    ANICCA_RESPONSES_MODEL: 'gpt-6-astra',
  }, {
    fetchImpl: async (url, options) => {
      calls.push({ url, options, body: JSON.parse(options.body) });
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          id: 'resp-2',
          output: [{
            type: 'message',
            role: 'assistant',
            content: [{ type: 'output_text', text: 'done' }],
          }],
        }),
      };
    },
  });

  assert.equal(response.output_text, 'done');
  assert.equal(response.choices[0].message.content, 'done');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'http://127.0.0.1:9999/v1/responses');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer test-key');
  assert.equal(calls[0].body.store, false);
  assert.equal(JSON.stringify(calls[0].body).includes('test-key'), false);
});

test('thinkResponses fails closed on multiple function calls and HTTP errors', async () => {
  await assert.rejects(
    () => thinkResponses(context, { OPENAI_RESPONSES_BASE_URL: 'http://127.0.0.1:9999/v1' }, {
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          id: 'resp-many',
          output: [
            { type: 'function_call', id: 'a', call_id: 'a', name: 'run_skill', arguments: '{}' },
            { type: 'function_call', id: 'b', call_id: 'b', name: 'run_skill', arguments: '{}' },
          ],
        }),
      }),
    }),
    /multiple function calls/i,
  );
  await assert.rejects(
    () => thinkResponses(context, { OPENAI_RESPONSES_BASE_URL: 'http://127.0.0.1:9999/v1' }, {
      fetchImpl: async () => ({ ok: false, status: 503, text: async () => 'secret body' }),
    }),
    /503/,
  );
});

test('thinkResponses aborts a request that exceeds its bounded timeout', async () => {
  await assert.rejects(
    () => thinkResponses(context, {
      OPENAI_RESPONSES_BASE_URL: 'http://127.0.0.1:9999/v1',
      RESPONSES_TIMEOUT_MS: 10,
    }, {
      fetchImpl: (_url, options) => new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
      }),
    }),
    /timeout|aborted/i,
  );
});

test('think routes ANICCA_BRAIN=responses through the adapter and preserves the existing parser contract', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({
      id: 'resp-routed',
      output: [{
        type: 'function_call',
        id: 'fc-routed',
        call_id: 'call-routed',
        name: 'run_skill',
        arguments: JSON.stringify({ slot: 'cook', args: { query: 'route test' } }),
      }],
    }),
  });
  try {
    const response = await think(context, {
      ANICCA_BRAIN: 'responses',
      OPENAI_RESPONSES_BASE_URL: 'http://127.0.0.1:9999/v1',
    });
    assert.deepEqual(parseToolCall(response), {
      slot: 'cook',
      args: { query: 'route test' },
    });
    assert.equal(response._anicca.response_id, 'resp-routed');
  } finally {
    globalThis.fetch = previousFetch;
  }
});
