'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {financialRecordId}=require('./financial-record-contract.js');
const {buildMaritimeManagerCycleJob}=require('./maritime-manager-runtime.js');
const {buildMaritimeDailyResult,renderMaritimeDailyEmail}=require('./maritime-manager-report.js');
const UID='lm_11111111-1111-4111-8111-111111111111';
const periodKey='maritime:daily:2026-10-21';
const enrollment={uid:UID,timezone:'Asia/Tokyo',release_sha:'a'.repeat(40)};
function row(key,kind,amount,currency='USD',occurredAt='2026-10-21T01:00:00Z'){
 return {schema_version:1,record_type:'financial_record',record_id:financialRecordId(UID,key),subject_id:UID,
 scope:'business',kind,direction:kind==='business_revenue'||kind==='payout'?'credit':'debit',amount_minor:amount,currency,
 occurred_at:occurredAt,recorded_at:occurredAt,idempotency_key:key,
 source:{provider:'capafy',source_type:'marketplace',external_ref:key},
 verification:{status:'verified',observed_at:occurredAt,evidence_refs:['capafy://receipt/'+key]}};
}
function coverage(){return {tenantId:UID,periodKey,timezone:'Asia/Tokyo',complete:true,currencies:['USD'],evidenceRefs:['capafy://daily/2026-10-21']};}
test('daily result never turns missing sales, cost or payout observations into zero',()=>{
 const result=buildMaritimeDailyResult({enrollment,periodKey});
 assert.equal(result.financial.gross.status,'unknown');assert.equal(result.financial.costs.status,'unknown');
 assert.equal(result.financial.payouts.status,'unknown');assert.equal(result.financial.profit,null);
 const text=renderMaritimeDailyEmail(result);assert.match(text,/今日実行したこと/);assert.match(text,/売上：未確認/);
 assert.match(text,/費用：未確認/);assert.match(text,/利益：未確認/);assert.doesNotMatch(text,/USD 0|¥0/);
});
test('verified observations remain subtotals until coverage is complete',()=>{
 const result=buildMaritimeDailyResult({enrollment,periodKey,financialRecords:[row('sale','business_revenue',1200)]});
 assert.deepEqual(result.financial.gross,{status:'observed',amounts:[{currency:'USD',amountMinor:1200}]});
 assert.equal(result.financial.profit,null);assert.match(renderMaritimeDailyEmail(result),/確認済み小計/);
});
test('complete same-tenant coverage permits verified zero and separates payout from revenue',()=>{
 const result=buildMaritimeDailyResult({enrollment,periodKey,financialCoverage:coverage(),costs:{...coverage(),records:[]},
 financialRecords:[row('sale','business_revenue',1200),row('capafy-financial:v1:2026-10-21:refund','business_cost',100),row('payout','payout',500)]});
 assert.deepEqual(result.financial.gross.amounts,[{currency:'USD',amountMinor:1200}]);
 assert.deepEqual(result.financial.payouts.amounts,[{currency:'USD',amountMinor:500}]);
 assert.deepEqual(result.financial.refunds.amounts,[{currency:'USD',amountMinor:100}]);
 assert.deepEqual(result.financial.profit,[{currency:'USD',amountMinor:1100}]);
 const zero=buildMaritimeDailyResult({enrollment,periodKey,financialCoverage:coverage()});
 assert.deepEqual(zero.financial.gross,{status:'complete',amounts:[{currency:'USD',amountMinor:0}]});
 assert.equal(zero.financial.profit,null);
});
test('duplicate financial records and incomplete observations cannot become complete totals',()=>{
 const sale=row('sale','business_revenue',1200);
 assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,financialRecords:[sale,sale]}),/invalid/);
 assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,financialCoverage:coverage(),financialRecords:[{...sale,verification:{...sale.verification,status:'unverified'}}]}),/invalid/);
});
test('currency and local calendar boundaries use existing Financial Manager aggregation',()=>{
 const result=buildMaritimeDailyResult({enrollment,periodKey,financialRecords:[
 row('usd','business_revenue',250),row('jpy','business_revenue',900,'JPY'),
 row('previous','business_revenue',9999,'USD','2026-10-20T14:59:59Z')]});
 assert.deepEqual(result.financial.gross.amounts,[{currency:'JPY',amountMinor:900},{currency:'USD',amountMinor:250}]);
});
test('foreign tenant financials, personal money and foreign coverage are rejected',()=>{
 for(const record of [{...row('foreign','business_revenue',1),subject_id:'other'},{...row('personal','fee',1),scope:'personal'}]){
  assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,financialRecords:[record]}),/invalid/);
 }
 assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,financialCoverage:{...coverage(),tenantId:'other'}}),/invalid/);
});
test('daily work uses verified cycle receipts, queue timestamps, and replay deduplication',()=>{
 const job=buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'first',dateKey:'2026-10-20'});
 const ref='maritime-execution://agent-1/exec-1';
 const receipt={schema_version:1,kind:'maritime_manager_cycle',tenant_id:UID,job_id:job.job_id,
  occurrence_id:'first',date_key:'2026-10-20',release_sha:enrollment.release_sha,agent_id:'agent-1',execution_id:'exec-1',
  status:'completed',artifact_refs:['artifact://original/商品.md'],error_class:null,provider:'maritime',external_ref:ref,evidence_refs:[ref]};
 const completed={receipt,completedAt:'2026-10-20T15:00:00Z'};
 const pendingJob=buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'second',dateKey:'2026-10-21'});
 const pending={job:pendingJob,receipt:null,status:'reconciling',completedAt:'2026-10-21T01:00:00Z'};
 const result=buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[completed,completed,pending,pending,{...completed,completedAt:'2026-10-20T14:59:59Z'}]});
 assert.deepEqual(result.actions,{completedCycles:1,artifactCount:1,deferredCycles:0,unconfirmedCycles:1,failedCycles:0});
 assert.equal(result.publicationStatus,'unconfirmed');
 assert.deepEqual(result.work[0].artifactRefs,['artifact://original/商品.md']);
 assert.deepEqual(result.work[0].evidenceRefs,[ref]);
 assert.match(renderMaritimeDailyEmail(result),/original\/商品.md/);
 assert.match(renderMaritimeDailyEmail(result),/結果確認中：1件/);
 assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[{...completed,receipt:{...receipt,tenant_id:'other'}}]}),/invalid/);
});
test('unknown currency and estimated API units never establish complete zero or profit',()=>{
 for(const currency of ['UNKNOWN','USD_API_EQUIV']){
  const input={...coverage(),currencies:[currency]};
  const result=buildMaritimeDailyResult({enrollment,periodKey,financialCoverage:input,costs:{...input,records:[]}});
  assert.equal(result.financial.gross.status,'unknown');assert.equal(result.financial.costs.status,'unknown');
  assert.equal(result.financial.profit,null);
 }
});
