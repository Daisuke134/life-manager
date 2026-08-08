"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  validateRegistry,
  canonicalJson,
  sha256Canonical,
  matchesLabel,
  classifyLabel,
} = require("./cfo-registry.js");

function validFixture() {
  return {
    schema_version: 1,
    registry_id: "life_manager_cfo_financial_units",
    relevant_runtime_prefixes: ["ai.anicca.writer-", "ai.anicca.cfo-"],
    financial_units: [{
      financial_unit_id: "writer_agent", unit_kind: "business", display_order: 1,
      display_name: { en: "Writer Agent", ja: "Writer Agent" }, owner_ref: "human:dais",
      cost_center_refs: [], lifecycle: "active", runtime_matchers: ["ai.anicca.writer-*"],
      revenue_channel_ids: ["publisher_writer"], ledger_source_ids: ["writer_receipts"],
      evidence_refs: ["docs/writer-agent/WRITER-AGENT-SSOT.md"],
    }],
    runtime_exclusions: [{
      exclusion_id: "cfo_controller", runtime_matchers: ["ai.anicca.cfo-*"],
      classification: "controller", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    }],
    ledger_sources: [{
      ledger_source_id: "writer_receipts", probe_kind: "sqlite", locator: "writer-receipts",
      default_status: "available",
    }],
  };
}

function clone(value) {
  return structuredClone(value);
}

function invalidMutations() {
  return [
    (value) => {
      const next = clone(value);
      next.unknown_root_key = true;
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].unknown_unit_key = true;
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units.push(clone(next.financial_units[0]));
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].revenue_channel_ids = ["publisher_writer", "publisher_writer"];
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].unit_kind = "other";
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].lifecycle = "unknown";
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].evidence_refs = [];
      return next;
    },
    (value) => {
      const next = clone(value);
      next.monthly_revenue = 0;
      return next;
    },
    (value) => {
      const next = clone(value);
      next.api_secret = "not-a-secret";
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].owner_ref = "/Users/name/state";
      return next;
    },
    (value) => {
      const next = clone(value);
      next.financial_units[0].runtime_matchers = ["ai.anicca.*.writer-report"];
      return next;
    },
  ];
}

test("valid registry is frozen and exact/terminal-star labels classify once", () => {
  const registry = validateRegistry(validFixture());
  assert.equal(Object.isFrozen(registry), true);
  assert.equal(Object.isFrozen(registry.financial_units), true);
  assert.equal(Object.isFrozen(registry.financial_units[0]), true);
  assert.deepEqual(classifyLabel(registry, "ai.anicca.writer-report"), {
    kind: "financial_unit", targetIds: ["writer_agent"],
  });
  assert.deepEqual(classifyLabel(registry, "ai.anicca.cfo-controller"), {
    kind: "exclusion", targetIds: ["cfo_controller"],
  });
  assert.deepEqual(classifyLabel(registry, "ai.anicca.other"), {
    kind: "unmapped", targetIds: [],
  });
  assert.equal(matchesLabel("ai.anicca.writer-*", "ai.anicca.writer-report"), true);
  assert.equal(matchesLabel("ai.anicca.writer-report", "ai.anicca.writer-report"), true);
  assert.equal(matchesLabel("ai.*.writer-*", "ai.anicca.writer-report"), false);
  assert.equal(matchesLabel("ai.anicca.writer-*", "ai.anicca.writer-report-extra"), true);
  assert.equal(matchesLabel("ai.anicca.writer-*", "ai.anicca.writer"), false);
});

test("wildcard-only matcher is accepted consistently by the public and registry contracts", () => {
  assert.equal(matchesLabel("*", "any.launchd.label"), true);
  const fixture = validFixture();
  fixture.financial_units[0].runtime_matchers = ["*"];
  const registry = validateRegistry(fixture);
  assert.deepEqual(classifyLabel(registry, "any.launchd.label"), {
    kind: "financial_unit", targetIds: ["writer_agent"],
  });
});

