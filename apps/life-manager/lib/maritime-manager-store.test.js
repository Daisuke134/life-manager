"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
let createMaritimeManagerStore;
try { ({ createMaritimeManagerStore } = require("./maritime-manager-store.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
const { MANAGER_CONSENT_VERSION } = require("./maritime-distribution.js");
const SUBJECT_A = "11111111-1111-4111-8111-111111111111";
const SUBJECT_B = "22222222-2222-4222-8222-222222222222";
const UID_A = `lm_${SUBJECT_A}`;
const UID_B = `lm_${SUBJECT_B}`;
const SHA = "a".repeat(40);
function input(uid = UID_A, subject = SUBJECT_A) {
  return { uid, authSubject: subject, email: "person@example.invalid", timezone: "Asia/Tokyo",
    source: "referral", consentVersion: MANAGER_CONSENT_VERSION, releaseSha: SHA };
}
function fixture() {
  assert.equal(typeof createMaritimeManagerStore, "function", "enrollment store must exist");
  const rows = new Map(); const identities = new Map([[UID_A, SUBJECT_A], [UID_B, SUBJECT_B]]);
  const executions = new Map(); const requests = []; const pgQueries = [];
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
      const row = { ...body, auth_subject: body.auth_subject.toLowerCase(), status: "pending", agent_id: null, paused_at: null,
        created_at: "2026-10-20T00:00:00.000Z" };
      rows.set(body.uid, row); return response([row]);
    }
    const uid = u.searchParams.get("uid")?.replace(/^eq\./, ""); const row = rows.get(uid);
    if (opts.method === "PATCH" && row) Object.assign(row, body);
    return response(row ? [row] : []);
  };
  const pgRow = row => ({ ...row, consent_v2_at: row.consent_v2_at == null ? null : new Date(row.consent_v2_at),
    paused_at: row.paused_at == null ? null : new Date(row.paused_at), created_at: new Date(row.created_at) });
  const pgPool = { query: async (statement, values = []) => {
    pgQueries.push({ statement, values });
    let selected;
    if (statement.includes("INSERT INTO public.lm_maritime_manager_enrollments")) {
      const [uid, authSubject, email, timezone, source, consentVersion, releaseSha] = values;
      if (identities.get(uid) === authSubject && !rows.has(uid)) {
        rows.set(uid, { uid, auth_subject: authSubject, email, timezone, status: "pending", source,
          consent_version: consentVersion, agent_id: null, release_sha: releaseSha, paused_at: null,
          created_at: "2026-10-20T00:00:00.000Z" });
        return { rows: [{ uid }] };
      }
      return { rows: [] };
    }
    if (statement.includes("UPDATE public.lm_maritime_manager_enrollments") && statement.includes("SET consent_version = $3")) {
      const [uid, authSubject, consentVersion] = values;
      const row = rows.get(uid);
      const eligible = row && ["pending", "provisioning", "active"].includes(row.status) && row.paused_at == null
        && row.consent_version === "maritime-manager-v1"
        && ((row.status === "active" && row.agent_id != null) || (row.status !== "active" && row.agent_id == null));
      if (!eligible || row.auth_subject !== authSubject) return { rows: [] };
      row.consent_version = consentVersion;row.consent_v2_at ||= "2026-10-26T02:00:00.000Z";
      return { rows: [pgRow(row)] };
    }
    if (statement.includes("claim_lm_maritime_manager_provision_v1")) {
      const row = rows.get(values[0]);
      const claimed = Boolean(row && row.status === "pending" && row.paused_at == null);
      if (claimed) row.status = "provisioning";
      return { rows: [{ claimed }] };
    }
    if (statement.includes("bind_lm_maritime_manager_agent_v1")) {
      const [uid, authSubject, agentId, releaseSha] = values;
      const row = rows.get(uid);
      const duplicateAgent = [...rows.values()].some(candidate => candidate.uid !== uid && candidate.agent_id === agentId);
      const allowedStatus = row && (['provisioning', 'effect_unknown', 'paused'].includes(row.status)
        || (row.status === 'active' && row.agent_id === agentId));
      const bound = Boolean(row && row.auth_subject === authSubject && row.release_sha === releaseSha
        && (row.agent_id == null || row.agent_id === agentId) && allowedStatus && !duplicateAgent);
      if (bound) {
        row.agent_id = agentId;
        row.status = row.paused_at == null ? 'active' : 'paused';
      }
      return { rows: [{ bound }] };
    }
    if (statement.includes("claim_lm_maritime_manager_cycle_v1")) {
      const [uid, occurrenceId, agentId, releaseSha, dateKey] = values;
      const enrollment = rows.get(uid);
      const key = uid + ":" + occurrenceId;
      const claimed = Boolean(enrollment && enrollment.status === "active" && enrollment.paused_at == null
        && enrollment.agent_id === agentId && enrollment.release_sha === releaseSha && !executions.has(key));
      if (claimed) executions.set(key, { uid, occurrence_id: occurrenceId, agent_id: agentId,
        date_key: new Date(`${dateKey}T00:00:00.000Z`), release_sha: releaseSha, execution_id: null });
      return { rows: [{ claimed }] };
    }
    if (statement.includes("bind_lm_maritime_manager_execution_v1")) {
      const [uid, occurrenceId, agentId, releaseSha, dateKey, executionId] = values;
      const row = executions.get(uid + ":" + occurrenceId);
      const duplicateExecution = [...executions.values()].some(candidate => candidate.agent_id === agentId
        && candidate.execution_id === executionId && candidate !== row);
      const bound = Boolean(row && row.agent_id === agentId && row.release_sha === releaseSha
        && row.date_key.toISOString().slice(0, 10) === dateKey
        && (row.execution_id == null || row.execution_id === executionId) && !duplicateExecution);
      if (bound) row.execution_id = executionId;
      return { rows: [{ bound }] };
    }
    if (statement.includes("FROM public.lm_maritime_manager_executions")) {
      const row = executions.get(values[0] + ":" + values[1]);
      return { rows: row ? [{ ...row }] : [] };
    }
    if (statement.includes("SET status = $2") && statement.includes("agent_id IS NULL")) {
      const [uid, status, expected] = values;
      const row = rows.get(uid);
      if (!row || row.status !== expected || row.paused_at != null || row.agent_id != null) return { rows: [] };
      row.status = status;
      return { rows: [pgRow(row)] };
    }
    if (statement.includes("SET status = 'paused'")) {
      const [uid, pausedAt] = values;
      const row = rows.get(uid);
      if (!row || row.paused_at != null) return { rows: [] };
      row.status = "paused";
      row.paused_at = pausedAt;
      return { rows: [{ uid }] };
    }
    if (statement.includes("WHERE uid = $1 LIMIT 2")) selected = [rows.get(values[0])].filter(Boolean);
    else if (statement.includes("status = $1 AND paused_at IS NULL AND agent_id IS NULL")) {
      selected = [...rows.values()].filter(row => row.status === values[0] && row.paused_at == null && row.agent_id == null)
        .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.uid.localeCompare(b.uid)).slice(0, values[1]);
    } else if (statement.includes("status = $1 AND paused_at IS NOT NULL")) {
      selected = [...rows.values()].filter(row => row.status === values[0] && row.paused_at != null && (values[1] == null || row.uid > values[1]))
        .sort((a, b) => a.uid.localeCompare(b.uid)).slice(0, values[2])
        .map(({ uid, status, paused_at, agent_id, release_sha }) => ({ uid, status, paused_at, agent_id, release_sha }));
    } else throw new Error("unexpected_pg_query");
    return { rows: selected.map(pgRow) };
  } };
  return { rows, identities, requests, pgQueries, store: createMaritimeManagerStore({ supaUrl: "https://database.invalid",
    supaKey: "fixture-private-key", fetchImpl, pgPool, now: () => "2026-10-20T00:00:00.000Z" }) };
}

