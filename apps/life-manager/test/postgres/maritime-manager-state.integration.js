"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { Client } = require("pg");
const test = require("node:test");

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
  } finally {
    if (client) await client.end();
    if (started) execFileSync(bin + "/pg_ctl", ["-D", data, "-m", "fast", "-w", "stop"], { env, stdio: "pipe" });
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});
