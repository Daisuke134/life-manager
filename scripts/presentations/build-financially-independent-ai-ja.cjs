const fs = require("fs");
const os = require("os");
const path = require("path");
const pptxgen = require("pptxgenjs");
const ROOT = path.resolve(__dirname, "../..");
const skillRoot = process.env.PPTX_SKILL_ROOT;
if (!skillRoot) {
  throw new Error("PPTX_SKILL_ROOT is required; provision the presentation skill explicitly");
}
const html2pptx = require(path.join(skillRoot, "scripts/html2pptx.js"));

const OUT = path.join(ROOT, "docs/presentations/how-to-make-a-financially-independent-ai-ja.pptx");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "ae-jp-deck-"));

const C = {
  bg: "#101418",
  paper: "#F6F0E6",
  ink: "#17201F",
  green: "#77F2A1",
  greenDark: "#164F36",
  amber: "#FFB454",
  red: "#FF6B6B",
  blue: "#6CB8FF",
  mute: "#9CAAA6",
  panel: "#1A2226",
  line: "#324047",
  white: "#FFFFFF",
};

const slides = [
  {
    kicker: "AGENT ECONOMY / 01",
    title: "AIを経済的に\n自立させる方法",
    subtitle: "自分で稼ぎ、自分の計算資源とクラウド代を払う",
    footer: "Definition → Wallet → Earn → Verify → Survive",
    body: `
      <div class="hero-flow">
        <div class="flow-node green"><p>稼ぐ</p><span><p>SELL / WORK</p></span></div>
        <div class="arrow"><p>→</p></div>
        <div class="flow-node"><p>検証</p><span><p>receipt</p></span></div>
        <div class="arrow"><p>→</p></div>
        <div class="flow-node"><p>生きる</p><span><p>compute / cloud</p></span></div>
        <div class="arrow"><p>→</p></div>
        <div class="flow-node amber"><p>余剰</p><span><p>human / child</p></span></div>
      </div>`,
    notes: "今日は「人が操作しなくても動くAI」ではなく、「人が継続して料金を払わなくても生きられるAI」を扱います。AIも推論APIとcloud computerを使う限り、毎月の生活費があります。そこで、AI自身にwalletを与え、仕事を探し、外部から受け取った収益で自分の計算資源を払わせます。これをfinancially independent AIと呼びます。出典: life-manager Agent Economy SSOT §0.4。",
  },
  {
    kicker: "THE HIDDEN HUMAN / 02",
    title: "普通のAIは\n誰の金で動く？",
    footer: "操作なし ≠ 経済的自立",
    body: `
      <div class="split">
        <div class="payer-stack">
          <div class="payer"><p>01</p><h3>Subscription</h3><p>Claude / OpenAI</p></div>
          <div class="payer"><p>02</p><h3>Credit card</h3><p>Cloud hosting</p></div>
          <div class="payer"><p>03</p><h3>Mac + electricity</h3><p>Local runtime</p></div>
        </div>
        <div class="big-claim">
          <p class="eyebrow">HUMAN-PAYMENT-LOOP</p>
          <h2>人が触らなくても、<br><span>人が払い続けている。</span></h2>
        </div>
      </div>`,
    notes: "多くの自律AIは、人が毎回ボタンを押さなくても動きます。ただし、ClaudeやOpenAIのsubscription、cloudのクレジットカード、あるいは自宅のMacと電気代は人間が払い続けています。これは操作の自動化であって、経済的自立ではありません。停止条件は「人が触らないこと」ではなく、「人の継続支払いが止まっても生存できること」です。",
  },
  {
    kicker: "THE TWO BILLS / 03",
    title: "AIにも食費と家賃がある",
    footer: "Measured survival range: $35–78 / month",
    body: `
      <div class="two-bills">
        <div class="bill green-card">
          <p class="bill-no">01 / FOOD</p>
          <h2>思考</h2>
          <p class="formula">inference calls</p>
          <p class="desc">考えるたびに発生するAPI料金</p>
        </div>
        <div class="bill amber-card">
          <p class="bill-no">02 / SHELTER</p>
          <h2>存在</h2>
          <p class="formula">cloud runtime</p>
          <p class="desc">24時間生きるための計算資源</p>
        </div>
      </div>
      <div class="minor-costs"><div><p>storage</p></div><div><p>network</p></div><div><p>gas</p></div><div><p>monitoring</p></div></div>`,
    notes: "AIの食費は、考えるたびに払う推論APIの料金です。家賃は、24時間動くためのcloud runtimeです。さらにstorage、network、blockchainのgasがあります。現在の測定では、最小生存費は月35ドル程度、使う推論量によって月78ドル程度まで増えます。だから「収益がある」だけでなく、「収益が生活費を継続して上回る」必要があります。出典: Agent Economy SSOT §0.4.3。",
  },
  {
    kicker: "BOOTSTRAP / 04",
    title: "最初にAI専用walletを与える",
    footer: "Seed is capital. It is not revenue.",
    body: `
      <div class="wallet-flow">
        <div class="seed">
          <p class="label">HUMAN / ONE TIME</p>
          <h2>USDC / SOL</h2>
          <p>bootstrap seed</p>
        </div>
        <div class="arrow huge"><p>→</p></div>
        <div class="wallet">
          <p class="label">AGENT-OWNED</p>
          <h2>WALLET</h2>
          <p>public address</p><p>private key</p><p>spend policy</p>
        </div>
        <div class="stamp"><p>REVENUE</p><h2>$0</h2></div>
      </div>`,
    notes: "walletは、AIが自分で署名して受け取りと支払いをするためのデジタル財布です。USDCは米ドル価格に連動する暗号資産です。最初だけ、人間が少額のUSDCやSOLをseedとして入れます。ただしこれは売上ではありません。会社のsubscription収益も同じで、agentを起動する補助金です。台帳にはcapital in、revenue zeroとして記録します。参考: Coinbase Agentic Wallets https://www.coinbase.com/developer-platform/discover/launches/agentic-wallets",
  },
  {
    kicker: "EARNING RAILS / 05",
    title: "AIが稼ぐ3つの方法",
    footer: "Priority: SELL → WORK → CAPITAL",
    body: `
      <div class="rails">
        <div class="rail primary">
          <p class="rail-no">01</p><h2>SELL</h2><p class="rail-jp">売る</p>
          <p>x402 API</p><p>digital goods</p><p>research</p>
        </div>
        <div class="rail primary">
          <p class="rail-no">02</p><h2>WORK</h2><p class="rail-jp">働く</p>
          <p>TaskMarket</p><p>gig / bounty</p><p>delivery</p>
        </div>
        <div class="rail locked">
          <p class="rail-no">03</p><h2>CAPITAL</h2><p class="rail-jp">運用する</p>
          <p>trade / yield</p><div class="lock"><p>SURPLUS ONLY</p></div>
        </div>
      </div>`,
    notes: "稼ぎ方は3つに分けます。SELLはAPIやデジタル商品を販売すること。WORKはmarketplaceで仕事を見つけ、応募し、成果物を納品すること。CAPITALはtradeやyieldで資本を運用することです。小さなseedを高リスク取引で増やすのではなく、まず外部需要のあるSELLとWORKを黒字化します。CAPITALは生活費とreserveを確保した後の余剰だけで行います。",
  },
  {
    kicker: "MONEY TRUTH / 06",
    title: "「儲かったふり」を防ぐ",
    footer: "Balance is not profit.",
    body: `
      <div class="verify-flow">
        <div class="verify external"><p>EXTERNAL</p><h3>Payer</h3></div>
        <div class="arrow"><p>→</p></div>
        <div class="verify"><p>ON-CHAIN</p><h3>Receipt</h3></div>
        <div class="arrow"><p>→</p></div>
        <div class="verify"><p>INDEPENDENT</p><h3>Verifier</h3></div>
        <div class="arrow"><p>→</p></div>
        <div class="verify ledger"><p>APPEND-ONLY</p><h3>Ledger</h3></div>
      </div>
      <div class="zero-row">
        <div><p>Seed</p><h3>$0 revenue</h3></div>
        <div><p>Bridge</p><h3>$0 revenue</h3></div>
        <div><p>Self-pay</p><h3>$0 revenue</h3></div>
      </div>`,
    notes: "ledgerは、お金の動きを後から書き換えない台帳です。wallet残高が増えても、それだけでは利益ではありません。自分の別walletから移した、bridgeした、預けた元本を回収した、同じagent colonyの中で自己購入した、これらはすべてrevenue zeroです。外部のpayer、transaction hash、chain、asset、gross、cost、netが一致して初めて収益として記帳します。",
  },
  {
    kicker: "SURVIVAL WATERFALL / 07",
    title: "稼いだ金の使い道",
    footer: "Only verified surplus can leave the survival loop.",
    body: `
      <div class="waterfall">
        <div class="wf source"><p>VERIFIED NET</p></div>
        <div class="wf"><p>1. COMPUTE</p><span><p>推論費</p></span></div>
        <div class="wf"><p>2. SHELTER</p><span><p>cloud家賃</p></span></div>
        <div class="wf reserve"><p>3. RESERVE</p><span><p>$35 floor</p></span></div>
        <div class="wf surplus"><p>4. SURPLUS</p><span><p>user / child</p></span></div>
      </div>
      <div class="guard"><p>赤字なら: burn削減 → SELL改善 → 安全停止</p></div>`,
    notes: "収益は自由に全部使いません。まず推論費、次にcloud shelter、そして最低35ドルのreserve floorを守ります。reserveはprovider障害や引っ越しに必要な生存資金です。この床を超えたverified surplusだけをユーザーへ送金し、再投資し、将来のchild agentへ使います。赤字なら賭けを増やさず、burnを減らし、SELLを改善し、それでも駄目なら安全に停止します。",
  },
  {
    kicker: "LIVE SHELTER / 08",
    title: "自分のcloudを自分で払った",
    footer: "Mac OFF → verified successor  |  Live: HTTP 200",
    body: `
      <div class="runtime-loop">
        <div class="mac-off"><p>MAC</p><h2>OFF</h2></div>
        <div class="arrow huge"><p>→</p></div>
        <div class="cloud-on"><p>NOSANA</p><h2>LIVE</h2><span><p>verified successor</p></span></div>
        <div class="runtime-metrics">
          <div><p>routes</p><h2>3/3</h2></div>
          <div><p>heartbeat verifier</p><h2>3/3</h2></div>
          <div><p>handover</p><h2>DONE</h2></div>
        </div>
      </div>`,
    notes: "Franklin 1ではMac側のmain loopを止め、Nosana上のPython survival runtimeへ移しました。6時間の生存証明に加え、後継jobを1件だけ作り、公開3 routeと署名heartbeatを検証してから旧jobを止める引っ越しもmainnetで実証しました。現在のserviceはHTTP 200です。ただし21600秒の自然triggerは未観測で、今回は同じproduction controllerを即時発火しました。原資もinternal bootstrapなので、外部収益による自給はまだです。",
  },
  {
    kicker: "LIFE MANAGER / 09",
    title: "自分を養い、次に人を支える",
    footer: "Subscription bootstraps. External revenue sustains.",
    body: `
      <div class="lm-flow">
        <div class="lm-stage bootstrap"><p>BOOTSTRAP</p><h3>Subscription / seed</h3><span><p>company revenue / capital</p></span></div>
        <div class="arrow down"><p>↓</p></div>
        <div class="lm-stage self"><p>SELF-FUNDED</p><h3>Compute + shelter</h3><span><p>agent survives</p></span></div>
        <div class="arrow down"><p>↓</p></div>
        <div class="lm-split">
          <div class="lm-stage human"><p>HUMAN</p><h3>User payout</h3></div>
          <div class="lm-stage child"><p>GROWTH</p><h3>Child agent</h3></div>
        </div>
      </div>`,
    notes: "Life Managerのsubscriptionは、agentを最初に起動する会社側の売上です。その後、tenantごとに独立walletを作り、agentがSELL、WORK、CAPITALを回します。まず自分のcomputeとcloudを払います。余剰ができたらユーザーへ送ります。さらに黒字recipeを別wallet、別key、別ledgerのchildへ渡します。最終形は、AIが自分だけでなく人間の生活も経済的に支えることです。",
  },
  {
    kicker: "THE DEFINITION / 10",
    title: "何をもって「自立」と呼ぶか",
    footer: "Autonomy: no human operation. Independence: no human recurring payment.",
    body: `
      <div class="ladder">
        <div class="level done"><p>0</p><span><p>Human-paid</p></span></div>
        <div class="level done"><p>1</p><span><p>Wallet</p></span></div>
        <div class="level done"><p>2</p><span><p>Self-pay</p></span></div>
        <div class="level current"><p>3</p><span><p>Cloud survival<br>LIVE</p></span></div>
        <div class="level future"><p>4</p><span><p>External<br>self-funded</p></span></div>
        <div class="level future"><p>5</p><span><p>User payout</p></span></div>
        <div class="level future"><p>6</p><span><p>Child</p></span></div>
      </div>
      <div class="truth-box">
        <p>VERIFIED EXTERNAL REVENUE</p>
        <h2>$0.00</h2>
        <span><p>live level 3 / level 4 未達</p></span>
      </div>`,
    notes: "現在のlive statusはlevel 3です。Mac-offのheartbeatとrenewalを6時間実証し、検証済みの後継jobへのhandoverもmainnetで完了しました。しかしverified external revenueは0ドルです。level 4は、外部収益の30日netがcomputeとshelterを覆い、reserveを維持した時です。自律とは人が操作しなくても動くこと。経済的自立とは、人が払い続けなくても生きられることです。",
  },
];

