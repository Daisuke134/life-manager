"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { importContentObject } = require("../lib/content-object-store.js");
const { fetchRevenueCatCustomerActivity, persistRevenueCatSubscriptions, persistRevenueCatSubscriptionsDaily, revenueCatBindingsFromCredentials } = require("./marketing-revenuecat-subscriptions.js");

function fixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-rc-"));
  const objectDir = path.join(dataDir, "objects");
  const ascDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc/2026-08-23");
  fs.mkdirSync(ascDir, { recursive: true });
  const source = path.join(dataDir, "asc-source.json");
  fs.writeFileSync(source, "{}\n");
  const asc = importContentObject(source, { objectDir });
  fs.writeFileSync(path.join(ascDir, "acquisition.json"), JSON.stringify({ snapshot_ref: asc.ref }));
  return { dataDir, objectDir };
}

const APP_BINDINGS = [
  { product_id: "anicca-ios", project_id: "project-mobile", app_id: "app511ef26659" },
  { product_id: "honne-ai", project_id: "project-mobile", app_id: "app3bbd298d22" },
];

function chartOptions(appIds) {
  return {
    object: "chart_options",
    resolutions: [{ id: "0", display_name: "day" }],
    segments: [],
    filters: [{ object: "chart_filter_option", id: "first_app_id", options: appIds.map((appId) => ({ id: appId, display_name: appId })) }],
    user_selectors: {},
  };
}

function chartData(chart, dataFrom, dataTo, { missingDay = false, incompleteDay = false } = {}) {
  const start = Date.parse(`${dataFrom}T00:00:00.000Z`);
  const days = Array.from({ length: 28 }, (_, index) => ({
    cohort: (start + index * 86_400_000) / 1000,
    incomplete: incompleteDay && index === 27,
    measure: 0,
    value: chart === "customers_new" ? 1 : (index % 2 ? 4 : 3),
  })).filter((_, index) => !(missingDay && index === 13));
  return {
    object: "chart_data",
    category: "customers",
    display_type: "line",
    display_name: chart === "customers_new" ? "New Customers" : "Active Customers",
    description: "Customer chart fixture",
    documentation_link: "https://www.revenuecat.com/docs/api-v2/charts-and-metrics",
    last_computed_at: 0,
    start_date: start / 1000,
    end_date: Date.parse(`${dataTo}T00:00:00.000Z`) / 1000,
    yaxis_currency: null,
    filtering_allowed: true,
    segmenting_allowed: true,
    resolution: "day",
    measures: [{ chartable: true, decimal_precision: 0, display_name: chart === "customers_new" ? "New Customers" : "Active Customers", tabulable: true, unit: "#" }],
    periods: null,
    values: days,
    summary: chart === "customers_new" ? { average: { "New Customers": 1 }, total: { "New Customers": 28 } } : { average: { "Active Customers": 3.5 } },
    yaxis: "#",
    segments: null,
    segments_limit: null,
    unsupported_params: null,
    user_selectors: {},
  };
}

function fakeRevenueCat({ missingAniccaActiveDay = false, incompleteHonneNewDay = false } = {}) {
  const calls = [];
  return {
    calls,
    bindings: { apiKey: "fixture-only-api-key", apps: APP_BINDINGS },
    requestJson: async (url, apiKey) => {
      assert.equal(apiKey, "fixture-only-api-key");
      const parsed = new URL(url);
      const match = /^\/v2\/projects\/([^/]+)\/charts\/([^/]+)(\/options)?$/.exec(parsed.pathname);
      assert.ok(match, `unexpected RevenueCat URL: ${parsed.pathname}`);
      const [, projectId, chart, optionsSuffix] = match;
      const apps = APP_BINDINGS.filter((row) => row.project_id === decodeURIComponent(projectId));
      assert.ok(apps.length, `unknown RevenueCat project: ${projectId}`);
      assert.equal(parsed.searchParams.get("realtime"), "true");
      if (optionsSuffix) {
        calls.push({ chart, options: true, url: parsed });
        return chartOptions(apps.map((app) => app.app_id));
      }
      const filter = JSON.parse(parsed.searchParams.get("filters"));
      const app = apps.find((row) => filter[0]?.values?.[0] === row.app_id);
      assert.ok(app, `chart app filter did not identify one app: ${chart}`);
      calls.push({ product_id: app.product_id, chart, options: false, url: parsed });
      assert.equal(parsed.searchParams.get("start_date"), "2026-09-14");
      assert.equal(parsed.searchParams.get("end_date"), "2026-10-11");
      assert.equal(parsed.searchParams.get("resolution"), "0");
      assert.equal(parsed.searchParams.get("expand_periods"), "false");
      assert.deepEqual(filter, [{ name: "first_app_id", values: [app.app_id] }]);
      return chartData(chart, "2026-09-14", "2026-10-11", {
        missingDay: missingAniccaActiveDay && app.product_id === "anicca-ios" && chart === "customers_active",
        incompleteDay: incompleteHonneNewDay && app.product_id === "honne-ai" && chart === "customers_new",
      });
    },
  };
}

