# Life Manager demo capture plan

> Historical snapshot from 2026-10-21. Its dated counts, URLs, and statuses are not the current readback. Current status and cursor: [integrated SSOT](../../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md); current evidence: [2026-10-24 readback](../../../evidence/maritime/live-readback-20261024-1102Z.json).


**Readback at 2026-10-21 11:10 UTC:** this file contains a shot list; no video has been captured or published. EN/JA production routes return HTTP 200, but both still describe daily email as current behavior and omit that the hosted cycle is unverified. Production is on SHA `982875d`; latest main is `cab4320` and contains source changes after the original copy fix. Owner PKCE/retention consent and the hosted work-to-report cycle are unverified; latest internal participant, execution, completed-work, and report counts are 0. Capture gates below prevent screenshots, narration, or edits from implying otherwise.

**Audience and goal:** reviewers and prospective pilot users should see one truthfully labeled manager cycle: email entry, Life Manager choosing work without a user-entered goal or budget, an artifact, a provider-confirmed result only if one exists for that same job, and a report only if its provider receipt exists. The demo must not imply the full hosted cycle is verified today. Existing research suggests one specific problem → visible action/result → one proof point → one CTA. Source map: docs/research/maritime/2026-10-20-source-map.md. Todoist, Ahrefs, Levels, Arc, and Panda provide mechanisms only; no same-product causal example proves this campaign will reach 1,000 users. Their metrics are not Life Manager results.

## 30-second X video

Use 9:16 format for the existing X identity. Do not create an Instagram account or route the pilot into another product-specific account.

| Time | Shot and source | Caption / narration | Capture gate and evidence |
|---|---|---|---|
| 0–5s | `GET /maritime?lang=en` or `GET /maritime?lang=ja` | “Early pilot: Life Manager is designed to choose work without a goals-and-budget setup.” | Latest GETs at 11:10Z returned HTTP 200, but the live copy is not capture-ready: it presents daily email as current and omits the hosted-cycle caveat. The GET is page evidence only, not signup or work evidence. Mask email, query IDs, and browser profile. |
| 5–11s | `POST /maritime/activate`, then the runtime's provision and selected cycle receipts | “Life Manager chooses the next task; here is the run tied to this account.” | `/maritime/activate` returns a pending/active status, not proof of work. Show the common `maritime_manager_cycle` receipt with the same `job_id`, `occurrence_id`, `execution_id`, and `release_sha`. Do not show a mock selector as live. |
| 11–18s | `GET /maritime/artifacts/{encoded_job_id}/{artifact_path}` and its verified artifact | “Here is the output file and its hash.” | The route only serves an artifact attached to a verified completed cycle receipt. The current cycle receipt has no external provider result reference; do not say a seller/provider confirmed revenue or completion until that same job has an official provider receipt. |
| 18–24s | `maritime.manager.report` job and the report sent receipt | “The report separates completed work, confirmed revenue, costs, and unknowns.” | Show the same `period_key`/`release_sha` and `kind=maritime_manager_report` receipt with `provider_message_id` and `external_ref=resend-email://…`. Inbox arrival is a separate fact. Redact recipient address, identifiers, and private financial details. |
| 24–30s | Corrected live pilot page and share URL | “Try the early pilot. The hosted cycle is still being validated; review the data-retention notice first.” | Require the current-main deployment SHA, then fresh HTTP 200/body readback for both locales. Use the same URL as the CTA; retain retention and no-revenue-guarantee disclosures. |

**Current capture status:** shot 1 is not capture-ready because the live page still makes the daily-email claim. Shots 2–4 are not capture-ready because no owner-consented hosted cycle/report exists. Shot 5 is not capture-ready until the live copy is corrected. Do not substitute a fabricated user, run, provider receipt, email, sales number, testimonial, or balance. An illustrative screen may appear only with a visible “concept, not live” label and must not serve as the competition proof demo.

## Two-minute reviewer demo

| Time | Evidence shown | Required source / privacy boundary |
|---|---|---|
| 0–15s | Product statement: Manager is designed to select work, act, check the result, and report it; no goal/budget setup is required. | Use corrected public copy and disclose that the complete hosted cycle is unverified until evidence exists. |
| 15–35s | `GET /maritime`, `POST /auth/maritime/email`, same-browser confirmation/PKCE, then `POST /maritime/activate`. | Show the retention notice before activation. Mask email, session cookies, confirmation tokens, and all identifiers. Activation status alone is not a work receipt. |
| 35–60s | `maritime.manager.provision` and `maritime.manager.cycle` receipts for one account. | Match `tenant_id`, `job_id`, `occurrence_id`, `execution_id`, and `release_sha`; show the manager's work choice and running Cloud occurrence. No user-provided daily task or invented autonomy. |
| 60–85s | `GET /maritime/artifacts/{encoded_job_id}/{artifact_path}` and the verified artifact. | Show artifact hash and the `maritime_manager_cycle` receipt. Add a provider receipt only if it joins to this exact job; the current receipt contract has no provider receipt refs. Label revenue “unverified” when absent. |
| 85–105s | `maritime.manager.report` receipt and `POST /maritime/stop`. | Show `kind=maritime_manager_report`, Resend message ID, then stop response `status=paused` and the persisted paused state. A `202`/`cleanupPending` response is not cleanup completion. Hide recipient data. |
| 105–120s | Competition status and CTA. | Give only verified distinct-user counts from Keiki/Maritime project usage; distinguish internal/official counts. Show the corrected pilot URL and limitations. Current official-user count is unverified and internal counts are 0. |

## T25 capture and publication gates

- The shot list names exact public routes, worker capabilities, receipt kinds, and same-job join fields. A recorded route response alone does not prove that the hosted work/report cycle completed.
- T25.3 captures only after T22.1e.2's real cycle provides usable work/result/report receipts and T26.5b confirms the public copy. Reuse the existing capture and video workspace.
- T25.4 packages the 9:16 X cut, 16:9 reviewer cut, subtitles, thumbnail, and caption only after source footage passes the gates. No Instagram publication is in this plan.
- Use the existing HyperFrames skill/CLI when the capture is ready; do not add a renderer or audio service.
- The URL-share email to Dais already has a sent receipt. Do not resend it as a substitute for correcting the landing page.