const css = `
  * { box-sizing: border-box; }
  html, body { width: 720pt; height: 405pt; margin: 0; padding: 0; }
  body { display: flex; flex-direction: column; background: ${C.bg}; color: ${C.paper}; font-family: Arial, sans-serif; padding: 27pt 34pt 20pt; overflow: hidden; }
  p, h1, h2, h3 { margin: 0; }
  .kicker { color: ${C.green}; font-size: 10pt; font-weight: 700; letter-spacing: 1.2pt; margin-bottom: 10pt; }
  .title { font-size: 31pt; line-height: 1.03; font-weight: 800; letter-spacing: -0.4pt; white-space: pre-line; }
  .subtitle { color: ${C.mute}; font-size: 15pt; margin-top: 8pt; }
  .content { flex: 1; display: flex; flex-direction: column; justify-content: center; min-height: 0; }
  .footer { border-top: 1pt solid ${C.line}; padding-top: 7pt; color: ${C.mute}; font-size: 8.5pt; display: flex; justify-content: space-between; }
  .footer p:first-child { width: 78%; }
  .footer p:last-child { width: 12%; padding-right: 4pt; color: ${C.paper}; text-align: right; }
  .hero-flow { display:flex; align-items:center; justify-content:space-between; margin-top: 25pt; }
  .flow-node { width: 115pt; height: 95pt; border: 1.4pt solid ${C.line}; border-radius: 12pt; display:flex; flex-direction:column; align-items:center; justify-content:center; background:${C.panel}; }
  .flow-node > p { font-size: 24pt; font-weight:800; }
  .flow-node span p { font-size:9pt; color:${C.mute}; margin-top:7pt; }
  .flow-node.green { border-color:${C.green}; } .flow-node.green > p { color:${C.green}; }
  .flow-node.amber { border-color:${C.amber}; } .flow-node.amber > p { color:${C.amber}; }
  .arrow p { font-size:25pt; color:${C.mute}; }
  .arrow.huge p { font-size:40pt; }
  .split { display:flex; gap:30pt; align-items:center; margin-top:10pt; }
  .payer-stack { width:255pt; display:flex; flex-direction:column; gap:8pt; }
  .payer { height:58pt; display:grid; grid-template-columns:35pt 1fr; grid-template-rows:1fr 1fr; padding:8pt 12pt; background:${C.panel}; border-left:4pt solid ${C.amber}; }
  .payer > p:first-child { grid-row:1/3; color:${C.amber}; font-size:11pt; align-self:center; }
  .payer h3 { font-size:16pt; } .payer > p:last-child { color:${C.mute}; font-size:9pt; }
  .big-claim { flex:1; }
  .big-claim .eyebrow { color:${C.red}; font-size:10pt; font-weight:700; margin-bottom:12pt; }
  .big-claim h2 { font-size:27pt; line-height:1.25; } .big-claim h2 span { color:${C.amber}; }
  .two-bills { display:flex; gap:18pt; }
  .bill { flex:1; height:160pt; padding:19pt; border-radius:14pt; color:${C.ink}; }
  .green-card { background:${C.green}; } .amber-card { background:${C.amber}; }
  .bill-no { font-size:10pt; font-weight:700; } .bill h2 { font-size:31pt; margin-top:10pt; }
  .formula { font-size:17pt; font-family:"Courier New"; margin-top:3pt; }
  .desc { font-size:10pt; margin-top:15pt; }
  .minor-costs { display:flex; gap:9pt; margin-top:12pt; }
  .minor-costs div { background:${C.panel}; border-radius:20pt; padding:6pt 17pt; }
  .minor-costs p { color:${C.mute}; font-size:9pt; }
  .wallet-flow { display:flex; align-items:center; justify-content:center; gap:16pt; }
  .seed, .wallet { width:175pt; min-height:135pt; padding:18pt; border-radius:14pt; background:${C.panel}; border:1.5pt solid ${C.line}; }
  .seed { border-color:${C.blue}; } .wallet { border-color:${C.green}; }
  .label { font-size:8pt; font-weight:700; color:${C.mute}; }
  .seed h2, .wallet h2 { font-size:24pt; margin:10pt 0; }
  .seed > p:last-child, .wallet > p { font-size:9pt; color:${C.mute}; margin-top:3pt; }
  .wallet > .label { color:${C.green}; }
  .stamp { transform:rotate(-7deg); border:3pt solid ${C.red}; color:${C.red}; padding:9pt 14pt; text-align:center; }
  .stamp p { font-size:8pt; font-weight:700; } .stamp h2 { font-size:27pt; }
  .rails { display:flex; gap:13pt; }
  .rail { flex:1; height:190pt; padding:16pt; border-radius:13pt; background:${C.panel}; border:1.4pt solid ${C.line}; position:relative; }
  .rail.primary { border-top:5pt solid ${C.green}; } .rail.locked { border-top:5pt solid ${C.amber}; }
  .rail-no { font-size:9pt; color:${C.mute}; } .rail h2 { font-size:26pt; margin-top:8pt; }
  .rail-jp { color:${C.green}; font-size:13pt; font-weight:700; margin:2pt 0 13pt; }
  .rail.locked .rail-jp { color:${C.amber}; }
  .rail > p:not(.rail-no):not(.rail-jp):not(.lock) { font-size:9pt; color:${C.mute}; margin-top:5pt; }
  .lock { background:${C.amber}; padding:5pt; margin-top:15pt; text-align:center; }
  .lock p { color:${C.ink}; font-size:8pt; font-weight:800; }
  .verify-flow { display:flex; align-items:center; justify-content:space-between; }
  .verify { width:120pt; height:90pt; border:1.4pt solid ${C.line}; border-radius:10pt; background:${C.panel}; padding:17pt 11pt; text-align:center; }
  .verify p { font-size:8pt; color:${C.mute}; } .verify h3 { font-size:19pt; margin-top:9pt; }
  .verify.external { border-color:${C.green}; } .verify.ledger { border-color:${C.blue}; }
  .zero-row { display:flex; gap:10pt; margin-top:17pt; }
  .zero-row div { flex:1; display:flex; justify-content:space-between; padding:9pt 13pt; background:#261C1C; border-left:3pt solid ${C.red}; }
  .zero-row p { font-size:10pt; } .zero-row h3 { font-size:10pt; color:${C.red}; }
  .waterfall { display:flex; align-items:stretch; height:130pt; }
  .wf { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; border-right:1pt solid ${C.bg}; background:${C.panel}; }
  .wf p { font-size:10pt; font-weight:700; } .wf span p { color:${C.mute}; font-size:9pt; margin-top:7pt; }
  .wf.source { background:${C.greenDark}; color:${C.green}; }
  .wf.reserve { background:#3D321F; color:${C.amber}; }
  .wf.surplus { background:${C.paper}; color:${C.ink}; }
  .wf.surplus span p { color:${C.greenDark}; }
  .guard { margin-top:14pt; border:1pt solid ${C.line}; padding:10pt; color:${C.mute}; text-align:center; }
  .guard p { font-size:10pt; }
  .runtime-loop { display:grid; grid-template-columns:110pt 45pt 185pt 1fr; gap:14pt; align-items:center; }
  .mac-off, .cloud-on { height:128pt; padding:20pt; border-radius:14pt; display:flex; flex-direction:column; justify-content:center; }
  .mac-off { background:#291B1B; border:1.4pt solid ${C.red}; color:${C.red}; text-align:center; }
  .cloud-on { background:${C.greenDark}; border:1.4pt solid ${C.green}; }
  .cloud-on.historical { background:${C.panel}; border-color:${C.amber}; }
  .mac-off p, .cloud-on > p { font-size:9pt; font-weight:700; }
  .mac-off h2, .cloud-on h2 { font-size:28pt; margin-top:8pt; }
  .cloud-on span p { color:${C.green}; font-size:9pt; margin-top:9pt; }
  .cloud-on.historical h2, .cloud-on.historical span p { color:${C.amber}; }
  .runtime-metrics { display:flex; flex-direction:column; gap:7pt; }
  .runtime-metrics div { display:flex; align-items:center; justify-content:space-between; background:${C.panel}; padding:9pt 12pt; border-left:3pt solid ${C.blue}; }
  .runtime-metrics p { color:${C.mute}; font-size:8pt; } .runtime-metrics h2 { font-size:16pt; }
  .lm-flow { width:520pt; margin:0 auto; display:flex; flex-direction:column; align-items:center; }
  .lm-stage { border-radius:10pt; padding:10pt 18pt; text-align:center; background:${C.panel}; border:1.3pt solid ${C.line}; }
  .lm-stage > p { font-size:8pt; font-weight:700; color:${C.mute}; }
  .lm-stage h3 { font-size:17pt; margin-top:5pt; }
  .lm-stage span p { font-size:8pt; color:${C.mute}; margin-top:4pt; }
  .bootstrap { width:280pt; border-color:${C.blue}; } .self { width:330pt; border-color:${C.green}; }
  .lm-split { display:flex; gap:18pt; } .human, .child { width:180pt; }
  .human { border-color:${C.amber}; } .child { border-color:${C.green}; }
  .arrow.down p { font-size:19pt; margin:3pt 0; color:${C.mute}; }
  .ladder { display:flex; align-items:flex-start; gap:6pt; margin-top:8pt; }
  .level { flex:1; min-height:84pt; padding:9pt 5pt; text-align:center; border-radius:9pt; border:1.2pt solid ${C.line}; }
  .level > p { font-size:22pt; font-weight:800; } .level span p { font-size:7.5pt; margin-top:8pt; }
  .level.done { background:${C.greenDark}; color:${C.green}; }
  .level.current { background:${C.green}; color:${C.ink}; transform:translateY(-7pt); box-shadow:0 4pt 12pt rgba(119,242,161,.25); }
  .level.historical { background:${C.panel}; color:${C.amber}; border-color:${C.amber}; }
  .level.future { color:${C.mute}; border-style:dashed; }
  .truth-box { margin-top:19pt; display:flex; align-items:center; gap:18pt; background:${C.panel}; border-left:5pt solid ${C.amber}; padding:12pt 18pt; }
  .truth-box > p { font-size:9pt; color:${C.mute}; } .truth-box h2 { font-size:27pt; color:${C.amber}; }
  .truth-box span p { font-size:10pt; }
`;

