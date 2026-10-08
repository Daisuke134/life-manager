"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { evaluateWebAppFactory } = require("./web-app-factory.js");
const { financialRecordId } = require("./financial-record-contract.js");
const NOW = "2026-10-08T09:00:00Z";
const SHA = "a".repeat(40);
function evidence(scope = "provider_readback") {
  return { product_id: "sample-pdf", ref: "receipt://synthetic/check-1", observed_at: NOW, scope, revision: SHA };
}
function input() {
  return {
    schema_version: 1,
    product: { product_id: "sample-pdf", display_name: "Sample PDF", url: "https://example.com/pdf",
      source: { git_remote: "https://example.com/sample.git", revision: SHA, access: "private" }, source_owner: "factory-test" },
    assignment: { owner: "factory-test", worktree: "/isolated/factory", paths: ["src/pdf"], resource_ids: ["sample-site"],
      lease: { owner: "factory-test", worktree: "/isolated/factory", expires_at: "2026-10-09T09:00:00Z" },
      inventory_complete: true, claims: [] },
    period: { start: "2026-10-01T00:00:00Z", end: "2026-10-08T00:00:00Z", currency: "USD" },
    demand: ["competitor", "problem_signal"].map(kind => ({ kind, evidence: evidence() })),
    qa: ["core_flow", "quota", "entitlement", "copy", "privacy"].map(check => ({ check, status: "pass", evidence: evidence("offline") })),
    marketing_claims: [{ id: "parse-pdf", evidence: evidence() }],
    distribution: [{ channel: "owned_site", resource_id: "sample-site", owner: "factory-test", permission: "granted", cost_minor: 0 }],
    metrics: {}, financial_records: [], additional_spend_minor: 0,
    unit_economics: { price_minor: 1900, max_variable_cost_minor: 100, evidence: evidence() },
  };
}
function run(value = input()) { return evaluateWebAppFactory(value, { now: NOW }); }
function metric(value, currency = "USD") {
  return { status: "verified", value, complete: true, period_start: "2026-10-01T00:00:00Z",
    period_end: "2026-10-08T00:00:00Z", currency, evidence: evidence() };
}

