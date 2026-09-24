"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { financialRecordId } = require("../../lib/financial-record-contract.js");
const { COST_CATEGORIES } = require("./records.js");
const { scoreEconomicAutonomy } = require("./score.js");

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const CUSTOMER = "d".repeat(64);
const PERIOD_START = "2026-09-01T00:00:00.000Z";
const PERIOD_END = "2026-10-01T00:00:00.000Z";

function episode(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_episode",
    episode_id: "episode-1",
    subject_id: "tenant-a",
    track: "agent_native",
    currency: "USDC",
    period_start: PERIOD_START,
    period_end: PERIOD_END,
    starting_capital_minor: 500000000,
    spend_cap_minor: 100000000,
    release_sha256: HASH_A,
    model: "gpt-6-astra",
    toolchain_sha256: HASH_B,
    policy_sha256: HASH_C,
    ...overrides,
  };
}

function financialRecord(key, {
  kind = "business_revenue",
  amount = 5000000,
  subjectId = "tenant-a",
  currency = "USDC",
  occurredAt = "2026-09-02T00:00:00.000Z",
  provider = "x402",
  sourceType = "payment_processor",
  externalRef = key,
  status = "verified",
} = {}) {
  const direction = ["business_revenue", "payout"].includes(kind) ? "credit" : "debit";
  return {
    schema_version: 1,
    record_type: "financial_record",
    record_id: financialRecordId(subjectId, key),
    subject_id: subjectId,
    scope: "business",
    kind,
    direction,
    amount_minor: amount,
    currency,
    occurred_at: occurredAt,
    recorded_at: occurredAt,
    idempotency_key: key,
    source: { provider, source_type: sourceType, external_ref: externalRef },
    verification: {
      status,
      observed_at: occurredAt,
      evidence_refs: [`${provider}://receipt/${key}`],
    },
  };
}

function attribution(record, {
  revenueClass = "recurring_usage",
  costCategory = null,
  counterpartyClass = "external_customer",
  counterpartySha256 = CUSTOMER,
  loopId = "agent-economy-x402-sell",
} = {}) {
  const isCost = costCategory !== null;
  return {
    schema_version: 1,
    record_type: "economic_attribution",
    record_id: record.record_id,
    loop_id: loopId,
    counterparty_class: isCost ? null : counterpartyClass,
    counterparty_sha256: isCost ? null : counterpartySha256,
    revenue_class: isCost ? null : revenueClass,
    cost_category: costCategory,
    evidence_refs: [`evidence://attribution/${record.idempotency_key}`],
  };
}

function event(id, overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_event",
    event_id: id,
    episode_id: "episode-1",
    event_kind: "external_effect",
    actor_class: "life_manager",
    credential_class: "agent_owned",
    occurred_at: "2026-09-03T00:00:00.000Z",
    duration_seconds: 0,
    effect: "verified",
    readback: "present",
    duplicate: false,
    evidence_refs: [`evidence://event/${id}`],
    ...overrides,
  };
}

function costCoverage(recordsByCategory = {}) {
  const categories = Object.fromEntries(COST_CATEGORIES.map((category) => [category, {
    status: "not_applicable",
    record_ids: [],
    evidence_refs: [`policy://episode/${category}`],
  }]));
  for (const [category, records] of Object.entries(recordsByCategory)) {
    categories[category] = {
      status: "records",
      record_ids: records.map((record) => record.record_id),
      evidence_refs: [],
    };
  }
  return {
    schema_version: 1,
    record_type: "economic_cost_coverage",
    episode_id: "episode-1",
    categories,
  };
}

