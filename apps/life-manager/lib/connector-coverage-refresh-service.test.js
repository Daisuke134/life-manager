"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const test = require("node:test");

const { evaluateCalendarCandidateGate } = require("./calendar-candidate-gate.js");
const { syncVerifiedRegistrationToGoogleCalendar } = require("./connector-calendar-sync.js");
const {
  buildVerifiedRegistrationCoverageEvidence,
  proveAllDayCalendarUnavailable,
  rebuildRollingEventCoverage,
} = require("./connector-coverage-assembler.js");
const {
  createConnectorCoverageRefreshService,
} = require("./connector-coverage-refresh-service.js");
const { inspectGoogleCalendarBusyInventory } = require("./google-calendar-busy-inventory.js");
const { collectLumaInventory } = require("./luma-discovery.js");
const { normalizeLumaEventDetail } = require("./luma-event-detail.js");
const { buildLumaDateInventory } = require("./luma-date-inventory.js");
const { buildEventApplicationJob } = require("./outbound-event-job.js");
const { verifyOutboundEvidence } = require("./outbound-evidence.js");
const { buildVerifiedOutboundReceipt } = require("./outbound-success.js");
const { buildRollingEventCoverage } = require("./rolling-event-coverage.js");

const TENANT = "dais-local";
const NOW = "2026-08-02T01:00:00.000Z";

function currentCoverage() {
  return buildRollingEventCoverage({
    tenantId: TENANT,
    timeZone: "Asia/Tokyo",
    now: NOW,
    resolvedDays: [],
  });
}

async function dateInventory(coverage, slug = "founder-night") {
  let round = 0;
  const inventory = await collectLumaInventory({
    readSnapshot: async () => (++round === 1 ? [{
      href: `https://luma.com/${slug}`,
      title: "Founder Night",
      cardText: "Founder Night",
      timelineText: "Aug 5",
    }] : []),
    advance: async () => ({ atEnd: true, scrollHeight: 100 }),
    stableEndRounds: 1,
  });
  const detail = normalizeLumaEventDetail({
    canonicalUrl: `https://luma.com/${slug}`,
    jsonLd: [{
      "@type": "Event",
      name: "Founder Night",
      description: "Public founder gathering",
      startDate: "2026-08-05T12:00:00+09:00",
      endDate: "2026-08-05T13:00:00+09:00",
      eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
      eventStatus: "https://schema.org/EventScheduled",
      location: { name: "Shibuya Hall", address: "Shibuya, Tokyo" },
    }],
    controls: ["Register"],
  });
  return buildLumaDateInventory({ coverage, inventory, details: [detail], now: NOW });
}

async function completedRegistration(slug = "founder-night") {
  const job = buildEventApplicationJob({
    tenantId: TENANT,
    eventUrl: `https://luma.com/${slug}`,
    eventStartIso: "2026-08-05T12:00:00+09:00",
    identityRef: "identity://dais-local/luma",
    browserProfileRef: "browser-profile://cloakbrowser/daily-driver",
    calendarRef: "calendar://google/primary",
  });
  const claimedJob = Object.freeze({ ...job, attempt: 1 });
  const bytes = Buffer.alloc(5_000, 0x61);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(bytes);
  const hash = createHash("sha256").update(bytes).digest("hex");
  const evidence = await verifyOutboundEvidence({
    tenantId: TENANT,
    attemptRef: `runtime-attempt://${TENANT}/${job.job_id}/1`,
    externalReceiptRef: "provider-receipt://luma/fixture-registration",
    artifactRef: `object://sha256/${hash}`,
    canonicalUrl: `https://luma.com/${slug}`,
  }, {
    async readExternalReceipt() {
      return { kind: "provider_response", provider_id: "fixture", observed_at: NOW };
    },
    async readArtifact() { return bytes; },
    async fetchImpl() { return { status: 200 }; },
  });
  return Object.freeze({
    event_ref: job.input_refs.event_ref,
    job: claimedJob,
    receipt: buildVerifiedOutboundReceipt({
      tenantId: TENANT,
      jobId: job.job_id,
      attempt: 1,
      verifiedAt: NOW,
    }, evidence),
  });
}

async function busyInventory() {
  return inspectGoogleCalendarBusyInventory({
    calendar: {
      async listCalendarsRaw() { return [{ id: "primary" }]; },
      async listAllEventsRaw() {
        return [{
          CalendarID: "primary",
          id: "fixed-all-day",
          status: "confirmed",
          start: { date: "2026-08-06" },
          end: { date: "2026-08-07" },
        }];
      },
    },
    timeMin: "2026-08-01T15:00:00.000Z",
    timeMax: "2026-08-22T15:00:00.000Z",
    timeZone: "Asia/Tokyo",
    now: NOW,
  });
}

