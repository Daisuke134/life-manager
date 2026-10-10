#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const { connectCdp } = require("../lib/cdp-connection.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const {
  extractTikTokNativeMetrics,
  persistTikTokCombinedSnapshot,
  persistPostizPhotoSnapshot,
  persistTikTokNativeSnapshot,
} = require("../lib/tiktok-native-metric-source.js");

async function postizAnalytics(input, env = process.env) {
  if (!input.integrationId && !input.providerPostId) return null;
  if (!input.integrationId || !input.providerPostId || !env.LM_POSTIZ_API_KEY) {
    throw new Error("combined TikTok metrics require integrationId, providerPostId, and LM_POSTIZ_API_KEY");
  }
  const request = async (url) => {
    const response = await fetch(url, { headers: { Authorization: env.LM_POSTIZ_API_KEY } });
    if (!response.ok) throw new Error(`Postiz analytics HTTP ${response.status}`);
    return response.json();
  };
  const [account, post] = await Promise.all([
    request(`https://api.postiz.com/public/v1/analytics/${encodeURIComponent(input.integrationId)}?date=1`),
    request(`https://api.postiz.com/public/v1/analytics/post/${encodeURIComponent(input.providerPostId)}?date=1`),
  ]);
  return { account, post };
}

async function collectTikTokWindow(input, env = process.env, observedAt = new Date().toISOString()) {
  // The endpoint comes from the browser-guard lease (with-browser.sh tiktok-anicca-jp), never a fixed
  // port: the old default was the operator's own Chrome, which loops must not touch (2026-09-30).
  const endpoint = env.LM_CDP_ENDPOINT; if (!endpoint) throw new Error("TikTok native metric CDP endpoint missing (run under with-browser.sh)"); const base = new URL(endpoint); if (base.protocol !== "http:" || base.hostname !== "127.0.0.1" || !base.port) throw new Error("TikTok native metric CDP endpoint invalid");
  const request = async (suffix, options = {}) => { const response = await fetch(new URL(suffix, base), { ...options, signal: AbortSignal.timeout(10_000) }); if (!response.ok) throw new Error(`TikTok native metric CDP HTTP ${response.status}`); return response.json(); };
  const version = await request("/json/version"); const target = await request(`/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" }); if (!version.webSocketDebuggerUrl || !target.id) throw new Error("TikTok native metric CDP target unavailable");
  let client;
  try {
    client = await connectCdp(version.webSocketDebuggerUrl, { targetId: target.id, timeoutMs: 60_000 }); await client.navigate(input.publicUrl); await new Promise((resolve) => setTimeout(resolve, 2_000));
    const scripts = await client.evaluate("Array.from(document.scripts, (script) => script.textContent || '')"); if (!Array.isArray(scripts)) throw new Error("TikTok native metric scripts unavailable"); const metrics = extractTikTokNativeMetrics(scripts, input);
    const provider = await postizAnalytics(input, env);
    const result = provider ? persistTikTokCombinedSnapshot({
      ...input,
      dataDir: resolveDataRoot(env),
      observedAt,
      metrics,
      postizAccountAnalytics: provider.account,
      postizPostAnalytics: provider.post,
    }) : persistTikTokNativeSnapshot({
      ...input,
      dataDir: resolveDataRoot(env),
      observedAt,
      metrics,
    });
    return { created: result.created, file: result.file, snapshot: result.snapshot, post: result.snapshot.post, account: result.snapshot.account_metrics };
  } finally {
    if (client) await client.close();
    try { await fetch(new URL(`/json/close/${encodeURIComponent(target.id)}`, base), { method: "PUT", signal: AbortSignal.timeout(5_000) }); } catch {}
  }
}

async function collectPostizPhotoWindow(input, env = process.env, observedAt = new Date().toISOString()) {
  const provider = await postizAnalytics(input, env);
  if (!provider) throw new Error("Postiz photo metrics are unavailable");
  if (Array.isArray(provider.post) && provider.post.length === 0) {
    return { created: false, deferred: true, reason: "postiz_post_analytics_empty" };
  }
  const result = persistPostizPhotoSnapshot({ ...input, dataDir: resolveDataRoot(env), observedAt, postizAccountAnalytics: provider.account, postizPostAnalytics: provider.post });
  return { created: result.created, file: result.file, snapshot: result.snapshot, post: result.snapshot.post, account: result.snapshot.account_metrics };
}

if (require.main === module) collectTikTokWindow(JSON.parse(fs.readFileSync(process.argv[2], "utf8"))).then((result) => process.stdout.write(`${JSON.stringify({ created: result.created, file: result.file, post: result.post, account: result.account })}\n`)).catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
module.exports = { collectPostizPhotoWindow, collectTikTokWindow, postizAnalytics };
