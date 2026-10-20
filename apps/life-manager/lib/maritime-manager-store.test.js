"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
let createMaritimeManagerStore;
try { ({ createMaritimeManagerStore } = require("./maritime-manager-store.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
const SUBJECT_A = "11111111-1111-4111-8111-111111111111";
const SUBJECT_B = "22222222-2222-4222-8222-222222222222";
const UID_A = `lm_${SUBJECT_A}`;
const UID_B = `lm_${SUBJECT_B}`;
const SHA = "a".repeat(40);
function input(uid = UID_A, subject = SUBJECT_A) {
  return { uid, authSubject: subject, email: "person@example.invalid", timezone: "Asia/Tokyo",
    source: "referral", consentVersion: "maritime-retention-v1", releaseSha: SHA };
}
function fixture() {
  assert.equal(typeof createMaritimeManagerStore, "function", "enrollment store must exist");
  const rows = new Map(); const executions = new Map(); const requests = [];
  const fetchImpl = async (url, opts = {}) => {
    const u = new URL(url); const body = JSON.parse(opts.body || "null");
    requests.push({ url: u, method: opts.method || "GET", body });
    const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
    if (u.pathname.endsWith("/rpc/claim_lm_maritime_manager_cycle_v1")) {
      const enrollment = rows.get(body.p_uid);
      const key = body.p_uid + ':' + body.p_occurrence_id;
      if (!enrollment || enrollment.status !== 'active' || enrollment.paused_at
        || enrollment.agent_id !== body.p_agent_id || enrollment.release_sha !== body.p_release_sha
        || executions.has(key)) return response(false);
      executions.set(key, { uid: body.p_uid, occurrence_id: body.p_occurrence_id,
        agent_id: body.p_agent_id, date_key: body.p_date_key, release_sha: body.p_release_sha, execution_id: null });
      return response(true);
    }
    if (u.pathname.endsWith("/rpc/bind_lm_maritime_manager_execution_v1")) {
      const row = executions.get(body.p_uid + ':' + body.p_occurrence_id);
      if (!row || row.agent_id !== body.p_agent_id || row.date_key !== body.p_date_key
        || row.release_sha !== body.p_release_sha || (row.execution_id && row.execution_id !== body.p_execution_id)) return response(false);
      row.execution_id = body.p_execution_id;
      return response(true);
    }
    if (u.pathname.endsWith('/lm_maritime_manager_executions')) {
      const row = executions.get(u.searchParams.get('uid').slice(3) + ':' + u.searchParams.get('occurrence_id').slice(3));
      return response(row ? [row] : []);
    }
    if (u.pathname.endsWith("/rpc/claim_lm_maritime_manager_provision_v1")) {
      const row = rows.get(body.p_uid);
      const claim = !!row && row.status === "pending" && !row.paused_at;
      if (claim) row.status = "provisioning";
      return response(claim);
    }
    if (u.pathname.endsWith("/rpc/bind_lm_maritime_manager_agent_v1")) {
      const row = rows.get(body.p_uid);
      if (!row || row.auth_subject !== body.p_auth_subject
        || (row.agent_id && row.agent_id !== body.p_agent_id)
        || [...rows.values()].some(r => r.uid !== body.p_uid && r.agent_id === body.p_agent_id)) return response(false);
      row.agent_id = body.p_agent_id; row.release_sha = body.p_release_sha;
      row.status = row.paused_at ? "paused" : "active";
      return response(true);
    }
    if (opts.method === "POST") {
      if (rows.has(body.uid)) return response([]);
      if ([...rows.values()].some(r => r.auth_subject === body.auth_subject)) return response({}, 409);
      const row = { ...body, auth_subject: body.auth_subject.toLowerCase(), status: "pending", agent_id: null, paused_at: null };
      rows.set(body.uid, row); return response([row]);
    }
    const uid = u.searchParams.get("uid")?.replace(/^eq\./, ""); const row = rows.get(uid);
    if (opts.method === "PATCH" && row) Object.assign(row, body);
    return response(row ? [row] : []);
  };
  return { rows, requests, store: createMaritimeManagerStore({ supaUrl: "https://database.invalid",
    supaKey: "fixture-private-key", fetchImpl, now: () => "2026-10-20T00:00:00.000Z" }) };
}

test("enrollment_is_idempotent_and_tenant_scoped", async () => {
  const { store, rows } = fixture();
  const a = await store.enroll(input()); const again = await store.enroll(input());
  assert.equal(rows.size, 1); assert.equal(a.uid, UID_A); assert.deepEqual(again, a);
  await assert.rejects(store.enroll(input(UID_A, SUBJECT_B)), /identity_mismatch/);
  assert.equal(rows.get(UID_A).auth_subject, SUBJECT_A);
});
test("only_one_concurrent_provision_claim_succeeds", async () => {
  const { store } = fixture(); await store.enroll(input());
  const claims = await Promise.all([store.claimProvision(UID_A), store.claimProvision(UID_A)]);
  assert.deepEqual(claims, [true, false]);
});
test("a_foreign_subject_or_agent_binding_is_rejected", async () => {
  const { store } = fixture(); await store.enroll(input()); await store.enroll(input(UID_B, SUBJECT_B));
  await store.claimProvision(UID_A); await store.claimProvision(UID_B);
  await store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "agent-a", releaseSha: SHA });
  await assert.rejects(store.bindAgent({ uid: UID_B, authSubject: SUBJECT_A, agentId: "agent-b", releaseSha: SHA }), /binding_rejected/);
  await assert.rejects(store.bindAgent({ uid: UID_B, authSubject: SUBJECT_B, agentId: "agent-a", releaseSha: SHA }), /binding_rejected/);
  assert.equal((await store.read(UID_B)).agent_id, null);
});
test("pause_before_provision_blocks_claim_and_late_binding_never_reactivates", async () => {
  const { store } = fixture(); await store.enroll(input()); await store.pause(UID_A);
  assert.equal(await store.claimProvision(UID_A), false);
  await store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "late-agent", releaseSha: SHA });
  const row = await store.read(UID_A); assert.equal(row.status, "paused"); assert.equal(row.agent_id, "late-agent");
});
test("invalid_identity_and_unconfigured_storage_do_not_dispatch", async () => {
  const { store, requests } = fixture();
  await assert.rejects(store.enroll({ ...input(), uid: "other&uid=eq.victim" }), /input_invalid/);
  await assert.rejects(store.enroll({ ...input(), timezone: "Invalid/Zone" }), /input_invalid/);
  assert.equal(requests.length, 0);
  await assert.rejects(createMaritimeManagerStore({ env: {} }).read(UID_A), /unconfigured/);
});