function makeService(input) {
  return createConnectorCoverageRefreshService({
    receiptReader: input.receiptReader,
    calendar: input.calendar,
    calendarId: "primary",
    now: () => NOW,
    readDateInventory: input.readDateInventory,
    readBusyCalendar: input.readBusyCalendar || (async () => busyInventory()),
    gateDateCalendar: evaluateCalendarCandidateGate,
    syncRegistrationCalendar: input.syncRegistrationCalendar || syncVerifiedRegistrationToGoogleCalendar,
    buildRegistrationCoverageEvidence: input.buildRegistrationCoverageEvidence
      || buildVerifiedRegistrationCoverageEvidence,
    proveUnavailableDay: proveAllDayCalendarUnavailable,
    rebuildCoverage: rebuildRollingEventCoverage,
    readUnavailablePlanEvidence: input.readUnavailablePlanEvidence || (() => {
      throw new Error("unexpected unavailable plan");
    }),
    rebindUnavailablePlan: input.rebindUnavailablePlan || (() => {
      throw new Error("unexpected unavailable plan");
    }),
    planOpenDate: input.planOpenDate || (async ({ coverage }) => ({
      open_date_plan_id: `connector-open-date-plan:${"a".repeat(64)}`,
      coverage_snapshot_id: coverage.coverage_snapshot_id,
      inventory_snapshot_id: "luma-date-inventory:fixture",
      date: coverage.days.find((day) => day.status === "open")?.date || null,
      status: coverage.counts.open > 0 ? "waiting" : "complete",
      event_ref: null,
      job_ref: null,
    })),
    profile: input.profile || { tenant_id: TENANT },
    apiKey: "fixture-key",
  });
}

test("verified RSVP becomes a Calendar event and coverage while a real all-day blocker closes only its date", async () => {
  const coverage = currentCoverage();
  const inventory = await dateInventory(coverage);
  const registration = await completedRegistration();
  const created = [];
  let found = [];
  let requiredCanonicalUrls;
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return [registration]; } },
    readDateInventory: async (input) => {
      requiredCanonicalUrls = input.requiredCanonicalUrls;
      return inventory;
    },
    calendar: {
      async findConnectorEvents() { return found; },
      async createConnectorEvent(input) {
        created.push(input);
        found = [{ id: "created-event", htmlLink: "https://calendar.google.com/calendar/event?eid=created" }];
        return found[0];
      },
    },
  });

  const result = await refresh({
    coverage,
    tenantId: TENANT,
    identityRef: "identity://dais-local/luma",
    browserProfileRef: "browser-profile://cloakbrowser/daily-driver",
    calendarRef: "calendar://google/primary",
  });

  assert.equal(created.length, 1);
  assert.deepEqual(requiredCanonicalUrls, ["https://luma.com/founder-night"]);
  assert.equal(created[0].canonicalUrl, "https://luma.com/founder-night");
  assert.equal(result.coverage.counts.covered_new, 1);
  assert.equal(result.coverage.counts.unavailable, 1);
  assert.equal(result.coverage.counts.open, 26);
  assert.deepEqual(result.observedOutcomes, [{ date: "2026-08-05", observed_status: "booked" }]);
});

test("a retried Connector registration remains covered_new when its exact Calendar event already exists", async () => {
  const coverage = currentCoverage();
  const inventory = await dateInventory(coverage);
  const registration = await completedRegistration();
  let creates = 0;
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return [registration]; } },
    readDateInventory: async () => inventory,
    calendar: {
      async findConnectorEvents() {
        return [{
          id: "existing-event",
          htmlLink: "https://calendar.google.com/calendar/event?eid=existing",
        }];
      },
      async createConnectorEvent() { creates += 1; },
    },
  });

  const result = await refresh({ coverage, tenantId: TENANT });
  assert.equal(result.coverage.counts.covered_existing, 0);
  assert.equal(result.coverage.counts.covered_new, 1);
  assert.equal(result.coverage.counts.unavailable, 1);
  assert.equal(result.coverage.counts.open, 26);
  assert.equal(creates, 0);
});