test("keeps both products unavailable when no product-owned observation exists", () => {
  const { dataDir } = fixture();
  const result = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T13:00:00.000Z");
  assert.equal(result.products.length, 2);
  for (const product of result.products) {
    assert.equal(product.source_status, "unavailable");
    for (const metric of Object.values(product.metrics)) assert.deepEqual(metric, { status: "unavailable", value: null, reason: "product_pack_observation_missing" });
  }
});

test("imports isolated measured and unavailable metrics and replays without a second object", () => {
  const { dataDir } = fixture();
  const inbox = path.join(dataDir, "tenants/dais-local/product-packs/metrics/revenuecat");
  fs.mkdirSync(inbox, { recursive: true });
  fs.writeFileSync(path.join(inbox, "anicca-ios.json"), JSON.stringify({
    schema_version: 1, kind: "product_revenuecat_observation", product_id: "anicca-ios",
    observed_at: "2026-08-23T12:55:00.000Z", data_from: "2026-08-22", data_to: "2026-08-22",
    source: "revenuecat_charts_api", source_status: "partial",
    metrics: {
      trial_starts: { status: "measured", value: 1, unit: "count" },
      active_subscriptions: { status: "measured", value: 5, unit: "count" },
      renewals: { status: "unavailable", value: null, reason: "chart_not_exported" },
      cancellations: { status: "measured", value: 0, unit: "count" },
      proceeds_usd: { status: "measured", value: 3.25, unit: "USD", truth: "revenuecat_estimate" }
    }
  }));
  const first = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T13:00:00.000Z");
  const replay = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T14:00:00.000Z");
  const anicca = first.products.find((item) => item.product_id === "anicca-ios");
  const honne = first.products.find((item) => item.product_id === "honne-ai");
  assert.equal(anicca.metrics.active_subscriptions.value, 5);
  assert.equal(anicca.metrics.renewals.status, "unavailable");
  assert.equal(honne.source_status, "unavailable");
  assert.equal(replay.created, false);
  assert.equal(replay.snapshot_ref, first.snapshot_ref);
});

test("rejects product identity mismatch and false unavailable zero", () => {
  const { dataDir } = fixture();
  const inbox = path.join(dataDir, "tenants/dais-local/product-packs/metrics/revenuecat");
  fs.mkdirSync(inbox, { recursive: true });
  fs.writeFileSync(path.join(inbox, "anicca-ios.json"), JSON.stringify({
    schema_version: 1, kind: "product_revenuecat_observation", product_id: "honne-ai", observed_at: "2026-08-23T12:55:00.000Z",
    source: "revenuecat_charts_api", source_status: "unavailable",
    metrics: Object.fromEntries(["trial_starts", "active_subscriptions", "renewals", "cancellations", "proceeds_usd"].map((key) => [key, { status: "unavailable", value: 0, reason: "missing" }]))
  }));
  assert.throws(() => persistRevenueCatSubscriptions(dataDir, "2026-08-23"), /product identity mismatch/);
});

test("loads only exact RevenueCat deployment and app service bindings", () => {
  const result = revenueCatBindingsFromCredentials({ credentials: [
    { service: "revenuecat-mobile-existing-deployment", api_key: "fixture-only-api-key" },
    { service: "revenuecat-anicca-ios-sdk", project_id: "project-mobile" },
    { service: "revenuecat-honne-ios-sdk", project_id: "project-mobile" },
    { service: "revenuecat-anicca-ios-sdk-old", project_id: "wrong-project" },
  ] });
  assert.deepEqual(result, { apiKey: "fixture-only-api-key", apps: APP_BINDINGS });
  assert.throws(() => revenueCatBindingsFromCredentials({ credentials: [
    { service: "revenuecat-mobile-existing-deployment", api_key: "fixture-only-api-key" },
    { service: "revenuecat-mobile-existing-deployment", api_key: "duplicate-key" },
  ] }), /credential_binding_invalid/);
});

