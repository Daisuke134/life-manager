'use strict';
const http = require('node:http');

// This VM receives platform wake notifications. Business work stays in the
// existing central queue and is dispatched separately through detached exec.
function createMaritimeManagerServer({ config = {}, relayWake, readSchedules, relayTimeoutMs = 10000 } = {}) {
  const tenantId = config.tenantId;
  const releaseSha = config.releaseSha;
  if (typeof tenantId !== 'string' || !/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(tenantId)
    || typeof releaseSha !== 'string' || !/^[0-9a-f]{40}$/.test(releaseSha)
    || !Number.isInteger(relayTimeoutMs) || relayTimeoutMs < 1 || relayTimeoutMs > 25000) {
    throw new Error('maritime_server_config_invalid');
  }
  const modelReady = config.modelReady === true;
  const ready = modelReady && typeof relayWake === 'function';
  function json(response, status, body) {
    response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
    response.end(JSON.stringify(body));
  }
  const server = http.createServer(async (request, response) => {
    if (request.method === 'GET' && request.url === '/health') {
      json(response, ready ? 200 : 503, { ok: ready, releaseSha,
        ...(!ready ? { errorClass: modelReady ? 'wake_relay_unconfigured' : 'cloud_model_config_missing' } : {}) });
      return;
    }
    if (request.method === 'GET' && request.url === '/schedules') {
      if (!ready) { json(response, 503, { errorClass: 'schedule_unavailable' }); return; }
      try {
        const schedules = readSchedules ? await readSchedules()
          : require('../lib/maritime-manager-schedules.js').readMaritimeSchedules({ tenantId, releaseSha });
        json(response, 200, schedules);
      } catch { json(response, 503, { errorClass: 'schedule_unavailable' }); }
      return;
    }
    if (request.method !== 'POST' || request.url !== '/chat') {
      json(response, 404, { errorClass: 'not_found' }); return;
    }
    let body;
    try {
      const chunks = []; let bytes = 0;
      for await (const chunk of request) {
        bytes += chunk.length;
        if (bytes <= 8192) chunks.push(chunk);
      }
      if (bytes > 8192) { json(response, 413, { errorClass: 'body_too_large' }); return; }
      body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!body || Array.isArray(body) || typeof body.message !== 'string'
        || (body.source != null && typeof body.source !== 'string')) throw new Error();
    } catch { json(response, 400, { errorClass: 'invalid_message' }); return; }
    if (!ready) { json(response, 503, { response: '現在、実行環境を準備しています。' }); return; }
    const kind = body.source === 'scheduled'
      ? (body.message === 'lm:cycle' ? 'cycle' : body.message === 'lm:report' ? 'report' : null) : null;
    if (!kind) {
      json(response, 200, { response: 'Life Managerは定期的に仕事を進め、結果を日次レポートでお知らせします。' }); return;
    }
    const abort = new AbortController(); let timer;
    try {
      const accepted = await Promise.race([
        Promise.resolve().then(() => relayWake({ tenantId, releaseSha, kind }, { signal: abort.signal })),
        new Promise((_, reject) => { timer = setTimeout(() => { abort.abort(); reject(new Error('relay_timeout')); }, relayTimeoutMs); }),
      ]);
      if (accepted?.accepted !== true) throw new Error();
      json(response, 202, { response: '処理を受け付けました。結果は日次レポートでお知らせします。' });
    } catch { json(response, 503, { response: '受付結果を確認できません。日次レポートの更新を確認してください。' }); }
    finally { clearTimeout(timer); }
  });
  server.requestTimeout = 25000;
  return server;
}
function startMaritimeManagerServer({ env = process.env, prepareRuntime, fetchImpl = globalThis.fetch } = {}) {
  const port = Number(env.PORT);
  if (!/^[0-9]+$/.test(String(env.PORT || '')) || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('maritime_server_port_invalid');
  }
  let relayWake;
  if (env.LM_WAKE_RELAY_URL && env.LM_WAKE_RELAY_TOKEN) {
    let url;
    try { url = new URL(env.LM_WAKE_RELAY_URL); } catch { throw new Error('maritime_server_relay_invalid'); }
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
      || url.pathname !== '/api/internal/maritime/wake' || /[\r\n\0]/.test(env.LM_WAKE_RELAY_TOKEN)) {
      throw new Error('maritime_server_relay_invalid');
    }
    relayWake = async (input, { signal }) => {
      const response = await fetchImpl(url.toString(), { method: 'POST', redirect: 'error', signal,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.LM_WAKE_RELAY_TOKEN}` },
        body: JSON.stringify(input) });
      if (!response.ok) return { accepted: false };
      const result = await response.json();
      return { accepted: result?.accepted === true };
    };
  }
  const prepare = prepareRuntime || require('./runtime-env.js').prepareMaritimeRuntime;
  const runtime = prepare({ env });
  const server = createMaritimeManagerServer({ config: runtime.config, relayWake });
  server.listen(port, '0.0.0.0');
  return server;
}
if (require.main === module) {
  try { startMaritimeManagerServer(); }
  catch { process.stderr.write('maritime_server_startup_failed\n'); process.exitCode = 2; }
}
module.exports = { createMaritimeManagerServer, startMaritimeManagerServer };