test("a completed receipt absent from the fresh exhaustive inventory cannot create Calendar or coverage", async () => {
  const coverage = currentCoverage();
  const registration = await completedRegistration("not-in-inventory");
  let creates = 0;
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return [registration]; } },
    readDateInventory: async () => dateInventory(coverage),
    calendar: {
      async findConnectorEvents() { return []; },
      async createConnectorEvent() { creates += 1; },
    },
  });

  await assert.rejects(refresh({
    coverage,
    tenantId: TENANT,
    identityRef: "identity://dais-local/luma",
    browserProfileRef: "browser-profile://cloakbrowser/daily-driver",
    calendarRef: "calendar://google/primary",
  }), (error) => (
    error.code === "CONNECTOR_COVERAGE_REGISTRATION_INVENTORY_MATCH_FAILED"
    && error.message === "Connector coverage refresh unavailable"
  ));
  assert.equal(creates, 0);
});

test("registration restore separates Calendar sync from coverage evidence without private text", async () => {
  const coverage = currentCoverage();
  const inventory = await dateInventory(coverage);
  const registration = await completedRegistration();
  const privateText = "private provider response";
  const cases = [
    {
      code: "CONNECTOR_COVERAGE_REGISTRATION_CALENDAR_SYNC_FAILED",
      overrides: {
        async syncRegistrationCalendar() { throw new Error(privateText); },
      },
    },
    {
      code: "CONNECTOR_COVERAGE_REGISTRATION_EVIDENCE_FAILED",
      overrides: {
        async syncRegistrationCalendar() { return Object.freeze({ verified: true }); },
        buildRegistrationCoverageEvidence() { throw new Error(privateText); },
      },
    },
  ];
  for (const item of cases) {
    const refresh = makeService({
      receiptReader: { async listForCoverage() { return [registration]; } },
      readDateInventory: async () => inventory,
      calendar: { async findConnectorEvents() { return []; }, async createConnectorEvent() {} },
      ...item.overrides,
    });
    await assert.rejects(refresh({ coverage, tenantId: TENANT }), (error) => (
      error.code === item.code
      && error.message === "Connector coverage refresh unavailable"
      && !JSON.stringify(error).includes(privateText)
    ));
  }
});

test("inventory failure exposes only a stable operational stage code", async () => {
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return []; } },
    readDateInventory: async () => { throw new Error("private browser detail"); },
    calendar: {
      async findConnectorEvents() { return []; },
      async createConnectorEvent() { throw new Error("must not create"); },
    },
  });
  await assert.rejects(
    refresh({ coverage: currentCoverage(), tenantId: TENANT }),
    (error) => error.message === "Connector coverage refresh unavailable"
      && error.code === "CONNECTOR_COVERAGE_INVENTORY_FAILED"
      && !JSON.stringify(error).includes("private browser detail"),
  );
});

test("preserves a safe exact Luma inventory substage code", async () => {
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return []; } },
    calendar: { async findConnectorEvents() { return []; }, async createConnectorEvent() {} },
    readDateInventory: async () => {
      const error = new Error("private browser detail");
      error.code = "CONNECTOR_COVERAGE_INVENTORY_DETAIL_FAILED";
      throw error;
    },
  });
  await assert.rejects(
    refresh({ coverage: currentCoverage(), tenantId: TENANT }),
    (error) => error.message === "Connector coverage refresh unavailable"
      && error.code === "CONNECTOR_COVERAGE_INVENTORY_DETAIL_FAILED"
      && !JSON.stringify(error).includes("private browser detail"),
  );
});

test("open-date planning runs only after verified registrations are rebuilt into coverage", async () => {
  const coverage = currentCoverage();
  const inventory = await dateInventory(coverage);
  const registration = await completedRegistration();
  let plannedCoverage;
  const plan = Object.freeze({
    open_date_plan_id: `connector-open-date-plan:${"b".repeat(64)}`,
    coverage_snapshot_id: "assigned-by-test",
    inventory_snapshot_id: inventory.inventory_snapshot_id,
    date: "2026-08-02",
    status: "enqueued",
    event_ref: "luma-event://event/next",
    job_ref: `runtime-job://${TENANT}/${"c".repeat(64)}`,
  });
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return [registration]; } },
    readDateInventory: async () => inventory,
    calendar: {
      async findConnectorEvents() { return [{ id: "existing", htmlLink: "https://calendar.google.com/calendar/event?eid=existing" }]; },
      async createConnectorEvent() { throw new Error("must not create"); },
    },
    async planOpenDate(input) {
      plannedCoverage = input.coverage;
      return { ...plan, coverage_snapshot_id: input.coverage.coverage_snapshot_id };
    },
  });
  const result = await refresh({ coverage, tenantId: TENANT });
  assert.equal(plannedCoverage.counts.covered_new, 1);
  assert.equal(plannedCoverage.counts.covered_existing, 0);
  assert.equal(result.openDatePlan.status, "enqueued");
  assert.equal(result.openDatePlan.coverage_snapshot_id, result.coverage.coverage_snapshot_id);
});

