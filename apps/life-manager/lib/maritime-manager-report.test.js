'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {financialRecordId}=require('./financial-record-contract.js');
const {buildMaritimeManagerCycleJob}=require('./maritime-manager-runtime.js');
const {buildMaritimeDailyResult,renderMaritimeDailyEmail,deliverMaritimeDailyResult,readMaritimeDailyObservations}=require('./maritime-manager-report.js');
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
 const pending={job:pendingJob,receipt:null,status:'reconciling',observedAt:'2026-10-21T01:00:00Z'};
 const result=buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[completed,completed,pending,pending,{...completed,completedAt:'2026-10-20T14:59:59Z'}]});
 assert.deepEqual(result.actions,{completedCycles:1,artifactCount:1,deferredCycles:0,unconfirmedCycles:1,failedCycles:0});
 assert.equal(result.publicationStatus,'unconfirmed');
 assert.deepEqual(result.work[0].artifactRefs,['artifact://original/商品.md']);
 assert.deepEqual(result.work[0].evidenceRefs,[ref]);
 assert.match(renderMaritimeDailyEmail(result),/original\/商品.md/);
 const linked=renderMaritimeDailyEmail(result,{publicOrigin:'https://manager.example'});
 const artifactPath=require('./maritime-manager-artifacts.js').buildMaritimeArtifactPath({jobId:job.job_id,artifactRef:receipt.artifact_refs[0]});
 assert.ok(linked.includes('https://manager.example'+artifactPath));
 assert.throws(()=>renderMaritimeDailyEmail(result,{publicOrigin:'https://private@manager.example'}),/origin/);
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
test('missing or malformed cost records do not become verified zero expense',()=>{
 for(const records of [undefined,0,false])assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,
  financialCoverage:coverage(),costs:{...coverage(),records}}),/invalid/);
});
function deliveryFixture(){
 const current={...enrollment,status:'active',paused_at:null,email:'person@example.invalid'};
 let receipt=null;const sends=[];
 const deps={managerStore:{read:async()=>({...current})},
  cfoReceiptIO:{read:async()=>receipt,claim:async(_,value)=>{if(receipt)return false;receipt={...value};return true;},mark:async(_,patch)=>Object.assign(receipt,patch)},
  sendEmail:async args=>{sends.push(args);return {sent:true,id:'mail-1'};}};
 const input={enrollment:{...current,email:'stale@example.invalid'},result:buildMaritimeDailyResult({enrollment,periodKey}),observedAt:'2026-10-21T10:00:00Z'};
 return {current,deps,sends,input};
}
test('daily email replays original provider ID and uses the latest verified enrollment recipient',async()=>{
 const f=deliveryFixture();
 const first=await deliverMaritimeDailyResult(f.input,f.deps);
 const second=await deliverMaritimeDailyResult(f.input,f.deps);
 assert.equal(first.providerMessageId,'mail-1');assert.equal(second.providerMessageId,'mail-1');
 assert.equal(second.status,'duplicate');assert.equal(f.sends.length,1);
 assert.equal(f.sends[0].to,'person@example.invalid');assert.match(f.sends[0].text,/利益：未確認/);
});
test('paused, foreign, malformed report scopes and invalid timestamps do not send email',async()=>{
 const f=deliveryFixture();f.current.paused_at='2026-10-21T09:00:00Z';
 await assert.rejects(deliverMaritimeDailyResult(f.input,f.deps),/inactive/);f.current.paused_at=null;
 for(const patch of [{result:{...f.input.result,tenantId:'other'}},{observedAt:'invalid'},{result:{...f.input.result,date:'2026-10-20'}}]){
  await assert.rejects(deliverMaritimeDailyResult({...f.input,...patch},f.deps),/invalid/);
 }
 assert.equal(f.sends.length,0);
});
test('artifact emails require a configured real origin before claiming or sending',async()=>{
 const f=deliveryFixture();const job=buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'first',dateKey:'2026-10-21'});
 f.input.result.work=[{jobId:job.job_id,artifactRefs:['artifact://product.md'],evidenceRefs:[],status:'completed',errorClass:null}];
 f.deps.env={RAILWAY_PUBLIC_DOMAIN:'worker.example',LM_PANEL_BASE_URL:'https://life-call-production.up.railway.app'};
 await assert.rejects(deliverMaritimeDailyResult(f.input,f.deps),/Cloud public origin/);assert.equal(f.sends.length,0);

 const cloud=deliveryFixture();cloud.input.result.work=[{jobId:job.job_id,artifactRefs:['artifact://product.md'],evidenceRefs:[],status:'completed',errorClass:null}];
 cloud.deps.env={LM_PANEL_BASE_URL:'https://life-call-production.up.railway.app',LM_MARITIME_WEB_ORIGIN:'https://aniccaai.com'};
 cloud.deps.publicOrigin='https://life-call-production.up.railway.app';
 await deliverMaritimeDailyResult(cloud.input,cloud.deps);
 assert.ok(cloud.sends[0].text.includes('https://aniccaai.com/maritime/artifacts/'));
 assert.ok(!cloud.sends[0].text.includes('life-call-production.up.railway.app'));
});