test("class instances and custom prototypes are rejected before cloning", () => {
  class RegistryLike {}
  const root = Object.assign(new RegistryLike(), validFixture());
  assert.throws(() => validateRegistry(root), /^Error: cfo_registry_invalid:/);

  const unit = Object.assign(Object.create({ custom: true }), validFixture().financial_units[0]);
  const unitFixture = validFixture();
  unitFixture.financial_units[0] = unit;
  assert.throws(() => validateRegistry(unitFixture), /^Error: cfo_registry_invalid:/);

  const displayName = Object.assign(Object.create({ custom: true }), { en: "Writer Agent", ja: "Writer Agent" });
  const displayNameFixture = validFixture();
  displayNameFixture.financial_units[0].display_name = displayName;
  assert.throws(() => validateRegistry(displayNameFixture), /^Error: cfo_registry_invalid:/);
});

test("typed owner and cost-center references preserve their namespaces", () => {
  const fixture = validFixture();
  fixture.financial_units[0].cost_center_refs = ["agent:franklin1", "agent:franklin2"];
  const registry = validateRegistry(fixture);
  assert.equal(registry.financial_units[0].owner_ref, "human:dais");
  assert.deepEqual(registry.financial_units[0].cost_center_refs, ["agent:franklin1", "agent:franklin2"]);
});

test("typed owner and cost-center references reject untyped or wrong namespaces", () => {
  const mutations = [
    (fixture) => { fixture.financial_units[0].owner_ref = "dais"; },
    (fixture) => { fixture.financial_units[0].owner_ref = "agent:dais"; },
    (fixture) => { fixture.financial_units[0].cost_center_refs = ["franklin1"]; },
    (fixture) => { fixture.financial_units[0].cost_center_refs = ["human:franklin1"]; },
  ];
  for (const mutate of mutations) {
    const fixture = validFixture();
    mutate(fixture);
    assert.throws(() => validateRegistry(fixture), /^Error: cfo_registry_invalid:/);
  }
});

test("duplicates, unknown keys, money, secret-like keys, unsafe paths, and overlap fail", () => {
  for (const mutate of invalidMutations()) {
    assert.throws(() => validateRegistry(mutate(validFixture())), /^Error: cfo_registry_invalid:/);
  }
});

test("canonical hash ignores object insertion order but preserves array order", () => {
  assert.equal(sha256Canonical({ b: 2, a: 1 }), sha256Canonical({ a: 1, b: 2 }));
  assert.equal(canonicalJson({ b: 2, a: 1 }), '{"a":1,"b":2}');
  assert.notEqual(sha256Canonical({ a: [1, 2] }), sha256Canonical({ a: [2, 1] }));
  assert.match(sha256Canonical({ a: 1 }), /^[0-9a-f]{64}$/);
});

