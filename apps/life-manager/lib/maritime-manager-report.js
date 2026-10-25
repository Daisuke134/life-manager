'use strict';
const {buildFinancialManagerReport,formatFinancialAmount}=require('./financial-manager-report.js');
const {projectFinancialRecord}=require('./financial-record-contract.js');
const {buildMaritimeManagerCycleJob,createMaritimeManagerLoopAdapter,readMaritimeCycleContract}=require('./maritime-manager-runtime.js');
const {localDay,zoneOffsetHours}=require('./user-tz.js');

const CAPAFY_CAPABILITIES=new Set(['maritime.manager.capafy.prepare','maritime.manager.capafy.publish']);
function readProviderObservation(item,uid){
 try{
  const provider=require('./maritime-manager-provider-runtime.js');
  const identity=provider.readMaritimeCapafyJobContract(item.job);
  const source=item.sourceCycleJob,sourceReceipt=item.sourceCycleReceipt;
  const cycle=readMaritimeCycleContract(source);
  if(identity.tenantId!==uid||source.status!=='completed'||source.job_id!==identity.sourceCycleJobId
   ||cycle.tenantId!==uid||cycle.occurrenceId!==identity.occurrenceId||cycle.releaseSha!==identity.releaseSha
   ||!createMaritimeManagerLoopAdapter().verify(sourceReceipt,source)||sourceReceipt.status!=='completed'
   ||!sourceReceipt.artifact_refs.includes(identity.artifactRef))throw new Error();
  if(identity.phase==='publish'){
   const prepare=item.prepareJob,receipt=item.prepareReceipt;
   if(prepare?.status!=='completed'||prepare.job_id!==identity.prepareJobId
    ||!provider.verifyMaritimeCapafyPrepareReceipt(receipt,prepare,source,sourceReceipt)
    ||['source_cycle_job_id','artifact_ref','account_ref','occurrence_id','release_ref'].some(key=>prepare.input_refs[key]!==item.job.input_refs[key])
    ||receipt.agent_id!==identity.agentId||receipt.agent_version_id!==identity.agentVersionId)throw new Error();
  }
  if(item.receipt){
   const valid=identity.phase==='prepare'
    ?provider.verifyMaritimeCapafyPrepareReceipt(item.receipt,item.job,source,sourceReceipt)
    :provider.verifyMaritimeCapafyPublishReceipt(item.receipt,item.job,item.prepareJob,item.prepareReceipt,source,sourceReceipt);
   if(!valid)throw new Error();
  }else if(!['reconciling','dead_letter'].includes(item.status))throw new Error();
  return identity;
 }catch{throw new Error('maritime_daily_provider_observation_invalid');}
}