test("uppercase_auth_subject_matches_postgres_uuid_canonical_form", async () => {
  const { store } = fixture();
  const subject = "aabbccdd-1111-4111-8111-111111111111";
  const uid = `lm_${subject}`;
  const row = await store.enroll({ ...input(uid, subject.toUpperCase()) });
  assert.equal(row.auth_subject, subject);
  await store.claimProvision(uid);
  const bound = await store.bindAgent({ uid, authSubject: subject.toUpperCase(), agentId: "agent-upper", releaseSha: SHA });
  assert.equal(bound.agent_id, "agent-upper");
});

function cycleIdentity() {
  return { uid: UID_A, agentId: 'agent-a', occurrenceId: 'cycle-1', dateKey: '2026-10-20', releaseSha: SHA };
}
async function activeFixture() {
  const f = fixture();
  await f.store.enroll(input());
  await f.store.claimProvision(UID_A);
  await f.store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: 'agent-a', releaseSha: SHA });
  return f;
}

test('cycle replay preserves its dispatch marker and immutable execution id', async () => {
  const { store } = await activeFixture();
  const identity = cycleIdentity();
  const initial = await store.claimCycleDispatch(identity);
  assert.equal(initial.claimed, true);
  assert.equal(initial.row.execution_id, null);
  const replay = await store.claimCycleDispatch(identity);
  assert.equal(replay.claimed, false);
  assert.equal(replay.row.execution_id, null);
  await store.bindCycleExecution({ ...identity, executionId: 'exec-1' });
  const resume = await store.claimCycleDispatch(identity);
  assert.equal(resume.claimed, false);
  assert.equal(resume.row.execution_id, 'exec-1');
  await assert.rejects(store.bindCycleExecution({ ...identity, executionId: 'exec-2' }), /binding_rejected/);
  assert.equal((await store.readCycleDispatch(identity)).execution_id, 'exec-1');
});

