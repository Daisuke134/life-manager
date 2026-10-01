"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");

const { runNativeConnectorWrite } = require("./connector-native-write-pipeline.js");
const { buildRollingEventCoverage } = require("./rolling-event-coverage.js");
const { runLumaCandidateSequence } = require("./luma-candidate-loop.js");
const {
  createEventSourceCapabilities, executeEventSourceHandoff, planEventSourceHandoff,
} = require("./event-source-handoff.js");
const { buildEventProviderDateInventory } = require("./event-provider-date-inventory.js");

const FIXTURE_CONNPASS_API_KEY = ["connpass", "test", "key", "0".repeat(16)].join("-");

const NOW = "2026-08-02T01:00:00.000Z";
const EVENT_REF = "luma-event://event/founder-night";
const EVENT_URL = "https://luma.com/founder-night";
const CHAT_HASH = "37da4c800042eb1a27e8081315efc08f7d546c5be1e47d2d026be17417a090b3";
const TEST_PNG = Buffer.alloc(5_000, 0x61);
Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(TEST_PNG);
const TEST_PNG_HASH = createHash("sha256").update(TEST_PNG).digest("hex");

function input(overrides = {}) {
  const coverage = {
    tenant_id: "dais-local",
    timezone: "Asia/Tokyo",
    coverage_snapshot_id: "coverage-snapshot",
    window_start_date: "2026-08-02",
    window_end_date: "2026-08-22",
    counts: { open: 0, covered_existing: 0, covered_new: 1, unavailable: 0 },
  };
  const dateInventory = {
    coverage_snapshot_id: coverage.coverage_snapshot_id,
    timezone: coverage.timezone,
    days: [{ date: "2026-08-05", events: [{
      event_ref: EVENT_REF,
      canonical_url: EVENT_URL,
      title: "Founder Night",
      starts_at: "2026-08-05T12:00:00.000Z",
      ends_at: "2026-08-05T14:00:00.000Z",
      venue_name: "Shibuya Hall",
      venue_address: "Shibuya, Tokyo",
    }] }],
  };
  return {
    application: {
      tenantId: "dais-local",
      eventUrl: EVENT_URL,
      eventStartIso: "2026-08-05T21:00:00+09:00",
      eventRef: EVENT_REF,
      identityRef: "identity://dais-local/luma",
      browserProfileRef: "browser-profile://cloakbrowser/daily-driver",
      calendarRef: "calendar://google/primary",
      goalDecision: { ranked_events: [{ event_ref: EVENT_REF }] },
      priorityClass: "open_talk",
      preferenceReason: "AI founder向けLT枠が公開されているため最優先です",
      talkState: "provider_verified",
      applicationDeadlineAt: "2026-08-04T14:59:00.000Z",
    },
    dateInventory,
    currentCoverage: coverage,
    busyInventory: { time_zone: "Asia/Tokyo" },
    now: NOW,
    calendar: { kind: "gog" },
    calendarId: "primary",
    telegramTarget: "fixture-target",
    calendarCoverageUrl: "https://calendar.google.com/calendar/u/0/r",
    ...overrides,
  };
}