test("canonical registry exposes exactly nine ordered financial units", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  assert.deepEqual(registry.financial_units.map((unit) => unit.financial_unit_id), [
    "life_manager_saas", "anicca_ios", "writer_agent", "affiliate_agent",
    "gig_work", "x402_services", "job_income", "capafy_marketplace", "proprietary_investing",
  ]);
  assert.equal(registry.financial_units.find((unit) => unit.financial_unit_id === "job_income").unit_kind, "personal_income");
  assert.ok(registry.financial_units.filter((unit) => unit.financial_unit_id !== "job_income").every((unit) => unit.unit_kind === "business"));
  assert.deepEqual(registry.financial_units.map((unit) => unit.display_order), [1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.owner_ref), Array(9).fill("human:dais"));
  assert.deepEqual(registry.financial_units.map((unit) => unit.display_name), [
    { en: "Life Manager", ja: "ライフマネージャー" },
    { en: "Anicca iOS", ja: "アニッチャ iOS" },
    { en: "Writer Agent", ja: "ライターエージェント" },
    { en: "Affiliate Agent", ja: "アフィリエイトエージェント" },
    { en: "Gig Work", ja: "ギグワーク" },
    { en: "x402 Services", ja: "x402サービス" },
    { en: "Employment Income", ja: "給与所得" },
    { en: "Capafy Marketplace", ja: "Capafyマーケットプレイス" },
    { en: "Proprietary Investing", ja: "プロプライエタリ投資" },
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.lifecycle), [
    "active", "active", "active", "building", "active", "active", "active", "building", "planned",
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.runtime_matchers), [
    ["ai.anicca.life-manager-*", "ai.anicca.agent-economy-loop", "ai.anicca.hf-reddit-loop-*", "ai.anicca.reddit-loop-*", "ai.anicca.lateness-heartbeat", "ai.anicca.lm-recording-store", "ai.anicca.outbound-runtime-healthcheck", "ai.anicca.phone-conversation", "ai.anicca.pipecat-phone", "ai.anicca.realtime-guide", "ai.anicca.telegram-bot", "ai.anicca.phone-tunnel*"], [], ["ai.anicca.writer-*", "ai.anicca.article-*"], ["ai.anicca.affiliate-*", "ai.anicca.clip-loop"],
    ["ai.anicca.hf-gig-*", "ai.anicca.gig-outcome-watch", "ai.anicca.hf-bounty-daily", "ai.anicca.bounty-core-healthcheck", "ai.anicca.freelancer-bid-watch"], ["ai.anicca.x402-*", "ai.anicca.image-claude-p", "ai.anicca.image-franklin1", "ai.anicca.image-franklin2", "ai.anicca.mcp-claude-p", "ai.anicca.mcp-franklin1", "ai.anicca.mcp-franklin2", "ai.anicca.the402-*"],
    ["ai.anicca.job-search-*"],
    ["ai.anicca.capafy-*", "ai.anicca.provision-browser.instagram.capafy-provision"],
    ["ai.anicca.autohedge", "ai.anicca.pm-*", "ai.anicca.reinvest"],
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.revenue_channel_ids), [
    ["stripe_life_manager", "taskmarket_life_manager", "ugig_life_manager"],
    ["apple_app_store_anicca"], ["note_writer", "substack_writer", "publisher_writer"],
    ["amazon_associates", "rakuten_affiliate", "affiliate_networks"],
    ["gig_marketplaces", "direct_gig_clients"], ["x402_onchain"], ["payroll_bank"],
    ["capafy_sales"], ["proprietary_investing"],
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.ledger_source_ids), [
    ["lm_agent_earnings"], ["revenuecat_subscription_events"], ["writer_receipts"],
    ["affiliate_commission_receipts"], ["gig_payment_receipts"],
    ["x402_settlement_receipts"], ["payroll_bank_receipts"],
    ["capafy_sales_receipts"], ["proprietary_investing_receipts"],
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.cost_center_refs), [
    [], [], [], [], [], ["agent:franklin1", "agent:franklin2"], [], [], [],
  ]);
  assert.deepEqual(registry.financial_units.map((unit) => unit.evidence_refs), [
    ["docs/superpowers/specs/2026-06-21-life-manager-LAUNCH-ORDER.md"],
    ["AGENTS.md"], ["docs/writer-agent/WRITER-AGENT-SSOT.md"],
    ["docs/affiliate-agent/AFFILIATE-AGENT-SSOT.md"],
    ["docs/loop-engineering/26-gig-loop-asis-tobe-plan.md"],
    ["apps/x402-agents/package.json"], ["launchd:ai.anicca.job-search-*"],
    ["docs/superpowers/specs/2026-07-30-capafy-10k-mrr-game-plan.md"],
    ["docs/superpowers/specs/2026-06-10-ai-entity-content-engine-design.md"],
  ]);
  assert.deepEqual(registry.relevant_runtime_prefixes, ["ai.anicca."]);
  assert.deepEqual(registry.runtime_exclusions, [
    {
      exclusion_id: "cfo_controller", runtime_matchers: ["ai.anicca.cfo-*"],
      classification: "controller", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
    {
      exclusion_id: "fleet_observer", runtime_matchers: ["ai.anicca.fleet-*"],
      classification: "observer", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-04-fleet-and-remote-stability-design.md"],
    },
    {
      exclusion_id: "repair_infrastructure",
      runtime_matchers: ["ai.anicca.self-fix-*", "ai.anicca.connector-healer-*"],
      classification: "repair_infrastructure", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
    {
      exclusion_id: "franklin_cost_centres",
      runtime_matchers: ["ai.anicca.franklin-loop", "ai.anicca.franklin2-loop"],
      classification: "agent_cost_centre", cost_treatment: "x402_services",
      evidence_refs: ["docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md"],
    },
    {
      exclusion_id: "shared_marketing",
      runtime_matchers: ["ai.anicca.marketing-*", "ai.anicca.self-improve-evolve", "ai.anicca.warmup-flip-daily"],
      classification: "shared_marketing", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-06-06-anicca-marketing-aso-overhaul-design.md"],
    },
    {
      exclusion_id: "financial_observer",
      runtime_matchers: ["ai.anicca.daily-nl-report", "ai.anicca.earn-watch", "ai.anicca.earning-health-allslots", "ai.anicca.sbi-usdc-monitor", "ai.anicca.stripe-revenue-listener", "ai.anicca.stripe-revenue-poller"],
      classification: "observer", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
    {
      exclusion_id: "economic_controller",
      runtime_matchers: ["ai.anicca.ceo-runner", "ai.anicca.citizen-refill", "ai.anicca.founder-loop-cadence"],
      classification: "controller", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
    {
      exclusion_id: "shared_connector",
      runtime_matchers: ["ai.anicca.agentmail-*", "ai.anicca.clawrouter", "ai.anicca.slack-bridge", "ai.anicca.tsbridge"],
      classification: "connector", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
    {
      exclusion_id: "shared_ops_repair",
      runtime_matchers: ["ai.anicca.agents-skills-sync", "ai.anicca.browser-state-backup", "ai.anicca.cadence-deadline-check", "ai.anicca.cdp-daily-driver-owner", "ai.anicca.citizens-diff-monitor", "ai.anicca.claude-projects-backup", "ai.anicca.colima-autostart", "ai.anicca.disk-autoprune", "ai.anicca.disk-janitor", "ai.anicca.effect-watch", "ai.anicca.f7-silence-check", "ai.anicca.fuel-watch", "ai.anicca.monkey-watchdog", "ai.anicca.openclaw-conformity-monkey", "ai.anicca.openclaw-core-backup", "ai.anicca.openclaw-janitor-monkey", "ai.anicca.session-vault", "ai.anicca.sync-memory", "ai.anicca.tier1-remediate", "ai.anicca.tier2-agent-diagnose", "ai.anicca.token-daily-report", "ai.anicca.verify-loops-audit", "ai.anicca.watchdog"],
      classification: "repair_infrastructure", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    },
  ]);
});

test("final census uses the complete runtime root and two verified units", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  assert.deepEqual(registry.financial_units.map((unit) => unit.financial_unit_id), [
    "life_manager_saas", "anicca_ios", "writer_agent", "affiliate_agent",
    "gig_work", "x402_services", "job_income", "capafy_marketplace",
    "proprietary_investing",
  ]);
  assert.deepEqual(registry.relevant_runtime_prefixes, ["ai.anicca."]);
  assert.deepEqual(registry.financial_units.find((unit) => unit.financial_unit_id === "capafy_marketplace").runtime_matchers, [
    "ai.anicca.capafy-*", "ai.anicca.provision-browser.instagram.capafy-provision",
  ]);
  assert.deepEqual(registry.financial_units.find((unit) => unit.financial_unit_id === "proprietary_investing").runtime_matchers, [
    "ai.anicca.autohedge", "ai.anicca.pm-*", "ai.anicca.reinvest",
  ]);
});

test("verified runtime extensions classify once", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  const cases = [
    ["ai.anicca.agent-economy-loop", "life_manager_saas"],
    ["ai.anicca.hf-reddit-loop-daily", "life_manager_saas"],
    ["ai.anicca.reddit-loop-healthcheck", "life_manager_saas"],
    ["ai.anicca.lateness-heartbeat", "life_manager_saas"],
    ["ai.anicca.lm-recording-store", "life_manager_saas"],
    ["ai.anicca.outbound-runtime-healthcheck", "life_manager_saas"],
    ["ai.anicca.phone-conversation", "life_manager_saas"],
    ["ai.anicca.pipecat-phone", "life_manager_saas"],
    ["ai.anicca.realtime-guide", "life_manager_saas"],
    ["ai.anicca.telegram-bot", "life_manager_saas"],
    ["ai.anicca.phone-tunnel-watcher", "life_manager_saas"],
    ["ai.anicca.article-daily", "writer_agent"],
    ["ai.anicca.hf-bounty-daily", "gig_work"],
    ["ai.anicca.bounty-core-healthcheck", "gig_work"],
    ["ai.anicca.freelancer-bid-watch", "gig_work"],
    ["ai.anicca.clip-loop", "affiliate_agent"],
    ["ai.anicca.image-claude-p", "x402_services"],
    ["ai.anicca.image-franklin1", "x402_services"],
    ["ai.anicca.image-franklin2", "x402_services"],
    ["ai.anicca.mcp-claude-p", "x402_services"],
    ["ai.anicca.mcp-franklin1", "x402_services"],
    ["ai.anicca.mcp-franklin2", "x402_services"],
    ["ai.anicca.the402-worker", "x402_services"],
    ["ai.anicca.the402-provider", "x402_services"],
    ["ai.anicca.capafy-goal-monitor", "capafy_marketplace"],
    ["ai.anicca.provision-browser.instagram.capafy-provision", "capafy_marketplace"],
    ["ai.anicca.autohedge", "proprietary_investing"],
    ["ai.anicca.pm-live-trade", "proprietary_investing"],
    ["ai.anicca.reinvest", "proprietary_investing"],
  ];
  for (const [label, targetId] of cases) {
    assert.deepEqual(classifyLabel(registry, label), {
      kind: "financial_unit", targetIds: [targetId],
    }, label);
  }
});

test("final census exclusions classify shared runtimes exactly once", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  const cases = [
    ["ai.anicca.marketing-dashboard", "shared_marketing"],
    ["ai.anicca.self-improve-evolve", "shared_marketing"],
    ["ai.anicca.warmup-flip-daily", "shared_marketing"],
    ["ai.anicca.daily-nl-report", "financial_observer"],
    ["ai.anicca.stripe-revenue-poller", "financial_observer"],
    ["ai.anicca.ceo-runner", "economic_controller"],
    ["ai.anicca.citizen-refill", "economic_controller"],
    ["ai.anicca.agentmail-nudge", "shared_connector"],
    ["ai.anicca.clawrouter", "shared_connector"],
    ["ai.anicca.slack-bridge", "shared_connector"],
    ["ai.anicca.tsbridge", "shared_connector"],
    ["ai.anicca.agents-skills-sync", "shared_ops_repair"],
    ["ai.anicca.watchdog", "shared_ops_repair"],
    ["ai.anicca.verify-loops-audit", "shared_ops_repair"],
  ];
  for (const [label, targetId] of cases) {
    assert.deepEqual(classifyLabel(registry, label), {
      kind: "exclusion", targetIds: [targetId],
    }, label);
  }
});

test("ledger catalogue resolves every declared source with closed probe and status values", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  assert.deepEqual(registry.ledger_sources.map((source) => source.ledger_source_id), [
    "lm_agent_earnings", "revenuecat_subscription_events", "writer_receipts",
    "affiliate_commission_receipts", "gig_payment_receipts", "x402_settlement_receipts",
    "payroll_bank_receipts", "capafy_sales_receipts", "proprietary_investing_receipts",
  ]);
  assert.ok(registry.ledger_sources.every((source) => [
    "available", "present_empty", "stale_alias", "planned", "unavailable",
  ].includes(source.default_status)));
  assert.deepEqual(registry.ledger_sources.map((source) => source.probe_kind), [
    "external", "external", "sqlite", "planned", "jsonl", "directory", "planned", "directory", "planned",
  ]);
  assert.ok(registry.ledger_sources.every((source) => !Object.keys(source).some((key) => /amount|balance|secret|token|account|payload|path/i.test(key))));
});

