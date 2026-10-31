import assert from "node:assert/strict";
import { test } from "node:test";
import { parseClick, targetUrl, clickKey } from "../site/netlify/functions/go.mjs";
import { summarize } from "../site/netlify/functions/go-stats.mjs";

test("legacy link keeps the exact old redirect and key shape", () => {
  const click = parseClick("https://x.app/.netlify/functions/go/8123079349");
  assert.equal(
    targetUrl(click),
    "https://capafy.ai/agent/8123079349?utm_source=instagram_bio&utm_medium=bio_link&utm_campaign=capafy_marketing",
  );
  assert.equal(clickKey(click, 1, "u"), "clicks/8123079349/1-u");
});

test("tracked link records platform/post and forwards ct", () => {
  const click = parseClick("https://x.app/go/8123079349/x/x-hook-lab-2026-10-31-am?ct=hooklab_x");
  assert.deepEqual(click, { agentId: "8123079349", platform: "x", post: "x-hook-lab-2026-10-31-am", ct: "hooklab_x" });
  assert.equal(clickKey(click, 1, "u"), "clicks/8123079349/x/x-hook-lab-2026-10-31-am/1-u");
  const target = new URL(targetUrl(click));
  assert.equal(target.searchParams.get("ct"), "hooklab_x");
  assert.equal(target.searchParams.get("utm_source"), "x");
  assert.equal(target.searchParams.get("utm_content"), "x-hook-lab-2026-10-31-am");
});

test("unsafe platform/post/ct tokens are dropped", () => {
  const click = parseClick("https://x.app/go/1/a%20b/c?ct=%3Cs%3E");
  assert.equal(click.platform, "");
  assert.equal(click.ct, "");
});

test("stats summarize legacy and tracked keys", () => {
  const { counts, detail } = summarize(
    ["clicks/1/5-u", "clicks/1/x/p1/6-u", "clicks/1/article/a1/7-u", "clicks/1/x/p1/8-u"],
    ["1", "2"],
  );
  assert.deepEqual(counts, { 1: 4, 2: 0 });
  assert.equal(detail.total, 4);
  assert.deepEqual(detail.platforms, { legacy: 1, x: 2, article: 1 });
  assert.deepEqual(detail.agents["1"].posts, { "x/p1": 2, "article/a1": 1 });
});