function depsFor(calls, overrides = {}) {
  return {
    isVerifiedLumaDateInventory: () => true,
    isVerifiedRollingEventCoverage: () => true,
    isVerifiedGoogleCalendarBusyInventory: () => true,
    isVerifiedEventGoalSerendipity: () => true,
    buildEventApplicationJob(application) {
      calls.push(["build", application]);
      return { job_id: "outbound-event:job-1", tenant_id: application.tenantId };
    },
    async executeLumaRsvpJob(job) {
      calls.push(["execute", job]);
      return { receipt: {
        status: "verified",
        attempt_ref: `runtime-attempt://${job.tenant_id}/${job.job_id}/1`,
        canonical_url: EVENT_URL,
        external_receipt_ref: "provider-receipt://luma/fixture",
        artifact_ref: `object://sha256/${TEST_PNG_HASH}`,
        evidence_observed_at: NOW,
        artifact_sha256: TEST_PNG_HASH,
        verified_at: NOW,
      } };
    },
    assertVerifiedOutboundReceipt(receipt, job) {
      calls.push(["assert-receipt", receipt, job]);
      return receipt;
    },
    async readArtifact() { return TEST_PNG; },
    async readLumaConfirmation() { return { id: "gmail-1", body: "verified mail body" }; },
    verifyLumaConfirmationMessage() {
      return Object.freeze({ kind: "confirmation_mail", provider_id: "gmail-1" });
    },
    async recordLumaConfirmation() {
      return { external_receipt_ref: `gmail-message://dais-local/${"b".repeat(64)}` };
    },
    createLumaGuestBinding() { return Object.freeze({ binding: "verified" }); },
    async captureLumaTicketQr() { return Object.freeze({ kind: "ticket" }); },
    async recordLumaTicketQr() {
      return {
        ticket_receipt_ref: `ticket://dais-local/${"c".repeat(64)}`,
        artifact_ref: `object://sha256/${"d".repeat(64)}`,
      };
    },
    async deliverConnectorTicket() {
      return { kind: "telegram_delivery", provider_id: "323" };
    },
    async syncVerifiedRegistrationToGoogleCalendar(syncInput) {
      calls.push(["calendar", syncInput]);
      return {
        status: "created",
        calendar_sync_id: "connector-calendar-sync:sync-1",
        event_ref: EVENT_REF,
        canonical_event_url: EVENT_URL,
        registration_receipt_ref: "runtime-receipt://outbound-event/receipt-1",
        calendar_event_ref: "calendar-evidence://google/event/event-1",
        calendar_event_url: "https://calendar.google.com/calendar/event?eid=opaque",
      };
    },
    buildVerifiedRegistrationCoverageEvidence(evidenceInput) {
      calls.push(["evidence", evidenceInput]);
      return { date: "2026-08-05", status: "covered_new", evidence_refs: ["runtime-receipt://outbound-event/receipt-1"] };
    },
    rebuildRollingEventCoverage(rebuildInput) {
      calls.push(["rebuild", rebuildInput]);
      return {
        ...rebuildInput.previousCoverage,
        counts: { open: 0, covered_existing: 0, covered_new: 1, unavailable: 0 },
        coverage_snapshot_id: "rebuilt-coverage",
      };
    },
    buildConnectorCoverageTelegramMessage(messageInput) {
      calls.push(["message", messageInput]);
      return "verified message";
    },
    async deliverConnectorCoverageTelegram(deliveryInput) {
      calls.push(["telegram", deliveryInput]);
      return {
        kind: "connector_coverage_telegram_delivery",
        provider_id: "321",
        photo_provider_id: "322",
        artifact_sha256: TEST_PNG_HASH,
        observed_at: NOW,
        tenant_id: "dais-local",
        chat_id_sha256: CHAT_HASH,
        coverage_snapshot_id: deliveryInput.coverage.coverage_snapshot_id,
      };
    },
    ...overrides,
  };
}

async function connpassInput() {
  const coverage = buildRollingEventCoverage({
    tenantId: "dais-local", timeZone: "Asia/Tokyo",
    now: "2026-08-01T16:00:00.000Z", resolvedDays: [],
  });
  const lumaOutcome = await runLumaCandidateSequence({ candidates: [], attempt: async () => {} });
  const capabilities = createEventSourceCapabilities({ connpassApiKey: FIXTURE_CONNPASS_API_KEY });
  const plan = planEventSourceHandoff({ date: "2026-08-05", lumaOutcome, capabilities });
  const handoff = await executeEventSourceHandoff({
    plan,
    connpassClient: { async searchEvents() { return {
      results_returned: 1, results_available: 1, results_start: 1,
      events: [{
        id: 101, title: "Connpass Night", catch: "Public", description: "Public details",
        started_at: "2026-08-05T19:00:00+09:00", ended_at: "2026-08-05T21:00:00+09:00",
        place: "Shibuya Hall", address: "Shibuya, Tokyo", group: { subdomain: "tokyo-builders" },
      }],
    }; } },
  });
  const dateInventory = buildEventProviderDateInventory({
    coverage, handoff, eligibleCandidates: handoff.advisory_candidates, now: NOW,
  });
  const event = dateInventory.days.flatMap((day) => day.events)[0];
  return input({
    application: {
      tenantId: "dais-local", eventUrl: event.canonical_url, eventStartIso: event.starts_at,
      eventRef: event.event_ref, identityRef: "identity://dais-local/connpass",
      browserProfileRef: "browser-profile://cloakbrowser/daily-driver",
      calendarRef: "calendar://google/primary",
    },
    dateInventory,
    currentCoverage: coverage,
  });
}

