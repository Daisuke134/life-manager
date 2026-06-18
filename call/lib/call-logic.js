// call-logic.js — pure business logic for B-call (spec27 WF-B B-call).
//
// Anicca phones the user 15 min before each calendar event and talks two-way via
// Gemini Live (voice = Charon) bridged over Twilio Media Streams. The hard,
// bug-prone part is the audio transcoding (μ-law 8kHz PSTN ↔ PCM 16kHz-in/24kHz-out
// Gemini) plus the exact wire-message shapes. Those are the pure functions below.
//
// This module has ZERO I/O — no network, no env. The skill entrypoint
// (~/anicca/skills/life/call/call.js) wires these into the Twilio + Gemini sockets.
// Pattern mirrors telemetry-verify.js / travel-logic.js (node:test, CommonJS).
//
// Standards / sources:
//   - G.711 μ-law: ITU-T G.711 (8-bit companded, 14-bit linear range).
//   - Gemini Live realtimeInput / setup / speechConfig shapes: ctx7
//     /websites/ai_google_dev_gemini-api (input PCM 16kHz, output PCM 24kHz, voice Charon).
//   - Twilio Media Streams media frame (audio/x-mulaw @ 8000Hz, base64): ctx7
//     /websites/twilio_voice (websocket-messages).

"use strict";

const MULAW_BIAS = 0x84; // 132
const MULAW_CLIP = 32635;

// The model id the live bidi API actually accepts (verified by a real ws handshake
// 2026-06-16: gemini-2.0-flash-live-001 returns "CLOSE 1008 … not supported for
// bidiGenerateContent", while this native-audio model returns setupComplete + real
// Charon PCM24 audio). Bridges default to this.
const LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-09-2025";

/**
 * Build the Gemini Live websocket URL (BidiGenerateContent) for an API key.
 * Source (ctx7 /websites/ai_google_dev_gemini-api, live-api/get-started-websocket):
 *   wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=...
 * @param {string} apiKey
 * @returns {string} wss:// url
 */
function geminiLiveWsUrl(apiKey) {
  return (
    "wss://generativelanguage.googleapis.com/ws/" +
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent" +
    `?key=${encodeURIComponent(apiKey || "")}`
  );
}

// ── G.711 μ-law (single sample) ───────────────────────────────────────────────

/**
 * Decode one μ-law byte (0..255) to a signed 16-bit PCM sample.
 * @param {number} u - μ-law byte
 * @returns {number} int16 PCM (-32768..32767)
 */
function muLawDecodeSample(u) {
  u = ~u & 0xff; // μ-law is stored inverted
  const sign = u & 0x80;
  const exponent = (u >> 4) & 0x07;
  const mantissa = u & 0x0f;
  let sample = ((mantissa << 3) + MULAW_BIAS) << exponent;
  sample -= MULAW_BIAS;
  // `|| 0` normalizes -0 → 0 (the inverted-sign silence byte decodes to negative zero).
  return (sign ? -sample : sample) || 0;
}

/**
 * Encode one signed 16-bit PCM sample to a μ-law byte (0..255).
 * @param {number} pcm - int16 PCM
 * @returns {number} μ-law byte
 */
function muLawEncodeSample(pcm) {
  let sign = (pcm >> 8) & 0x80;
  if (sign !== 0) pcm = -pcm;
  if (pcm > MULAW_CLIP) pcm = MULAW_CLIP;
  pcm += MULAW_BIAS;

  let exponent = 7;
  for (let mask = 0x4000; (pcm & mask) === 0 && exponent > 0; mask >>= 1) exponent--;

  const mantissa = (pcm >> (exponent + 3)) & 0x0f;
  const muLaw = ~(sign | (exponent << 4) | mantissa) & 0xff;
  return muLaw;
}

// ── Whole-buffer transcode ────────────────────────────────────────────────────

/**
 * Convert a buffer of μ-law bytes to little-endian 16-bit PCM.
 * @param {Buffer} buf - n μ-law bytes
 * @returns {Buffer} 2n PCM bytes (LE int16)
 */
function muLawBufToPcm16(buf) {
  const out = Buffer.alloc(buf.length * 2);
  for (let i = 0; i < buf.length; i++) {
    out.writeInt16LE(muLawDecodeSample(buf[i]), i * 2);
  }
  return out;
}

/**
 * Convert a buffer of little-endian 16-bit PCM to μ-law bytes.
 * @param {Buffer} buf - 2n PCM bytes (LE int16)
 * @returns {Buffer} n μ-law bytes
 */
