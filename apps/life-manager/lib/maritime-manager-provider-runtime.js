"use strict";
const {createHash} = require("node:crypto");
const {isDeepStrictEqual} = require("node:util");
const {buildRuntimeJob} = require("./runtime-job-store.js");
const {readMaritimeCycleContract,createMaritimeManagerLoopAdapter} = require("./maritime-manager-runtime.js");
const {CAPAFY_PUBLISHER_AGREEMENT_VERSION} = require("./maritime-manager-capafy-consent.js");

class ProviderError extends Error {
  constructor(code,unknownEffect=false) {super(code);this.code=code.toUpperCase();this.unknownEffect=unknownEffect;}
}
const invalid = () => {throw new ProviderError("maritime_capafy_chain_invalid");};
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256=/^[a-f0-9]{64}$/;
function providerJob(phase,input={}) {
  if((input.skillId===undefined)!==(input.disclosureSha256===undefined)
    ||(input.skillId!==undefined&&(!ID.test(input.skillId)||!SHA256.test(input.disclosureSha256))))
    throw new ProviderError(input.skillId===undefined?"maritime_capafy_skill_id_required":"maritime_capafy_skill_data_disclosure_required");
  const refs={source_cycle_job_id:input.sourceCycleJobId||input.cycleJobId,artifact_ref:input.artifactRef,
    account_ref:input.accountRef,occurrence_id:input.occurrenceId,release_ref:`release://git/${input.releaseSha}`,
    ...(input.skillId===undefined?{}:{skill_id:input.skillId,skill_disclosure_sha256:input.disclosureSha256}),
    ...(phase==="publish"?{prepare_job_id:input.prepareJobId,agent_id:input.agentId,agent_version_id:input.agentVersionId}:{})};
  const digest=createHash("sha256").update(`maritime-capafy-${phase}:v1:${input.tenantId}:${input.occurrenceId}`).digest("hex");
  return buildRuntimeJob({jobId:`maritime-capafy-${phase}:${digest}`,tenantId:input.tenantId,
    loopId:`maritime.manager.capafy.${phase}`,capability:`maritime.manager.capafy.${phase}`,
    effectClass:"publish",effectKey:`maritime-capafy-${phase}://${input.tenantId}/${encodeURIComponent(input.occurrenceId)}`,
    maxAttempts:1,inputRefs:refs});
}
const buildMaritimeCapafyPrepareJob=input=>providerJob("prepare",input);
const buildMaritimeCapafyPublishJob=input=>providerJob("publish",input);
function readMaritimeCapafyJobContract(job) {
  try {
    const normalized=buildRuntimeJob(job),refs=normalized.input_refs;
    const phase=normalized.capability==="maritime.manager.capafy.prepare"?"prepare":
      normalized.capability==="maritime.manager.capafy.publish"?"publish":null;
    if(!phase)invalid();
    const c={phase,tenantId:normalized.tenant_id,releaseSha:refs.release_ref.slice(14),
      occurrenceId:refs.occurrence_id,sourceCycleJobId:refs.source_cycle_job_id,
      artifactRef:refs.artifact_ref,accountRef:refs.account_ref,
      ...(refs.skill_id===undefined?{}:{skillId:refs.skill_id,disclosureSha256:refs.skill_disclosure_sha256}),
      ...(phase==="publish"?{prepareJobId:refs.prepare_job_id,agentId:refs.agent_id,agentVersionId:refs.agent_version_id}:{})};
    if((refs.skill_id===undefined)!==(refs.skill_disclosure_sha256===undefined)
      ||(refs.skill_id!==undefined&&(!ID.test(refs.skill_id)||!SHA256.test(refs.skill_disclosure_sha256))))invalid();
    if(!isDeepStrictEqual(normalized,providerJob(phase,c)))invalid();
    return Object.freeze(c);
  } catch {invalid();}
}
function verifyCycle(c,job,receipt) {
  try {
    const source=readMaritimeCycleContract(job);
    return job.status==="completed" && job.job_id===c.sourceCycleJobId && source.tenantId===c.tenantId
      && source.releaseSha===c.releaseSha && source.occurrenceId===c.occurrenceId
      && createMaritimeManagerLoopAdapter().verify(receipt,job) && receipt.status==="completed"
      && receipt.providerSnapshotRef === undefined && receipt.providerReceiptRefs === undefined
      && receipt.artifact_refs.includes(c.artifactRef);
  } catch {return false;}
}
function officialUrl(value,agentId) {
  try {
    const url=new URL(value);
    return url.protocol==="https:" && ["capafy.ai","www.capafy.ai"].includes(url.hostname)
      && !url.port && !url.username && !url.password && !url.search && !url.hash
      && url.pathname.split("/").includes(agentId);
  } catch {return false;}
}
function credentialFree(value) {
  if(typeof value==="string")return !/am_sk_[A-Za-z0-9_-]{16,480}|Bearer\s+\S+/i.test(value);
  if(Array.isArray(value))return value.every(credentialFree);
  if(value && typeof value==="object")return Object.entries(value).every(([key,item])=>
    !/(?:access.?token|api.?key|authorization|password|secret|credential)/i.test(key)&&credentialFree(item));
  return true;
}
function hasExactReceiptKeys(receipt,job,contract) {
  if(!receipt || typeof receipt!=="object" || Array.isArray(receipt))return false;
  const prototype=Object.getPrototypeOf(receipt);
  if(prototype!==Object.prototype && prototype!==null)return false;
  const keys=Reflect.ownKeys(receipt);
  if(keys.some(key=>typeof key!=="string"))return false;
  const allowed=new Set(["schema_version","kind","tenant_id","job_id","attempt","effect_key","provider",
    ...Object.keys(job.input_refs),"status","url","external_ref","evidence_refs","observed_at"]);
  if(contract.phase==="prepare"){
    allowed.add("agent_id");allowed.add("agent_version_id");
  }
  return keys.length===allowed.size && keys.every(key=>allowed.has(key));
}
function verifyReceipt(receipt,job,statuses) {
  try {
    const c=readMaritimeCapafyJobContract(job),ref=`capafy-action://${job.job_id}/1`;
    return hasExactReceiptKeys(receipt,job,c) && credentialFree(receipt) && job.attempt===1
      && receipt.schema_version===1 && receipt.tenant_id===c.tenantId
      && receipt.job_id===job.job_id && receipt.attempt===1 && receipt.effect_key===job.effect_key
      && receipt.provider==="capafy" && statuses.includes(receipt.status)
      && receipt.kind===(c.phase==="prepare"?"maritime_capafy_prepare":"provider_action_receipt")
      && Object.entries(job.input_refs).every(([key,value])=>receipt[key]===value)
      && ID.test(receipt.agent_id||"") && ID.test(receipt.agent_version_id||"")
      && officialUrl(receipt.url,receipt.agent_id) && receipt.external_ref===ref
      && isDeepStrictEqual(receipt.evidence_refs,[ref])
      && typeof receipt.observed_at==="string" && Number.isFinite(Date.parse(receipt.observed_at))
      && new Date(receipt.observed_at).toISOString()===receipt.observed_at;
  } catch {return false;}
}
function verifyMaritimeCapafyPrepareReceipt(receipt,job,sourceCycleJob,sourceCycleReceipt) {
  try {
    const c=readMaritimeCapafyJobContract(job);
    return c.phase==="prepare" && verifyCycle(c,sourceCycleJob,sourceCycleReceipt)
      && verifyReceipt(receipt,job,["prepared"]);
  } catch {return false;}
}
function verifyMaritimeCapafyPublishReceipt(receipt,job,prepareJob,prepareReceipt,sourceCycleJob,sourceCycleReceipt) {
  try {
    const c=readMaritimeCapafyJobContract(job);
    return c.phase==="publish" && prepareJob?.status==="completed" && prepareJob.job_id===c.prepareJobId
      && verifyMaritimeCapafyPrepareReceipt(prepareReceipt,prepareJob,sourceCycleJob,sourceCycleReceipt)
      && ["source_cycle_job_id","artifact_ref","account_ref","occurrence_id","release_ref"]
        .every(key=>prepareJob.input_refs[key]===job.input_refs[key])
      && prepareReceipt.agent_id===c.agentId && prepareReceipt.agent_version_id===c.agentVersionId
      && verifyReceipt(receipt,job,["under_review","published"]);
  } catch {return false;}
}
async function withProviderAccess(provider,expectedIdentity,operation,mode="action") {
  if(typeof provider?.withAccessToken!=="function")throw new ProviderError("maritime_capafy_unconfigured");
  return provider.withAccessToken({tenantId:expectedIdentity.tenantId,accountRef:expectedIdentity.accountRef,
    skillId:expectedIdentity.skillId,disclosureSha256:expectedIdentity.disclosureSha256},async(accessToken,identity)=>{
    if(typeof accessToken!=="string" || identity?.provider!=="capafy"
      || identity.tenantId!==expectedIdentity.tenantId || identity.accountRef!==expectedIdentity.accountRef
      || identity.providerSubject!==expectedIdentity.providerSubject
      || identity.autonomyConsentVersion!==expectedIdentity.autonomyConsentVersion
      || identity.publisherAgreementVersion!==CAPAFY_PUBLISHER_AGREEMENT_VERSION)
      throw new ProviderError("maritime_capafy_identity_mismatch");
    return operation({accessToken,identity});
  },{mode});
}
function createAdapter(phase,services={}) {
  const provider=services.provider;
  async function publisherConfirmed(bound,agentId,agentVersionId) {
    if(typeof provider?.readPublisherConfirmation!=="function")return false;
    const proof=await withProviderAccess(provider,bound.account,({accessToken,identity})=>
      provider.readPublisherConfirmation({identity,agentId,agentVersionId,accessToken}),"readback");
    return proof?.agentId===agentId && proof.agentVersionId===agentVersionId
      && proof.isConfirmedSkills===true && proof.isConfirmedConfigKeys===true;
  }
  async function context(job,{active=false,guard=false}={}) {
    const c=readMaritimeCapafyJobContract(job);
    if(c.phase!==phase || job.attempt!==1)invalid();
    if(!provider || typeof provider.readAccountBinding!=="function"
      || typeof services.readCompletedCycle!=="function")throw new ProviderError("maritime_capafy_unconfigured");
    const account=await provider.readAccountBinding({tenantId:c.tenantId,accountRef:c.accountRef});
    if(account?.provider!=="capafy" || account.tenantId!==c.tenantId || account.accountRef!==c.accountRef
      || account.publisherAgreementVersion!==CAPAFY_PUBLISHER_AGREEMENT_VERSION)invalid();
    if(active) {
      const enrollment=await services.managerStore?.read(c.tenantId);
      if(enrollment?.uid!==c.tenantId || enrollment.status!=="active" || enrollment.paused_at
        || enrollment.release_sha!==c.releaseSha)throw new ProviderError("maritime_capafy_inactive");
    }
    const cycle=await services.readCompletedCycle({tenantId:c.tenantId,jobId:c.sourceCycleJobId});
    if(!verifyCycle(c,cycle?.job,cycle?.receipt))invalid();
    let prepared=null;
    if(phase==="publish") {
      if(typeof services.readPrepareReceipt!=="function")throw new ProviderError("maritime_capafy_unconfigured");
      prepared=await services.readPrepareReceipt({tenantId:c.tenantId,jobId:c.prepareJobId});
      if(prepared?.job?.status!=="completed" || prepared.job.job_id!==c.prepareJobId
        || !verifyMaritimeCapafyPrepareReceipt(prepared.receipt,prepared.job,cycle.job,cycle.receipt)
        || ["source_cycle_job_id","artifact_ref","account_ref","occurrence_id","release_ref"]
          .some(key=>prepared.job.input_refs[key]!==job.input_refs[key])
        || prepared.receipt.agent_id!==c.agentId || prepared.receipt.agent_version_id!==c.agentVersionId)invalid();
    }
    if(guard) {
      if(typeof provider.guardArtifact!=="function")throw new ProviderError("maritime_capafy_unconfigured");
      const gate=await withProviderAccess(provider,{...account,skillId:c.skillId,disclosureSha256:c.disclosureSha256},({accessToken,identity})=>
        provider.guardArtifact({identity,...c,accessToken}));
      if(gate?.original!==true || gate.frozen!==false || gate.duplicate!==false)
        throw new ProviderError("maritime_capafy_artifact_rejected");
    }
    return {c,cycle,prepared,account};
  }
  function verifyWithContext(receipt,job,bound) {
    return phase==="prepare"
      ?verifyMaritimeCapafyPrepareReceipt(receipt,job,bound.cycle.job,bound.cycle.receipt)
      :verifyMaritimeCapafyPublishReceipt(receipt,job,bound.prepared.job,bound.prepared.receipt,bound.cycle.job,bound.cycle.receipt);
  }
  async function inspect(job,bound) {
    if(phase==="publish") {
      let enrollment;
      try {enrollment=await services.managerStore?.read(bound.c.tenantId);}catch {}
      if(enrollment?.uid!==bound.c.tenantId || enrollment.status!=="active" || enrollment.paused_at)
        return {state:"unknown",errorClass:"maritime_capafy_manager_paused",nextAction:"resume_manager",retryable:false};
      if(!await publisherConfirmed(bound,bound.c.agentId,bound.c.agentVersionId))
        return {state:"unknown",errorClass:"maritime_capafy_publisher_confirmation_required",
          nextAction:"confirm_in_capafy",retryable:false};
    }
    const read=provider[phase==="prepare"?"readPrepare":"readPublish"];
    if(typeof read!=="function")throw new ProviderError("maritime_capafy_unconfigured");
    // This trusted host service must read official target and action evidence.
    // VM stdout and model output never supply a provider receipt.
    const proof=await withProviderAccess(provider,bound.account,({accessToken,identity})=>
      read({job,identity,accessToken}),"readback");
    if(proof?.state==="present" && verifyWithContext(proof.receipt,job,bound))return proof;
    if(proof?.state==="absent" && verifyWithContext({...proof.receipt,status:phase==="prepare"?"prepared":"under_review"},job,bound)
      && proof.receipt.status==="absent")return phase==="publish"
        ?{state:"unknown",errorClass:"maritime_capafy_submission_required",nextAction:"submit_for_review_in_capafy",retryable:false}
        :proof;
    return {state:"unknown",errorClass:"maritime_capafy_readback_unknown",nextAction:"inspect_provider_action",retryable:false};
  }
  return Object.freeze({
    plan:async input=>[providerJob(phase,input)],
    async execute(job) {
      // Publish jobs now only read back the Publisher's own Capafy action. Keep
      // them durable across pause; inspect() holds provider reads until resume.
      const bound=await context(job,{active:phase==="prepare",guard:phase==="prepare"});
      if(job.status!=="running")invalid();
      if(phase==="publish") {
        // Capafy requires the publisher to submit each Agent version through its website.
        // Keep a durable readback fence while the publisher completes those website steps.
        const proof=await inspect(job,bound);
        if(proof.state==="present")return {receipt:proof.receipt};
        throw new ProviderError(proof.errorClass||"maritime_capafy_publish_readback_unknown",true);
      }
      const dispatch=provider[phase];
      if(typeof dispatch!=="function")throw new ProviderError("maritime_capafy_unconfigured");
      try {
        await withProviderAccess(provider,{...bound.account,skillId:bound.c.skillId,
          disclosureSha256:bound.c.disclosureSha256},({accessToken,identity})=>
          dispatch({job,identity,accessToken}));
        const proof=await inspect(job,bound);
        if(proof.state==="present")return {receipt:proof.receipt};
        throw new ProviderError("maritime_capafy_effect_unknown",true);
      } catch(error) {
        if(error instanceof ProviderError && error.unknownEffect)throw error;
        throw new ProviderError("maritime_capafy_effect_unknown",true);
      }
    },
    async reconcile(job) {
      try {return await inspect(job,await context(job));}
      catch {return {state:"unknown",errorClass:"maritime_capafy_readback_unknown",nextAction:"inspect_provider_action",retryable:false};}
    },
    async verify(receipt,job) {
      try {return verifyWithContext(receipt,job,await context(job));}catch{return false;}
    },
    async continuation(job,receipt) {
      if(phase!=="prepare")return null;
      const bound=await context(job);
      if(!verifyWithContext(receipt,job,bound))invalid();
      const availableAt=(services.now||(()=>new Date().toISOString()))();
      if(!Number.isFinite(Date.parse(availableAt)))invalid();
      return {job:buildMaritimeCapafyPublishJob({...bound.c,prepareJobId:job.job_id,
        agentId:receipt.agent_id,agentVersionId:receipt.agent_version_id}),availableAt:new Date(availableAt).toISOString()};
    },
    report:receipt=>({status:receipt?.status||"unknown",provider:"capafy"}),
  });
}
// Called by a trusted host after durable central cycle completion. No account
// is inferred from model output, a founder profile, or a VM environment variable.
async function enqueueMaritimeCapafyPrepareFromCycle({job,receipt,skillId,disclosureSha256}={},services={}) {
  const c=readMaritimeCycleContract(job),provider=services.provider;
  if(!provider || typeof provider.readAccountBinding!=="function" || typeof provider.guardArtifact!=="function"
    || typeof services.enqueueJob!=="function")throw new ProviderError("maritime_capafy_unconfigured");
  const account=await provider.readAccountBinding({tenantId:c.tenantId});
  if(account?.tenantId!==c.tenantId || account.provider!=="capafy")invalid();
  const enrollment=await services.managerStore?.read(c.tenantId);
  if(enrollment?.uid!==c.tenantId || enrollment.status!=="active" || enrollment.paused_at
    || enrollment.release_sha!==c.releaseSha)throw new ProviderError("maritime_capafy_inactive");
  if(typeof provider.withAccessToken!=="function")throw new ProviderError("maritime_capafy_unconfigured");
  for(const artifactRef of receipt?.artifact_refs||[]) {
    const identity={...c,sourceCycleJobId:job.job_id,artifactRef,accountRef:account.accountRef,
      ...(skillId===undefined?{}:{skillId}),...(disclosureSha256===undefined?{}:{disclosureSha256})};
    if(!verifyCycle(identity,job,receipt))invalid();
    const next=buildMaritimeCapafyPrepareJob(identity);
    const gate=await withProviderAccess(provider,{...account,skillId:identity.skillId,
      disclosureSha256:identity.disclosureSha256},({accessToken,identity:bound})=>
      provider.guardArtifact({identity:bound,...identity,accessToken}));
    if(gate?.original===true && gate.frozen===false && gate.duplicate===false)return services.enqueueJob(next);
  }
  throw new ProviderError("maritime_capafy_artifact_rejected");
}
const createMaritimeManagerCapafyPrepareAdapter=services=>createAdapter("prepare",services);
const createMaritimeManagerCapafyPublishAdapter=services=>createAdapter("publish",services);
module.exports={enqueueMaritimeCapafyPrepareFromCycle,buildMaritimeCapafyPrepareJob,buildMaritimeCapafyPublishJob,readMaritimeCapafyJobContract,
  verifyMaritimeCapafyPrepareReceipt,verifyMaritimeCapafyPublishReceipt,
  createMaritimeManagerCapafyPrepareAdapter,createMaritimeManagerCapafyPublishAdapter};