test("missing economic evidence never becomes zero or a successful business", () => {
  const result = run();
  assert.equal(result.metrics.revenue_minor.status, "unknown");
  assert.equal(result.metrics.revenue_minor.value, null);
  assert.equal(result.net_contribution_minor, null);
  assert.equal(result.production_verified, false);
  assert.equal(result.external_effects, false);
  assert.equal(result.additional_spend_minor, 0);
});
test("complete zero is known; refunds and costs preserve a loss", () => {
  const value = input();
  value.metrics = { revenue_minor: metric(0), refunds_minor: metric(50), costs_minor: metric(100), visits: metric(0), successful_uses: metric(0), invoices_paid: metric(0) };
  const result = run(value);
  assert.equal(result.metrics.revenue_minor.status, "verified");
  assert.equal(result.metrics.invoices_paid.value, 0);
  assert.equal(result.net_contribution_minor, -150);
});
for (const [name, change] of [
  ["partial", x => { x.complete = false; }],
  ["cross-product", x => { x.evidence.product_id = "another-app"; }],
  ["test-mode", x => { x.evidence.scope = "offline"; }],
  ["stale", x => { x.evidence.observed_at = "2026-09-01T00:00:00Z"; }],
  ["future", x => { x.evidence.observed_at = "2026-11-01T00:00:00Z"; }],
  ["wrong-period", x => { x.period_start = "2026-09-01T00:00:00Z"; }],
  ["wrong-currency", x => { x.currency = "JPY"; }],
  ["fractional", x => { x.value = 1.5; }],
]) test(`${name} financial evidence remains unknown`, () => {
  const value = input(); value.metrics.revenue_minor = metric(100); change(value.metrics.revenue_minor);
  assert.equal(run(value).metrics.revenue_minor.value, null);
});
test("source must stay pinned and credential-free", () => {
  const value = input(); value.product.source.revision = "main";
  assert.throws(() => run(value), /revision/);
  value.product.source.revision = SHA; value.product.source.git_remote = "https://example.com/repo?token=secret";
  assert.throws(() => run(value), /URL/);
});
test("unproven ownership blocks even a passing local product", () => {
  for (const change of [
    x => { x.assignment.inventory_complete = false; },
    x => { x.assignment.lease.expires_at = NOW; },
    x => { x.assignment.lease.owner = "other"; },
    x => { x.product.source_owner = "unknown"; },
  ]) { const value = input(); change(value); assert.equal(run(value).next_task, "resolve_ownership"); }
});
test("foreign parent, child and case-variant path claims block without reclaiming stale owners", () => {
  for (const path of ["src", "src/pdf/parse.js", "SRC/PDF"]) {
    const value = input();
    value.assignment.claims.push({ owner: "other", repository: "https://example.com/sample.git", paths: [path], resource_ids: [] });
    assert.equal(run(value).ownership.state, "blocked");
  }
});
test("shared resource blocks even across repositories; disjoint source paths do not", () => {
  const value = input();
  value.assignment.claims.push({ owner: "other", repository: "https://example.com/else.git", paths: ["src/pdf"], resource_ids: [] });
  assert.equal(run(value).ownership.state, "verified");
  value.assignment.claims[0].resource_ids.push("sample-site");
  assert.equal(run(value).ownership.state, "blocked");
});
test("unsafe path traversal is rejected before a handoff exists", () => {
  const value = input(); value.assignment.paths = ["src/../shared"];
  assert.throws(() => run(value), /path/);
});
test("competitor evidence alone does not prove demand", () => {
  const value = input(); value.demand.pop();
  assert.equal(run(value).next_task, "validate_demand");
});
test("offline QA cannot authorize marketing or imply production passed", () => {
  assert.equal(run().qa.offline_verified, true);
  assert.equal(run().production_verified, false);
  assert.equal(run().next_task, "verify_product_readback");
});
test("stale revision and duplicate QA rows cannot satisfy verification", () => {
  const value = input(); value.qa[0].evidence.revision = "b".repeat(40);
  assert.equal(run(value).qa.offline_verified, false);
  value.qa.push(value.qa[1]);
  assert.throws(() => run(value), /duplicate/);
});
test("known QA failure routes to product repair before marketing", () => {
  const value = input(); value.qa[1].status = "fail";
  assert.equal(run(value).next_task, "repair_product");
  assert.equal(run(value).marketing_ready, false);
});
test("all passing readbacks still emit only a self-build planning handoff", () => {
  const value = input(); value.qa.forEach(x => { x.evidence.scope = "provider_readback"; });
  const result = run(value);
  assert.equal(result.production_verified, true);
  assert.equal(result.next_task, "prepare_distribution");
  assert.equal(result.lifecycle.loop_id, "self-build");
  assert.equal(result.lifecycle.state, "setup_required");
  assert.equal(result.external_effects, false);
});
test("unsubstantiated marketing claims cannot become factual copy", () => {
  const value = input(); value.qa.forEach(x => { x.evidence.scope = "provider_readback"; });
  value.marketing_claims[0].evidence.product_id = "other-app";
  assert.equal(run(value).next_task, "prepare_factual_marketing");
});
test("distribution is restricted to explicitly permitted zero-cost owned resources", () => {
  for (const change of [
    x => { x.cost_minor = 1; }, x => { x.permission = "unknown"; },
    x => { x.owner = "other"; }, x => { x.resource_id = "unowned"; }, x => { x.channel = "direct_message"; },
  ]) {
    const value = input(); change(value.distribution[0]);
    assert.equal(run(value).distribution[0].state, "blocked");
  }
});
test("unknown or loss-making per-order economics fence distribution", () => {
  for (const economics of [null, { price_minor: 100, max_variable_cost_minor: 101, evidence: evidence() }]) {
    const value = input(); value.unit_economics = economics;
    value.qa.forEach(x => { x.evidence.scope = "provider_readback"; });
    assert.equal(run(value).distribution[0].state, "blocked");
    assert.equal(run(value).next_task, "verify_unit_economics");
  }
});
test("a budget cannot enable spending and unknown fields cannot carry secret data", () => {
  const value = input(); value.additional_spend_minor = 1;
  assert.throws(() => run(value), /zero/);
  value.additional_spend_minor = 0; value.api_key = "do-not-echo-this";
  assert.throws(() => run(value), error => !error.message.includes("do-not-echo-this") && /fields/.test(error.message));
});
test("known CFO records use the shared validator without synthesizing money", () => {
  const value = input();
  value.financial_records = [{ schema_version: 1, record_type: "financial_record", record_id: financialRecordId("sample-pdf", "invoice-1"),
    subject_id: "sample-pdf", scope: "business", kind: "business_revenue", direction: "credit", amount_minor: 1900, currency: "USD",
    occurred_at: NOW, recorded_at: NOW, idempotency_key: "invoice-1", source: { provider: "stripe", source_type: "payment_processor", external_ref: "sample-invoice" },
    verification: { status: "verified", observed_at: NOW, evidence_refs: ["receipt://synthetic/invoice-1"] } }];
  assert.equal(run(value).financial_records_validated, 1);
  assert.equal(run(value).metrics.revenue_minor.value, null);
  value.financial_records[0].amount_minor = -1;
  assert.throws(() => run(value), /amount_minor/);
});
test("evaluation does not mutate operator input", () => {
  const value = input(); const before = structuredClone(value); run(value); assert.deepEqual(value, before);
});
module.exports = { input, evidence, NOW };
