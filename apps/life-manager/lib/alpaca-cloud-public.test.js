"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const { resolveAlpacaPublicProjection } = require("./alpaca-public.js");
const { fetchCloudAlpacaPublicProjection } = require('./alpaca-public.js');
const { sealRuntimeBundle } = require('./investment-runtime-state-store.js');
function cloudFixture() {
  const at = '2026-09-30T12:00:00Z';
  const binding = { provider: 'alpaca', endpoint: 'live', account_id_hash: 'a'.repeat(64) };
  const cutover = { status: 'ready', local_stopped_at: at, queues_drained_at: at,
    broker_reconciled_at: at, source_release_sha: 'b'.repeat(40) };
  const encode = v => Buffer.from(JSON.stringify(v)).toString('base64');
  const sealed = sealRuntimeBundle({ schema_version: 1, exported_at: at, account_binding: binding, cutover,
    files: { 'control.json': encode({paused:false,killed:false,revision:1}),
      'risk-day.json': encode({ny_day:'2026-09-30',baseline_equity:'66',baseline_observed_at:at,
        baseline_bank_cash_flow:'0',baseline_trade_activity_ids:[],baseline_trades_clean:true,crypto_cash_flow:'0',transfers:{}}),
      'receipts.jsonl': Buffer.from(JSON.stringify({receipt_type:'decision',mode:'live',recorded_at:at,
        decision:{reason:'private-token',candidate_ref:'private-account-id'}})+'\n').toString('base64'),
      'telegram-outbox.sqlite3': Buffer.from('SQLite format 3\0fixture').toString('base64') } });
  const files = { '.cutover.json': {account_id_hash:binding.account_id_hash,source_release_sha:cutover.source_release_sha},
    'observation-latest.json': {clock:{observed_at:at},account:{equity:'66.63',cash:'0',id:'private-account-id'},
      positions:[{symbol:'PRIVATE',qty:'99'}],open_and_closed_orders_count:0},
    'campaign.json': {unrealized_pnl_usd:'0',fills:[]} };
  const row = {deployment:'cloud',mode:'live',paused:false,killed:false,bundle:sealed.bundle,bundle_digest:sealed.digest};
  const env = {LM_RUNTIME_TENANT_ID:'tenant-a',LM_INVESTMENT_CLOUD_STATE_ROOT:'/private/cloud',LM_INVESTMENT_CLOUD_LIVE_ENABLED:'true'};
  return {env, now:Date.parse(at)+1000, query:async (sql,params)=>{
    assert.match(sql,/WHERE s.uid = \$1 AND/);assert.match(sql,/s.deployment = 'cloud'/);
    assert.deepEqual(params,['tenant-a']);return {rows:[row]};
  },readJson:file=>files[require('node:path').basename(file)]||{}, files,row};
}
test('cloud projection reads bound owner and only publishes safe aggregates',async()=>{
  const p=await fetchCloudAlpacaPublicProjection(cloudFixture());
  assert.equal(p.paper,false);assert.equal(p.status,'fresh');assert.equal(p.equity_usd,66.63);
  assert.equal(p.starting_equity_usd,null);assert.equal(p.total_pnl_usd,null);assert.deepEqual(p.positions,[]);
  assert.equal(p.reconciliation.positions,1);assert.equal(p.reconciliation.last_receipt,'2026-09-30T12:00:00.000Z');
  assert.doesNotMatch(JSON.stringify(p),/private-|PRIVATE|tenant-a|aaaaaa|bbbbbb/);
});
test('cloud mode never falls back to old paper data on missing tenant or database failure',async()=>{
  let fallback=false;
  await assert.rejects(resolveAlpacaPublicProjection({env:{LM_INVESTMENT_CLOUD_LIVE_ENABLED:'true'},
    buildLocal:()=>{fallback=true;return INPUT;}}),/tenant unavailable/);assert.equal(fallback,false);
  const f=cloudFixture();await assert.rejects(resolveAlpacaPublicProjection({...f,query:async()=>{throw Error('offline');}}),/offline/);
});
test('cloud freshness comes from observation, not read time or bundle export time',async()=>{
  const f=cloudFixture();const p=await fetchCloudAlpacaPublicProjection({...f,now:f.now+3600000});
  assert.equal(p.status,'stale');assert.equal(p.observed_at,'2026-09-30T12:00:00.000Z');
});
test('missing or misbound observation is unavailable, not zero equity or historical paper',async()=>{
  const f=cloudFixture();f.files['.cutover.json']={};const p=await fetchCloudAlpacaPublicProjection(f);
  assert.equal(p.status,'unavailable');assert.equal(p.equity_usd,null);assert.equal(p.observed_at,null);
});
test('digest drift is rejected and paused state remains visible',async()=>{
  const f=cloudFixture();f.row.paused=true;assert.equal((await fetchCloudAlpacaPublicProjection(f)).paused,true);
  f.row.bundle_digest='c'.repeat(64);await assert.rejects(fetchCloudAlpacaPublicProjection(f),/unavailable/);
});
test('Local handoff keeps a retired Cloud view without publishing old values as current',async()=>{
  const f=cloudFixture();f.row.deployment='local';f.row.paused=true;
  f.env.LM_INVESTMENT_CLOUD_LIVE_ENABLED='false';f.env.LM_INVESTMENT_CLOUD_SHADOW_ENABLED='false';
  let sql;const query=async(...args)=>{sql=args[0];return f.query(...args);};
  const p=await resolveAlpacaPublicProjection({...f,query,
    buildLocal:()=>{assert.fail('retired Cloud must not fall back to paper');}});
  assert.equal(p.status,'retired');assert.equal(p.source,'cloud_runtime');
  assert.equal(p.paper,false);assert.equal(p.mode,'live');assert.equal(p.paused,true);
  for(const key of ['observed_at','starting_equity_usd','equity_usd','cash_usd','total_pnl_usd',
    'daily_pnl_usd','realized_pnl_usd','unrealized_pnl_usd']) assert.equal(p[key],null,key);
  assert.deepEqual(p.positions,[]);assert.deepEqual(p.fills,[]);assert.deepEqual(p.timeline,[]);
  assert.equal(p.latest_decision,null);assert.equal(p.telegram.delivered,false);
  assert.equal(p.reconciliation.status,'CLOUD_EXECUTION_RETIRED');
  for(const key of ['positions','fills','broker_orders','last_receipt']) assert.equal(p.reconciliation[key],null,key);
  assert.match(sql,/s.deployment = 'local' AND s.paused = true/);
  assert.doesNotMatch(JSON.stringify(p),/private-|PRIVATE|tenant-a|aaaaaa|bbbbbb/);
});
test('public Cloud view rejects unpaused Local and unknown deployment rows',async()=>{
  for(const deployment of ['local','other']) {
    const f=cloudFixture();f.row.deployment=deployment;
    await assert.rejects(fetchCloudAlpacaPublicProjection(f),/state unavailable/);
  }
});