test('an occurrence cannot be rebound to another date agent or release', async () => {
  const { store } = await activeFixture();
  await store.claimCycleDispatch(cycleIdentity());
  for (const patch of [{ dateKey: '2026-10-21' }, { agentId: 'other-agent' }, { releaseSha: 'b'.repeat(40) }]) {
    await assert.rejects(store.claimCycleDispatch({ ...cycleIdentity(), ...patch }), /binding_rejected/);
  }
});

test('paused enrollment cannot claim a new cloud dispatch', async () => {
  const { store } = await activeFixture();
  await store.pause(UID_A);
  assert.deepEqual(await store.claimCycleDispatch(cycleIdentity()), { claimed: false, row: null });
});

test('invalid cycle input is rejected before any provider database request', async () => {
  const { store, requests } = fixture();
  for (const patch of [{ dateKey: '2026-02-30' }, { occurrenceId: '../other' }, { releaseSha: 'invalid' }]) {
    await assert.rejects(store.claimCycleDispatch({ ...cycleIdentity(), ...patch }), /input_invalid/);
  }
  await assert.rejects(store.bindCycleExecution({ ...cycleIdentity(), executionId: 'exec&other' }), /input_invalid/);
  assert.equal(requests.length, 0);
});

test('malformed claim response and foreign readback never authorize dispatch', async () => {
  const malformed = createMaritimeManagerStore({ supaUrl: 'https://database.invalid', supaKey: 'fixture',
    fetchImpl: async () => new Response(JSON.stringify({ claimed: true })) });
  await assert.rejects(malformed.claimCycleDispatch(cycleIdentity()), /store_invalid/);
  const foreign = createMaritimeManagerStore({ supaUrl: 'https://database.invalid', supaKey: 'fixture',
    fetchImpl: async () => new Response(JSON.stringify([{ uid: UID_B, occurrence_id: 'cycle-1',
      agent_id: 'agent-a', date_key: '2026-10-20', release_sha: SHA, execution_id: null }])) });
  await assert.rejects(foreign.readCycleDispatch(cycleIdentity()), /binding_rejected/);
});


test('RPC and readback stay bound to the original identity during caller mutation', async () => {
  for (const operation of ['claimCycleDispatch', 'bindCycleExecution']) {
    const mutable = { ...cycleIdentity(), executionId: 'exec-1' };
    const rows = [
      { uid: UID_A, occurrence_id: 'cycle-1', agent_id: 'agent-a', date_key: '2026-10-20', release_sha: SHA, execution_id: 'exec-1' },
      { uid: UID_B, occurrence_id: 'cycle-1', agent_id: 'agent-b', date_key: '2026-10-20', release_sha: SHA, execution_id: 'exec-1' },
    ];
    const store = createMaritimeManagerStore({ supaUrl: 'https://database.invalid', supaKey: 'fixture',
      fetchImpl: async (url, options) => {
        if (options.method === 'POST') {
          Object.assign(mutable, { uid: UID_B, agentId: 'agent-b' });
          return new Response('true');
        }
        const uid = new URL(url).searchParams.get('uid').slice(3);
        return new Response(JSON.stringify(rows.filter(row => row.uid === uid)));
      } });
    const result = await store[operation](mutable);
    assert.equal(operation === 'claimCycleDispatch' ? result.row.uid : result.uid, UID_A);
  }
});

