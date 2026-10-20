"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { Client } = require("pg");

const app = path.resolve(__dirname, "../..");
const fixture = fs.mkdtempSync("/tmp/lm-pgrst-");
const data = path.join(fixture, "data");
const env = { PATH: process.env.PATH, LANG: "C", LC_ALL: "C", PGPASSFILE: path.join(fixture, "no-password-file") };
const bin = path.dirname(execFileSync("/usr/bin/which", ["initdb"], { env, encoding: "utf8" }).trim());
const clients = [];
let started = false;

async function connect(user) {
  const client = new Client({ host: fixture, port: 55441, database: "postgres", user, password: "", connectionTimeoutMillis: 5000 });
  clients.push(client);
  await client.connect();
  return client;
}

async function main() {
  try {
    execFileSync(path.join(bin, "initdb"), ["-D", data, "-A", "trust", "-U", "fixture_owner", "--no-locale", "-E", "UTF8"], { env, stdio: "pipe" });
    fs.appendFileSync(path.join(data, "postgresql.conf"), `\nlisten_addresses = ''\nunix_socket_directories = '${fixture}'\nport = 55441\n`);
    execFileSync(path.join(bin, "pg_ctl"), ["-D", data, "-l", path.join(fixture, "postgres.log"), "-w", "start"], { env, stdio: "pipe" });
    started = true;
    const admin = await connect("fixture_owner");
    await admin.query("CREATE ROLE authenticator LOGIN; CREATE ROLE service_role; CREATE ROLE anon; CREATE ROLE authenticated; ALTER ROLE authenticator SET statement_timeout='15s'; ALTER ROLE authenticator SET lock_timeout='8s'; ALTER ROLE anon SET statement_timeout='3s'; ALTER ROLE authenticated SET statement_timeout='8s';");
    const snapshot = async () => (await admin.query("SELECT rolname, rolconfig FROM pg_roles WHERE rolname IN ('authenticator','service_role','anon','authenticated') ORDER BY rolname")).rows;
    const baseline = await snapshot();
    const existing = await connect("authenticator");
    assert.equal((await existing.query("SHOW statement_timeout")).rows[0].statement_timeout, "15s");

    const forward = fs.readFileSync(process.argv[2] || path.join(app, "migrations/20261021070000_lm_postgrest_startup_budget.sql"), "utf8");
    await admin.query(forward);
    await admin.query(forward);
    const fresh = await connect("authenticator");
    assert.equal((await fresh.query("SHOW statement_timeout")).rows[0].statement_timeout, "1min");
    assert.equal((await existing.query("SHOW statement_timeout")).rows[0].statement_timeout, "15s");
    assert.equal((await fresh.query("SHOW lock_timeout")).rows[0].lock_timeout, "8s");
    const changed = await snapshot();
    assert.deepEqual(changed.filter(row => ["anon", "authenticated"].includes(row.rolname)), baseline.filter(row => ["anon", "authenticated"].includes(row.rolname)));
    assert.deepEqual(changed.find(row => row.rolname === "service_role").rolconfig, ["statement_timeout=15s"]);

    const rollback = fs.readFileSync(path.join(app, "scripts/postgrest-startup-budget-rollback.sql"), "utf8");
    await admin.query(rollback);
    await admin.query(rollback);
    assert.deepEqual(await snapshot(), baseline);
    const restored = await connect("authenticator");
    assert.equal((await restored.query("SHOW statement_timeout")).rows[0].statement_timeout, "15s");
    assert.equal((await fresh.query("SHOW statement_timeout")).rows[0].statement_timeout, "1min");
    process.stdout.write(JSON.stringify({ ok: true, checks: ["forward_replay", "new_connection_60s", "existing_connection_unchanged", "normal_role_settings_preserved", "lock_timeout_preserved", "service_role_15s_explicit", "rollback_replay_restores_original_catalog", "rollback_requires_new_connection"] }) + "\n");
  } finally {
    await Promise.allSettled(clients.map(client => client.end()));
    if (started) execFileSync(path.join(bin, "pg_ctl"), ["-D", data, "-m", "fast", "-w", "stop"], { env, stdio: "pipe" });
    fs.rmSync(fixture, { recursive: true, force: true });
  }
}

main().catch(error => { process.stderr.write(String(error.stack) + "\n"); process.exitCode = 1; });