test("ledger catalogue rejects duplicate, missing, orphaned, unsafe, and secret-bearing sources", () => {
  const mutations = [
    (raw) => raw.ledger_sources.push(structuredClone(raw.ledger_sources[0])),
    (raw) => { raw.financial_units[0].ledger_source_ids = ["missing_source"]; },
    (raw) => raw.ledger_sources.push({
      ledger_source_id: "orphan_source", probe_kind: "external", locator: "orphan", default_status: "unavailable",
    }),
    (raw) => { raw.ledger_sources[0].locator = "/Users/dais/ledger.jsonl"; },
    (raw) => { raw.ledger_sources[0].locator = "api_key=secret-value"; },
    (raw) => { raw.ledger_sources[0].locator = "token-value"; },
    (raw) => { raw.ledger_sources[0].probe_kind = "money_reader"; },
    (raw) => { raw.ledger_sources[0].default_status = "healthy"; },
  ];
  for (const mutate of mutations) {
    const raw = structuredClone(JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8")));
    mutate(raw);
    assert.throws(() => validateRegistry(raw), /^Error: cfo_registry_invalid:/);
  }
});

test("evidence and locator refs reject traversal, query, credentials, secrets, private keys, and account-like digits", () => {
  const mutations = [
    (raw) => { raw.financial_units[0].evidence_refs = ["../escape.md"]; },
    (raw) => { raw.financial_units[0].evidence_refs = ["docs/\u0000escape.md"]; },
    (raw) => { raw.financial_units[0].evidence_refs = ["https://example.test/report?token=secret"]; },
    (raw) => { raw.financial_units[0].evidence_refs = ["https://user:pass@example.test/report"]; },
    (raw) => { raw.financial_units[0].evidence_refs = ["receipt-123456789012"]; },
    (raw) => { raw.ledger_sources[0].locator = "../../outside"; },
    (raw) => { raw.ledger_sources[0].locator = "https://example.test/ledger#fragment"; },
    (raw) => { raw.ledger_sources[0].locator = "private_key=-----BEGIN PRIVATE KEY-----"; },
    (raw) => { raw.ledger_sources[0].locator = "account-123456789012"; },
  ];
  for (const mutate of mutations) {
    const raw = structuredClone(JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8")));
    mutate(raw);
    assert.throws(() => validateRegistry(raw), /^Error: cfo_registry_invalid:/);
  }
});

test("canonical runtime namespaces classify financial units and exclusions", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  const cases = [
    ["ai.anicca.life-manager-worker", { kind: "financial_unit", targetIds: ["life_manager_saas"] }],
    ["ai.anicca.writer-worker", { kind: "financial_unit", targetIds: ["writer_agent"] }],
    ["ai.anicca.affiliate-worker", { kind: "financial_unit", targetIds: ["affiliate_agent"] }],
    ["ai.anicca.hf-gig-worker", { kind: "financial_unit", targetIds: ["gig_work"] }],
    ["ai.anicca.gig-outcome-watch", { kind: "financial_unit", targetIds: ["gig_work"] }],
    ["ai.anicca.x402-worker", { kind: "financial_unit", targetIds: ["x402_services"] }],
    ["ai.anicca.job-search-worker", { kind: "financial_unit", targetIds: ["job_income"] }],
    ["ai.anicca.cfo-controller", { kind: "exclusion", targetIds: ["cfo_controller"] }],
    ["ai.anicca.fleet-observer", { kind: "exclusion", targetIds: ["fleet_observer"] }],
    ["ai.anicca.self-fix-repair", { kind: "exclusion", targetIds: ["repair_infrastructure"] }],
    ["ai.anicca.connector-healer-repair", { kind: "exclusion", targetIds: ["repair_infrastructure"] }],
    ["ai.anicca.franklin-loop", { kind: "exclusion", targetIds: ["franklin_cost_centres"] }],
    ["ai.anicca.franklin2-loop", { kind: "exclusion", targetIds: ["franklin_cost_centres"] }],
    ["ai.anicca.unregistered", { kind: "unmapped", targetIds: [] }],
  ];
  for (const [label, expected] of cases) assert.deepEqual(classifyLabel(registry, label), expected, label);
});
