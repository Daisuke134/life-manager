# REAL literal diff — Slice "call says the right event + escalates 15/10/5" (P3+P4)
# Grounded against exact current lines (read 2026-06-17). 6 hunks across 5 files.
# Fixes: call always speaks a hardcoded "dentist"; no urgency; offsets 15/14/13/5.
# After: call speaks the SPECIFIC event + tone escalates (15 calm → 10 firm → 5 harsh).

## HUNK 1 — skills/life/call/call.js  (placeCall forwards event+urgency)
```diff
 function placeCall(opts = {}) {
   const provider = opts.provider || process.env.LIFE_CALL_PROVIDER || "telnyx";
   const runner = runnerFor(provider);
   const args = [runner];
   if (opts.to) args.push(`--to=${opts.to}`);
+  if (opts.event) args.push(`--event=${JSON.stringify(opts.event)}`);
+  if (opts.urgency) args.push(`--urgency=${opts.urgency}`);
   if (opts.dryRun) args.push("--dry-run");
   const r = spawnSync("node", args, { stdio: "inherit", env: process.env });
   return r.status == null ? 1 : r.status;
 }
```

## HUNK 2 — skills/life/call/call.js  (CLI parses event+urgency)
```diff
   for (let i = 0; i < argv.length; i++) {
     if (argv[i] === "--provider") opts.provider = argv[++i];
     else if (argv[i].startsWith("--provider=")) opts.provider = argv[i].split("=")[1];
     else if (argv[i] === "--to") opts.to = argv[++i];
     else if (argv[i].startsWith("--to=")) opts.to = argv[i].split("=")[1];
+    else if (argv[i].startsWith("--event=")) opts.event = JSON.parse(argv[i].slice("--event=".length));
+    else if (argv[i].startsWith("--urgency=")) opts.urgency = argv[i].slice("--urgency=".length);
   }
```

## HUNK 3 — apps/landing/scripts/life-call-telnyx.mjs  (parse + forward to bridge)
```diff
 const args = process.argv.slice(2);
 const DRY = args.includes("--dry-run");
 let TO = process.env.LIFE_CALL_TO || "+<YOUR_E164_NUMBER>"; // Dais's real number (spec27 B-call)
 for (const a of args) if (a.startsWith("--to=")) TO = a.slice("--to=".length);
+let EVENT_JSON = "";
+let URGENCY = "";
+for (const a of args) {
+  if (a.startsWith("--event=")) EVENT_JSON = a.slice("--event=".length);
+  else if (a.startsWith("--urgency=")) URGENCY = a.slice("--urgency=".length);
+}
```
```diff
 bridge = spawn(
   "node",
-  [path.join(here, "call-bridge.cjs"), "--port", String(PORT), "--provider", "telnyx"],
+  [path.join(here, "call-bridge.cjs"), "--port", String(PORT), "--provider", "telnyx",
+    ...(EVENT_JSON ? ["--event", EVENT_JSON] : []),
+    ...(URGENCY ? ["--urgency", URGENCY] : [])],
   { ... }
 );
```

## HUNK 4 — apps/landing/scripts/call-bridge.cjs  (parse --urgency, KILL fake dentist default)
```diff
     else if (argv[i] === "--event") a.event = JSON.parse(argv[++i]);
     else if (argv[i] === "--provider") a.provider = String(argv[++i] || "twilio").toLowerCase();
+    else if (argv[i] === "--urgency") a.urgency = String(argv[++i] || "");
```
```diff
-function startServer({ port, event, provider }) {
+function startServer({ port, event, provider, urgency }) {
```
```diff
-  // The event Charon talks about; default = a dentist appointment 15 min out.
-  const callEvent = event || {
-    summary: "伊藤歯科 (dentist)",
-    start: { dateTime: "2026-06-16T09:45:00+09:00" },
-    location: "表参道",
-  };
+  // The event Charon talks about. NO fake default — a real call MUST carry a real event.
+  if (!event) { console.error("[bridge] no --event; refusing a fake call"); process.exit(1); }
+  const callEvent = event;
```
REVIEW-FIX 4d: line 135 lives in `geminiSetupForEvent(event, model)` (NOT startServer) — `callEvent`/`urgency`
are out of scope there → would ReferenceError. Thread urgency THROUGH that function instead:
```diff
# geminiSetupForEvent (~line 131): add urgency param; buildCallPrompt uses its own in-scope params
-function geminiSetupForEvent(event, model) {
+function geminiSetupForEvent(event, urgency, model) {
   return buildGeminiSetup({
     model: model || LIVE_MODEL,
     voiceName: "Charon",
-    systemInstruction: buildCallPrompt(event),
+    systemInstruction: buildCallPrompt(event, urgency),
   });
 }
```
```diff
# the call site inside startServer (~line 218) where callEvent + urgency ARE in scope:
-  geminiSend(geminiSetupForEvent(callEvent));
+  geminiSend(geminiSetupForEvent(callEvent, urgency));
```