function pcm16BufToMuLaw(buf) {
  const samples = Math.floor(buf.length / 2);
  const out = Buffer.alloc(samples);
  for (let i = 0; i < samples; i++) {
    out[i] = muLawEncodeSample(buf.readInt16LE(i * 2));
  }
  return out;
}

// ── Resampling (mono, LE int16, linear interpolation) ─────────────────────────

/**
 * Resample mono LE-int16 PCM from inRate to outRate via linear interpolation.
 * @param {Buffer} buf - input PCM (LE int16)
 * @param {number} inRate
 * @param {number} outRate
 * @returns {Buffer} resampled PCM (LE int16)
 */
function resamplePcm16(buf, inRate, outRate) {
  if (inRate === outRate) return Buffer.from(buf);
  const inSamples = Math.floor(buf.length / 2);
  if (inSamples === 0) return Buffer.alloc(0);
  const ratio = outRate / inRate;
  const outSamples = Math.round(inSamples * ratio);
  const out = Buffer.alloc(outSamples * 2);
  for (let i = 0; i < outSamples; i++) {
    const srcPos = i / ratio;
    const i0 = Math.floor(srcPos);
    const i1 = Math.min(i0 + 1, inSamples - 1);
    const frac = srcPos - i0;
    const s0 = buf.readInt16LE(i0 * 2);
    const s1 = buf.readInt16LE(i1 * 2);
    let v = Math.round(s0 + (s1 - s0) * frac);
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    out.writeInt16LE(v, i * 2);
  }
  return out;
}

// ── Composite codec paths (base64 → base64) ───────────────────────────────────

/**
 * Twilio inbound (μ-law 8kHz base64) → Gemini realtimeInput (PCM16 16kHz base64).
 * @param {string} b64MuLaw
 * @returns {string} base64 PCM16 @ 16kHz
 */
function twilioMuLawToGeminiPcm16(b64MuLaw) {
  const mu = Buffer.from(b64MuLaw, "base64");
  const pcm8 = muLawBufToPcm16(mu);
  const pcm16k = resamplePcm16(pcm8, 8000, 16000);
  return pcm16k.toString("base64");
}

/**
 * Gemini output (PCM16 24kHz base64) → Twilio play (μ-law 8kHz base64).
 * @param {string} b64Pcm24
 * @returns {string} base64 μ-law @ 8kHz
 */
function geminiPcm24ToTwilioMuLaw(b64Pcm24) {
  const pcm24 = Buffer.from(b64Pcm24, "base64");
  const pcm8 = resamplePcm16(pcm24, 24000, 8000);
  const mu = pcm16BufToMuLaw(pcm8);
  return mu.toString("base64");
}

// ── Gemini Live wire messages ─────────────────────────────────────────────────

/**
 * Build the BidiGenerateContentSetup message (AUDIO modality, Charon voice).
 * @param {object} o
 * @param {string} o.model - model id (with or without "models/" prefix)
 * @param {string} o.voiceName - prebuilt voice (e.g. "Charon")
 * @param {string} o.systemInstruction - the call's system instruction text
 * @returns {object} { setup: {...} }
 */
function buildGeminiSetup({ model, voiceName, systemInstruction }) {
  const m = model || LIVE_MODEL; // default to the verified-working live model
  const modelPath = String(m).startsWith("models/") ? m : `models/${m}`;
  return {
    setup: {
      model: modelPath,
      generationConfig: {
        responseModalities: ["AUDIO"],
        speechConfig: {
          voiceConfig: { prebuiltVoiceConfig: { voiceName: voiceName || "Charon" } },
        },
      },
      // Tune automatic VAD for a natural PHONE call: capture his first word (prefixPaddingMs)
      // and WAIT for him to finish instead of cutting in (longer silenceDurationMs + LOW
      // end-of-speech sensitivity). Source: live-api/capabilities "Configure Automatic VAD".
      realtimeInputConfig: {
        automaticActivityDetection: {
          startOfSpeechSensitivity: "START_SENSITIVITY_HIGH",
          endOfSpeechSensitivity: "END_SENSITIVITY_LOW",
          prefixPaddingMs: 300,
          silenceDurationMs: 800,
        },
      },
      systemInstruction: { parts: [{ text: systemInstruction || "" }] },
      // Transcribe BOTH sides so we can read what Gemini heard from the user (input) and what Charon
      // said (output). Server returns serverContent.inputTranscription.text / outputTranscription.text.
      // Verified: ai.google.dev/gemini-api/docs/live-guide (firecrawl 2026-06-16).
      inputAudioTranscription: {},
      outputAudioTranscription: {},
    },
  };
}

/**
 * Extract input/output transcription text from a parsed Gemini Live server message.
 * @param {object} msg - parsed JSON server message
 * @returns {{input?:string, output?:string}} present keys carry transcript text
 */