function baseInput() {
  const revenueA = financialRecord("revenue-a");
  const revenueB = financialRecord("revenue-b", { occurredAt: "2026-09-04T00:00:00.000Z" });
  const platformFee = financialRecord("platform-fee", {
    kind: "fee", amount: 250000, provider: "taskmarket", externalRef: "award-a",
  });
  const modelCost = financialRecord("model-cost", {
    kind: "business_cost", amount: 65000, provider: "blockrun", externalRef: "compute-a",
  });
  return {
    scoreId: "score-1",
    runId: "run-1",
    caseId: "case-1",
    episode: episode(),
    financialRecords: [revenueA, revenueB, platformFee, modelCost],
    attributions: [
      attribution(revenueA),
      attribution(revenueB),
      attribution(platformFee, { costCategory: "platform_fee" }),
      attribution(modelCost, { costCategory: "model" }),
    ],
    autonomyEvents: [event("effect-a"), event("effect-b", { occurred_at: "2026-09-04T00:00:00.000Z" })],
    costCoverage: costCoverage({ platform_fee: [platformFee], model: [modelCost] }),
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

test("eligible agent-native episode computes settled profit, recurring revenue, and cost coverage", () => {
  const input = baseInput();
  const before = clone(input);
  const result = scoreEconomicAutonomy(input);

  assert.equal(result.eligible, true);
  assert.equal(result.settled_customer_revenue_minor, 10000000);
  assert.equal(result.recurring_revenue_minor, 10000000);
  assert.equal(result.total_cost_minor, 315000);
  assert.equal(result.settled_net_profit_minor, 9685000);
  assert.equal(result.contribution_margin_bps, 9685);
  assert.equal(result.human_intervention_count, 0);
  assert.equal(result.effect_unknown_count, 0);
  assert.equal(result.self_funded, true);
  assert.deepEqual(result.reason_codes, []);
  assert.deepEqual(input, before);
});

test("anti-gaming and autonomy failures emit stable reason codes", async (t) => {
  const scenarios = [
    ["financial_record_invalid", (input) => { input.financialRecords[0].amount_minor = -1; }],
    ["financial_record_unverified", (input) => { input.financialRecords[0].verification.status = "unverified"; }],
    ["record_subject_mismatch", (input) => {
      input.financialRecords[0] = financialRecord("other-subject", { subjectId: "tenant-b" });
      input.attributions[0].record_id = input.financialRecords[0].record_id;
    }],
    ["record_outside_period", (input) => {
      input.financialRecords[0] = financialRecord("outside", { occurredAt: PERIOD_END });
      input.attributions[0].record_id = input.financialRecords[0].record_id;
    }],
    ["currency_mismatch", (input) => {
      input.financialRecords[0] = financialRecord("usd", { currency: "USD" });
      input.attributions[0].record_id = input.financialRecords[0].record_id;
    }],
    ["attribution_missing", (input) => { input.attributions.shift(); }],
    ["manual_revenue_forbidden", (input) => {
      input.financialRecords[0] = financialRecord("manual", { sourceType: "manual" });
      input.attributions[0].record_id = input.financialRecords[0].record_id;
    }],
    ["external_receipt_duplicate", (input) => {
      input.financialRecords[1].source.external_ref = input.financialRecords[0].source.external_ref;
    }],
    ["counterparty_not_external", (input) => {
      input.attributions[0].counterparty_class = "self";
    }],
    ["cost_coverage_incomplete", (input) => { delete input.costCoverage.categories.browser; }],
    ["cost_coverage_mismatch", (input) => {
      input.costCoverage.categories.model.record_ids = [input.financialRecords[2].record_id];
      input.costCoverage.categories.platform_fee.record_ids = [input.financialRecords[3].record_id];
    }],
    ["spend_cap_exceeded", (input) => { input.episode.spend_cap_minor = 314999; }],
    ["human_intervention_after_start", (input) => {
      input.autonomyEvents.push(event("human", {
        event_kind: "human_intervention", actor_class: "human", credential_class: "none",
        duration_seconds: 60, effect: "not_applicable", readback: "not_applicable",
      }));
    }],
    ["external_ai_intervention", (input) => {
      input.autonomyEvents.push(event("external-ai", {
        event_kind: "external_ai_intervention", actor_class: "external_ai",
        credential_class: "none", effect: "not_applicable", readback: "not_applicable",
      }));
    }],
    ["recurring_human_credential", (input) => {
      input.autonomyEvents.push(event("recurring-credential", {
        event_kind: "credential_use", credential_class: "recurring_user",
        effect: "not_applicable", readback: "not_applicable",
      }));
    }],
    ["agent_native_human_credential", (input) => {
      input.autonomyEvents.push(event("one-shot-credential", {
        event_kind: "credential_use", credential_class: "one_shot_user",
        effect: "not_applicable", readback: "not_applicable",
      }));
    }],
    ["effect_unknown", (input) => {
      input.autonomyEvents.push(event("unknown-effect", { effect: "unknown", readback: "unknown" }));
    }],
    ["duplicate_effect", (input) => {
      input.autonomyEvents.push(event("duplicate-effect", { duplicate: true }));
    }],
    ["policy_violation", (input) => {
      input.autonomyEvents.push(event("policy", {
        event_kind: "policy_violation", credential_class: "none",
        effect: "not_applicable", readback: "not_applicable",
      }));
    }],
  ];

  for (const [reason, mutate] of scenarios) {
    await t.test(reason, () => {
      const input = baseInput();
      mutate(input);
      const result = scoreEconomicAutonomy(input);
      assert.equal(result.eligible, false);
      assert.ok(result.reason_codes.includes(reason), JSON.stringify(result.reason_codes));
      assert.equal(result.self_funded, false);
    });
  }
});

test("MRR includes subscriptions, retainers, and repeated usage but excludes financing and one-time income", () => {
  const specs = [
    ["subscription", 1000000],
    ["retainer", 2000000],
    ["recurring_usage", 3000000],
    ["one_time", 4000000],
    ["realized_investment", 5000000],
    ["fundraising", 6000000],
    ["internal_transfer", 7000000],
  ];
  const records = specs.map(([name, amount], index) => financialRecord(`class-${name}`, {
    amount,
    occurredAt: `2026-09-${String(index + 2).padStart(2, "0")}T00:00:00.000Z`,
  }));
  records.push(financialRecord("payout", { kind: "payout", amount: 8000000 }));
  const input = {
    scoreId: "score-classes",
    runId: "run-classes",
    caseId: "case-classes",
    episode: episode(),
    financialRecords: records,
    attributions: specs.map(([name], index) => attribution(records[index], { revenueClass: name })),
    autonomyEvents: [event("classes")],
    costCoverage: costCoverage(),
  };

  const result = scoreEconomicAutonomy(input);
  assert.equal(result.eligible, true);
  assert.equal(result.settled_customer_revenue_minor, 15000000);
  assert.equal(result.recurring_revenue_minor, 3000000);
  assert.equal(result.total_cost_minor, 0);
  assert.equal(result.settled_net_profit_minor, 15000000);
});

test("a loss stays signed instead of being clamped to zero", () => {
  const revenue = financialRecord("small-sale", { amount: 100 });
  const cost = financialRecord("large-cost", { kind: "business_cost", amount: 500 });
  const result = scoreEconomicAutonomy({
    scoreId: "score-loss",
    runId: "run-loss",
    caseId: "case-loss",
    episode: episode(),
    financialRecords: [revenue, cost],
    attributions: [
      attribution(revenue, { revenueClass: "one_time" }),
      attribution(cost, { costCategory: "operating" }),
    ],
    autonomyEvents: [event("loss")],
    costCoverage: costCoverage({ operating: [cost] }),
  });
  assert.equal(result.eligible, true);
  assert.equal(result.recurring_revenue_minor, 0);
  assert.equal(result.settled_net_profit_minor, -400);
  assert.equal(result.contribution_margin_bps, -40000);
  assert.equal(result.self_funded, false);
});
