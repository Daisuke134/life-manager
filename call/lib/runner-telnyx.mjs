#!/usr/bin/env node
// life-call-telnyx.mjs — places the REAL B-call to Dais (+<YOUR_E164_NUMBER>) via Telnyx
// Call Control, bypassing the Twilio error-21216 fraud block on that one destination
// (Twilio JP geo-permissions are fully enabled; the block is account+destination
// fraud control that lifts only via an async Support ticket — see
// docs/superpowers/specs/2026-06-16-life-call-telnyx-charon-design.md §1).
//
// Telnyx outbound profile "anicca-out" has JP whitelisted, so it can legally dial +81.
// Flow (identical Charon/Gemini bridge, different carrier):
//   1. start call-bridge.cjs --provider telnyx (Telnyx media-streaming frame shapes)
//   2. cloudflared quick tunnel → public wss for the bridge /ws
//   3. POST https://api.telnyx.com/v2/calls with stream_url + stream_bidirectional_mode=rtp
//      + stream_bidirectional_codec=PCMU + stream_track=both_tracks  → Telnyx dials Dais
//   4. POST /v2/calls/{ccid}/actions/record_start (mp3, both channels) so the call is recorded
//   5. poll call status via webhook-less polling of /v2/calls is unavailable, so we derive
//      connect/hangup from the bridge's own start/stop frames + Charon frame counts, and we
//      fetch the recording from /v2/recordings filtered by call_session_id.
//
// NO FAKE RUN (HARD 0.24): real sockets + a real Telnyx call. The only human in the loop is
// Dais picking up his own phone (he is the callee).
//
// Usage:
//   node scripts/life-call-telnyx.mjs --dry-run                build the dial body only, exit 0
//   node scripts/life-call-telnyx.mjs                          real run → dial +<YOUR_E164_NUMBER>
//   node scripts/life-call-telnyx.mjs --to=+E164               override destination
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const { telnyxDialBody } = require(
  path.join(here, "call-logic.js")
);

// ---- args
const args = process.argv.slice(2);
const DRY = args.includes("--dry-run");
let TO = process.env.LIFE_CALL_TO || process.env.LIFE_PHONE || ""; // user's E.164 number (set LIFE_PHONE)
let EVENT_JSON = "";
let URGENCY = "";
for (const a of args) {
  if (a.startsWith("--to=")) TO = a.slice("--to=".length);
  else if (a.startsWith("--event=")) EVENT_JSON = a.slice("--event=".length);
  else if (a.startsWith("--urgency=")) URGENCY = a.slice("--urgency=".length);
}
const PORT = Number(process.env.BRIDGE_PORT || 8788); // distinct default from the Twilio runner

// ---- env (Telnyx)
const API = process.env.TELNYX_API_KEY;
const CONN = process.env.TELNYX_CONNECTION_ID || "2982013078364751402"; // anicca-cc
const FROM = process.env.TELNYX_PHONE_NUMBER || "+14322234204"; // our Telnyx number