test('PostgreSQL atomically claims dispatches and preserves execution binding with private roles', async (t) => {
  const fs = require('node:fs');
  const path = require('node:path');
  const { execFileSync, execFile } = require('node:child_process');
  const { promisify } = require('node:util');
  let bin;
  try { bin = path.dirname(execFileSync('/usr/bin/which', ['initdb'], { encoding: 'utf8' }).trim()); }
  catch { t.skip('PostgreSQL server binaries are not installed in this environment'); return; }
  const root = path.resolve(__dirname, '../../..');
  const workspace = path.join(root, '.superpowers/sdd/2026-10-20-maritime-week1-atomic-execution');
  fs.mkdirSync(workspace, { recursive: true });
  const fixtureRoot = fs.mkdtempSync(path.join(workspace, 'pg-execution-'));
  const socket = fs.mkdtempSync('/tmp/lm-cycle-pg-');
  const pgEnv = { PATH: process.env.PATH || '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C',
    PGPASSFILE: path.join(fixtureRoot, 'no-password-file') };
  const inheritedHostaddr = process.env.PGHOSTADDR;
  const data = path.join(fixtureRoot, 'data');
  const log = path.join(fixtureRoot, 'postgres.log');
  const args = ['-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-h', socket, '-p', '55437', '-U', 'fixture_owner', '-d', 'postgres'];
  const sql = (text) => execFileSync(path.join(bin, 'psql'), [...args, '-c', text], { env: pgEnv, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  const run = promisify(execFile);
  let started = false;
  try {
    process.env.PGHOSTADDR = 'invalid-fixture-address';
    execFileSync(path.join(bin, 'initdb'), ['-D', data, '-A', 'trust', '-U', 'fixture_owner', '--no-locale'], { env: pgEnv, stdio: 'pipe' });
    started = true;
    execFileSync(path.join(bin, 'pg_ctl'), ['-D', data, '-l', log, '-o', `-F -h '' -k ${socket} -p 55437`, '-w', '-t', '15', 'start'], { env: pgEnv, stdio: 'pipe' });
    sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE TABLE public.lm_users(uid text PRIMARY KEY);');
    const migrations = ['2026-10-20-lm-maritime-manager.sql', '2026-10-20-lm-maritime-runtime-executions.sql'];
    for (const name of migrations) sql(fs.readFileSync(path.join(root, 'apps/life-manager/migrations', name), 'utf8'));
    sql(`INSERT INTO public.lm_users VALUES ('${UID_A}'),('${UID_B}');
      INSERT INTO public.lm_maritime_manager_enrollments(uid,auth_subject,email,status,source,consent_version,agent_id,release_sha)
      VALUES ('${UID_A}','${SUBJECT_A}','a@example.invalid','active','fixture','maritime-manager-v1','agent-a','${SHA}'),
             ('${UID_B}','${SUBJECT_B}','b@example.invalid','active','fixture','maritime-manager-v1','agent-b','${SHA}');`);
    const claim = (uid, occurrence, agent = 'agent-a') => `SET ROLE service_role; SELECT public.claim_lm_maritime_manager_cycle_v1('${uid}','${occurrence}','${agent}','${SHA}','2026-10-20');`;
    const claims = await Promise.all([1, 2].map(() => run(path.join(bin, 'psql'), [...args, '-c', claim(UID_A, 'race')], { env: pgEnv })));
    assert.deepEqual(claims.map(result => result.stdout.trim()).sort(), ['f', 't']);
    assert.equal(sql(claim(UID_B, 'foreign', 'agent-a')), 'f');
    const bind = (execution) => `SET ROLE service_role; SELECT public.bind_lm_maritime_manager_execution_v1('${UID_A}','race','agent-a','${SHA}','2026-10-20','${execution}');`;
    assert.equal(sql(bind('exec-1')), 't');
    assert.equal(sql(bind('exec-1')), 't');
    assert.equal(sql(bind('exec-2')), 'f');
    assert.equal(sql(`SELECT execution_id FROM public.lm_maritime_manager_executions WHERE uid='${UID_A}' AND occurrence_id='race'`), 'exec-1');
    sql(`UPDATE public.lm_maritime_manager_enrollments SET status='paused',paused_at=clock_timestamp() WHERE uid='${UID_A}'`);
    assert.equal(sql(claim(UID_A, 'after-stop')), 'f');
    assert.equal(sql(bind('exec-1')), 't');
    assert.throws(() => sql('SET ROLE authenticated; SELECT * FROM public.lm_maritime_manager_executions'), /permission denied/);
    assert.throws(() => sql(`INSERT INTO public.lm_maritime_manager_executions(uid,occurrence_id,agent_id,date_key,release_sha) VALUES ('${UID_B}','bad-foreign','agent-a','2026-10-20','${SHA}')`), /foreign key constraint/);
    sql(fs.readFileSync(path.join(root, 'apps/life-manager/migrations', migrations[1]), 'utf8'));
    assert.equal(sql(`SELECT execution_id FROM public.lm_maritime_manager_executions WHERE uid='${UID_A}' AND occurrence_id='race'`), 'exec-1');
  } finally {
    if (inheritedHostaddr === undefined) delete process.env.PGHOSTADDR;
    else process.env.PGHOSTADDR = inheritedHostaddr;
    if (started) execFileSync(path.join(bin, 'pg_ctl'), ['-D', data, '-m', 'fast', '-w', 'stop'], { env: pgEnv, stdio: 'pipe' });
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
    fs.rmSync(socket, { recursive: true, force: true });
  }
});