// Inputs are central queue receipts and trusted collector observations, never VM
// financial claims. Empty records do not establish complete provider coverage.
function buildMaritimeDailyResult({enrollment,periodKey,actionReceipts=[],financialRecords=[],financialCoverage=null,costs=null}={}){
 const invalid=()=>{throw new Error('maritime_daily_result_invalid');};
 const uid=enrollment?.uid,timezone=enrollment?.timezone||'UTC';
 const day=typeof periodKey==='string'&&periodKey.startsWith('maritime:daily:')?periodKey.slice(15):'';
 if(!/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(uid||'')||!/^\d{4}-\d{2}-\d{2}$/.test(day)
  ||!Number.isFinite(Date.parse(day))||new Date(day).toISOString().slice(0,10)!==day
  ||!Array.isArray(actionReceipts)||!Array.isArray(financialRecords))invalid();
 function coverage(value){
  if(value==null)return null;
  if(value.tenantId!==uid||value.periodKey!==periodKey||value.timezone!==timezone||typeof value.complete!=='boolean')invalid();
  if(!value.complete)return null;
  if(!Array.isArray(value.currencies)||!value.currencies.length||new Set(value.currencies).size!==value.currencies.length
   ||value.currencies.some(c=>typeof c!=='string'||!/^[A-Z][A-Z0-9_]{2,19}$/.test(c))
   ||!Array.isArray(value.evidenceRefs)||!value.evidenceRefs.length
   ||value.evidenceRefs.some(ref=>typeof ref!=='string'||! /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/.test(ref)))invalid();
  if(value.currencies.some(c=>['UNKNOWN','USD_API_EQUIV'].includes(c)))return null;
  return [...value.currencies].sort();
 }
 const financialCurrencies=coverage(financialCoverage),costCurrencies=coverage(costs);
 const expenseRecords=costs==null?[]:costs.records;
 if(!Array.isArray(expenseRecords))invalid();
 const recordIds=new Set();
 const records=[...financialRecords,...expenseRecords].map((raw,index)=>{
  const record=projectFinancialRecord(raw);
  const expense=index>=financialRecords.length;
  if(record.subject_id!==uid||record.scope!=='business'||recordIds.has(record.record_id)
   ||(expense&&!['business_cost','fee','tax'].includes(record.kind))
   ||((expense?costCurrencies:financialCurrencies)&&record.verification.status!=='verified'))invalid();
  recordIds.add(record.record_id);
  return record;
 });
 const {report}=buildFinancialManagerReport(records,day,{timezone});
 const summary=report.business.today;
 // The existing Capafy converter encodes refunds in this stable machine key.
 const refundRows=records.filter(r=>r.source.provider==='capafy'&&r.kind==='business_cost'
  &&/^capafy-financial:v1:\d{4}-\d{2}-\d{2}:refund$/.test(r.idempotency_key));
 const refunds=buildFinancialManagerReport(refundRows,day,{timezone}).report.business.today.costs;
 function metric(amounts,currencies){
  if(currencies){
   if(amounts.some(row=>!currencies.includes(row.currency)))invalid();
   return {status:'complete',amounts:currencies.map(currency=>({currency,amountMinor:amounts.find(row=>row.currency===currency)?.amountMinor||0}))};
  }
  return {status:amounts.length?'observed':'unknown',amounts};
 }
 const allComplete=financialCurrencies&&costCurrencies&&JSON.stringify(financialCurrencies)===JSON.stringify(costCurrencies);
 const financial={gross:metric(summary.revenue,financialCurrencies),refunds:metric(refunds,financialCurrencies),payouts:metric(summary.payouts,financialCurrencies),
  costs:metric(summary.costs,allComplete?financialCurrencies:null),
  profit:allComplete?metric(summary.profit,financialCurrencies).amounts:null};
 const actions={completedCycles:0,artifactCount:0,deferredCycles:0,unconfirmedCycles:0,failedCycles:0};
 const work=[];const providerActions=[];
 const seen=new Set();const verify=createMaritimeManagerLoopAdapter().verify;
 for(const item of actionReceipts){
  const receipt=item?.receipt,at=Date.parse(receipt?item?.completedAt:item?.observedAt);
  if(!Number.isFinite(at))invalid();
  if(CAPAFY_CAPABILITIES.has(item?.job?.capability)||['maritime_capafy_prepare','provider_action_receipt'].includes(receipt?.kind)){
   const identity=readProviderObservation(item,uid);
   if(localDay(at,zoneOffsetHours(timezone,at))!==day||seen.has(item.job.job_id))continue;
   seen.add(item.job.job_id);
   providerActions.push({jobId:item.job.job_id,sourceCycleJobId:identity.sourceCycleJobId,phase:identity.phase,
    status:receipt?receipt.status:item.status,artifactRef:identity.artifactRef,accountRef:identity.accountRef,
    agentId:receipt?.agent_id||identity.agentId||null,agentVersionId:receipt?.agent_version_id||identity.agentVersionId||null,
    url:receipt?.url||null,evidenceRefs:receipt?[...receipt.evidence_refs]:[]});
   continue;
  }
  if(!receipt){
   const identity=readMaritimeCycleContract(item.job);
   if(identity.tenantId!==uid||!['reconciling','dead_letter'].includes(item.status))invalid();
   if(localDay(at,zoneOffsetHours(timezone,at))!==day||seen.has(item.job.job_id))continue;
   seen.add(item.job.job_id);
   if(item.status==='reconciling')actions.unconfirmedCycles++;else actions.failedCycles++;
   const error=item.job.last_error_code;
   work.push({jobId:item.job.job_id,status:item.status,artifactRefs:[],evidenceRefs:[],
    errorClass:typeof error==='string'&&/^[A-Z][A-Z0-9_]{0,199}$/.test(error)?error:null});
   continue;
  }
  if(receipt.tenant_id!==uid)invalid();
  if(localDay(at,zoneOffsetHours(timezone,at))!==day)continue;
  const job=buildMaritimeManagerCycleJob({tenantId:uid,occurrenceId:receipt.occurrence_id,dateKey:receipt.date_key,releaseSha:receipt.release_sha});
  if(!verify(receipt,job))invalid();
  if(seen.has(receipt.job_id))continue;seen.add(receipt.job_id);
  work.push({jobId:receipt.job_id,status:receipt.status,artifactRefs:[...receipt.artifact_refs],evidenceRefs:[...receipt.evidence_refs],errorClass:receipt.error_class});
  if(receipt.status==='completed'){actions.completedCycles++;actions.artifactCount+=receipt.artifact_refs.length;}
  else actions.deferredCycles++;
 }
 const publicationStatus=providerActions.some(action=>['reconciling','dead_letter'].includes(action.status))?'unconfirmed'
  :providerActions.some(action=>action.status==='published')?'published'
  :providerActions.some(action=>action.status==='under_review')?'under_review'
  :providerActions.some(action=>action.status==='prepared')?'prepared':'unconfirmed';
 return {schemaVersion:1,tenantId:uid,periodKey,date:day,timezone,actions,work,providerActions,financial,publicationStatus};
}
function renderMaritimeDailyEmail(result,options={}){
 const origin=options.publicOrigin?require('./web-auth.js').publicOrigin(null,{publicOrigin:options.publicOrigin}):null;
 const {buildMaritimeArtifactPath}=require('./maritime-manager-artifacts.js');
 const amount=metric=>metric.status==='unknown'?'未確認':metric.amounts.map(formatFinancialAmount).join(' / ')+(metric.status==='observed'?'（確認済み小計）':'');
 return [
  `Life Managerの日次報告（${result.date}）`,
  '', '今日実行したこと',
  `確認できた仕事：${result.actions.completedCycles}件。成果物の記録：${result.actions.artifactCount}件。`,
  ...result.work.flatMap(work=>work.artifactRefs.flatMap(ref=>[
   '成果物：'+JSON.stringify(ref.slice('artifact://'.length)).slice(1,-1),
   ...(origin?[origin+buildMaritimeArtifactPath({jobId:work.jobId,artifactRef:ref})]:[]),
  ])),
  '', '確認できた成果と売上',
  '金額は接続先アカウントの確認済み明細です。Life Managerによる売上かは未確認です。',
  '公開状況：'+({published:'公開済み',under_review:'審査待ち',prepared:'公開準備完了'}[result.publicationStatus]||'未確認')+'。',
  ...(result.providerActions||[]).flatMap(action=>[
   'Capafy：'+({prepared:'公開準備完了',under_review:'審査待ち',published:'公開済み',reconciling:'公開結果確認中',dead_letter:'公開失敗・要確認'}[action.status]||'未確認')+'。',
   ...(action.url?[action.url]:[]),
  ]),
  `売上：${amount(result.financial.gross)}`,
  `返金：${amount(result.financial.refunds)}`,
  `入金：${amount(result.financial.payouts)}`,
  '', '費用',
  `費用：${amount(result.financial.costs)}（返金を含む）`,
  `利益：${result.financial.profit===null?'未確認（費用または売上の確認が未完了）':result.financial.profit.map(formatFinancialAmount).join(' / ')}`,
  '', '未完・失敗',
  `確認済みの保留：${result.actions.deferredCycles}件。結果確認中：${result.actions.unconfirmedCycles}件。失敗・要確認：${result.actions.failedCycles}件。`,
  ...result.work.filter(work=>work.status==='deferred').map(work=>['cloud_model_config_missing','cloud_runtime_not_ready'].includes(work.errorClass)?'保留理由：実行環境の準備待ちです。':'保留理由：実行できる仕事を確認できなかったためです。'),
  '未取得の金額は未確認と表示しています。',
  '', '次に進めること',
  '確認できた成果と利用状況をもとに、次の仕事を進めます。',
 ].join('\n');
}
async function deliverMaritimeDailyResult({enrollment,result,observedAt}={},deps={}){
 const invalid=()=>{throw new Error('maritime_daily_delivery_invalid');};
 const uid=enrollment?.uid;
 if(!result||result.tenantId!==uid||result.periodKey!==`maritime:daily:${result.date}`
  ||!/^\d{4}-\d{2}-\d{2}$/.test(result.date)||!Number.isFinite(Date.parse(result.date))
  ||new Date(result.date).toISOString().slice(0,10)!==result.date
  ||typeof observedAt!=='string'||!Number.isFinite(Date.parse(observedAt))||!/(Z|[+-]\d{2}:\d{2})$/.test(observedAt))invalid();
 const store=deps.managerStore||require('./maritime-manager-store.js').createMaritimeManagerStore(deps);
 const current=await store.read(uid);
 if(!current||current.uid!==uid||(current.timezone||'UTC')!==result.timezone)invalid();
 if(current.status!=='active'||current.paused_at){
  const error=new Error('maritime_daily_delivery_inactive');error.unknownEffect=false;throw error;
 }
 if(typeof current.email!=='string'||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(current.email))invalid();
 const env=deps.env||process.env;
 const origin=result.work.some(work=>work.artifactRefs.length)
  ?require('./web-auth.js').cloudPublicOrigin(null,{env}):null;
 return require('./cfo-cloud-delivery.js').deliverCloudCfoEmail({uid,periodKey:result.periodKey,
  message:renderMaritimeDailyEmail(result,{publicOrigin:origin}),observedAt,recipient:current.email},deps);
}
async function readMaritimeDailyObservations({uid,periodKey}={},deps={}){
 const day=typeof periodKey==='string'?periodKey.slice('maritime:daily:'.length):'';
 if(!/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(uid||'')
  ||periodKey!==`maritime:daily:${day}`||!/^\d{4}-\d{2}-\d{2}$/.test(day)
  ||!Number.isFinite(Date.parse(day))||new Date(day).toISOString().slice(0,10)!==day||typeof deps.query!=='function'){
  throw new Error('maritime_daily_observations_invalid');
 }
 // A three-day UTC window includes every local day (UTC-12 through UTC+14).
 // The existing builder applies the exact user's local-day filter afterwards.
 const from=new Date(Date.parse(day)-86400000).toISOString(),until=new Date(Date.parse(day)+2*86400000).toISOString();
 const rows=(await deps.query(`
  SELECT row_to_json(jobs) AS job, receipts.receipt, receipts.created_at AS completed_at,
   row_to_json(source_cycle) AS source_cycle_job, source_receipts.receipt AS source_cycle_receipt,
   row_to_json(prepare) AS prepare_job, prepare_receipts.receipt AS prepare_receipt
  FROM public.lm_runtime_jobs AS jobs
  LEFT JOIN public.lm_runtime_job_receipts AS receipts ON receipts.job_id=jobs.job_id
   AND receipts.tenant_id=jobs.tenant_id AND receipts.attempt=jobs.attempt
   AND receipts.outcome IN ('completed','reconciled_present')
  LEFT JOIN public.lm_runtime_jobs AS source_cycle
   ON source_cycle.job_id=jobs.input_refs->>'source_cycle_job_id'
   AND source_cycle.tenant_id=jobs.tenant_id AND source_cycle.capability='maritime.manager.cycle'
   AND source_cycle.status='completed'
  LEFT JOIN public.lm_runtime_job_receipts AS source_receipts ON source_receipts.job_id=source_cycle.job_id
   AND source_receipts.tenant_id=source_cycle.tenant_id AND source_receipts.attempt=source_cycle.attempt
   AND source_receipts.outcome IN ('completed','reconciled_present')
  LEFT JOIN public.lm_runtime_jobs AS prepare
   ON prepare.job_id=jobs.input_refs->>'prepare_job_id'
   AND prepare.tenant_id=jobs.tenant_id AND prepare.capability='maritime.manager.capafy.prepare'
   AND prepare.status='completed'
  LEFT JOIN public.lm_runtime_job_receipts AS prepare_receipts ON prepare_receipts.job_id=prepare.job_id
   AND prepare_receipts.tenant_id=prepare.tenant_id AND prepare_receipts.attempt=prepare.attempt
   AND prepare_receipts.outcome IN ('completed','reconciled_present')
  WHERE jobs.tenant_id = $1 AND jobs.capability IN
   ('maritime.manager.cycle','maritime.manager.capafy.prepare','maritime.manager.capafy.publish')
   AND jobs.status IN ('completed','reconciling','dead_letter')
   AND COALESCE(jobs.completed_at,jobs.updated_at) >= $2::timestamptz
   AND COALESCE(jobs.completed_at,jobs.updated_at) < $3::timestamptz
  ORDER BY COALESCE(jobs.completed_at,jobs.updated_at),jobs.job_id LIMIT 1001
 `,[uid,from,until])).rows;
 if(!Array.isArray(rows)||rows.length>1000)throw new Error('maritime_daily_observations_invalid');
 const actionReceipts=rows.map(row=>{
  const job=row.job,invalid=()=>{throw new Error('maritime_daily_observations_invalid');};
  if(!job||job.tenant_id!==uid||!['completed','reconciling','dead_letter'].includes(job.status))invalid();
  function timestamp(value){if(value==null||!Number.isFinite(new Date(value).getTime()))invalid();return new Date(value).toISOString();}
  const item=job.status==='completed'
   ?{job,receipt:row.receipt,completedAt:timestamp(row.completed_at)}
   :{job,status:job.status,observedAt:timestamp(job.updated_at)};
  if(job.status==='completed'&&!row.receipt)invalid();
  if(CAPAFY_CAPABILITIES.has(job.capability)){
   Object.assign(item,{sourceCycleJob:row.source_cycle_job,sourceCycleReceipt:row.source_cycle_receipt,
    prepareJob:row.prepare_job,prepareReceipt:row.prepare_receipt});
   readProviderObservation(item,uid);
  }else{
   if(readMaritimeCycleContract(job).tenantId!==uid)invalid();
   if(item.receipt&&!createMaritimeManagerLoopAdapter().verify(item.receipt,job))invalid();
  }
  return item;
 });
 const financialStore=deps.financialStore||require('./financial-record-store.js').createPostgresFinancialRecordStore({query:deps.query});
 const financialRecords=(await financialStore.read({subjectId:uid,scope:'business',since:from})).filter(record=>Date.parse(record.occurred_at)<Date.parse(until));
 // Read existing observations only. Account totals do not establish Cloud attribution
 // or complete provider/cost coverage, and are never appended as new transactions.
 return {actionReceipts,financialRecords};
}
module.exports={buildMaritimeDailyResult,renderMaritimeDailyEmail,deliverMaritimeDailyResult,readMaritimeDailyObservations};
