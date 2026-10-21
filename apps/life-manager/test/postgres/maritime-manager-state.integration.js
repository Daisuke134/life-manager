"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { Client } = require("pg");
const test = require("node:test");
const { normalizeWebFunnelEvent } = require("../../lib/web-funnel-events.js");

const IDENTITY_MIGRATION = path.join(__dirname, "../../migrations/20261021090000_maritime_manager_runtime_state.sql");
const MANAGER_TABLES = [
  "lm_maritime_manager_identities",
  "lm_maritime_manager_enrollments",
  "lm_maritime_manager_executions",
  "lm_maritime_pilot_participants",
  "lm_web_funnel_events",
  "lm_cfo_result_receipts",
];

test("fresh runtime PostgreSQL fails closed until all six Manager state tables exist", async (t) => {
  let bin;
  try {
    bin = path.dirname(execFileSync("/usr/bin/which", ["initdb"], { encoding: "utf8" }).trim());
  } catch {
    t.skip("PostgreSQL server binaries are not installed in this environment");
    return;
  }

  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "lm-maritime-manager-state-"));
  fs.chmodSync(fixture, 0o700);
  const data = path.join(fixture, "data");
  const socket = path.join(fixture, "socket");
  fs.mkdirSync(socket, { mode: 0o700 });
  const log = path.join(fixture, "postgres.log");
  const port = 55447;
  const env = {
    PATH: process.env.PATH || "/usr/bin:/bin",
    LANG: "C",
    LC_ALL: "C",
    PGPASSFILE: path.join(fixture, "no-password-file"),
  };
  let started = false;
  let client;
  let racingClient;
  try {
    execFileSync(bin + "/initdb", ["-D", data, "-A", "trust", "-U", "fixture_owner", "--no-locale", "-E", "UTF8"], {
      env,
      stdio: "pipe",
    });
    execFileSync(bin + "/pg_ctl", ["-D", data, "-l", log, "-o", `-F -h '' -k ${socket} -p ${port}`, "-w", "-t", "15", "start"], {
      env,
      stdio: "pipe",
    });
    started = true;
    client = new Client({ host: socket, port, database: "postgres", user: "fixture_owner", password: "", connectionTimeoutMillis: 5000 });
    await client.connect();

    const present = await client.query(
      "SELECT name, to_regclass(format('public.%I', name))::text AS relation FROM unnest($1::text[]) AS name ORDER BY name",
      [MANAGER_TABLES],
    );
    assert.deepEqual(present.rows.map(row => row.relation), Array(MANAGER_TABLES.length).fill(null));

    for (const table of MANAGER_TABLES) {
      await assert.rejects(
        client.query(`SELECT 1 FROM public.${table} LIMIT 0`),
        error => error.code === "42P01",
        `${table} must fail as an absent relation before the Manager migration is applied`,
      );
    }

    assert.equal(client.connectionParameters.host, socket, "fixture connects only over its private Unix socket");
    assert.equal(fs.existsSync(IDENTITY_MIGRATION), true, "runtime identity migration must exist");
    await client.query(fs.readFileSync(IDENTITY_MIGRATION, "utf8"));

    const migrated = await client.query(
      "SELECT name, to_regclass(format('public.%I', name))::text AS relation FROM unnest($1::text[]) AS name ORDER BY name",
      [MANAGER_TABLES],
    );
    const relations = Object.fromEntries(migrated.rows.map(row => [row.name, row.relation]));
    assert.equal(relations.lm_maritime_manager_identities, "lm_maritime_manager_identities");
    assert.equal(relations.lm_maritime_manager_enrollments, "lm_maritime_manager_enrollments");
    assert.equal(relations.lm_maritime_manager_executions, "lm_maritime_manager_executions");
    assert.equal(relations.lm_maritime_pilot_participants, "lm_maritime_pilot_participants");
    assert.equal(relations.lm_web_funnel_events, "lm_web_funnel_events");
    assert.equal(relations.lm_cfo_result_receipts, "lm_cfo_result_receipts");
    assert.equal((await client.query("SELECT to_regclass('public.lm_users') AS relation")).rows[0].relation, null,
      "Manager runtime state does not require or create the global lm_users table");
    for (const table of MANAGER_TABLES.filter(name => !["lm_maritime_manager_identities", "lm_maritime_manager_enrollments", "lm_maritime_manager_executions", "lm_maritime_pilot_participants", "lm_web_funnel_events", "lm_cfo_result_receipts"].includes(name))) {
      assert.equal(relations[table], null, `${table} stays out of this Manager migration`);
    }

    const columns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_manager_identities'",
    );
    const names = new Set(columns.rows.map(row => row.column_name));
    for (const column of ["uid", "auth_subject", "verified_at", "first_touch", "first_touch_at"]) {
      assert.ok(names.has(column), `identity schema includes ${column}`);
    }
    const uidA = "lm_11111111-1111-4111-8111-111111111111";
    const uidB = "lm_22222222-2222-4222-8222-222222222222";
    const subjectA = "11111111-1111-4111-8111-111111111111";
    const subjectB = "22222222-2222-4222-8222-222222222222";
    const releaseSha = "a".repeat(40);
    await client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [uidA, subjectA]);
    await client.query("UPDATE public.lm_maritime_manager_identities SET first_touch=$1::jsonb,first_touch_at=clock_timestamp() WHERE uid=$2", [JSON.stringify({ utm_source: "x" }), uidA]);
    await assert.rejects(
      client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [uidB, subjectA]),
      error => error.code === "23505",
      "a verified Auth subject cannot be rebound to another UID",
    );
    await assert.rejects(
      client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [uidA, subjectB]),
      error => error.code === "23505",
      "a UID cannot be rebound to another verified Auth subject",
    );
    await assert.rejects(
      client.query("UPDATE public.lm_maritime_manager_identities SET auth_subject=$1 WHERE uid=$2", [subjectB, uidA]),
      error => error.code === "23514",
      "an existing identity binding cannot be reassigned",
    );
    await assert.rejects(
      client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject,first_touch) VALUES ($1,$2,'[]'::jsonb)", [uidB, subjectB]),
      error => error.code === "23514",
      "first-touch must be an object with its timestamp",
    );
    await client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [uidB, subjectB]);

    const enrollmentColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_manager_enrollments'",
    );
    const enrollmentNames = new Set(enrollmentColumns.rows.map(row => row.column_name));
    for (const column of ["uid", "auth_subject", "email", "timezone", "status", "source", "consent_version", "agent_id", "release_sha", "paused_at"]) {
      assert.ok(enrollmentNames.has(column), `enrollment schema includes ${column}`);
    }
    await client.query(`INSERT INTO public.lm_maritime_manager_enrollments(uid,auth_subject,email,status,source,consent_version,release_sha)
      VALUES ($1,$2,'a@example.invalid','pending','direct','maritime-manager-v1',$3),
             ($4,$5,'b@example.invalid','pending','direct','maritime-manager-v1',$3)`, [uidA, subjectA, releaseSha, uidB, subjectB]);
    const claim = uid => client.query('SELECT public.claim_lm_maritime_manager_provision_v1($1) AS claimed', [uid]).then(result => result.rows[0].claimed);
    const bind = (uid, subject, agent) => client.query(
      'SELECT public.bind_lm_maritime_manager_agent_v1($1,$2,$3,$4) AS bound', [uid, subject, agent, releaseSha],
    ).then(result => result.rows[0].bound);
    assert.equal(await claim(uidA), true);
    assert.equal(await claim(uidA), false);
    assert.equal(await bind(uidA, subjectA, 'agent-a'), true);
    assert.equal(await bind(uidA, subjectA, 'agent-a'), true);
    assert.equal(await bind(uidA, subjectB, 'agent-other'), false);
    assert.equal(await claim(uidB), true);
    assert.equal(await bind(uidB, subjectB, 'agent-a'), false);
    assert.equal(await bind(uidB, subjectB, 'agent-b'), true);

    const executionColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_manager_executions'",
    );
    const executionNames = new Set(executionColumns.rows.map(row => row.column_name));
    for (const column of ["uid", "occurrence_id", "agent_id", "date_key", "release_sha", "execution_id", "claimed_at"]) {
      assert.ok(executionNames.has(column), `execution schema includes ${column}`);
    }
    racingClient = new Client({ host: socket, port, database: "postgres", user: "fixture_owner", password: "", connectionTimeoutMillis: 5000 });
    await racingClient.connect();
    const cycleClaim = (connection, uid, occurrence, agent, sha = releaseSha, date = "2026-10-21") => connection.query(
      "SELECT public.claim_lm_maritime_manager_cycle_v1($1,$2,$3,$4,$5::date) AS claimed",
      [uid, occurrence, agent, sha, date],
    ).then(result => result.rows[0].claimed);
    const cycleBind = (uid, occurrence, agent, sha, date, executionId) => client.query(
      "SELECT public.bind_lm_maritime_manager_execution_v1($1,$2,$3,$4,$5::date,$6) AS bound",
      [uid, occurrence, agent, sha, date, executionId],
    ).then(result => result.rows[0].bound);
    const competingClaims = await Promise.all([
      cycleClaim(client, uidA, "week-1-occurrence", "agent-a"),
      cycleClaim(racingClient, uidA, "week-1-occurrence", "agent-a"),
    ]);
    assert.deepEqual(competingClaims.sort(), [false, true], "concurrent claims for one occurrence have exactly one winner");
    assert.equal(await cycleClaim(client, uidA, "week-1-occurrence", "agent-a"), false, "occurrence claim is not replayable");
    assert.equal(await cycleClaim(client, uidB, "foreign-occurrence", "agent-a"), false, "an agent cannot claim for another UID");
    assert.equal(await cycleClaim(client, uidA, "wrong-release", "agent-a", "b".repeat(40)), false, "a stale release cannot claim work");
    assert.equal(await cycleBind(uidA, "week-1-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-1"), true);
    assert.equal(await cycleBind(uidA, "week-1-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-1"), true, "same execution ID may be rebound idempotently");
    assert.equal(await cycleBind(uidA, "week-1-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-2"), false, "a bound occurrence cannot change execution ID");
    assert.equal(await cycleBind(uidA, "week-1-occurrence", "agent-a", releaseSha, "2026-10-20", "exec-1"), false, "date mismatch cannot bind");
    assert.equal((await client.query("SELECT execution_id FROM public.lm_maritime_manager_executions WHERE uid=$1 AND occurrence_id=$2", [uidA, "week-1-occurrence"])).rows[0].execution_id, "exec-1");
    assert.equal(await cycleClaim(client, uidA, "second-occurrence", "agent-a"), true);
    await assert.rejects(
      cycleBind(uidA, "second-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-1"),
      error => error.code === "23505",
      "an execution ID cannot be owned by two occurrences for one agent",
    );
    assert.equal(await cycleBind(uidA, "second-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-2"), true);
    await client.query("UPDATE public.lm_maritime_manager_enrollments SET status='paused',paused_at=clock_timestamp() WHERE uid=$1", [uidA]);
    assert.equal(await cycleClaim(client, uidA, "after-stop", "agent-a"), false, "a paused enrollment cannot dispatch another occurrence");
    assert.equal(await cycleBind(uidA, "week-1-occurrence", "agent-a", releaseSha, "2026-10-21", "exec-1"), true, "a prior dispatch can still read back its exact binding after pause");

    const participantColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_pilot_participants'",
    );
    const participantNames = new Set(participantColumns.rows.map(row => row.column_name));
    for (const column of ["participant_id", "source", "consent_version", "consented_at", "revoked_at", "first_response_at", "returned_at", "created_at", "updated_at"]) {
      assert.ok(participantNames.has(column), `participant schema includes ${column}`);
    }
    const claimParticipant = (connection, participantId, source, maxUsers = 1, consentVersion = "maritime-retention-v1") => connection.query(
      "SELECT public.claim_lm_maritime_participant_v1($1,$2,$3,$4,$5::timestamptz) AS status",
      [participantId, source, consentVersion, maxUsers, "2026-10-21T00:00:00Z"],
    ).then(result => result.rows[0].status);
    const participantIds = ["a".repeat(64), "b".repeat(64)];
    const participantRace = await Promise.all([
      claimParticipant(client, participantIds[0], "instagram"),
      claimParticipant(racingClient, participantIds[1], "x"),
    ]);
    assert.deepEqual(participantRace.slice().sort(), ["capacity_full", "consented"], "one-slot concurrent claims cannot oversubscribe capacity");
    const acceptedIndex = participantRace.indexOf("consented");
    const acceptedParticipantId = participantIds[acceptedIndex];
    const acceptedSource = acceptedIndex === 0 ? "instagram" : "x";
    assert.equal(await claimParticipant(client, acceptedParticipantId, acceptedSource), "already_consented");
    assert.equal(await claimParticipant(client, "c".repeat(64), "linkedin"), "invalid", "the database accepts only normalized source tokens");
    assert.equal(await claimParticipant(client, "d".repeat(64), "direct", 1001), "invalid", "the max remains bounded at 1000");
    await client.query("UPDATE public.lm_maritime_pilot_participants SET revoked_at='2026-10-21T01:00:00Z',updated_at='2026-10-21T01:00:00Z' WHERE participant_id=$1", [acceptedParticipantId]);
    assert.equal(await claimParticipant(client, acceptedParticipantId, "direct"), "consented", "a returning participant may restore consent without consuming a new slot");
    const restored = (await client.query("SELECT source,revoked_at FROM public.lm_maritime_pilot_participants WHERE participant_id=$1", [acceptedParticipantId])).rows[0];
    assert.equal(restored.source, acceptedSource, "re-consent preserves first-touch source");
    assert.equal(restored.revoked_at, null);
    assert.equal(await claimParticipant(client, "e".repeat(64), "direct"), "capacity_full", "re-consent does not increase capacity");

    const funnelColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_web_funnel_events'",
    );
    const funnelNames = new Set(funnelColumns.rows.map(row => row.column_name));
    for (const column of ["event_id", "event_name", "audience_kind", "uid", "source_object_id", "source_event_id", "attribution", "amount_usd", "currency", "billing_reason", "occurred_at"]) {
      assert.ok(funnelNames.has(column), `funnel schema includes ${column}`);
    }
    const insertFunnelEvent = row => client.query(
      `INSERT INTO public.lm_web_funnel_events(event_id,event_name,audience_kind,uid,source_object_id,source_event_id,attribution,amount_usd,currency,billing_reason,occurred_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11::timestamptz)`,
      [row.event_id, row.event_name, row.audience_kind || null, row.uid, row.source_object_id, row.source_event_id,
        JSON.stringify(row.attribution), row.amount_usd, row.currency, row.billing_reason, row.occurred_at],
    );
    const invoiceRow = normalizeWebFunnelEvent({
      eventName: "paid_invoice", eventId: "invoice-1", uid: uidA, sourceObjectId: "in_1", sourceEventId: "stripe-event-1",
      amountUsd: 29, currency: "USD", billingReason: "subscription_cycle", attribution: {},
    }, Date.parse("2026-10-21T00:00:00Z"));
    await insertFunnelEvent(invoiceRow);
    const storedInvoice = (await client.query("SELECT uid,audience_kind,amount_usd,currency,billing_reason FROM public.lm_web_funnel_events WHERE event_id='invoice-1'")).rows[0];
    assert.equal(storedInvoice.uid, uidA);
    assert.equal(storedInvoice.audience_kind, null);
    assert.equal(storedInvoice.amount_usd, "29");
    assert.equal(storedInvoice.currency, "usd");
    assert.equal(storedInvoice.billing_reason, "subscription_cycle");
    const workRow = normalizeWebFunnelEvent({
      eventName: "maritime_work_completed", eventId: "work-1", audienceKind: "external",
      sourceObjectId: "f".repeat(64), sourceEventId: "maritime:work-event-1",
      attribution: { utm_source: "maritime-instagram", utm_medium: "web", utm_campaign: "the-first-1000" },
    }, Date.parse("2026-10-21T00:00:00Z"));
    await insertFunnelEvent(workRow);
    const storedWork = (await client.query("SELECT * FROM public.lm_web_funnel_events WHERE event_id='work-1'")).rows[0];
    assert.equal(storedWork.audience_kind, "external");
    assert.equal(storedWork.attribution.utm_source, "maritime-instagram");
    assert.equal(storedWork.occurred_at.toISOString(), workRow.occurred_at, "the current normalizer payload stores without transformation");
    await insertFunnelEvent(normalizeWebFunnelEvent({
      eventName: "maritime_work_completed", eventId: "work-2", audienceKind: "external",
      sourceObjectId: "f".repeat(64), sourceEventId: "maritime:work-event-2",
    }, Date.parse("2026-10-21T00:01:00Z")));
    await assert.rejects(
      insertFunnelEvent(normalizeWebFunnelEvent({
        eventName: "maritime_report_sent", eventId: "report-duplicate-source", audienceKind: "external",
        sourceObjectId: "f".repeat(64), sourceEventId: "maritime:work-event-1",
      })),
      error => error.code === "23505",
      "stable source_event_id is globally unique",
    );
    const startRow = normalizeWebFunnelEvent({
      eventName: "maritime_start", eventId: "start-1", sourceObjectId: "f".repeat(64), sourceEventId: "maritime:start-event-1",
    });
    await insertFunnelEvent(startRow);
    await assert.rejects(
      insertFunnelEvent(normalizeWebFunnelEvent({
        eventName: "maritime_start", eventId: "start-2", sourceObjectId: "f".repeat(64), sourceEventId: "maritime:start-event-2",
      })),
      error => error.code === "23505",
      "a one-time milestone cannot be duplicated for one source object",
    );
    await assert.rejects(
      insertFunnelEvent({ ...workRow, event_id: "bad-audience-1", event_name: "paid_invoice", audience_kind: "external", source_event_id: "bad-audience-source-1" }),
      error => error.code === "23514",
      "only Maritime events may be assigned an audience kind",
    );
    await assert.rejects(
      insertFunnelEvent({ ...workRow, event_id: "bad-audience-2", audience_kind: "everyone", source_event_id: "bad-audience-source-2", source_object_id: "e".repeat(64) }),
      error => error.code === "23514",
      "audience kind is restricted to internal or external",
    );
    await assert.rejects(
      client.query("UPDATE public.lm_web_funnel_events SET attribution='{}'::jsonb WHERE event_id='work-1'"),
      error => error.code === "P0001",
      "funnel events are append-only for updates",
    );
    await assert.rejects(
      client.query("DELETE FROM public.lm_web_funnel_events WHERE event_id='work-1'"),
      error => error.code === "P0001",
      "funnel events are append-only for deletes",
    );
    await assert.rejects(
      client.query("TRUNCATE public.lm_web_funnel_events"),
      error => error.code === "P0001",
      "funnel events are append-only for truncation",
    );
    const cfoColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_cfo_result_receipts'",
    );
    const cfoNames = new Set(cfoColumns.rows.map(row => row.column_name));
    for (const column of ["uid", "period_key", "channel", "recipient_hash", "status", "message", "observed_at", "provider_message_id", "sent_at"]) {
      assert.ok(cfoNames.has(column), `CFO receipt schema includes ${column}`);
    }
    assert.equal(cfoNames.has("recipient"), false, "receipt stores only the recipient hash");
    const receiptHash = "c".repeat(64);
    const insertReceipt = (uid, periodKey, status, providerMessageId = null, sentAt = null, hash = receiptHash) => client.query(
      `INSERT INTO public.lm_cfo_result_receipts(uid,period_key,channel,recipient_hash,status,message,observed_at,provider_message_id,sent_at)
       VALUES ($1,$2,'email',$3,$4,'daily result','2026-10-21T00:00:00Z',$5,$6::timestamptz)`,
      [uid, periodKey, hash, status, providerMessageId, sentAt],
    );
    await insertReceipt(uidA, "maritime:daily:2026-10-21", "pending");
    await assert.rejects(
      insertReceipt(uidA, "maritime:daily:2026-10-21", "pending"),
      error => error.code === "23505",
      "only one receipt is allowed per UID and period",
    );
    await assert.rejects(
      insertReceipt(uidA, "maritime:daily:invalid-pending", "pending", "provider-message-1"),
      error => error.code === "23514",
      "pending receipts cannot contain a provider message or sent timestamp",
    );
    await assert.rejects(
      insertReceipt(uidA, "maritime:daily:invalid-sent", "sent", "provider-message-2"),
      error => error.code === "23514",
      "sent receipts require both provider message ID and sent timestamp",
    );
    await assert.rejects(
      insertReceipt(uidA, "maritime:daily:bad-hash", "pending", null, null, "not-a-hash"),
      error => error.code === "23514",
      "recipient hashes must be 64 lowercase hex characters",
    );
    await assert.rejects(
      insertReceipt("lm_33333333-3333-4333-8333-333333333333", "maritime:daily:orphan", "pending"),
      error => error.code === "23503",
      "CFO receipts bind to Manager identity, not global lm_users",
    );
    await insertReceipt(uidA, "maritime:daily:2026-10-22", "sent", "provider-message-3", "2026-10-21T23:00:00Z");
    const sentReceipt = (await client.query("SELECT status,recipient_hash,provider_message_id,sent_at FROM public.lm_cfo_result_receipts WHERE uid=$1 AND period_key=$2", [uidA, "maritime:daily:2026-10-22"])).rows[0];
    assert.equal(sentReceipt.status, "sent");
    assert.equal(sentReceipt.recipient_hash, receiptHash);
    assert.equal(sentReceipt.provider_message_id, "provider-message-3");
    assert.equal(sentReceipt.sent_at.toISOString(), "2026-10-21T23:00:00.000Z");
    await client.query(fs.readFileSync(IDENTITY_MIGRATION, "utf8"));
    assert.equal((await client.query("SELECT execution_id FROM public.lm_maritime_manager_executions WHERE uid=$1 AND occurrence_id=$2", [uidA, "week-1-occurrence"])).rows[0].execution_id, "exec-1", "reapplying the migration preserves the dispatch checkpoint");
    assert.equal((await client.query("SELECT revoked_at FROM public.lm_maritime_pilot_participants WHERE participant_id=$1", [acceptedParticipantId])).rows[0].revoked_at, null, "reapplying the migration preserves participant consent state");
    assert.equal((await client.query("SELECT event_id FROM public.lm_web_funnel_events WHERE event_id='work-1'")).rows[0].event_id, "work-1", "reapplying the migration preserves append-only events");
    assert.equal((await client.query("SELECT status FROM public.lm_cfo_result_receipts WHERE uid=$1 AND period_key=$2", [uidA, "maritime:daily:2026-10-22"])).rows[0].status, "sent", "reapplying the migration preserves CFO delivery receipts");
  } finally {
    if (racingClient) await racingClient.end();
    if (client) await client.end();
    if (started) execFileSync(bin + "/pg_ctl", ["-D", data, "-m", "fast", "-w", "stop"], { env, stdio: "pipe" });
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});
