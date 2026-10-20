'use strict';
const {maritimeArtifactRefsValid,readMaritimeCycleContract,createMaritimeManagerLoopAdapter}=require('./maritime-manager-runtime.js');
const PREFIX='/maritime/artifacts/';
function artifactIdentity(jobId,artifactRef){
 if(typeof jobId!=='string'||!/^maritime-cycle:[0-9a-f]{64}$/.test(jobId)||!maritimeArtifactRefsValid([artifactRef],true))throw new Error('maritime_artifact_invalid');
 return {jobId,artifactRef};
}
function buildMaritimeArtifactPath({jobId,artifactRef}){
 artifactIdentity(jobId,artifactRef);
 return PREFIX+encodeURIComponent(jobId)+'/'+artifactRef.slice('artifact://'.length).split('/').map(encodeURIComponent).join('/');
}
function parsePath(path){
 const parts=path.slice(PREFIX.length).split('/').map(decodeURIComponent);
 if(parts.some(part=>part.includes('/')))throw new Error('maritime_artifact_invalid');
 return artifactIdentity(parts.shift(),'artifact://'+parts.join('/'));
}
async function readVerifiedArtifact({uid,jobId,artifactRef},options){
 const job=await (options.readCommonJob||require('./runtime-job-store.js').readCommonJob)({tenantId:uid,jobId},options.storeOptions||{});
 if(!job||job.tenant_id!==uid||job.job_id!==jobId)return null;
 const identity=readMaritimeCycleContract(job);
 if(identity.tenantId!==uid)return null;
 const env=options.env||process.env;
 const managerStore=options.managerStore||require('./maritime-manager-store.js').createMaritimeManagerStore({env});
 const transport=options.transport||require('./transport/maritime-manager.js').createMaritimeManagerTransport({env,managerStore});
 const adapter=options.cycleAdapter||createMaritimeManagerLoopAdapter({managerStore,...transport});
 const proof=await adapter.reconcile(job);
 if(proof?.state!=='present'||!adapter.verify(proof.receipt,job)||proof.receipt.status!=='completed'
  ||!proof.receipt.artifact_refs.includes(artifactRef))return null;
 return transport.readArtifact({uid,agentId:proof.receipt.agent_id,artifactRef});
}
async function handleMaritimeManagerArtifact(req,res,options={}){
 const path=new URL(req.url||'/', 'http://localhost').pathname;
 if(!path.startsWith(PREFIX))return false;
 const headers={'cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff',
  'content-security-policy':"default-src 'none'; base-uri 'none'; frame-ancestors 'none'",'vary':'Cookie'};
 function send(status,text){res.writeHead(status,{'content-type':'text/plain; charset=utf-8',...headers});res.end(text);}
 if(req.method!=='GET'){send(405,'この操作にはGETが必要です。');return true;}
 let input;
 try{input=parsePath(path);}catch{send(404,'このファイルは見つかりませんでした。');return true;}
 if((options.env||process.env).LM_MARITIME_MANAGER_EMAIL_ENABLED!=='1'){send(503,'現在、利用できません。');return true;}
 try{
  const user=await (options.resolveUser||require('./maritime-manager-auth.js').resolveMaritimeManagerUser)(req,res,options);
  if(!user){
   res.writeHead(401,{'content-type':'text/html; charset=utf-8',...headers});
   res.end('<!doctype html><html lang="ja"><meta charset="utf-8"><title>ログインが必要です</title><p>登録メールでログインしてから、このリンクをもう一度開いてください。</p><a href="/maritime">Life Managerへ</a></html>');return true;
  }
  const bytes=await readVerifiedArtifact({...input,uid:user.uid},options);
  if(bytes===null){send(404,'このファイルは見つからないか、結果を確認中です。');return true;}
  if(!(bytes instanceof Uint8Array)||bytes.byteLength>20*1024*1024)throw new Error('maritime_artifact_unavailable');
  const filename=input.artifactRef.split('/').at(-1);
  res.writeHead(200,{...headers,'content-type':'application/octet-stream',
   'content-disposition':`attachment; filename="artifact"; filename*=UTF-8''${encodeURIComponent(filename).replace(/['()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase())}`});
  res.end(bytes);
  void require('./maritime-manager-usage.js').observeMaritimeUsage('returned',user.uid,signal=>(options.recordReturn||require('./maritime-manager-usage.js').recordMaritimeManagerReturn)(user.uid,{...options,signal,request:req}),options);
 }catch{send(503,'ファイルを取得できません。しばらくしてからもう一度お試しください。');}
 return true;
}
module.exports={buildMaritimeArtifactPath,handleMaritimeManagerArtifact};
