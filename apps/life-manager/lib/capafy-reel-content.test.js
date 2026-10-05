"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const {
  CAPAFY_REEL_EXAMPLES,
  buildCapafyReelCtaUrl,
  capafyReelHookText,
  capafyReelTextGenerator,
  selectCapafyReelEarner,
} = require("./capafy-reel-content.js");

const SELECTOR_SCRIPT = path.resolve(__dirname, "..", "..", "..", "skills", "earn", "capafy-marketing", "scripts", "select_capafy_distribute_skill.py");

test("CTA url for an earner contains ct=capafy-reel-<slug>", () => {
  const earner = { capafy_skill: "hook-lab", agent_id: "8123079349", landing_url: "https://capafy.ai/agent/8123079349", ct: "capafy-reel-hook-lab" };
  const url = buildCapafyReelCtaUrl(earner);
  assert.equal(url, "https://capafy.ai/agent/8123079349?ct=capafy-reel-hook-lab");
  assert.match(url, /\?ct=capafy-reel-hook-lab$/);
});

test("CTA url falls back to a derived ct and landing_url when the selector omits them", () => {
  const url = buildCapafyReelCtaUrl({ capafy_skill: "slide-maker", agent_id: "8828622062" });
  assert.equal(url, "https://capafy.ai/agent/8828622062?ct=capafy-reel-slide-maker");
});

test("hook text surfaces the real LISTING.md example input and output for every wired skill", () => {
  for (const slug of Object.keys(CAPAFY_REEL_EXAMPLES)) {
    const text = capafyReelHookText({ earner: { capafy_skill: slug }, locale: "en" });
    assert.match(text, /You send:/);
    assert.ok(text.includes(CAPAFY_REEL_EXAMPLES[slug].input.split("—")[0].trim().slice(0, 10)), slug);
  }
});

test("hook text generation fails closed for a skill with no wired example", () => {
  assert.throws(() => capafyReelHookText({ earner: { capafy_skill: "unknown-skill" } }), /no LISTING\.md example wired/);
});

test("selectCapafyReelEarner rejects a selector result with no skill", () => {
  assert.throws(() => selectCapafyReelEarner({ runSelector: () => ({}) }), /no skill/);
});

test("capafyReelTextGenerator matches the textGenerator({styleHint,avoidTexts,locale}) -> {hook,costUsd} adapter contract", async () => {
  const runSelector = () => ({ capafy_skill: "tiktok-script-pro", agent_id: "2844813315", landing_url: "https://capafy.ai/agent/2844813315", ct: "capafy-reel-tiktok-script-pro" });
  const generated = await capafyReelTextGenerator({ locale: "en", runSelector });
  assert.equal(typeof generated.hook, "string");
  assert.ok(generated.hook.length > 0);
  assert.equal(generated.costUsd, 0);
  assert.equal(generated.ctaUrl, "https://capafy.ai/agent/2844813315?ct=capafy-reel-tiktok-script-pro");
});

test("rotation only ever picks an online, profitable earner (reuses capafy-distribute's own ranking script)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "capafy-reel-test-"));
  const products = {
    products: {
      "capafy-skills": {
        skills: {
          "offline-loser": { agent_id: "1000000001" },
          "online-winner-a": { agent_id: "1000000002" },
          "online-winner-b": { agent_id: "1000000003" },
          "online-but-unprofitable": { agent_id: "1000000004" },
        },
      },
    },
  };
  const analytics = {
    per_skill_rows: [
      { agent_id: "1000000001", status: "offline", profit_30d_actual_usd: 50 },
      { agent_id: "1000000002", status: "online", profit_30d_actual_usd: 120 },
      { agent_id: "1000000003", status: "online", profit_30d_actual_usd: 40 },
      { agent_id: "1000000004", status: "online", profit_30d_actual_usd: -5 },
    ],
  };
  const productsPath = path.join(dir, "products.json");
  const analyticsPath = path.join(dir, "analytics.json");
  fs.writeFileSync(productsPath, JSON.stringify(products));
  fs.writeFileSync(analyticsPath, JSON.stringify(analytics));

  const onlineEarners = new Set(["online-winner-a", "online-winner-b"]);
  const seen = new Set();
  for (let slot = 0; slot < 8; slot += 1) {
    const stdout = execFileSync("python3", [
      SELECTOR_SCRIPT, "--date", "2026-10-05", "--products", productsPath, "--analytics", analyticsPath,
      "--channel", "capafy-reel", "--slot", String(slot),
    ], { encoding: "utf8" });
    const result = JSON.parse(stdout);
    assert.ok(onlineEarners.has(result.capafy_skill), `slot ${slot} picked ${result.capafy_skill}`);
    assert.equal(result.ct, `capafy-reel-${result.capafy_skill}`);
    seen.add(result.capafy_skill);
  }
  // Both online earners get picked in turn across the 8 three-hour slots;
  // the offline and unprofitable skills are never selected.
  assert.deepEqual(seen, onlineEarners);
});