test("enrollment_is_idempotent_and_tenant_scoped", async () => {
  const { store, rows } = fixture();
  const a = await store.enroll(input()); const again = await store.enroll(input());
  assert.equal(rows.size, 1); assert.equal(a.uid, UID_A); assert.deepEqual(again, a);
  await assert.rejects(store.enroll(input(UID_A, SUBJECT_B)), /identity_mismatch/);
  await assert.rejects(store.enroll({ ...input(), email: "changed@example.invalid" }), /identity_mismatch/);
  assert.equal(rows.get(UID_A).auth_subject, SUBJECT_A);
  assert.equal(rows.get(UID_A).email, "person@example.invalid");
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
  await assert.rejects(store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "agent-a", releaseSha: "b".repeat(40) }), /binding_rejected/);
  assert.equal((await store.read(UID_B)).agent_id, null);
  assert.equal((await store.read(UID_A)).release_sha, SHA);
});
test("reconsent_updates_only_the_matching_active_tenant_and_preserves_its_agent", async () => {
  const { store, rows, pgQueries } = fixture();
  await store.enroll(input());
  await store.claimProvision(UID_A);
  await store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "agent-a", releaseSha: SHA });
  rows.get(UID_A).consent_version = "maritime-manager-v1";

  const updated = await store.reconsent({ uid: UID_A, authSubject: SUBJECT_A, consentVersion: MANAGER_CONSENT_VERSION });
  assert.equal(updated.consent_version, MANAGER_CONSENT_VERSION);
  assert.equal(updated.status, "active");
  assert.equal(updated.agent_id, "agent-a");
  assert.equal(updated.release_sha, SHA);
  assert.equal(updated.consent_v2_at, "2026-10-26T02:00:00.000Z");
  assert.equal(await store.reconsent({ uid: UID_A, authSubject: SUBJECT_B, consentVersion: MANAGER_CONSENT_VERSION }), null);
  assert.match(pgQueries.find(item => item.statement.includes("SET consent_version" )).statement,
    /status IN \('pending', 'provisioning', 'active'\).*paused_at IS NULL/);
});
test("reconsent_updates_legacy_pending_and_provisioning_rows_but_not_paused_or_unknown_rows",async()=>{
 const {store,rows}=fixture();
 const enrollment=await store.enroll(input());
 for(const status of ["pending","provisioning"]){
  const row=rows.get(UID_A);row.status=status;row.consent_version="maritime-manager-v1";row.agent_id=null;row.consent_v2_at=null;
  const updated=await store.reconsent({uid:UID_A,authSubject:SUBJECT_A,consentVersion:MANAGER_CONSENT_VERSION});
  assert.equal(updated.status,status);assert.equal(updated.consent_version,MANAGER_CONSENT_VERSION);assert.equal(updated.agent_id,null);
  assert.equal(updated.release_sha,SHA);assert.equal(updated.created_at,enrollment.created_at);
 }
 for(const status of ["paused","effect_unknown"]){
  const row=rows.get(UID_A);row.status=status;row.paused_at=status==="paused"?"2026-10-25T00:00:00.000Z":null;row.consent_version="maritime-manager-v1";
  assert.equal(await store.reconsent({uid:UID_A,authSubject:SUBJECT_A,consentVersion:MANAGER_CONSENT_VERSION}),null);
 }
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
  const { store, identities } = fixture();
  const subject = "aabbccdd-1111-4111-8111-111111111111";
  const uid = `lm_${subject}`;
  identities.set(uid, subject);
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
  const malformed = createMaritimeManagerStore({ pgPool: { query: async statement => statement.includes('claim_lm_maritime_manager_cycle_v1')
    ? { rows: [{ claimed: true }] } : { rows: [] } } });
  await assert.rejects(malformed.claimCycleDispatch(cycleIdentity()), /store_invalid/);
  const foreign = createMaritimeManagerStore({ pgPool: { query: async statement => statement.includes('claim_lm_maritime_manager_cycle_v1')
    ? { rows: [{ claimed: false }] }
    : { rows: [{ uid: UID_B, occurrence_id: 'cycle-1', agent_id: 'agent-a', date_key: new Date('2026-10-20T00:00:00Z'), release_sha: SHA, execution_id: null }] } } });
  await assert.rejects(foreign.readCycleDispatch(cycleIdentity()), /binding_rejected/);
});


