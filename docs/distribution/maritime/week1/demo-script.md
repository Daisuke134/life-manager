# Life Manager demo capture plan

**State at 2026-10-21 10:49 UTC:** script/shot list only; no video has been captured or published. The production signup page returns HTTP 200 but still describes daily email as current behavior. The owner PKCE/retention consent and hosted work-to-report cycle are unverified; internal manager participants, executions, completed work, and reports are 0. Capture gates below prevent screenshots, narration, or edits from implying otherwise.

**Audience and goal:** reviewers and prospective pilot users should see one real manager cycle: email entry, Life Manager choosing work without a user-entered goal or budget, the work result, an evidence-backed daily report, and the exact URL to try. Existing research suggests one specific problem → visible action/result → one proof point → one CTA. Source map: docs/research/maritime/2026-10-20-source-map.md. Todoist, Ahrefs, Levels, Arc, and Panda provide mechanisms only; no same-product causal example proves this campaign will reach 1,000 users. Their metrics are not Life Manager results.

## 30-second X video

Use 9:16 format for the existing X identity. Do not create an Instagram account or route the pilot into another product-specific account.

| Time | Shot and source | Caption / narration | Capture gate and evidence |
|---|---|---|---|
| 0–5s | Email entry at GET /maritime?lang=en or ?lang=ja | “Give Life Manager an email, not a list of goals and budgets.” | T26.5b must first correct the live page. Mask email, query IDs, and browser profile. The page GET alone proves neither signup nor work. |
| 5–11s | Same user's authenticated activation and the runtime's selected work | “Life Manager chooses the next useful task and starts it without a daily instruction.” | T22.1e.2 must produce a real activation and cycle. Show one safe run/occurrence reference and the loaded release; do not show a mock selector as live. |
| 11–18s | Output artifact and external provider result | “Here is the work and what the provider confirmed.” | Show the artifact hash and provider receipt/status for the same occurrence. If no provider result exists, label the shot “not verified” and do not imply completion or earnings. |
| 18–24s | The actual report in the recipient mailbox | “The report separates completed work, confirmed revenue, costs, and unknowns.” | Show a real sent/read receipt tied to the same occurrence. Redact recipient address, identifiers, and private financial details. No email capture until a real report arrives. |
| 24–30s | Corrected live pilot page and share URL | “Try the early pilot. The hosted cycle is still being validated; review the data-retention notice first.” | Require T26.5b and a fresh HTTP 200/body readback for both locales. Use the same URL as the CTA; retain retention and no-revenue-guarantee disclosures. |

**Current capture status:** shot 1 is not capture-ready because the live page still makes the daily-email claim. Shots 2–4 are not capture-ready because no owner-consented hosted cycle/report exists. Shot 5 is not capture-ready until the live copy is corrected. Do not substitute a fabricated user, run, provider receipt, email, sales number, testimonial, or balance. An illustrative screen may appear only with a visible “concept, not live” label and must not serve as the competition proof demo.

## Two-minute reviewer demo

| Time | Evidence shown | Required source / privacy boundary |
|---|---|---|
| 0–15s | Product statement: Manager selects work, acts, checks the result, and reports it; no goal/budget setup is required. | Use corrected public copy; do not call the hosted cycle complete. |
| 15–35s | Email signup and retention notice, followed by the owner-consented session. | GET /maritime plus actual email verification/PKCE. Mask email, session cookies, and all tokens. The retention notice must be visible before activation. |
| 35–60s | Life Manager's self-selected work and the running Cloud occurrence. | Same user, job, occurrence, and loaded release across receipts. No user-provided daily task or invented autonomy. |
| 60–85s | Artifact and external provider result. | Show artifact hash, provider receipt/status, and any confirmed amount/currency. Label absent revenue “unverified”; do not use founder/local revenue as a pilot user's result. |
| 85–105s | Daily result email and stop state. | Show provider message receipt and same-occurrence report; read back the stop route/state. Hide recipient data. |
| 105–120s | Competition status and CTA. | Give only verified distinct-user counts from Keiki/Maritime project usage; distinguish internal/official counts. Show the corrected pilot URL and limitations. |

## T25 capture and publication gates

- T25.1/T25.2 define this exact 5-shot narrative, source evidence, privacy handling, and non-live labels. They do not mean footage exists.
- T25.3 captures only after T22.1e.2's real cycle provides usable work/result/report receipts and T26.5b confirms the public copy. Reuse the existing capture and video workspace.
- T25.4 packages the 9:16 X cut, 16:9 reviewer cut, subtitles, thumbnail, and caption only after source footage passes the gates. No Instagram publication is in this plan.
- Use the existing HyperFrames skill/CLI when the capture is ready; do not add a renderer or audio service.
- The URL-share email to Dais already has a sent receipt. Do not resend it as a substitute for correcting the landing page.