function parseGeminiTranscripts(msg) {
  const sc = (msg && msg.serverContent) || {};
  const out = {};
  if (sc.inputTranscription && sc.inputTranscription.text) out.input = sc.inputTranscription.text;
  if (sc.outputTranscription && sc.outputTranscription.text) out.output = sc.outputTranscription.text;
  return out;
}

/**
 * Build a realtimeInput audio message (PCM16 @ 16kHz) for Gemini Live.
 * @param {string} b64Pcm16
 * @returns {object} { realtimeInput: { audio: { data, mimeType } } }
 */
function buildGeminiAudioInput(b64Pcm16) {
  return {
    realtimeInput: { audio: { data: b64Pcm16, mimeType: "audio/pcm;rate=16000" } },
  };
}

/**
 * Build a clientContent turn (text) to kick off Charon's opening line once the
 * call connects (Gemini sometimes waits for the first turn before speaking).
 * @param {string} text
 * @returns {object} { clientContent: { turns:[...], turnComplete:true } }
 */
function buildGeminiTurn(text) {
  return {
    clientContent: {
      turns: [{ role: "user", parts: [{ text: String(text || "") }] }],
      turnComplete: true,
    },
  };
}

/**
 * Extract base64 PCM24 audio chunks from a parsed Gemini Live server message.
 * Returns [] for non-audio messages (setupComplete, text, toolCall, etc).
 * @param {object} msg - parsed JSON server message
 * @returns {string[]} base64 PCM24 audio payloads (in order)
 */
function parseGeminiAudio(msg) {
  const parts = (msg && msg.serverContent && msg.serverContent.modelTurn &&
    msg.serverContent.modelTurn.parts) || [];
  const out = [];
  for (const p of parts) {
    const d = p && p.inlineData && p.inlineData.data;
    if (d) out.push(d);
  }
  return out;
}

// ── Twilio wire messages ──────────────────────────────────────────────────────

/**
 * Build an outbound Twilio Media Streams media frame.
 * @param {string} streamSid
 * @param {string} b64MuLaw - μ-law 8kHz base64 payload (no file header)
 * @returns {object} { event:"media", streamSid, media:{ payload } }
 */
function buildTwilioMediaFrame(streamSid, b64MuLaw) {
  return { event: "media", streamSid, media: { payload: b64MuLaw } };
}

// ── Telnyx Media Streaming wire messages ──────────────────────────────────────
//
// Telnyx forks call media to a ws (Call Control `stream_url`) and sends the same
// connected→start→media→stop lifecycle as Twilio, with base64 PCMU (μ-law 8kHz)
// payloads. Field names differ: the stream id is top-level `stream_id` (not
// `media.streamSid`), and the start frame's `start.media_format.encoding` is "PCMU".
// To play Charon back, send a `media` frame with `stream_id` + base64 μ-law payload.
// Source: ctx7 /websites/developers_telnyx (voice/programmable-voice/media-streaming,
// api-reference/websockets/stream-call-media-over-websocket).

/**
 * Build an outbound Telnyx Media Streaming `media` frame (Charon → caller).
 * Telnyx's documented bidirectional send-back shape is `{event:"media",media:{payload}}` with NO
 * stream_id (one bidirectional stream per call; Telnyx routes by the socket). Verified:
 * developers.telnyx.com/docs/voice/programmable-voice/media-streaming "Sending RTP stream".
 * @param {string} _streamId - accepted for call-site symmetry with buildTwilioMediaFrame; unused
 * @param {string} b64MuLaw - μ-law 8kHz base64 payload (no RTP/file header)
 * @returns {object} { event:"media", media:{ payload } }
 */
function buildTelnyxMediaFrame(_streamId, b64MuLaw) {
  return { event: "media", media: { payload: b64MuLaw } };
}

/**
 * Body for `POST /v2/calls/{ccid}/actions/streaming_start` — the contingency used only if a
 * dial-params stream does not auto-start on answer. Same stream config as the dial body.
 * Verified: media-streaming "It can be requested using answer and streaming_start commands".
 * @param {object} o
 * @param {string} o.streamUrl - public wss of the bridge /ws
 * @returns {object} request body
 */
function telnyxStreamingStartBody({ streamUrl }) {
  return {
    stream_url: streamUrl,
    stream_track: "inbound_track",
    stream_bidirectional_mode: "rtp",
    stream_bidirectional_codec: "PCMU",
  };
}

/**
 * Extract the stream_id (and call_control_id) from a Telnyx `start` frame.
 * Null-safe; returns {} for non-start or malformed frames.
 * @param {object} msg - parsed Telnyx ws frame
 * @returns {{streamId?:string, callControlId?:string}}
 */