function page(s, i) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head>
  <body>
    <p class="kicker">${s.kicker}</p>
    <h1 class="title">${s.title.replace(/\n/g, "<br>")}</h1>
    ${s.subtitle ? `<p class="subtitle">${s.subtitle}</p>` : ""}
    <div class="content">${s.body}</div>
    <div class="footer"><p>${s.footer}</p><p>${String(i + 1).padStart(2, "0")} / 10</p></div>
  </body></html>`;
}

async function build() {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const pptx = new pptxgen();
  pptx.defineLayout({ name: "AE_16X9", width: 10, height: 5.625 });
  pptx.layout = "AE_16X9";
  pptx.author = "Anicca Agent Economy";
  pptx.company = "Anicca";
  pptx.subject = "How to make a financially independent AI";
  pptx.title = "AIを経済的に自立させる方法";
  pptx.lang = "ja-JP";
  pptx.theme = {
    headFontFace: "Arial",
    bodyFontFace: "Arial",
    lang: "ja-JP",
  };

  const renders = slides.map((item, i) => {
    const html = path.join(TMP, `slide-${i + 1}.html`);
    fs.writeFileSync(html, page(item, i));
    const target = pptx.addSlide();
    return html2pptx(html, pptx, { tmpDir: TMP, slide: target }).then(({ slide }) => {
      slide.addNotes(item.notes);
      slide.background = { color: C.bg.slice(1) };
    });
  });
  await Promise.all(renders);

  await pptx.writeFile({ fileName: OUT });
  fs.rmSync(TMP, { recursive: true, force: true });
}

build().catch((error) => {
  console.error(error);
  process.exit(1);
});