test("a chosen candidate write pipeline is available as an explicit orchestrator", () => {
  assert.equal(typeof runNativeConnectorWrite, "function");
});

test("one occurrence binds discovery, qualification, registration, mail, and Calendar refs", async () => {
  const result = await runNativeConnectorWrite({
    ...input(),
    occurrenceId: "life-manager-connector-native:occurrence-1",
  }, depsFor([]));

  assert.equal(result.occurrence_id, "life-manager-connector-native:occurrence-1");
  assert.deepEqual(Object.keys(result.journey), [
    "discovery", "qualification", "registration", "confirmation_mail", "calendar",
  ]);
  for (const stage of Object.values(result.journey)) {
    assert.equal(stage.occurrence_id, result.occurrence_id);
  }
  assert.equal(result.journey.discovery.event_ref, EVENT_REF);
  assert.equal(result.journey.registration.provider_receipt_ref, "provider-receipt://luma/fixture");
  assert.match(result.journey.confirmation_mail.external_receipt_ref, /^gmail-message:\/\//);
  assert.equal(result.journey.calendar.calendar_event_ref, "calendar-evidence://google/event/event-1");
});

test("verified Connpass inventory enters the common write chain without a fabricated Luma goal", async () => {
  const calls = [];
  const result = await runNativeConnectorWrite(await connpassInput(), depsFor(calls, {
    isVerifiedLumaDateInventory: undefined,
    buildEventApplicationJob(application) {
      calls.push(["build", application]);
      return { job_id: "connpass-job:101", tenant_id: application.tenantId };
    },
  }));

  assert.equal(result.status, "complete");
  assert.equal(result.event_ref, "connpass-event://event/101");
  assert.equal(calls.some((call) => call[0] === "calendar"), true);
  assert.equal(calls.some((call) => call[0] === "telegram"), true);
});

test("an unknown RSVP effect stops before Calendar, coverage, or Telegram", async () => {
  const calls = [];
  const deps = depsFor(calls, {
    async executeLumaRsvpJob(job) {
      calls.push(["execute", job]);
      const error = new Error("provider state disappeared");
      error.unknownEffect = true;
      throw error;
    },
  });

  const result = await runNativeConnectorWrite(input(), deps);

  assert.equal(result.status, "reconciliation_required");
  assert.equal(result.outcome, "unknown_external_effect");
  assert.deepEqual(calls.map((call) => call[0]), ["build", "execute"]);
});

test("verified RSVP evidence gates Calendar sync and then runs the remaining chain in order", async () => {
  const calls = [];
  const result = await runNativeConnectorWrite(input(), depsFor(calls));

  assert.equal(result.status, "complete");
  assert.deepEqual(calls.map((call) => call[0]), [
    "build", "execute", "assert-receipt", "calendar", "evidence", "rebuild", "message", "telegram",
  ]);
  assert.equal(calls[1][1].attempt, 1);
  assert.equal(result.telegram.provider_id, "321");
  assert.deepEqual(result.registration_receipt, {
    attempt_ref: "runtime-attempt://dais-local/outbound-event:job-1/1",
    external_receipt_ref: "provider-receipt://luma/fixture",
    artifact_ref: `object://sha256/${TEST_PNG_HASH}`,
    evidence_observed_at: NOW,
    artifact_sha256: TEST_PNG_HASH,
    canonical_url: EVENT_URL,
    verified_at: NOW,
  });
  assert.equal(result.calendar_sync.calendar_event_ref, "calendar-evidence://google/event/event-1");
  assert.deepEqual(result.selection, {
    priority_class: "open_talk",
    preference_reason: "AI founder向けLT枠が公開されているため最優先です",
    talk_state: "provider_verified",
    application_deadline_at: "2026-08-04T14:59:00.000Z",
  });
  assert.deepEqual(calls.find((call) => call[0] === "message")[1].newEvents[0].selection, result.selection);
});

test("write pipeline reads the verified PNG and binds it to Telegram photo delivery", async () => {
  const calls = [];
  const bytes = Buffer.alloc(5_000, 0x61);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(bytes);
  const hash = createHash("sha256").update(bytes).digest("hex");
  const result = await runNativeConnectorWrite(input(), depsFor(calls, {
    async executeLumaRsvpJob(job) {
      return { receipt: {
        status: "verified",
        attempt_ref: `runtime-attempt://${job.tenant_id}/${job.job_id}/1`,
        canonical_url: EVENT_URL,
        external_receipt_ref: "provider-receipt://luma/fixture",
        artifact_ref: `object://sha256/${hash}`,
        evidence_observed_at: NOW,
        artifact_sha256: hash,
        verified_at: NOW,
      } };
    },
    async readArtifact(tenantId, artifactRef) {
      assert.equal(tenantId, "dais-local");
      assert.equal(artifactRef, `object://sha256/${hash}`);
      return bytes;
    },
    async deliverConnectorCoverageTelegram(deliveryInput) {
      assert.equal(deliveryInput.registrationEvidence.event_ref, EVENT_REF);
      assert.equal(deliveryInput.registrationEvidence.canonical_url, EVENT_URL);
      assert.equal(deliveryInput.registrationEvidence.artifact_sha256, hash);
      assert.equal(createHash("sha256").update(deliveryInput.registrationEvidence.bytes).digest("hex"), hash);
      return {
        kind: "connector_coverage_telegram_delivery",
        provider_id: "321",
        photo_provider_id: "322",
        artifact_sha256: hash,
        observed_at: NOW,
        tenant_id: "dais-local",
        chat_id_sha256: CHAT_HASH,
        coverage_snapshot_id: deliveryInput.coverage.coverage_snapshot_id,
      };
    },
  }));

  assert.equal(result.status, "complete");
  assert.equal(result.telegram.provider_id, "321");
  assert.equal(result.telegram.photo_provider_id, "322");
  assert.equal(result.telegram.photo_provider_id, "322");
  assert.equal(result.telegram.artifact_sha256, hash);
});

test("write pipeline requires verified confirmation mail and official QR before final delivery", async () => {
  const calls = [];
  const result = await runNativeConnectorWrite(input(), depsFor(calls, {
    async readLumaConfirmation(inputValue) {
      calls.push(["confirmation-read", inputValue]);
      return { id: "gmail-1", body: "verified mail body" };
    },
    verifyLumaConfirmationMessage(inputValue) {
      calls.push(["confirmation-verify", inputValue]);
      return Object.freeze({ kind: "confirmation_mail", provider_id: "gmail-1" });
    },
    async recordLumaConfirmation(receipt) {
      calls.push(["confirmation-record", receipt]);
      return { external_receipt_ref: `gmail-message://dais-local/${"b".repeat(64)}` };
    },
    createLumaGuestBinding(inputValue) {
      calls.push(["guest-binding", inputValue]);
      return Object.freeze({ binding: "verified" });
    },
    async captureLumaTicketQr(binding) {
      calls.push(["qr-capture", binding]);
      return Object.freeze({ kind: "ticket" });
    },
    async recordLumaTicketQr(ticket) {
      calls.push(["qr-record", ticket]);
      return {
        ticket_receipt_ref: `ticket://dais-local/${"c".repeat(64)}`,
        artifact_ref: `object://sha256/${"d".repeat(64)}`,
      };
    },
    async deliverConnectorTicket(inputValue) {
      calls.push(["ticket-telegram", inputValue]);
      return { kind: "telegram_delivery", provider_id: "323" };
    },
  }));

  assert.equal(result.status, "complete");
  assert.deepEqual(result.confirmation, {
    external_receipt_ref: `gmail-message://dais-local/${"b".repeat(64)}`,
  });
  assert.deepEqual(result.ticket, {
    ticket_receipt_ref: `ticket://dais-local/${"c".repeat(64)}`,
    artifact_ref: `object://sha256/${"d".repeat(64)}`,
    telegram_provider_id: "323",
  });
  assert.deepEqual(calls.filter(([name]) => [
    "confirmation-read", "confirmation-verify", "confirmation-record", "guest-binding",
    "qr-capture", "qr-record", "calendar", "ticket-telegram", "telegram",
  ].includes(name)).map(([name]) => name), [
    "confirmation-read", "confirmation-verify", "confirmation-record", "guest-binding",
    "qr-capture", "qr-record", "calendar", "ticket-telegram", "telegram",
  ]);
});

test("optional ticket evidence failure cannot block Calendar and registration-page Telegram delivery", async () => {
  const calls = [];
  const result = await runNativeConnectorWrite(input(), depsFor(calls, {
    async readLumaConfirmation() {
      calls.push(["confirmation-read"]);
      throw new Error("confirmation unavailable");
    },
    async deliverConnectorTicket() {
      calls.push(["ticket-telegram"]);
      throw new Error("must not run without a verified ticket");
    },
  }));

  assert.equal(result.status, "complete");
  assert.deepEqual(result.ticket, {
    status: "unavailable",
    reason: "TICKET_EVIDENCE_FAILED",
  });
  assert.equal(result.calendar_sync.calendar_event_ref, "calendar-evidence://google/event/event-1");
  assert.equal(result.telegram.provider_id, "321");
  assert.equal(result.telegram.photo_provider_id, "322");
  assert.deepEqual(calls.map(([name]) => name), [
    "build", "execute", "assert-receipt", "confirmation-read",
    "calendar", "evidence", "rebuild", "message", "telegram",
  ]);
});

test("an unverified Calendar sync cannot produce coverage evidence or Telegram", async () => {
  const calls = [];
  const deps = depsFor(calls, {
    async syncVerifiedRegistrationToGoogleCalendar(syncInput) {
      calls.push(["calendar", syncInput]);
      throw new Error("calendar sync unavailable");
    },
  });

  const result = await runNativeConnectorWrite(input(), deps);

  assert.equal(result.status, "incomplete");
  assert.equal(result.outcome, "calendar_sync_failed");
  assert.deepEqual(calls.map((call) => call[0]), ["build", "execute", "assert-receipt", "calendar"]);
});

test("coverage rebuild is the gate before Telegram message construction and delivery", async () => {
  const calls = [];
  const deps = depsFor(calls, {
    buildVerifiedRegistrationCoverageEvidence(evidenceInput) {
      calls.push(["evidence", evidenceInput]);
      return {};
    },
    rebuildRollingEventCoverage() {
      calls.push(["rebuild"]);
      throw new Error("coverage rebuild unavailable");
    },
  });

  const result = await runNativeConnectorWrite(input(), deps);

  assert.equal(result.status, "incomplete");
  assert.equal(result.outcome, "coverage_rebuild_failed");
  assert.deepEqual(calls.map((call) => call[0]), [
    "build", "execute", "assert-receipt", "calendar", "evidence", "rebuild",
  ]);
});

test("a Telegram delivery without a positive receipt cannot complete the write", async () => {
  const calls = [];
  const deps = depsFor(calls, {
    async deliverConnectorCoverageTelegram(deliveryInput) {
      calls.push(["telegram", deliveryInput]);
      return { ok: true };
    },
  });

  const result = await runNativeConnectorWrite(input(), deps);

  assert.equal(result.status, "reconciliation_required");
  assert.equal(result.outcome, "unknown_external_effect");
  assert.equal(calls.at(-1)[0], "telegram");
});

test("open coverage remains incomplete even after a positive Telegram receipt", async () => {
  const calls = [];
  const result = await runNativeConnectorWrite(input({
    currentCoverage: {
      ...input().currentCoverage,
      counts: { open: 1, covered_existing: 0, covered_new: 1, unavailable: 0 },
    },
  }), depsFor(calls, {
    rebuildRollingEventCoverage(rebuildInput) {
      calls.push(["rebuild", rebuildInput]);
      return {
        ...rebuildInput.previousCoverage,
        counts: { open: 1, covered_existing: 0, covered_new: 1, unavailable: 0 },
        coverage_snapshot_id: "rebuilt-open-coverage",
      };
    },
  }));

  assert.equal(result.status, "incomplete");
  assert.equal(result.outcome, "open_coverage");
  assert.equal(result.coverage.counts.open, 1);
});

test("untrusted candidate I/O functions cannot replace trusted provider and evidence seams", async () => {
  const calls = [];
  const malicious = input({
    provider: { async inspectRegistration() { return { state: "registered" }; } },
    readExternalReceipt: async () => ({ kind: "provider_response", provider_id: "forged", observed_at: NOW }),
    readArtifact: async () => Buffer.alloc(5_000, 0x61),
    fetchImpl: async () => ({ status: 200 }),
    send: async () => ({ messageId: "forged" }),
  });
  const deps = depsFor(calls, {
    async executeLumaRsvpJob(job, services) {
      calls.push(["execute", job, services]);
      assert.equal(services.provider, undefined);
      assert.equal(services.readExternalReceipt, undefined);
      assert.equal(services.readArtifact, undefined);
      assert.equal(services.fetchImpl, undefined);
      throw new Error("trusted provider unavailable");
    },
  });

  const result = await runNativeConnectorWrite(malicious, deps);

  assert.equal(result.status, "incomplete");
  assert.equal(result.outcome, "application_failed");
  assert.deepEqual(calls.map((call) => call[0]), ["build", "execute"]);
});

test("only the exact verified Telegram delivery contract can complete", async (t) => {
  const mutations = [
    ["kind", (receipt) => ({ ...receipt, kind: "telegram_delivery" })],
    ["provider_id", (receipt) => ({ ...receipt, provider_id: "" })],
    ["photo_provider_id", (receipt) => ({ ...receipt, photo_provider_id: "" })],
    ["artifact_sha256", (receipt) => ({ ...receipt, artifact_sha256: "0".repeat(64) })],
    ["observed_at", (receipt) => ({ ...receipt, observed_at: "not-a-time" })],
    ["tenant_id", (receipt) => ({ ...receipt, tenant_id: "other-tenant" })],
    ["coverage_snapshot_id", (receipt) => ({ ...receipt, coverage_snapshot_id: "other-coverage" })],
    ["chat_id_sha256", (receipt) => ({ ...receipt, chat_id_sha256: "not-a-sha256" })],
    ["chat_id_sha256_valid_wrong", (receipt) => ({ ...receipt, chat_id_sha256: "0".repeat(64) })],
  ];
  for (const [label, mutate] of mutations) {
    await t.test(`rejects forged ${label}`, async () => {
      const calls = [];
      const deps = depsFor(calls, {
        async deliverConnectorCoverageTelegram(deliveryInput) {
          calls.push(["telegram", deliveryInput]);
          return mutate({
            kind: "connector_coverage_telegram_delivery",
            provider_id: "321",
            photo_provider_id: "322",
            artifact_sha256: TEST_PNG_HASH,
            observed_at: NOW,
            tenant_id: "dais-local",
            chat_id_sha256: CHAT_HASH,
            coverage_snapshot_id: "rebuilt-coverage",
          });
        },
      });
      const result = await runNativeConnectorWrite(input(), deps);
      assert.equal(result.status, "reconciliation_required");
      assert.equal(result.outcome, "unknown_external_effect");
      assert.equal(calls.at(-1)[0], "telegram");
    });
  }
});