function die(msg) {
  console.error("FATAL:", msg);
  process.exit(1);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- Telnyx REST helpers (Bearer auth, JSON)
async function txPost(p, body) {
  const res = await fetch(`https://api.telnyx.com/v2${p}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${API}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Telnyx POST ${p} ${res.status}: ${JSON.stringify(j)}`);
  return j;
}
async function txGet(p) {
  const res = await fetch(`https://api.telnyx.com/v2${p}`, {
    headers: { Authorization: `Bearer ${API}` },
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Telnyx GET ${p} ${res.status}: ${JSON.stringify(j)}`);
  return j;
}

// ---- dry run: prove the dial body without side effects
if (DRY) {
  const body = telnyxDialBody({
    connectionId: CONN,
    to: TO,
    from: FROM,
    streamUrl: "wss://EXAMPLE.trycloudflare.com/ws",
  });
  console.log(JSON.stringify({ dryRun: true, provider: "telnyx", dialBody: body }, null, 2));
  process.exit(0);
}

// ---- real run
if (!API) die("TELNYX_API_KEY missing in env");
if (!process.env.GEMINI_API_KEY) die("GEMINI_API_KEY missing in env");

// G5 preflight: refuse to dial on an empty Telnyx balance (a mid-call cutoff is a fake "connected").
// JSON path confirmed against the live /v2/balance payload (Commands §0 prints the raw shape first):
//   { "data": { "balance": "5.00", "currency": "USD", "available_credit": "...", ... } }
// `data.balance` is a STRING → Number() coerces it. NOTE: --dry-run exits BEFORE this block
// (the `if (DRY) … process.exit(0)` above), so the preflight only gates a REAL run.
{
  const bal = await txGet("/balance").catch((e) => die("balance check failed: " + e.message));
  const usd = Number(bal && bal.data && bal.data.balance);
  console.log(`[runner] telnyx balance=$${isFinite(usd) ? usd.toFixed(2) : "?"} currency=${bal?.data?.currency || "?"}`);
  if (!isFinite(usd)) die(`unexpected /v2/balance shape: ${JSON.stringify(bal)}`); // path-mismatch fail-loud
  if (usd < 0.50) die(`telnyx balance too low ($${usd}); top up before dialing`);
}

let bridge, tunnel;
function cleanup() {
  try { bridge && bridge.kill("SIGTERM"); } catch {}
  try { tunnel && tunnel.kill("SIGTERM"); } catch {}
}
process.on("exit", cleanup);
process.on("SIGINT", () => { cleanup(); process.exit(130); });

async function waitFor(stream, re, timeoutMs, label) {
  return await new Promise((resolve, reject) => {
    const to = setTimeout(() => reject(new Error(`timeout waiting for ${label}`)), timeoutMs);
    const onData = (d) => {
      const s = d.toString();
      process.stdout.write(s);
      const m = s.match(re);
      if (m) { clearTimeout(to); stream.off("data", onData); resolve(m); }
    };
    stream.on("data", onData);
  });
}

async function main() {
  // 1. cloudflared tunnel — override the bin path via CLOUDFLARED_BIN if it's not on PATH.
  const CLOUDFLARED = process.env.CLOUDFLARED_BIN || "cloudflared";
  tunnel = spawn(CLOUDFLARED, ["tunnel", "--url", `http://localhost:${PORT}`], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  const m = await waitFor(tunnel.stderr, /https:\/\/[a-z0-9-]+\.trycloudflare\.com/, 40000, "tunnel url");
  const httpsUrl = m[0];
  const wsUrl = httpsUrl.replace(/^https:/, "wss:") + "/ws";
  console.log(`\n[runner] tunnel=${httpsUrl}  ws=${wsUrl}`);

  // 2. start the bridge in Telnyx mode (Telnyx frame shapes both ways)
  bridge = spawn(
    process.execPath,  // absolute node — resolves regardless of the gateway's PATH
    [path.join(here, "call-bridge.cjs"), "--port", String(PORT), "--provider", "telnyx",
      ...(EVENT_JSON ? ["--event", EVENT_JSON] : []),
      ...(URGENCY ? ["--urgency", URGENCY] : [])],
    { env: { ...process.env, BRIDGE_PUBLIC_WSS: wsUrl }, stdio: ["ignore", "pipe", "pipe"] }
  );
  bridge.stderr.on("data", (d) => process.stderr.write("[bridge.err] " + d));
  let bridgeLog = "";
  bridge.stdout.on("data", (d) => { bridgeLog += d.toString(); });
  await waitFor(bridge.stdout, /listening \d+ path=\/ws/, 15000, "bridge listening");
  await sleep(4000); // let the edge route settle

  // 3. place the REAL Telnyx call to Dais with bidirectional media streaming
  const dialBody = telnyxDialBody({ connectionId: CONN, to: TO, from: FROM, streamUrl: wsUrl });
  const call = await txPost("/calls", dialBody);
  const ccid = call.data.call_control_id;
  const sessionId = call.data.call_session_id;
  const legId = call.data.call_leg_id;
  console.log(`[runner] CALL_CONTROL_ID=${ccid}\n[runner] CALL_SESSION_ID=${sessionId} to=${TO}`);

  // 4. Wait for the call to be ANSWERED. The bridge logs `twilio_start` when Telnyx opens the media
  //    stream, which (verified live 2026-06-16) happens on answer via the dial-params — record_start and
  //    streaming_start both 422 with "Call not answered yet" (90034) if issued before this point.
  let recStarted = false;
  let answered = false;
  for (let i = 0; i < 25; i++) { // up to ~50s of ringing
    if (/twilio_start/.test(bridgeLog)) { answered = true; break; }
    await sleep(2000);
  }
  if (answered) {
    // 4a. answered → the dial-params stream auto-started; now start the recording (mp3).
    try {
      await txPost(`/calls/${encodeURIComponent(ccid)}/actions/record_start`, { format: "mp3", channels: "single" });
      recStarted = true;
      console.log("[runner] record_start ok (post-answer)");
    } catch (e) { console.error("[runner] record_start err:", e.message); }
  } else {
    // 4b. Contingency: still no stream after ringing — the dial-params stream did not auto-start;
    //     explicitly request it (docs: answer/streaming_start).
    try {
      const { telnyxStreamingStartBody } = require(
        path.join(here, "call-logic.js"));
      await txPost(`/calls/${encodeURIComponent(ccid)}/actions/streaming_start`,
        telnyxStreamingStartBody({ streamUrl: wsUrl }));
      console.log("[runner] streaming_start contingency sent");
    } catch (e) { console.error("[runner] streaming_start err:", e.message); }
  }

  // 5. let the call run; the bridge logs uplink/downlink frames as audio flows.
  //    We give it up to ~50s of conversation (Dais answers, Charon speaks, Dais replies).
  for (let i = 0; i < 18; i++) {
    await sleep(3000);
    const inM = (bridgeLog.match(/twilio_media frames=(\d+)/g) || []).pop();
    const outM = (bridgeLog.match(/gemini_audio frames=(\d+)/g) || []).pop();
    const stopped = /twilio_stop/.test(bridgeLog);
    process.stdout.write(`[poll ${i}] uplink=${inM || "0"} downlink=${outM || "0"} stopped=${stopped}\n`);
    if (stopped) break;
  }

  // 6. hang up (best effort) + fetch the recording for this call session
  try { await txPost(`/calls/${encodeURIComponent(ccid)}/actions/hangup`, {}); } catch {}

  // G7: carrier-truth status + duration (do NOT infer "connected" from bridge log strings).
  let callStatus = "unknown";
  try {
    const c = await txGet(`/calls/${encodeURIComponent(ccid)}`);
    callStatus = (c.data && (c.data.status || c.data.state)) || callStatus;
  } catch (e) { console.error("[runner] call status fetch err:", e.message); }

  let recUrl = "";
  let recId = "";
  let recDurSec = 0;
  // G8: Telnyx finalizes recordings ASYNCHRONOUSLY after hangup — a single 4s wait false-fails the
  // recDurSec<3 gate. Poll /v2/recordings until a recording with download_urls + duration appears
  // (up to ~30s: 10 × 3s). A genuinely-connected call will surface here once Telnyx flushes the mp3.
  for (let i = 0; i < 10; i++) {
    await sleep(3000);
    try {
      const recs = await txGet(`/recordings?filter[call_session_id]=${encodeURIComponent(sessionId)}`);
      const r = (recs.data && recs.data[0]) || null;
      if (r && (r.download_urls && (r.download_urls.mp3 || r.download_urls.wav))) {
        recId = r.id;
        recUrl = r.download_urls.mp3 || r.download_urls.wav;
        recDurSec = Number(r.duration_millis ? r.duration_millis / 1000 : r.recording_duration || 0) || 0;
        if (recDurSec > 0) break; // recording finalized with a real duration → done waiting
      }
    } catch (e) {
      console.error("[runner] recording fetch err:", e.message);
    }
    process.stdout.write(`[rec-poll ${i}] recId=${recId || "-"} dur=${recDurSec}s\n`);
  }

  // bridge frame accounting (same log strings as the Twilio runner)
  const inM = bridgeLog.match(/twilio_media frames=(\d+)/g) || [];
  const outM = bridgeLog.match(/gemini_audio frames=(\d+)/g) || [];
  const setupOk = /EVENT setupComplete/.test(bridgeLog);
  const startedOk = /twilio_start/.test(bridgeLog);
  const lastIn = inM.length ? inM[inM.length - 1].match(/(\d+)/)[0] : "0";
  const lastOut = outM.length ? outM[outM.length - 1].match(/(\d+)/)[0] : "0";

  console.log("\n==== B-call (Telnyx) RESULT ====");
  console.log(JSON.stringify({
    PROVIDER: "telnyx",
    CALL_CONTROL_ID: ccid,
    CALL_SESSION_ID: sessionId,
    CALL_LEG_ID: legId,
    TO,
    FROM,
    CALL_STATUS: callStatus,
    RECORDING_DURATION_SEC: recDurSec,
    RECORDING_STARTED: recStarted,
    RECORDING_ID: recId,
    RECORDING_URL: recUrl,
    BRIDGE_STREAM_STARTED: startedOk,
    BRIDGE_GEMINI_SETUP: setupOk,
    UPLINK_FRAMES: lastIn,
    DOWNLINK_FRAMES: lastOut,
  }, null, 2));

  cleanup();
  // success requires the carrier media stream to have started (Dais's leg connected)
  // and Charon to have spoken at least one downlink frame.
  if (!ccid) process.exit(1);
  // G7/G8: carrier-truth gate — the stream started, Charon spoke, AND the recording is non-trivial.
  if (!startedOk || Number(lastOut) <= 0 || recDurSec < 3) {
    console.error(`[runner] FAIL streamStarted=${startedOk} downlink=${lastOut} recDur=${recDurSec}s — exiting non-zero`);
    process.exit(2);
  }
  process.exit(0);
}

main().catch((e) => { console.error("FATAL:", e.message); cleanup(); process.exit(1); });
