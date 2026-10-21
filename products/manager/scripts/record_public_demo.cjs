/** Render the actual captured kernel execution as a short, silent evidence demo. */
const fs=require('fs');
const path=require('path');
const {chromium}=require('../tests/e2e/node_modules/playwright');
const {execFileSync}=require('child_process');
const root=path.resolve(__dirname,'..');
const data=JSON.parse(fs.readFileSync(path.join(root,'docs/demos/manager-public-no-action-20261022.json')));
if(data.source!=='ACTUAL_PUBLIC_HTTPS_READBACK'||data.decision!=='NO_ACTION'||!data.trace_valid||data.observed_pages!==6)throw Error('actual verified demo capture required');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const steps=[
 ['01 / OBSERVE','Read the actual public environment',`${data.observed_pages} public pages fetched over HTTPS.<br>Every page matched its published SHA-256 digest.`,data.public_url],
 ['02 / PROPOSE','Compare an action with NO_ACTION',`Candidate: republish the identical artifact.<br>Alternative: keep the current verified public state.`,`Source ${data.source_commit}`],
 ['03 / EVALUATE','No useful change was proposed',`Changed pages: ${data.changed_pages.length}<br>The baseline and candidate manifests are identical.`,`Effect ${data.effect_key}`],
 ['04 / DECIDE','NO_ACTION',`The actual kernel selected NO_ACTION.<br>External writes: ${data.external_writes}. No duplicate publish.`,`Audit chain valid: ${data.trace_valid}`],
 ['05 / EXPLAIN','Public proof has a clear boundary',`Real: public observation + executed software decision.<br>Human outcomes: ${data.human_outcome}.<br>No new intervention or causal welfare result.`,`Captured ${data.captured_at}`]
];
const html=`<!doctype html><html lang="en"><meta charset="utf-8"><title>Manager — real public decision demo</title><style>*{box-sizing:border-box}body{margin:0;background:#101c18;color:#f2f6ec;font-family:Arial,sans-serif}.shell{width:1280px;height:720px;padding:65px 80px;display:flex;flex-direction:column}.brand{font-size:20px;letter-spacing:5px;color:#b7d2bf}.badge{float:right;letter-spacing:1px;font-size:14px;color:#c6d2cb}.step{font-size:18px;color:#c4dd87;margin-top:62px}h1{font-size:49px;line-height:1.12;max-width:1000px;margin:22px 0 28px;font-weight:600}p{font-size:28px;line-height:1.6;margin:0;max-width:1070px}.detail{margin-top:28px;font:16px/1.5 monospace;color:#a6bdb0;overflow-wrap:anywhere}.foot{margin-top:auto;font-size:15px;color:#a6bdb0;display:flex;justify-content:space-between}.track{height:4px;background:#2d4638;margin-top:20px}.progress{height:4px;background:#c4dd87;transition:width .25s}</style><div class="shell"><div class="brand">MANAGER<span class="badge">RECORDED CODE OUTPUT · READ ONLY</span></div><div id="step" class="step"></div><h1 id="title"></h1><p id="body"></p><div id="detail" class="detail"></div><div class="foot"><span>Observe → compare → act or abstain → retain evidence</span><span>Human welfare is NOT_MEASURED</span></div><div class="track"><div id="progress" class="progress"></div></div></div>`;
(async()=>{
 const out=path.join(root,'output/demo-recording');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:out,size:{width:1280,height:720}}});
 const page=await context.newPage();await page.setContent(html);
 for(let i=0;i<steps.length;i++){
  const [k,t,b,d]=steps[i];await page.evaluate(({k,t,b,d,i})=>{document.querySelector('#step').textContent=k;document.querySelector('#title').textContent=t;document.querySelector('#body').innerHTML=b;document.querySelector('#detail').textContent=d;document.querySelector('#progress').style.width=((i+1)*20)+'%'},{k,t,b,d,i});
  if(i===3)await page.screenshot({path:path.join(out,'demo-preview.png')});
  await page.waitForTimeout(4500);
 }
 const video=page.video();await context.close();await browser.close();const captured=await video.path();
 const target=path.join(root,'docs/demos/manager-public-no-action-20261022.mp4');
 execFileSync('ffmpeg',['-y','-i',captured,'-an','-c:v','libx264','-crf','24','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',target],{stdio:'pipe'});
 console.log(JSON.stringify({video:target,capture:path.join(root,'docs/demos/manager-public-no-action-20261022.json'),screens:steps.length}));
})().catch(e=>{console.error(e);process.exit(1)});
