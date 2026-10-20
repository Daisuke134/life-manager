'use strict';
const {buildFinancialManagerReport,formatFinancialAmount}=require('./financial-manager-report.js');
const {projectFinancialRecord}=require('./financial-record-contract.js');
const {buildMaritimeManagerCycleJob,createMaritimeManagerLoopAdapter,readMaritimeCycleContract}=require('./maritime-manager-runtime.js');
const {localDay,zoneOffsetHours}=require('./user-tz.js');

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
 const work=[];
 const seen=new Set();const verify=createMaritimeManagerLoopAdapter().verify;
 for(const item of actionReceipts){
  const receipt=item?.receipt,at=Date.parse(item?.completedAt);
  if(!Number.isFinite(at))invalid();
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
 return {schemaVersion:1,tenantId:uid,periodKey,date:day,timezone,actions,work,financial,publicationStatus:'unconfirmed'};
}
function renderMaritimeDailyEmail(result){
 const amount=metric=>metric.status==='unknown'?'未確認':metric.amounts.map(formatFinancialAmount).join(' / ')+(metric.status==='observed'?'（確認済み小計）':'');
 return [
  `Life Managerの日次報告（${result.date}）`,
  '', '今日実行したこと',
  `確認できた仕事：${result.actions.completedCycles}件。作成したファイル：${result.actions.artifactCount}件。`,
  ...result.work.flatMap(work=>work.artifactRefs.map(ref=>'作成：'+ref.slice('artifact://'.length))),
  '', '確認できた成果と売上',
  '公開状況：未確認。ファイル作成を公開・販売の完了とは数えていません。',
  `売上：${amount(result.financial.gross)}`,
  `返金：${amount(result.financial.refunds)}`,
  `入金：${amount(result.financial.payouts)}`,
  '', '費用',
  `費用：${amount(result.financial.costs)}（返金を含む）`,
  `利益：${result.financial.profit===null?'未確認（費用または売上の確認が未完了）':result.financial.profit.map(formatFinancialAmount).join(' / ')}`,
  '', '未完・失敗',
  `確認済みの保留：${result.actions.deferredCycles}件。結果確認中：${result.actions.unconfirmedCycles}件。失敗・要確認：${result.actions.failedCycles}件。`,
  ...result.work.filter(work=>work.status==='deferred').map(work=>work.errorClass==='cloud_model_config_missing'?'保留理由：実行環境の準備待ちです。':'保留理由：実行できる仕事を確認できなかったためです。'),
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
 return require('./cfo-cloud-delivery.js').deliverCloudCfoEmail({uid,periodKey:result.periodKey,
  message:renderMaritimeDailyEmail(result),observedAt,recipient:current.email},deps);
}
module.exports={buildMaritimeDailyResult,renderMaritimeDailyEmail,deliverMaritimeDailyResult};