test('PG claim/bind and readback stay bound to the original identity during caller mutation', async () => {
  for (const operation of ['claimCycleDispatch', 'bindCycleExecution']) {
    const mutable = { ...cycleIdentity(), executionId: 'exec-1' };
    const rows = [
      { uid: UID_A, occurrence_id: 'cycle-1', agent_id: 'agent-a', date_key: '2026-10-20', release_sha: SHA, execution_id: 'exec-1' },
      { uid: UID_B, occurrence_id: 'cycle-1', agent_id: 'agent-b', date_key: '2026-10-20', release_sha: SHA, execution_id: 'exec-1' },
    ];
    const store = createMaritimeManagerStore({ pgPool: { query: async (statement, values) => {
        if (statement.includes('claim_lm_maritime_manager_cycle_v1') || statement.includes('bind_lm_maritime_manager_execution_v1')) {
          Object.assign(mutable, { uid: UID_B, agentId: 'agent-b' });
          return { rows: [{ [operation === 'claimCycleDispatch' ? 'claimed' : 'bound']: true }] };
        }
        return { rows: rows.filter(row => row.uid === values[0]).map(row => ({ ...row, date_key: new Date(`${row.date_key}T00:00:00Z`) })) };
      } } });
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

test('pending enrollment recovery is bounded and excludes paused or claimed rows', async () => {
  const requested=[];
  const store=createMaritimeManagerStore({pgPool:{query:async(statement,values)=>{
    requested.push({statement,values});return {rows:[{uid:UID_A,auth_subject:SUBJECT_A,email:'person@example.invalid',timezone:'UTC',status:'pending',source:'direct',consent_version:'maritime-manager-v1',agent_id:null,release_sha:SHA,paused_at:null,created_at:new Date('2026-10-20T00:00:00Z')}]};
  }}});
  const rows=await store.listPending(5);
  assert.equal(rows.length,1);assert.equal(rows[0].uid,UID_A);
  assert.match(requested[0].statement,/status = \$1 AND paused_at IS NULL AND agent_id IS NULL/);
  assert.deepEqual(requested[0].values,['pending',5]);
  assert.equal(rows[0].created_at,'2026-10-20T00:00:00.000Z');
  for(const limit of [0,101,'5'])await assert.rejects(store.listPending(limit),/input_invalid/);
  assert.equal(requested.length,1);
  const foreign=createMaritimeManagerStore({pgPool:{query:async()=>({rows:[{uid:UID_A,status:'paused',paused_at:null,agent_id:null,release_sha:SHA}]})}});
  await assert.rejects(foreign.listPending(1),/store_invalid/);
});


test('quarantine pending provision is tenant scoped and cannot change active or paused enrollments',async()=>{
 const calls=[];
 const store=createMaritimeManagerStore({pgPool:{query:async(statement,values)=>{
  calls.push({statement,values});
  assert.match(statement,/status = \$2/);assert.match(statement,/status = \$3 AND paused_at IS NULL AND agent_id IS NULL/);
  assert.deepEqual(values,[UID_A,'effect_unknown','pending']);
  return {rows:[{uid:UID_A,auth_subject:SUBJECT_A,email:'person@example.invalid',timezone:'UTC',status:'effect_unknown',source:'direct',consent_version:'maritime-manager-v1',agent_id:null,release_sha:SHA,paused_at:null,created_at:new Date('2026-10-20T00:00:00Z')}]};
 }}});
 assert.equal((await store.quarantinePendingProvision(UID_A)).status,'effect_unknown');
 await assert.rejects(()=>store.quarantinePendingProvision('../foreign'),/invalid/);assert.equal(calls.length,1);
});


test('paused cleanup recovery reads bounded identity pages without contact data fallback',async()=>{
 const calls=[];const row={uid:UID_B,status:'paused',paused_at:new Date('2026-10-21T00:00:00Z'),agent_id:null,release_sha:SHA};
 const normalizedRow={...row,paused_at:'2026-10-21T00:00:00.000Z'};
 const store=createMaritimeManagerStore({pgPool:{query:async(statement,values)=>{calls.push({statement,values});return {rows:[row]};}}});
 assert.deepEqual(await store.listPaused(20,UID_A),[normalizedRow]);
 assert.equal(calls[0].values[0],'paused');assert.equal(calls[0].values[1],UID_A);assert.equal(calls[0].values[2],20);
 assert.match(calls[0].statement,/uid > \$2/);assert.equal((await store.listPaused(20))[0].paused_at,'2026-10-21T00:00:00.000Z');
 await assert.rejects(()=>store.listPaused(0),/invalid/);await assert.rejects(()=>store.listPaused(20,'foreign'),/invalid/);assert.equal(calls.length,2);
});