test("reads each customer chart through its exact app filter over the previous 28 complete days", async () => {
  const api = fakeRevenueCat();
  const { dataDir } = fixture();
  const result = await persistRevenueCatSubscriptionsDaily(dataDir, "2026-10-12", "2026-10-12T13:00:00.000Z", api);

  assert.equal(api.calls.filter((call) => call.options).length, 2);
  assert.equal(api.calls.filter((call) => !call.options).length, 4);
  const anicca = result.products.find((product) => product.product_id === "anicca-ios");
  const honne = result.products.find((product) => product.product_id === "honne-ai");
  assert.deepEqual([anicca.customer_activity.data_from, anicca.customer_activity.data_to], ["2026-09-14", "2026-10-11"]);
  assert.deepEqual([honne.customer_activity.data_from, honne.customer_activity.data_to], ["2026-09-14", "2026-10-11"]);
  assert.deepEqual([anicca.metrics.customers_new.status, anicca.metrics.customers_new.value], ["measured", 28]);
  assert.deepEqual([anicca.metrics.customers_active.status, anicca.metrics.customers_active.value, anicca.metrics.customers_active.aggregation], ["measured", 3.5, "average_daily"]);
  assert.equal(anicca.customer_activity.charts.customers_new.series.length, 28);
  assert.equal(anicca.customer_activity.charts.customers_active.series[0].date, "2026-09-14");
  assert.match(anicca.customer_activity.charts.customers_new.evidence_sha256, /^[a-f0-9]{64}$/);
  assert.equal(honne.customer_activity.app_id, "app3bbd298d22");
  assert.equal(honne.customer_activity.charts.customers_new.filter.name, "first_app_id");
  assert.deepEqual([result.report_day, result.observed_at, result.customer_activity_status], ["2026-10-12", "2026-10-12T13:00:00.000Z", "measured"]);
  assert.equal(JSON.stringify(result).includes("fixture-only-api-key"), false);

  const replay = await persistRevenueCatSubscriptionsDaily(dataDir, "2026-10-12", "2026-10-12T14:00:00.000Z", {
    ...api,
    requestJson: async () => { throw new Error("daily replay must not query RevenueCat again"); },
  });
  assert.equal(replay.created, false);
  assert.equal(replay.snapshot_ref, result.snapshot_ref);
  assert.equal(api.calls.length, 6);
});

test("keeps missing or incomplete customer chart coverage unavailable instead of zero", async () => {
  const api = fakeRevenueCat({ missingAniccaActiveDay: true, incompleteHonneNewDay: true });
  const result = await fetchRevenueCatCustomerActivity({
    reportDay: "2026-10-12",
    observedAt: "2026-10-12T13:00:00.000Z",
    bindings: api.bindings,
    requestJson: api.requestJson,
  });
  const anicca = result.products.find((product) => product.product_id === "anicca-ios");
  const honne = result.products.find((product) => product.product_id === "honne-ai");

  assert.deepEqual([anicca.charts.customers_active.status, anicca.charts.customers_active.value, anicca.charts.customers_active.reason], ["unavailable", null, "chart_period_coverage_incomplete"]);
  assert.deepEqual([honne.charts.customers_new.status, honne.charts.customers_new.value, honne.charts.customers_new.reason], ["unavailable", null, "chart_period_incomplete"]);
  assert.equal(anicca.charts.customers_active.series.length, 27);
  assert.equal(honne.charts.customers_new.series.length, 28);
});

test("preserves chart API rate-limit and timeout states without masking other app metrics", async () => {
  const api = fakeRevenueCat();
  const requestJson = async (url, key) => {
    const parsed = new URL(url);
    if (parsed.pathname.endsWith("/customers_active/options")) throw new Error("provider_http_429");
    if (parsed.pathname.endsWith("/customers_new") && !parsed.pathname.endsWith("/options")
      && JSON.parse(parsed.searchParams.get("filters"))[0].values[0] === "app511ef26659") {
      const error = new Error("fixture timeout"); error.name = "TimeoutError"; throw error;
    }
    return api.requestJson(url, key);
  };
  const result = await fetchRevenueCatCustomerActivity({
    reportDay: "2026-10-12",
    observedAt: "2026-10-12T13:00:00.000Z",
    bindings: api.bindings,
    requestJson,
  });

  for (const product of result.products) {
    assert.deepEqual([product.charts.customers_active.status, product.charts.customers_active.value, product.charts.customers_active.reason], ["unavailable", null, "provider_http_429"]);
    if (product.product_id === "anicca-ios") {
      assert.deepEqual([product.charts.customers_new.status, product.charts.customers_new.value, product.charts.customers_new.reason], ["unavailable", null, "provider_timeout"]);
      assert.equal(product.source_status, "unavailable");
    } else {
      assert.equal(product.charts.customers_new.status, "measured");
      assert.equal(product.source_status, "partial");
    }
  }
});
