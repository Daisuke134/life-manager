"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { Client } = require("pg");
const test = require("node:test");
const { createMaritimeManagerStore } = require("../../lib/maritime-manager-store.js");
const { deliverCloudCfoEmail } = require("../../lib/cfo-cloud-delivery.js");
const { separateWebUidForSubject } = require("../../lib/web-auth.js");
const { CONSENT_VERSION, normalizeMaritimeSource } = require("../../lib/maritime-distribution.js");
const { normalizeWebFunnelEvent } = require("../../lib/web-funnel-events.js");
let createMaritimeManagerPersistence;
try { ({ createMaritimeManagerPersistence } = require("../../lib/maritime-manager-persistence.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }

const IDENTITY_MIGRATION = path.join(__dirname, "../../migrations/20261021090000_maritime_manager_runtime_state.sql");
const CONSENT_ANCHOR_MIGRATION = path.join(__dirname, "../../migrations/20261025174214_lm_maritime_manager_consent_anchor.sql");
const STOP_LOOKUP_MIGRATION = path.join(__dirname, "../../migrations/20261025221000_lm_maritime_manager_execution_stop_lookup.sql");
const MANAGER_TABLES = [
  "lm_maritime_manager_identities",
  "lm_maritime_manager_enrollments",
  "lm_maritime_manager_executions",
  "lm_maritime_pilot_participants",
  "lm_web_funnel_events",
  "lm_cfo_result_receipts",
];

test("consent resume migration adds its durable anchor", () => {
  const sql = fs.readFileSync(CONSENT_ANCHOR_MIGRATION, "utf8");
  assert.match(sql, /ALTER\s+TABLE\s+public\.lm_maritime_manager_enrollments[\s\S]*ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+consent_v2_at\s+timestamptz/i);
  assert.match(sql, /COMMENT\s+ON\s+COLUMN\s+public\.lm_maritime_manager_enrollments\.consent_v2_at/i);
});

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
    for (const role of ["anon", "authenticated", "service_role"]) {
      await client.query(`CREATE ROLE ${role} NOLOGIN`);
    }

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
    assert.equal(fs.existsSync(CONSENT_ANCHOR_MIGRATION), true, "consent resume anchor migration must exist");
    await client.query(fs.readFileSync(CONSENT_ANCHOR_MIGRATION, "utf8"));
    assert.equal(fs.existsSync(STOP_LOOKUP_MIGRATION), true, "bounded Stop readback index migration must exist");
    await client.query(fs.readFileSync(STOP_LOOKUP_MIGRATION, "utf8"));
    assert.equal((await client.query("SELECT to_regclass('public.lm_maritime_manager_execution_stop_lookup')::text")).rows[0].to_regclass,
      "lm_maritime_manager_execution_stop_lookup", "Stop readback index is present");
    assert.equal((await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_manager_enrollments' AND column_name='consent_v2_at'",
    )).rowCount, 1, "consent resume anchor column is present");

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

    const tableAcl = await client.query(
      `SELECT c.relname, c.relrowsecurity,
              has_table_privilege('service_role', c.oid, 'SELECT') AS service_select,
              has_table_privilege('service_role', c.oid, 'INSERT') AS service_insert,
              has_table_privilege('service_role', c.oid, 'UPDATE') AS service_update,
              has_table_privilege('service_role', c.oid, 'DELETE') AS service_delete,
              has_table_privilege('service_role', c.oid, 'TRUNCATE') AS service_truncate,
              has_table_privilege('service_role', c.oid, 'REFERENCES') AS service_references,
              has_table_privilege('service_role', c.oid, 'TRIGGER') AS service_trigger,
              has_table_privilege('anon', c.oid, 'SELECT') OR has_table_privilege('anon', c.oid, 'INSERT')
                OR has_table_privilege('anon', c.oid, 'UPDATE') OR has_table_privilege('anon', c.oid, 'DELETE')
                OR has_table_privilege('anon', c.oid, 'TRUNCATE') OR has_table_privilege('anon', c.oid, 'REFERENCES')
                OR has_table_privilege('anon', c.oid, 'TRIGGER') AS anon_any,
              has_table_privilege('authenticated', c.oid, 'SELECT') OR has_table_privilege('authenticated', c.oid, 'INSERT')
                OR has_table_privilege('authenticated', c.oid, 'UPDATE') OR has_table_privilege('authenticated', c.oid, 'DELETE')
                OR has_table_privilege('authenticated', c.oid, 'TRUNCATE') OR has_table_privilege('authenticated', c.oid, 'REFERENCES')
                OR has_table_privilege('authenticated', c.oid, 'TRIGGER') AS authenticated_any
         FROM pg_class AS c
        WHERE c.relnamespace = 'public'::regnamespace AND c.relname = ANY($1::text[])
        ORDER BY c.relname`,
      [MANAGER_TABLES],
    );
    assert.equal(tableAcl.rows.length, MANAGER_TABLES.length, "all Manager tables have ACL readback");
    for (const table of tableAcl.rows) {
      assert.equal(table.relrowsecurity, true, `${table.relname} enables RLS`);
      assert.equal(table.service_select, true, `${table.relname} grants service_role SELECT`);
      assert.equal(table.service_insert, true, `${table.relname} grants service_role INSERT`);
      assert.equal(table.service_update, table.relname !== "lm_web_funnel_events", `${table.relname} keeps only required UPDATE`);
      for (const privilege of ["service_delete", "service_truncate", "service_references", "service_trigger", "anon_any", "authenticated_any"]) {
        assert.equal(table[privilege], false, `${table.relname} denies ${privilege}`);
      }
    }

    const functionAcl = await client.query(
      `SELECT p.proname, p.oid::regprocedure::text AS signature,
              has_function_privilege('service_role', p.oid, 'EXECUTE') AS service_execute,
              has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_execute,
              has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_execute
         FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = ANY($1::text[])
        ORDER BY p.proname, signature`,
      [[
        "prevent_lm_maritime_manager_identity_reassignment_v1",
        "claim_lm_maritime_manager_provision_v1",
        "bind_lm_maritime_manager_agent_v1",
        "claim_lm_maritime_manager_cycle_v1",
        "bind_lm_maritime_manager_execution_v1",
        "claim_lm_maritime_participant_v1",
        "lm_web_funnel_events_guard",
      ]],
    );
    assert.equal(functionAcl.rows.length, 7, "all Manager RPC and trigger functions have ACL readback");
    const triggerFunctions = new Set([
      "prevent_lm_maritime_manager_identity_reassignment_v1",
      "lm_web_funnel_events_guard",
    ]);
    for (const fn of functionAcl.rows) {
      assert.equal(fn.anon_execute, false, `${fn.signature} denies anon EXECUTE`);
      assert.equal(fn.authenticated_execute, false, `${fn.signature} denies authenticated EXECUTE`);
      assert.equal(fn.service_execute, !triggerFunctions.has(fn.proname), `${fn.signature} grants only business RPCs to service_role`);
    }

    await client.query("BEGIN");
    await client.query("SET ROLE service_role");
    try {
      const serviceUid = "lm_77777777-7777-4777-8777-777777777777";
      const serviceSubject = "77777777-7777-4777-8777-777777777777";
      const serviceRelease = "c".repeat(40);
      await client.query(
        "INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)",
        [serviceUid, serviceSubject],
      );
      assert.equal((await client.query("SELECT count(*)::integer AS count FROM public.lm_maritime_manager_identities WHERE uid=$1", [serviceUid])).rows[0].count, 1,
        "service_role RLS policy allows reading its trusted Manager state");
      await client.query(
        "UPDATE public.lm_maritime_manager_identities SET first_touch=$1::jsonb,first_touch_at=clock_timestamp() WHERE uid=$2",
        [JSON.stringify({ utm_source: "service-role" }), serviceUid],
      );
      await client.query(
        `INSERT INTO public.lm_maritime_manager_enrollments(uid,auth_subject,email,source,consent_version,release_sha)
         VALUES ($1,$2,$3,'direct','maritime-manager-v1',$4)`,
        [serviceUid, serviceSubject, "service-role@example.invalid", serviceRelease],
      );
      assert.equal((await client.query("SELECT public.claim_lm_maritime_manager_provision_v1($1) AS claimed", [serviceUid])).rows[0].claimed, true,
        "service_role can execute the SECURITY INVOKER provisioning RPC through RLS");
      assert.equal((await client.query(
        "SELECT public.bind_lm_maritime_manager_agent_v1($1,$2,$3,$4) AS bound",
        [serviceUid, serviceSubject, "service-role-agent", serviceRelease],
      )).rows[0].bound, true, "service_role can execute the SECURITY INVOKER bind RPC through RLS");
      assert.equal((await client.query(
        "SELECT public.claim_lm_maritime_manager_cycle_v1($1,$2,$3,$4,$5::date) AS claimed",
        [serviceUid, "service-role-occurrence", "service-role-agent", serviceRelease, "2026-10-21"],
      )).rows[0].claimed, true, "service_role can execute the SECURITY INVOKER cycle claim through RLS");
      assert.equal((await client.query(
        "SELECT public.bind_lm_maritime_manager_execution_v1($1,$2,$3,$4,$5::date,$6) AS bound",
        [serviceUid, "service-role-occurrence", "service-role-agent", serviceRelease, "2026-10-21", "service-role-execution"],
      )).rows[0].bound, true, "service_role can execute the SECURITY INVOKER execution bind through RLS");
      assert.equal((await client.query(
        "SELECT public.claim_lm_maritime_participant_v1($1,'direct','maritime-retention-v1',10,$2::timestamptz) AS status",
        ["5".repeat(64), "2026-10-21T02:00:00Z"],
      )).rows[0].status, "consented", "service_role can execute the SECURITY INVOKER participant RPC through RLS");
      await client.query(
        `INSERT INTO public.lm_web_funnel_events(event_id,event_name,audience_kind,uid,source_object_id,source_event_id,attribution)
         VALUES ('service-role-event','maritime_work_completed','external',$1,$2,'service-role-source-event','{}'::jsonb)`,
        [serviceUid, "5".repeat(64)],
      );
      await client.query(
        `INSERT INTO public.lm_cfo_result_receipts(uid,period_key,channel,recipient_hash,status,message,observed_at)
         VALUES ($1,'2026-10-21','email',$2,'pending','verified report','2026-10-21T02:00:00Z')`,
        [serviceUid, "6".repeat(64)],
      );
      assert.equal((await client.query(
        "UPDATE public.lm_cfo_result_receipts SET status='sent',provider_message_id='service-role-mail',sent_at='2026-10-21T02:01:00Z' WHERE uid=$1 AND period_key='2026-10-21' RETURNING status",
        [serviceUid],
      )).rows[0].status, "sent", "service_role can update its trusted CFO receipt through RLS");
    } finally {
      await client.query("ROLLBACK");
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
    const uidD = "lm_44444444-4444-4444-8444-444444444444";
    const subjectA = "11111111-1111-4111-8111-111111111111";
    const subjectB = "22222222-2222-4222-8222-222222222222";
    const subjectC = "33333333-3333-4333-8333-333333333333";
    const uidC = separateWebUidForSubject(subjectC);
    const subjectD = "44444444-4444-4444-8444-444444444444";
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
    assert.equal(typeof createMaritimeManagerPersistence, "function", "Runtime PG identity persistence must exist");
    const managerPersistence = createMaritimeManagerPersistence({ pgPool: client,
      env: { LM_UID_SECRET: "fixture-secret", LM_MARITIME_INTERNAL_UIDS: uidC },
      now: () => "2026-10-21T00:00:00.000Z", nowMs: () => Date.parse("2026-10-21T00:00:00.000Z") });
    assert.equal(await managerPersistence.ensureWebUserImpl(subjectC), uidC);
    assert.equal(await managerPersistence.ensureWebUserImpl(subjectC), uidC, "verified subject resolution is idempotent");
    assert.equal(typeof managerPersistence.storeFirstTouch, "function", "Manager first-touch persistence must exist");
    assert.equal(typeof managerPersistence.readFirstTouch, "function", "Manager first-touch readback must exist");
    const initialTouch = { utm_source: "x", utm_medium: "social", email: "private@example.invalid", token: "private-token" };
    assert.equal(await managerPersistence.storeFirstTouch(uidC, initialTouch), true);
    assert.deepEqual(await managerPersistence.readFirstTouch(uidC), { utm_source: "x", utm_medium: "social" });
    assert.equal(await managerPersistence.storeFirstTouch(uidC, { utm_source: "instagram", utm_campaign: "later" }), true);
    assert.deepEqual(await managerPersistence.readFirstTouch(uidC), { utm_source: "x", utm_medium: "social" }, "later touch cannot overwrite the first attribution");
    assert.equal((await client.query("SELECT first_touch_at IS NOT NULL AS stored FROM public.lm_maritime_manager_identities WHERE uid=$1", [uidC])).rows[0].stored, true);
    assert.equal(typeof managerPersistence.recordManagerEvent, "function", "Manager distribution event writer must exist");
    assert.equal(typeof managerPersistence.recordAnonymousEvent, "function", "anonymous distribution event writer must exist");
    const managerEvent = { eventKey: "job:first", source: "x", attribution: { utm_source: "x", email: "private@example.invalid", token: "private-token" } };
    assert.equal(await managerPersistence.recordManagerEvent("maritime_work_completed", uidC, managerEvent), true);
    assert.equal(await managerPersistence.recordManagerEvent("maritime_work_completed", uidC, managerEvent), true, "stable event replay is idempotent");
    assert.equal(await managerPersistence.recordManagerEvent("maritime_work_completed", uidC, { ...managerEvent, eventKey: "job:second" }), true);
    assert.equal(typeof managerPersistence.readFirstCompletedWorkAt, "function", "Manager return reads first completed work from Runtime PG");
    assert.equal(await managerPersistence.recordManagerEvent("maritime_work_completed", uidB, {
      eventKey: "external-first", source: "x", occurredAt: "2026-10-20T09:00:00Z",
    }), true);
    assert.equal(await managerPersistence.recordManagerEvent("maritime_work_completed", uidB, {
      eventKey: "external-second", source: "x", occurredAt: "2026-10-20T12:00:00Z",
    }), true);
    assert.equal(await managerPersistence.readFirstCompletedWorkAt(uidB), "2026-10-20T09:00:00.000Z");
    assert.equal(await managerPersistence.readFirstCompletedWorkAt(uidC), null, "internal cohort work is excluded from return eligibility");
    assert.equal(await managerPersistence.recordAnonymousEvent("maritime_landing_view", "x"), true);
    const participantId = managerPersistence.participantId(uidC);
    const managerEvents = await client.query("SELECT source_event_id,audience_kind,uid,attribution FROM public.lm_web_funnel_events WHERE source_object_id=$1 ORDER BY source_event_id", [participantId]);
    assert.equal(managerEvents.rows.length, 2, "same event key dedups, a second completed job remains countable");
    assert.ok(managerEvents.rows.every(row => row.audience_kind === "internal" && row.uid === null));
    assert.ok(managerEvents.rows.every(row => row.attribution.utm_source === "x" && !JSON.stringify(row.attribution).includes("private")));
    const anonymousEvent = (await client.query("SELECT uid,source_object_id,source_event_id FROM public.lm_web_funnel_events WHERE event_name='maritime_landing_view' ORDER BY occurred_at DESC LIMIT 1")).rows[0];
    assert.equal(anonymousEvent.uid, null);
    assert.equal(anonymousEvent.source_object_id, null);
    assert.equal(anonymousEvent.source_event_id, null);
    const conflictSubject = "55555555-5555-4555-8555-555555555555";
    const conflictUid = "lm_66666666-6666-4666-8666-666666666666";
    await client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [conflictUid, conflictSubject]);
    await assert.rejects(managerPersistence.ensureWebUserImpl(conflictSubject), /identity_mismatch/);
    assert.equal((await client.query("SELECT uid FROM public.lm_maritime_manager_identities WHERE auth_subject=$1", [conflictSubject])).rows[0].uid, conflictUid,
      "identity conflict cannot overwrite the existing UID");
    await client.query("INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2)", [uidD, subjectD]);

    const enrollmentColumns = await client.query(
      "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_maritime_manager_enrollments'",
    );
    const enrollmentNames = new Set(enrollmentColumns.rows.map(row => row.column_name));
    for (const column of ["uid", "auth_subject", "email", "timezone", "status", "source", "consent_version", "consent_v2_at", "agent_id", "release_sha", "paused_at"]) {
      assert.ok(enrollmentNames.has(column), `enrollment schema includes ${column}`);
    }
    await client.query(`INSERT INTO public.lm_maritime_manager_enrollments(uid,auth_subject,email,status,source,consent_version,release_sha)
      VALUES ($1,$2,'a@example.invalid','pending','direct','maritime-manager-v1',$3),
             ($4,$5,'b@example.invalid','pending','direct','maritime-manager-v1',$3)`, [uidA, subjectA, releaseSha, uidB, subjectB]);
    const storeQueries = [];
    const managerStore = createMaritimeManagerStore({ pgPool: { query: (statement, values = []) => {
      storeQueries.push({ statement, values });
      return client.query(statement, values);
    } } });
    const storedEnrollment = await managerStore.read(uidA);
    assert.equal(storedEnrollment.uid, uidA);
    assert.equal(storedEnrollment.status, "pending");
    assert.equal(storedEnrollment.paused_at, null);
    assert.match(storedEnrollment.created_at, /^\d{4}-\d{2}-\d{2}T.*Z$/);
    assert.equal(storeQueries[0].values[0], uidA, "UID is passed as a parameter");
    assert.match(storeQueries[0].statement, /WHERE uid = \$1/);
    const pendingEnrollments = await managerStore.listPending(5);
    assert.deepEqual(pendingEnrollments.map(row => row.uid), [uidA, uidB]);
    assert.deepEqual(storeQueries[1].values, ["pending", 5]);
    assert.ok(pendingEnrollments.every(row => /^\d{4}-\d{2}-\d{2}T.*Z$/.test(row.created_at)));
    assert.deepEqual(await managerStore.listPaused(5), []);
    const enrollmentInput = { uid: uidC, authSubject: subjectC, email: "c@example.invalid", timezone: "Pacific/Honolulu",
      source: "instagram", consentVersion: "maritime-manager-v1", releaseSha };
    const enrolled = await managerStore.enroll(enrollmentInput);
    assert.equal(enrolled.uid, uidC);
    assert.equal(enrolled.auth_subject, subjectC);
    assert.equal(enrolled.email, "c@example.invalid");
    assert.equal(enrolled.timezone, "Pacific/Honolulu");
    assert.equal(enrolled.source, "instagram");
    assert.equal(enrolled.status, "pending");
    assert.deepEqual(await managerStore.enroll(enrollmentInput), enrolled, "same verified enrollment is idempotent");
    await assert.rejects(managerStore.enroll({ ...enrollmentInput, email: "changed@example.invalid" }), /identity_mismatch/);
    await assert.rejects(managerStore.enroll({ ...enrollmentInput, authSubject: subjectA }), /identity_mismatch/);
    assert.equal((await managerStore.read(uidC)).email, "c@example.invalid", "conflicting input cannot overwrite the existing owner/contact");
    await managerStore.enroll({ uid: uidD, authSubject: subjectD, email: "d@example.invalid", timezone: "UTC",
      source: "direct", consentVersion: "maritime-manager-v1", releaseSha });
    const quarantined = await managerStore.quarantinePendingProvision(uidD);
    assert.equal(quarantined.status, "effect_unknown");
    assert.equal(quarantined.agent_id, null);
    assert.equal(await managerStore.quarantinePendingProvision(uidD), null, "quarantine cannot re-write a non-pending row");
    assert.equal((await managerStore.read(uidD)).status, "effect_unknown");
    assert.equal(await managerStore.claimProvision(uidC), true);
    assert.equal(await managerStore.claimProvision(uidC), false, "provision claim is one-shot");
    const boundEnrollment = await managerStore.bindAgent({ uid: uidC, authSubject: subjectC, agentId: "agent-c", releaseSha });
    assert.equal(boundEnrollment.status, "active");
    assert.equal(boundEnrollment.release_sha, releaseSha);
    assert.equal(await managerStore.quarantinePendingProvision(uidC), null, "an active enrollment cannot be quarantined as pending");
    await assert.rejects(managerStore.bindAgent({ uid: uidC, authSubject: subjectC, agentId: "agent-c", releaseSha: "b".repeat(40) }), /binding_rejected/);
    assert.equal((await managerStore.read(uidC)).release_sha, releaseSha, "release mismatch cannot overwrite the enrollment release");
    const storeCycle = { uid: uidC, agentId: "agent-c", occurrenceId: "store-cycle", dateKey: "2026-10-21", releaseSha };
    const storeCycleClaim = await managerStore.claimCycleDispatch(storeCycle);
    assert.equal(storeCycleClaim.claimed, true);
    assert.equal(storeCycleClaim.row.date_key, "2026-10-21", "PostgreSQL date is normalized to YYYY-MM-DD");
    const storeCycleReplay = await managerStore.claimCycleDispatch(storeCycle);
    assert.equal(storeCycleReplay.claimed, false);
    assert.equal(storeCycleReplay.row.date_key, "2026-10-21");
    assert.equal((await managerStore.bindCycleExecution({ ...storeCycle, executionId: "store-exec-1" })).execution_id, "store-exec-1");
    await assert.rejects(managerStore.bindCycleExecution({ ...storeCycle, executionId: "store-exec-2" }), /binding_rejected/);
    await assert.rejects(managerStore.claimCycleDispatch({ ...storeCycle, dateKey: "2026-10-22" }), /binding_rejected/);
    const claim = uid => client.query('SELECT public.claim_lm_maritime_manager_provision_v1($1) AS claimed', [uid]).then(result => result.rows[0].claimed);
    const bind = (uid, subject, agent, sha = releaseSha) => client.query(
      'SELECT public.bind_lm_maritime_manager_agent_v1($1,$2,$3,$4) AS bound', [uid, subject, agent, sha],
    ).then(result => result.rows[0].bound);
    assert.equal(await claim(uidA), true);
    assert.equal(await claim(uidA), false);
    assert.equal(await bind(uidA, subjectA, 'agent-a', 'b'.repeat(40)), false, 'agent binding cannot change the release pinned by enrollment');
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
    const receiptsBeforePause = (await client.query("SELECT count(*)::integer AS count FROM public.lm_cfo_result_receipts WHERE uid=$1", [uidA])).rows[0].count;
    const pausedEnrollment = await managerStore.pause(uidA);
    assert.equal(pausedEnrollment.status, "paused");
    assert.match(pausedEnrollment.paused_at, /^\d{4}-\d{2}-\d{2}T.*Z$/);
    assert.equal(await managerStore.claimProvision(uidA), false, "pause blocks a future provision claim");
    assert.equal((await managerStore.pause(uidA)).paused_at, pausedEnrollment.paused_at, "pause replay keeps its original timestamp");
    assert.equal((await client.query("SELECT count(*)::integer AS count FROM public.lm_cfo_result_receipts WHERE uid=$1", [uidA])).rows[0].count, receiptsBeforePause,
      "pause retains existing CFO receipts");
    const pausedEnrollments = await managerStore.listPaused(5);
    assert.equal(pausedEnrollments[0].uid, uidA);
    assert.match(pausedEnrollments[0].paused_at, /^\d{4}-\d{2}-\d{2}T.*Z$/);
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
    assert.equal(typeof managerPersistence.getParticipant, "function", "Manager participant read must exist");
    assert.equal(typeof managerPersistence.accept, "function", "Manager participant consent must exist");
    const managerConsent = await managerPersistence.accept(uidC, "instagram");
    assert.equal(managerConsent.ok, true);
    assert.equal(managerConsent.status, "consented");
    const managerParticipantId = managerPersistence.participantId(uidC);
    assert.equal(managerPersistence.participantId(uidC), managerParticipantId);
    const rawManagerParticipant = (await client.query("SELECT participant_id,source,consent_version,consented_at,revoked_at,first_response_at,returned_at FROM public.lm_maritime_pilot_participants WHERE participant_id=$1", [managerParticipantId])).rows[0];
    assert.equal(rawManagerParticipant.participant_id, managerParticipantId);
    assert.equal(rawManagerParticipant.source, "instagram");
    assert.equal(rawManagerParticipant.consent_version, "maritime-retention-v1");
    assert.equal(rawManagerParticipant.consent_version, CONSENT_VERSION);
    assert.equal(rawManagerParticipant.source, normalizeMaritimeSource(rawManagerParticipant.source));
    assert.ok(rawManagerParticipant.consented_at instanceof Date);
    assert.equal(rawManagerParticipant.revoked_at, null);
    assert.equal(rawManagerParticipant.first_response_at, null);
    assert.equal(rawManagerParticipant.returned_at, null);
    const managerParticipant = await managerPersistence.getParticipant(uidC);
    assert.equal(managerParticipant.ok, true);
    assert.equal(managerParticipant.participant.participant_id, managerParticipantId);
    assert.equal(managerParticipant.participant.consent_version, "maritime-retention-v1");
    assert.equal(managerParticipant.participant.source, "instagram");
    assert.match(managerParticipant.participant.consented_at, /^\d{4}-\d{2}-\d{2}T.*Z$/);
    assert.equal(await managerPersistence.accept(uidC, "x").then(result => result.status), "already_consented");
    assert.equal((await managerPersistence.getParticipant(uidC)).participant.source, "instagram", "repeat consent cannot rewrite first source");
    assert.equal((await client.query("SELECT count(*)::integer AS count FROM public.lm_maritime_pilot_participants WHERE participant_id=$1", [managerParticipantId])).rows[0].count, 1);
    assert.equal((await client.query("SELECT count(*)::integer AS count FROM public.lm_web_funnel_events WHERE event_name='maritime_consent' AND source_object_id=$1", [managerParticipantId])).rows[0].count, 1,
      "repeat consent deduplicates its stable funnel event");
    assert.equal(await managerPersistence.isConsentActive(uidC), true);
    assert.equal(await managerPersistence.revoke(uidC), true);
    assert.equal(await managerPersistence.isConsentActive(uidC), false);
    const revokedParticipant = await managerPersistence.getParticipant(uidC);
    assert.match(revokedParticipant.participant.revoked_at, /^\d{4}-\d{2}-\d{2}T.*Z$/);
    assert.equal(await managerPersistence.revoke(uidC), false, "revocation is one-shot");
    assert.equal((await client.query("SELECT count(*)::integer AS count FROM public.lm_web_funnel_events WHERE event_name='maritime_consent_revoked' AND source_object_id=$1", [managerParticipantId])).rows[0].count, 1);

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
      insertReceipt("lm_55555555-5555-4555-8555-555555555555", "maritime:daily:orphan", "pending"),
      error => error.code === "23503",
      "CFO receipts bind to Manager identity, not global lm_users",
    );
    await insertReceipt(uidA, "maritime:daily:2026-10-22", "sent", "provider-message-3", "2026-10-21T23:00:00Z");
    const sentReceipt = (await client.query("SELECT status,recipient_hash,provider_message_id,sent_at FROM public.lm_cfo_result_receipts WHERE uid=$1 AND period_key=$2", [uidA, "maritime:daily:2026-10-22"])).rows[0];
    assert.equal(sentReceipt.status, "sent");
    assert.equal(sentReceipt.recipient_hash, receiptHash);
    assert.equal(sentReceipt.provider_message_id, "provider-message-3");
    assert.equal(sentReceipt.sent_at.toISOString(), "2026-10-21T23:00:00.000Z");

    const maritimePersistence = createMaritimeManagerPersistence({ pgPool: client, env: {} });
    const racingPersistence = createMaritimeManagerPersistence({ pgPool: racingClient, env: {} });
    const pendingPeriodKey = "maritime:daily:2026-10-24";
    const pendingIdentity = { uid: uidA, periodKey: pendingPeriodKey };
    const pendingPayload = {
      uid: uidA,
      period_key: pendingPeriodKey,
      channel: "email",
      recipient_hash: "d".repeat(64),
      status: "pending",
      message: "frozen pending report",
      observed_at: "2026-10-21T23:30:00Z",
    };
    const cfoClaims = await Promise.all([
      maritimePersistence.cfoReceiptIO.claim(pendingIdentity, pendingPayload),
      racingPersistence.cfoReceiptIO.claim(pendingIdentity, pendingPayload),
    ]);
    assert.deepEqual(cfoClaims.sort(), [false, true], "concurrent receipt claims for one period have one winner");
    const pendingReceipt = await maritimePersistence.cfoReceiptIO.read(pendingIdentity);
    assert.equal(pendingReceipt.status, "pending");
    assert.equal(pendingReceipt.recipient_hash, "d".repeat(64));

    const periodKey = "maritime:daily:2026-10-23";
    const emailInput = {
      uid: uidA,
      periodKey,
      recipient: "manager@example.test",
      message: "frozen daily report",
      observedAt: "2026-10-21T23:30:00Z",
    };
    let emailSends = 0;
    const cfoDeps = {
      cfoReceiptIO: maritimePersistence.cfoReceiptIO,
      sendEmail: async ({ to, text, idempotencyKey }) => {
        emailSends += 1;
        assert.equal(to, "manager@example.test");
        assert.equal(text, "frozen daily report");
        assert.equal(idempotencyKey, `cfo:${uidA}:email:${periodKey}`);
        return { sent: true, id: "runtime-pg-message-id" };
      },
    };
    assert.equal((await deliverCloudCfoEmail(emailInput, cfoDeps)).status, "sent");
    assert.equal((await deliverCloudCfoEmail(emailInput, cfoDeps)).status, "duplicate");
    assert.equal(emailSends, 1, "a persisted PostgreSQL receipt prevents a second provider send");
    const cfoReceipt = await maritimePersistence.cfoReceiptIO.read({ uid: uidA, periodKey });
    assert.equal(cfoReceipt.status, "sent");
    assert.equal(cfoReceipt.message, "frozen daily report");
    assert.match(cfoReceipt.recipient_hash, /^[a-f0-9]{64}$/);
    assert.equal(Object.hasOwn(cfoReceipt, "recipient"), false, "PostgreSQL receipt does not retain the email address");
    assert.equal(cfoReceipt.provider_message_id, "runtime-pg-message-id");
    assert.equal(cfoReceipt.observed_at, "2026-10-21T23:30:00.000Z");
    assert.equal(cfoReceipt.sent_at, "2026-10-21T23:30:00.000Z");

    await client.query(fs.readFileSync(IDENTITY_MIGRATION, "utf8"));
    await client.query(fs.readFileSync(CONSENT_ANCHOR_MIGRATION, "utf8"));
    await client.query(fs.readFileSync(CONSENT_ANCHOR_MIGRATION, "utf8"));
    await client.query(fs.readFileSync(STOP_LOOKUP_MIGRATION, "utf8"));
    assert.equal((await client.query("SELECT execution_id FROM public.lm_maritime_manager_executions WHERE uid=$1 AND occurrence_id=$2", [uidA, "week-1-occurrence"])).rows[0].execution_id, "exec-1", "reapplying the migration preserves the dispatch checkpoint");
    assert.equal((await client.query("SELECT revoked_at FROM public.lm_maritime_pilot_participants WHERE participant_id=$1", [acceptedParticipantId])).rows[0].revoked_at, null, "reapplying the migration preserves participant consent state");
    assert.equal((await client.query("SELECT event_id FROM public.lm_web_funnel_events WHERE event_id='work-1'")).rows[0].event_id, "work-1", "reapplying the migration preserves append-only events");
    assert.equal((await client.query("SELECT status FROM public.lm_cfo_result_receipts WHERE uid=$1 AND period_key=$2", [uidA, "maritime:daily:2026-10-22"])).rows[0].status, "sent", "reapplying the migration preserves CFO delivery receipts");
    assert.equal((await client.query("SELECT consent_v2_at FROM public.lm_maritime_manager_enrollments WHERE uid=$1", [uidA])).rows[0].consent_v2_at,
      null, "reapplying the migration does not invent an acceptance timestamp for existing tenants");
  } finally {
    if (racingClient) await racingClient.end();
    if (client) await client.end();
    if (started) execFileSync(bin + "/pg_ctl", ["-D", data, "-m", "fast", "-w", "stop"], { env, stdio: "pipe" });
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});
