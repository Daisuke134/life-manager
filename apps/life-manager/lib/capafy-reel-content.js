"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");

// Capafy's online top-sellers (e.g. Ocup Football Analysis: $4,208 first
// week, per Capafy's own X) sell via short videos that show the agent's real
// output. This rotates the Capafy IG reel lane through whichever of our own
// capafy-skills products the shared ranking script currently scores as the
// top *online* earner -- never a fixed favorite, never an offline/losing
// skill -- reusing the exact rotation the capafy-distribute-daily (free
// article) loop already runs, per AGENTS.md rule 9 "copy a sibling loop".
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SELECTOR_SCRIPT = path.join(REPO_ROOT, "skills", "earn", "capafy-marketing", "scripts", "select_capafy_distribute_skill.py");
const PRODUCTS_CONFIG = path.join(REPO_ROOT, "skills", "writer-agent", "config", "products.json");
const ANALYTICS_STATE = path.join(os.homedir(), ".local", "state", "life-manager", "state", "capafy-skill-analytics.json");
const REEL_CHANNEL = "capafy-reel";

function jstDateAndSlot(nowMs) {
  const date = new Date(nowMs);
  const dateStr = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo" }).format(date);
  const jstHour = Number(new Intl.DateTimeFormat("en-US", { hour: "2-digit", hour12: false, timeZone: "Asia/Tokyo" }).format(date));
  return { dateStr, slot: Math.floor(jstHour / 3) % 8 };
}

function defaultRunSelector({ date, channel, slot, productsConfig = PRODUCTS_CONFIG, analyticsState = ANALYTICS_STATE }) {
  const args = [SELECTOR_SCRIPT, "--date", date, "--products", productsConfig, "--channel", channel, "--slot", String(slot)];
  if (fs.existsSync(analyticsState)) args.push("--analytics", analyticsState);
  const stdout = execFileSync("python3", args, { encoding: "utf8" });
  return JSON.parse(stdout);
}

// Selects the current top online earner for the reel lane. `runSelector` is
// injectable so callers/tests can point at fixture products/analytics files
// without shelling out against production state.
function selectCapafyReelEarner({ nowMs = Date.now(), channel = REEL_CHANNEL, runSelector = defaultRunSelector } = {}) {
  const { dateStr, slot } = jstDateAndSlot(nowMs);
  const result = runSelector({ date: dateStr, channel, slot });
  if (!result || typeof result.capafy_skill !== "string" || !result.capafy_skill) {
    throw new Error("capafy reel earner selection returned no skill");
  }
  return result;
}

function buildCapafyReelCtaUrl(earner) {
  const landingUrl = String(earner.landing_url || `https://capafy.ai/agent/${earner.agent_id}`);
  const ct = String(earner.ct || `${REEL_CHANNEL}-${earner.capafy_skill}`);
  const separator = landingUrl.includes("?") ? "&" : "?";
  return `${landingUrl}${separator}ct=${ct}`;
}

// Real input -> real output pairs lifted verbatim from each skill's own
// LISTING.md "## 🧪 Example" section (read 2026-10-05). The point is to show
// the agent's actual output, same as Capafy's top-selling reels -- never an
// invented demo. Add an entry here whenever a new capafy-skills product is
// added to skills/writer-agent/config/products.json's "capafy-skills" list.
const CAPAFY_REEL_EXAMPLES = Object.freeze({
  "hook-lab": {
    input: "Hooks for a 30s TikTok about why most people quit the gym in January — energetic, for beginners.",
    output: "5 ready hooks incl. \"Stop going to the gym every day.\" / \"Day 1 is where you quit\" plus the recommended pick and a timed script.",
  },
  "tiktok-script-pro": {
    input: "A 30-second TikTok about why cold email still works in 2026.",
    output: "A recommended hook — \"Everyone says cold email is dead. It isn't.\" — plus a beat-by-beat HOOK → BUILD → PAYOFF → CTA script.",
  },
  "youtube-script-writer": {
    input: "An 8-minute video for self-taught beginners about five mistakes when learning to code.",
    output: "3 titles, a thumbnail idea, and a timestamped script opening with \"You're not bad at coding. You're making these five mistakes.\"",
  },
  "slide-maker": {
    input: "Make a 10-slide deck from these notes.",
    output: "A finished 10-slide deck, structured and ready to present.",
  },
});

function capafyReelHookText({ earner, locale = "en" }) {
  const example = CAPAFY_REEL_EXAMPLES[earner.capafy_skill];
  if (!example) throw new Error(`capafy reel has no LISTING.md example wired for skill ${earner.capafy_skill}`);
  if (locale === "ja") return `「${example.input}」と送ると → ${example.output}`;
  return `You send: "${example.input}" → You get: ${example.output}`;
}

// Matches the textGenerator({ styleHint, avoidTexts, locale }) -> { hook,
// costUsd } contract marketing-video-generation-adapter.js already calls for
// every anicca-ios lane (see marketing-slide-pack-text.js's
// generateVideoHookText), so the Capafy lane plugs into the same adapter
// without a network call or API key -- the content is already real and
// static per skill, not model-generated.
async function capafyReelTextGenerator({ locale = "en", nowMs, runSelector } = {}) {
  const earner = selectCapafyReelEarner({ nowMs, runSelector });
  return { hook: capafyReelHookText({ earner, locale }), costUsd: 0, earner, ctaUrl: buildCapafyReelCtaUrl(earner) };
}

// Mirrors marketing-app-store-cta.js's buildMarketingCtaCaptionRef shape
// (import a short-lived 0600 file into the content object store) but for
// the Capafy lane's dynamic per-earner CTA url instead of a fixed App Store
// url -- kept in this file rather than touching the shared App Store CTA
// module so no sibling app lane's behavior changes.
function buildCapafyReelCaptionRef({ objectStore, workspaceDir, ctaUrl, locale = "en" }) {
  if (!ctaUrl) throw new Error("capafy reel caption requires a ctaUrl");
  const line = locale === "ja" ? `続きはこちら → ${ctaUrl}` : `Try it → ${ctaUrl}`;
  fs.mkdirSync(workspaceDir, { recursive: true, mode: 0o700 });
  const candidate = path.join(workspaceDir, `.capafy-reel-cta-${process.pid}-${crypto.randomUUID()}.txt`);
  fs.writeFileSync(candidate, line, { mode: 0o600, flag: "wx" });
  try {
    return objectStore.import(candidate).ref;
  } finally {
    fs.unlinkSync(candidate);
  }
}

module.exports = {
  CAPAFY_REEL_EXAMPLES,
  REEL_CHANNEL,
  buildCapafyReelCaptionRef,
  buildCapafyReelCtaUrl,
  capafyReelHookText,
  capafyReelTextGenerator,
  selectCapafyReelEarner,
};