test('daily observations reuse tenant-scoped queue and financial stores without appending aggregates',async()=>{
 const job={...buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:'a'.repeat(40),occurrenceId:'initial',dateKey:'2026-10-21'}),status:'reconciling',updated_at:'2026-10-21T01:00:00Z'};
 const calls=[];
 const query=async(sql,params)=>{calls.push({sql,params});return {rows:[{job,receipt:null,completed_at:null}]};};
 const financialStore={read:async input=>{assert.equal(input.subjectId,UID);assert.equal(input.scope,'business');return [row('sale','business_revenue',100)];},append:()=>{throw new Error('append forbidden');}};
 const result=await readMaritimeDailyObservations({uid:UID,periodKey},{query,financialStore});
 assert.equal(calls[0].params[0],UID);assert.match(calls[0].sql,/tenant_id = \$1/);
 assert.match(calls[0].sql,/LIMIT 1001/);
 assert.equal(result.actionReceipts[0].observedAt,new Date(job.updated_at).toISOString());
 assert.equal(result.financialRecords.length,1);
 assert.equal(result.financialCoverage,undefined);
 const foreign={...job,tenant_id:'lm_22222222-2222-4222-8222-222222222222'};
 await assert.rejects(()=>readMaritimeDailyObservations({uid:UID,periodKey},{query:async()=>({rows:[{job:foreign}]}),financialStore}),/invalid/);
});