function parseTelnyxStart(msg) {
  if (!msg || msg.event !== "start") return {};
  const streamId = msg.stream_id || (msg.start && msg.start.stream_id) || "";
  const callControlId = (msg.start && msg.start.call_control_id) || "";
  const out = {};
  if (streamId) out.streamId = streamId;
  if (callControlId) out.callControlId = callControlId;
  return out;
}

/**
 * Build the JSON body for `POST /v2/calls` (Telnyx Call Control outbound dial)
 * that ALSO requests bidirectional RTP media streaming to our bridge ws.
 * @param {object} o
 * @param {string} o.connectionId - Telnyx call-control connection_id
 * @param {string} o.to - E.164 destination (e.g. +<YOUR_E164_NUMBER>)
 * @param {string} o.from - E.164 originator (our Telnyx number)
 * @param {string} o.streamUrl - public wss:// of the bridge (the /ws path)
 * @returns {object} request body
 */
function telnyxDialBody({ connectionId, to, from, streamUrl }) {
  return {
    connection_id: connectionId,
    to,
    from,
    stream_url: streamUrl,
    stream_track: "inbound_track",
    stream_bidirectional_mode: "rtp",
    stream_bidirectional_codec: "PCMU",
  };
}

// ── Charon's call script (system instruction) ─────────────────────────────────

/**
 * Format an ISO/RFC3339 dateTime into a local HH:MM (best-effort, null-safe).
 * @param {string|undefined} dateTime
 * @returns {string} "HH:MM" or ""
 */
function formatTime(dateTime) {
  if (!dateTime || typeof dateTime !== "string") return "";
  // Match the wall-clock "HH:MM" the event was authored in (the source string),
  // not the bridge host's tz — calendar events carry their own offset.
  const m = dateTime.match(/T(\d{2}:\d{2})/);
  return m ? m[1] : "";
}

/**
 * Build the system-instruction text Charon speaks at the start of the call.
 * Null-safe: works even if the event has no title/time/location.
 * @param {object} event - GCal-shaped event { summary, start:{dateTime}, location }
 * @returns {string}
 */
function buildCallPrompt(event, urgency) {
  const e = event || {};
  const title = (e.summary || "your next appointment").toString().trim() || "your next appointment";
  const time = formatTime(e.start && e.start.dateTime);
  const location = (e.location || "").toString().trim();
  const tone =
    urgency === "harsh" ? "Be urgent and firm. They must leave RIGHT NOW or they will be late — push them hard, no small talk." :
    urgency === "firm"  ? "Be firm. It is really time to go now — get them moving." :
                          "Gently let them know it's about time to head out.";

  const lines = [
    "You are Anicca, a calm, concise voice assistant calling the user on the phone.",
    "Speak naturally. Keep it short. This is a two-way call — answer follow-ups.",
    `The user's next event is "${title}"${time ? ` at ${time}` : ""}.`,
    location ? `It is at ${location}.` : "",
    tone,
    "Then ask if they need directions or how to get there.",
    `Open with: "Hi, it's Anicca. Your next event is ${title}${time ? ` at ${time}` : ""} — time to leave now."`,
  ].filter(Boolean);

  return lines.join(" ");
}

// ── TwiML ─────────────────────────────────────────────────────────────────────

/**
 * XML-escape a string for use in an attribute value.
 * @param {string} s
 * @returns {string}
 */
function xmlEscape(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/**
 * Build the TwiML that connects the call's audio to our Media Streams ws bridge.
 * @param {string} wsUrl - public wss:// url of the bridge
 * @returns {string} TwiML document
 */
function buildConnectStreamTwiml(wsUrl) {
  return (
    '<?xml version="1.0" encoding="UTF-8"?>' +
    "<Response><Connect>" +
    `<Stream url="${xmlEscape(wsUrl)}" />` +
    "</Connect></Response>"
  );
}

module.exports = {
  LIVE_MODEL,
  geminiLiveWsUrl,
  buildGeminiTurn,
  parseGeminiAudio,
  parseGeminiTranscripts,
  muLawDecodeSample,
  muLawEncodeSample,
  muLawBufToPcm16,
  pcm16BufToMuLaw,
  resamplePcm16,
  twilioMuLawToGeminiPcm16,
  geminiPcm24ToTwilioMuLaw,
  buildGeminiSetup,
  buildGeminiAudioInput,
  buildTwilioMediaFrame,
  buildTelnyxMediaFrame,
  parseTelnyxStart,
  telnyxDialBody,
  telnyxStreamingStartBody,
  buildCallPrompt,
  buildConnectStreamTwiml,
  xmlEscape,
  formatTime,
};