test("application planning failure keeps its bounded stage code", async () => {
  const coverage = currentCoverage();
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return []; } },
    readDateInventory: async () => dateInventory(coverage),
    calendar: {
      async findConnectorEvents() { return []; },
      async createConnectorEvent() { throw new Error("must not create"); },
    },
    async planOpenDate() { throw new Error("private model response"); },
  });
  await assert.rejects(
    refresh({ coverage, tenantId: TENANT }),
    (error) => error.code === "CONNECTOR_COVERAGE_APPLICATION_PLAN_FAILED"
      && !JSON.stringify(error).includes("private model response"),
  );
});

test("application planning preserves a bounded substage code without provider text", async () => {
  const coverage = currentCoverage();
  const error = new Error("private model response");
  error.code = "CONNECTOR_COVERAGE_APPLICATION_RANKING_FAILED";
  const refresh = makeService({
    receiptReader: { async listForCoverage() { return []; } },
    readDateInventory: async () => dateInventory(coverage),
    calendar: {
      async findConnectorEvents() { return []; },
      async createConnectorEvent() { throw new Error("must not create"); },
    },
    async planOpenDate() { throw error; },
  });
  await assert.rejects(refresh({ coverage, tenantId: TENANT }), (caught) => (
    caught.code === "CONNECTOR_COVERAGE_APPLICATION_RANKING_FAILED"
    && caught.message === "Connector coverage refresh unavailable"
    && !JSON.stringify(caught).includes("private model response")
  ));
});

test("a planner-proven calendar conflict resolves the day before returning coverage", async () => {
  const coverage = currentCoverage();
  const inventory = await dateInventory(coverage);
  const unavailable = proveAllDayCalendarUnavailable({
    busyInventory: await busyInventory(), date: "2026-08-06",
  });
  const emptyBusy = await inspectGoogleCalendarBusyInventory({
    calendar: {
      async listCalendarsRaw() { return [{ id: "primary" }]; },
      async listAllEventsRaw() { return []; },
    },
    timeMin: "2026-08-01T15:00:00.000Z", timeMax: "2026-08-22T15:00:00.000Z",
    timeZone: "Asia/Tokyo", now: NOW,
  });
  const service = makeService({
    receiptReader: { async listForCoverage() { return []; } },
    calendar: { async findConnectorEvents() { return []; }, async createConnectorEvent() {} },
    readDateInventory: async () => inventory,
    readBusyCalendar: async () => emptyBusy,
    planOpenDate: async ({ coverage: source }) => ({
      open_date_plan_id: `connector-open-date-plan:${"f".repeat(64)}`,
      coverage_snapshot_id: source.coverage_snapshot_id,
      inventory_snapshot_id: inventory.inventory_snapshot_id,
      date: "2026-08-06", status: "unavailable", event_ref: null, job_ref: null,
      candidate_count: 1, runnable_candidate_count: 0,
      skip_reason_counts: [{ reason: "calendar_conflict", count: 1 }],
    }),
    readUnavailablePlanEvidence: () => unavailable,
    rebindUnavailablePlan: (plan, resolved) => ({
      ...plan, coverage_snapshot_id: resolved.coverage_snapshot_id,
    }),
  });
  const result = await service({ coverage, tenantId: TENANT });
  assert.equal(result.coverage.days.find((day) => day.date === "2026-08-06").status, "unavailable");
  assert.deepEqual(result.observedOutcomes.at(-1), {
    date: "2026-08-06", observed_status: "calendar_unavailable",
  });
  assert.equal(result.openDatePlan.coverage_snapshot_id, result.coverage.coverage_snapshot_id);
});

test("a verified unavailable day remains resolved inside the same rolling window", () => {
  const previous = buildRollingEventCoverage({
    tenantId: TENANT, timeZone: "Asia/Tokyo", now: NOW,
    resolvedDays: [{
      date: "2026-08-02", status: "unavailable",
      evidence_refs: [`calendar-evidence://google/event/${"a".repeat(64)}`],
    }],
  });
  const rebuilt = rebuildRollingEventCoverage({
    tenantId: TENANT, timeZone: "Asia/Tokyo", now: NOW,
    previousCoverage: previous, registrations: [], unavailableDays: [],
  });
  assert.equal(rebuilt.days[0].status, "unavailable");
  assert.deepEqual(rebuilt.days[0].evidence_refs, previous.days[0].evidence_refs);
});