## HUNK 5 — apps/landing/netlify/functions/_lib/call-logic.js  (buildCallPrompt escalating tone)
```diff
-function buildCallPrompt(event) {
+function buildCallPrompt(event, urgency) {
   const e = event || {};
   const title = (e.summary || "your next appointment").toString().trim() || "your next appointment";
   const time = formatTime(e.start && e.start.dateTime);
   const location = (e.location || "").toString().trim();
+  const tone =
+    urgency === "harsh" ? "Be urgent and firm. They must leave RIGHT NOW or they will be late — push them hard." :
+    urgency === "firm"  ? "Be firm. It is really time to go now." :
+                          "Gently let them know it's about time to head out.";

   const lines = [
     "You are Anicca, a calm, concise voice assistant calling the user on the phone.",
     "Speak naturally and warmly. Keep it short. This is a two-way call — answer follow-ups.",
     `The user's next event is "${title}"${time ? ` at ${time}` : ""}.`,
     location ? `It is at ${location}.` : "",
-    "Tell them it's time to leave now so they arrive on time, then ask if they need directions or anything else.",
+    tone,
+    "Then ask if they need directions or how to get there.",
     `Open with: "Hi, it's Anicca. Your next event is ${title}${time ? ` at ${time}` : ""} — time to leave now."`,
   ].filter(Boolean);

   return lines.join(" ");
 }
```

## HUNK 6 — skills/life/locate/locate.js  (offsets 15/10/5 + dialOnce passes event+urgency)
```diff
-const SCHEDULE_OFFSETS_MIN = (process.env.LIFE_SCHEDULE_OFFSETS || "15,14,13,5")
+const SCHEDULE_OFFSETS_MIN = (process.env.LIFE_SCHEDULE_OFFSETS || "15,10,5")
   .split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n));
```
```diff
+function toneFor(offMin) { return offMin >= 15 ? "calm" : offMin >= 10 ? "firm" : "harsh"; }
-function dialOnce({ dryRun, reason }) {
+function dialOnce({ dryRun, reason, event, urgency }) {
   if (dryRun) {
     console.log(JSON.stringify({ event: "would-call", reason }));
     return 0;
   }
   console.log(JSON.stringify({ event: "calling", reason }));
-  return placeCall({});
+  return placeCall({ event, urgency });
 }
```
```diff
# in runScheduleLoop's due-fire loop (~line 255):
-      dial({ dryRun, reason: `T-${d.offsetMin}min${d.emergency ? " EMERGENCY" : ""}` });
+      dial({ dryRun, event: opts.event, urgency: toneFor(d.offsetMin), reason: `T-${d.offsetMin}min` });
```
REVIEW-FIX 6 Gap 1+2: `opts.event` is never populated (parseArgs lacks `--event`; main passes neither loop
an event) → with the dentist default gone, the bridge would `exit(1)` and NEVER dial. Add these:
```diff
# locate.js parseArgs (~268-277): add --event
     else if (argv[i] === "--mode") opts.mode = argv[++i];
     else if (argv[i] === "--event-start") opts.eventStartMs = Date.parse(argv[++i]);
+    else if (argv[i] === "--event") opts.event = JSON.parse(argv[++i]);
+    else if (argv[i].startsWith("--event=")) opts.event = JSON.parse(argv[i].slice("--event=".length));
     else if (argv[i] === "--dry-run") opts.dryRun = true;
```
```diff
# locate.js main (~279-295): pass event into BOTH loops
-    const r = await runScheduleLoop({ dryRun, eventStartMs });
+    const r = await runScheduleLoop({ dryRun, eventStartMs, event: opts.event });
...
-    const r = await runLiveLocationLoop({ dryRun });
+    const r = await runLiveLocationLoop({ dryRun, event: opts.event });
```
```diff
# locate.js runLiveLocationLoop dial (~223): also name the event (not generic); firm tone while not moving
-      dial({ dryRun, reason: `not-moving (attempt ${attempts + 1})` });
+      dial({ dryRun, event: opts.event, urgency: "firm", reason: `not-moving (attempt ${attempts + 1})` });
```
After these, NO path calls `placeCall({})` generic → no bridge refusal → the call always names the real event.

## NOT in this slice (separate reviewed diffs follow): P1 travel search→ask spine, P4 planner.js
## scheduler (gcal→--at), P2 ask Gmail-poll, P5 notify motion-gate, P0 consolidate into anicca.
