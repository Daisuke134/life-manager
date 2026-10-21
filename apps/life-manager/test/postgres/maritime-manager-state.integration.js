"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { Client } = require("pg");
const test = require("node:test");

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
    assert.equal((await client.query("SELECT to_regclass('public.lm_users') AS relation")).rows[0].relation, null,
      "Manager runtime state does not require or create the global lm_users table");
    for (const table of MANAGER_TABLES.filter(name => !["lm_maritime_manager_identities", "lm_maritime_manager_enrollments"].includes(name))) {
      assert.equal(relations[table], null, `${table} stays out of the identity migration`);
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
  } finally {
    if (client) await client.end();
    if (started) execFileSync(bin + "/pg_ctl", ["-D", data, "-m", "fast", "-w", "stop"], { env, stdio: "pipe" });
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});