function capafyReportFixture(status='under_review'){
 const provider=require('./maritime-manager-provider-runtime.js');
 const cycleJob={...buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'provider-cycle',dateKey:'2026-10-20'}),status:'completed',attempt:1};
 const sourceRef='maritime-execution://manager-agent/source-exec';
 const cycleReceipt={schema_version:1,kind:'maritime_manager_cycle',tenant_id:UID,job_id:cycleJob.job_id,
  occurrence_id:'provider-cycle',date_key:'2026-10-20',release_sha:enrollment.release_sha,agent_id:'manager-agent',execution_id:'source-exec',
  status:'completed',artifact_refs:['artifact://original/agent-package.json'],error_class:null,provider:'maritime',external_ref:sourceRef,evidence_refs:[sourceRef]};
 const common={tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'provider-cycle',artifactRef:cycleReceipt.artifact_refs[0],accountRef:`account://capafy/${UID}/tenant-account`};
 const prepareJob={...provider.buildMaritimeCapafyPrepareJob({...common,cycleJobId:cycleJob.job_id}),status:'completed',attempt:1};
 const prepareReceipt={schema_version:1,kind:'maritime_capafy_prepare',tenant_id:UID,job_id:prepareJob.job_id,attempt:1,
  effect_key:prepareJob.effect_key,provider:'capafy',...prepareJob.input_refs,agent_id:'agent-123',agent_version_id:'version-456',
  status:'prepared',url:'https://capafy.ai/agent/agent-123',external_ref:`capafy-action://${prepareJob.job_id}/1`,evidence_refs:[`capafy-action://${prepareJob.job_id}/1`],observed_at:'2026-10-21T01:00:00.000Z'};
 const publishJob={...provider.buildMaritimeCapafyPublishJob({...common,sourceCycleJobId:cycleJob.job_id,prepareJobId:prepareJob.job_id,
  agentId:'agent-123',agentVersionId:'version-456'}),status:'completed',attempt:1};
 const publishReceipt={schema_version:1,kind:'provider_action_receipt',tenant_id:UID,job_id:publishJob.job_id,attempt:1,
  effect_key:publishJob.effect_key,provider:'capafy',...publishJob.input_refs,status,
  url:'https://capafy.ai/agent/agent-123',external_ref:`capafy-action://${publishJob.job_id}/1`,evidence_refs:[`capafy-action://${publishJob.job_id}/1`],observed_at:'2026-10-21T01:00:00.000Z'};
 const context={sourceCycleJob:cycleJob,sourceCycleReceipt:cycleReceipt,prepareJob,prepareReceipt};
 const prepare={receipt:prepareReceipt,job:prepareJob,completedAt:'2026-10-20T15:00:00Z',sourceCycleJob:cycleJob,sourceCycleReceipt:cycleReceipt};
 const publish={receipt:publishReceipt,job:publishJob,completedAt:'2026-10-21T01:00:00Z',...context};
 const pending={job:{...publishJob,status:'reconciling',updated_at:'2026-10-21T02:00:00Z'},status:'reconciling',observedAt:'2026-10-21T02:00:00Z',...context};
 const dbRow=item=>({job:item.job,receipt:item.receipt,completed_at:item.completedAt,
  source_cycle_job:item.sourceCycleJob,source_cycle_receipt:item.sourceCycleReceipt,prepare_job:item.prepareJob,prepare_receipt:item.prepareReceipt});
 return {prepare,publish,pending,dbRow};
}
test('daily_result_separates_artifact_publish_sales_payout_and_unknown_cost',()=>{
 const f=capafyReportFixture();
 const result=buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[f.prepare,f.publish,f.publish]});
 assert.equal(result.providerActions.length,2);
 assert.deepEqual(result.providerActions.map(action=>action.status),['prepared','under_review']);
 assert.equal(result.publicationStatus,'under_review');
 assert.equal(result.actions.completedCycles,0);assert.equal(result.actions.artifactCount,0);
 assert.equal(result.financial.gross.status,'unknown');assert.equal(result.financial.payouts.status,'unknown');assert.equal(result.financial.profit,null);
 const email=renderMaritimeDailyEmail(result);
 assert.match(email,/審査待ち/);assert.match(email,/売上：未確認/);assert.doesNotMatch(email,/販売可能|売上：.*0/);
 assert.ok(email.includes('https://capafy.ai/agent/agent-123'));
 const published=buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[capafyReportFixture('published').publish]});
 assert.equal(published.publicationStatus,'published');assert.match(renderMaritimeDailyEmail(published),/公開済み/);
});
test('daily provider results use queue local day and keep unresolved publication separate from revenue',()=>{
 const f=capafyReportFixture();
 const result=buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[f.pending,f.pending,{...f.publish,completedAt:'2026-10-20T14:59:59Z'}]});
 assert.equal(result.providerActions.length,1);assert.equal(result.providerActions[0].status,'reconciling');
 assert.equal(result.publicationStatus,'unconfirmed');assert.equal(result.financial.gross.status,'unknown');
 assert.equal(result.actions.unconfirmedCycles,0);assert.match(renderMaritimeDailyEmail(result),/公開結果確認中/);
});
test('provider report rejects foreign tenants and broken source, prepare, agent and version chains',()=>{
 const f=capafyReportFixture();
 const mutations=[
  item=>{item.job.tenant_id='lm_22222222-2222-4222-8222-222222222222';},
  item=>{item.sourceCycleJob.job_id='maritime-cycle:foreign';},
  item=>{item.sourceCycleReceipt.artifact_refs=['artifact://other/package.json'];},
  item=>{item.prepareJob.job_id='maritime-prepare:foreign';},
  item=>{item.prepareReceipt.agent_version_id='other-version';},
  item=>{item.receipt.agent_id='other-agent';},
  item=>{item.receipt.account_ref='account://capafy/foreign';},
 ];
 for(const mutate of mutations){const item=structuredClone(f.publish);mutate(item);
  assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[item]}),/invalid/);}
 const pending=structuredClone(f.pending);pending.job.input_refs.agent_version_id='other-version';
 assert.throws(()=>buildMaritimeDailyResult({enrollment,periodKey,actionReceipts:[pending]}),/invalid/);
});
test('daily observations join immutable provider source and prepare rows and reject mismatched chains',async()=>{
 const f=capafyReportFixture();const sqlCalls=[];
 const financialStore={read:async()=>[]};
 const query=async(sql,params)=>{sqlCalls.push({sql,params});return {rows:[f.dbRow(f.prepare),f.dbRow(f.publish),f.dbRow(f.pending)]};};
 const observations=await readMaritimeDailyObservations({uid:UID,periodKey},{query,financialStore});
 assert.equal(observations.actionReceipts.length,3);
 assert.equal(observations.actionReceipts[1].sourceCycleJob.job_id,f.publish.sourceCycleJob.job_id);
 assert.equal(observations.actionReceipts[1].prepareJob.job_id,f.publish.prepareJob.job_id);
 assert.equal(observations.actionReceipts[2].status,'reconciling');assert.equal(observations.actionReceipts[2].receipt,undefined);
 const result=buildMaritimeDailyResult({enrollment,periodKey,...observations});assert.equal(result.financial.gross.status,'unknown');
 assert.match(sqlCalls[0].sql,/source_cycle_job_id/);assert.match(sqlCalls[0].sql,/prepare_job_id/);
 assert.match(sqlCalls[0].sql,/maritime\.manager\.capafy\.prepare/);assert.match(sqlCalls[0].sql,/maritime\.manager\.capafy\.publish/);
 const foreign=f.dbRow(f.publish);foreign.prepare_receipt={...foreign.prepare_receipt,agent_version_id:'foreign'};
 await assert.rejects(()=>readMaritimeDailyObservations({uid:UID,periodKey},{query:async()=>({rows:[foreign]}),financialStore}),/invalid/);
});

test('daily observations reject completed receipts outside their immutable central job',async()=>{
 const job={...buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:enrollment.release_sha,occurrenceId:'exact-cycle',dateKey:'2026-10-21'}),status:'completed',attempt:1};
 const foreign={schema_version:1,kind:'maritime_manager_cycle',tenant_id:UID,job_id:'maritime-cycle:foreign',
  occurrence_id:'exact-cycle',date_key:'2026-10-21',release_sha:enrollment.release_sha,agent_id:'agent-1',execution_id:'exec-1',
  status:'completed',artifact_refs:['artifact://original/product.json'],error_class:null,provider:'maritime',
  external_ref:'maritime-execution://agent-1/exec-1',evidence_refs:['maritime-execution://agent-1/exec-1']};
 await assert.rejects(()=>readMaritimeDailyObservations({uid:UID,periodKey},{
  query:async()=>({rows:[{job,receipt:foreign,completed_at:'2026-10-21T01:00:00Z'}]}),financialStore:{read:async()=>[]}}),/invalid/);
});
