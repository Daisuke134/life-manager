# Keiki × Maritime: Life Manager Cloud 残作業・初週通過から1,000人までの実行計画

> **For agentic workers:** 実装時は superpowers:executing-plans を使い、各taskを一つずつ完了する。チェックボックスで進捗を記録する。状態と現在cursorの正本は統合SSOTだけに記録する。

**Goal:** 既に開発中のLife Manager Cloudを、Top 30選出に必要な動く証拠、実際に使う人、英語中心の配布につなぎ、公式の実利用者1,000人へ進める。

**Architecture:** 現在のLife Managerを同一repoのMaritime custom runtimeで実行する。既存Railway queue・tenant store・Capafy factory・Maritime receipt/reconciliation・Resendの日報をつなぐ。新しいプロダクト、scheduler、publisherは作らない。既存のLife Manager product page `/lm`、記事、既存Xアカウントを利用する。別のpublic pilot pageは作らない。

**Tech Stack:** 既存Node/CommonJS、Railway life-call/worker、Supabase Auth/Manager state、Maritime custom image/runtime、Capafy official API/receipt、既存Resend/CFO日報、既存UTM/funnel observer。

**Spec:** docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md の「Keiki × Maritime — 初週Top 30と実利用者1,000人」。最新のAs-Is/To-Be/statusは本計画ではなく、その正本の「更新された現在地・完了までの追跡表」を読む。

## Global Constraints

- 公式の最終条件は、6週間以内に実利用する別々の人1,000人へ達し、検証を受けること。先着3プロジェクトが対象。
- Top 30は第1週のcheckpoint。運営が公表していない採点配分・正確な初週締切を作らない。
- signup、pageview、投稿imp、agent/VM/subagent数は公式実利用者数にしない。founder/team/testは保守的に内部集計で別枠とし、実在するdistinct founder/team memberが公式に数えられるか主催者に確認する。明示された公式除外条件と内部方針を混同しない。
- 登録、明示的な保持条件同意、tenant-bound execution、実仕事receipt、結果メールreceipt、stopを別々に検証する。
- 利用者に目標・予算の入力、毎日の指示、Telegram連携を必須にしない。
- 未確認の外部effectを再送しない。effect_unknownは既存receiptで照合し、blind retryしない。
- FounderのCapafy account、browser session、商品、売上を別利用者へ共有しない。所有者のPKCEとMaritime保持条件への同意を代理で済ませない。
- 新しい利用者の私的な業務データを送る前に、保存条件と送信対象を示し、明示同意を記録する。
- 英語をglobal product、submission、demo、今後のlaunch assetの主言語にする。過去の日本語投稿は削除・再投稿せず、独立したconversionとして数えない。
- Distributionは既存アカウントと無料の所有チャネルを使う。広告・新規アカウント・複数回の不確かな投稿は行わない。
- 成功を主張する前に、native/provider receiptと公開先を再読する。記録のnullはunknownであってzeroではない。
- 正式提出は公式routeと必須fieldを確定して一度だけ行い、受付receiptを読む。既存Slack entryの再投稿はしない。

## Review Focus

1. 同じ人の複数アカウント、test traffic、signupだけをdistinct-user countへ誤算入しない。運営のcounting ruleで確かめる。
2. Maritimeの外部effectがtimeoutした時、同じCapafy publishを再実行しない。prepare/publish receiptとeffect fenceで照合する。
3. UID、Capafy subject、credential、browser sessionの所有者が一致しない時に実行を拒否する。
4. retention consent前に個人の業務内容をmodel/runtimeへ送信しない。
5. X/Threads/Instagramの投稿予約、URL削除、リンク先とUTMの違いを実際の公開先で再確認する。

---

Official reference: https://competition.maritime.sh/terms. Day-one public post: https://x.com/onkeiki/status/2112658078797791251. Round-one announcement does not publish an exact cutoff or scoring rubric.

## Metric Definitions

| Metric | Count rule | Source |
|---|---|---|
| Reach | Post impressions/views as returned by the platform; awareness only. | Native social readback |
| Visit | Unique tracked landing visitor, grouped by source/campaign/content without storing email or task text in analytics. | Existing web funnel/UTM observer |
| Signup | Email identity confirmed. Signup is not product usage. | Existing auth/enrollment store |
| Consent | Current product/data retention notice accepted through the explicit Manager action. | Tenant-bound consent record |
| First real use | Distinct human makes an actual request/action to the Life Manager; confirm that this precise event qualifies with organizers. | Keiki or Maritime project-level usage |
| Completed work | A bounded external task completes and has an authoritative provider receipt. | Central job/receipt chain + provider readback |
| Report delivered | Daily outcome email has an accepted provider receipt; accepted send is not inbox read. | Existing CFO/Resend receipt |
| Repeat use | Same authorized user returns and completes another qualifying use. Internal retention measure, not a separate official rule. | Tenant event + platform readback |
| Official competition count | Distinct real people with project-level Keiki or Maritime usage, after organizer verification. | Platform usage and organizer readback |

Do not present internal user cohort goals as organizer thresholds. Snapshot refresh: 2026-10-24 11:47Z, about 38.84 days remain to the official final deadline; verified user count and conversion remain unknown, so compute pace as (1,000 - N) / D only after obtaining N.

## Atomic Work Plan

### P0 — Resolve Round 1 unknowns through written organizer channels

**Owner:** Codex reads and records replies. The owner clarified that the Oct 25 10:00–10:15 JST office-hours conversation is about the future of the company, not Maritime rules or submission. Keep it separate and out of P0. The existing #competition-help question and 10/24 10:56:44Z organizer email follow-up already ask for the Round 1 cutoff, Top 30 criteria, official form/fields, counting rule, and Week 2. Do not duplicate them. Record an organizer reply or a dated no-reply readback for each field.

- [x] P0.1 Asked in the 10/24 10:56:44Z organizer follow-up; reply not found as of 11:47Z. Exact cutoff/timezone and Top 30 rubric remain UNKNOWN.
- [x] P0.2 Asked in the same follow-up; reply not found as of 11:47Z. Formal route, fields, and whether the Oct 21 channel entry is sufficient remain UNKNOWN.
- [x] P0.3 Asked in the same follow-up; reply not found as of 11:47Z. Qualifying activity, platform readback, founder/team treatment, and any repeat-use criterion remain UNKNOWN.
- [x] P0.4 Asked in the same follow-up; reply not found as of 11:47Z. Week 2 milestone and deadline remain UNKNOWN.
- [x] P0.5 Recorded the follow-up questions and dated no-reply status in requirements.json, the live readback, and the current tracker. Unknown fields remain UNKNOWN; do not duplicate the existing posts.
- [x] P0.6 Recalculated the planning estimate: seven calendar days after the Oct 20 kickoff is Oct 27. Exact official cutoff and timezone remain UNKNOWN.

**DONE when:** written organizer answer or a dated “no answer yet” readback exists for each field. This task does not block independent product/source work.

### P1 — Finish the already-started Cloud product path

**Owners:** The existing Codex/Maritime source claimant owns P1.1–P1.7 and keeps source changes on the claimed branch. The owner has explicitly authorized the existing PKCE/retention-consent flow in P1.8; Codex records only verified, owner-bound receipts. The connected browser or Gmail security boundary may still require the owner to request/open a fresh PKCE link in the same browser. Codex records tracker readbacks; Muse retains the Threads publish check and the owner retains Instagram SMS reconnection. This document does not transfer source or social claims.

- [x] P1.1a Snapshot current sources separately: origin/main is 6f81689f9e7bd5c12d296a2c4b73e5a2167ed379 at 11:47Z. Public EN pilot returned HTTP 200 at 11:47Z. Anicca life-call and money-printer-worker last SUCCESS deploys are 8e0e6f2 at 08:38:40Z; main deploy attempts at 11:46Z were SKIPPED; deployed apps/life-manager diff from current main is empty. The separate openclaw-lm-pilot SUCCESS deploy is from 2026-06-24 and the life-manager project service SUCCESS deploy is from 2026-09-11. PR #8745 remains OPEN/DRAFT head 764be4c2, base 5904b05 (not current), mergeable=false. Maritime image, end-to-end, official count, and cost remain unverified.
- [ ] P1.1b Read the existing T08/T16/T17/T18.9 plan and fetch exact-head CI/review status; identify current-base conflicts and record the source owner’s disposition.
- [ ] P1.2 Re-review the PR against current main. Keep its bounded prepare→receipt→publish chain, stable effect key, one attempt, read-only reconciliation, and report receipt. Resolve current-base conflicts without dropping later main work.
- [ ] P1.3 Close the actual missing trust boundary using existing T08/T16 ownership: resolve each participant's Capafy account/official subject/credential/browser session to that UID; ensure the host executor and automatic caller use only that binding; reject absent, ambiguous, or cross-tenant identity.
- [ ] P1.4 Add/retain focused red/green checks for valid tenant binding, wrong/missing owner, prepare receipt lost/unknown, publish replay, reconciliation present/absent/unknown, and report join to the same occurrence.
- [ ] P1.5 Run the source-boundary command, relevant provider/runtime/report checks, required CI for the exact current head, and an independent read-only review. Fix or classify every current finding. Do not merge because the previous head was green.
- [ ] P1.6 Integrate via the repository merge path only after current-head checks/review. Record merged SHA and new current main. This is source acceptance only, not deployment or product completion.
- [ ] P1.7 Build/deploy through the existing Maritime custom-image service and current main-derived sanitized artifact. Keep existing Railway app/worker identities. Read back artifact SHA, service deployment IDs/status, worker capability allowlist, owner binding, and health before any business effect.
- [ ] P1.8 Owner-authorized email PKCE/retention consent is still incomplete. A same-origin request returned HTTP 202 check_email and a Magic Link email arrived at 11:42:28Z. The request was initiated from a temporary Remote Desktop PKCE cookie jar; Gmail did not provide the one-use URL, so no callback, owner session, activation, enrollment, or consent was recorded. The owner must request and open a fresh link in the same actual browser; then verify the visible notice/checkbox and read back the owner-bound enrollment and consent_version receipt. Do not extract the hidden link or write a consent receipt directly.
- [ ] P1.9 Using that one authorized tenant and an explicitly bound business account, run one actual bounded task. Read back the same occurrence's trusted provider receipt, literal artifact/result, associated cost or UNKNOWN, and project-level Maritime/Keiki usage.
- [ ] P1.10 Confirm the report email accepted receipt and then stop. Read back paused state, no successor/new publish/send, and zero replay. Keep separate source, deployment, work-completion, email, and usage evidence.

**DONE when:** one current-main deployment has one authorized end-to-end tenant cycle with same-occurrence external receipt, report receipt and stop/replay-zero. A passing source suite alone does not close P1.

### P2 — Convert the working cycle into Top 30 proof

- [ ] P2.1 Update the existing English Life Manager product page to describe one manager across work, money, and everyday life; distinguish the current hosted Calendar workflow from the full Cloud target. Do not create or advertise a separate public pilot page. State availability and retention accurately until the corresponding readbacks pass.
- [ ] P2.2 Create an English 2–3 minute screen recording from the actual flow: signup/consent → manager selects work → visible action → provider receipt/result → email receipt → stop. No simulated result represented as production.
- [ ] P2.3 Make a one-page English submission packet using only confirmed data: user problem, what the agent does, live URL, actual demo, proof links, limits, measured counts with date, and next milestone. Keep all unknowns labeled.
- [ ] P2.4 Submit once via the organizer-confirmed route, verify receipt, and link it from the existing Slack entry if that is requested. Do not duplicate the project entry.
- [ ] P2.5 Read the organizer's Top 30 decision. Record selected/not selected/unknown and evidence; do not infer advancement from continued Slack access or social engagement.

**DONE when:** the official submission receipt and an explicit Top 30 status are recorded separately.

### D0 — Current distribution inventory (already completed)

- [x] D0.1 One English X launch post on @selawmqt with a direct tracked English pilot link; expanded destination returned HTTP 200 on 10/23.
- [x] D0.2 One @diceai0 Japanese awareness post that clicks through to the English post and pilot. It does not have independent Japanese conversion attribution.
- [x] D0.3 Existing English manager article is public and returned HTTP 200 on 10/24.
- [ ] D0.4 Refresh current impressions/clicks/landing/signup/first-use/cost readbacks. Existing post receipts are not user receipts.
- [ ] D0.5 Read Muse's response to the English Threads authorization and confirm author, existing account and destination before counting a post. If there is no confirmed publish receipt, leave pending. Instagram remains blocked pending owner SMS reconnect.

### D1 — Build a measurable English acquisition loop

**Distribution strategy:** Use one verified Life Manager workflow as the English anchor story. The existing EN X post and article are already live; once P1 proves the hosted cycle, create one honest 2–3 minute product demo and one tracked CTA, then adapt it for verified existing X, Threads, and Instagram identities. No duplicate launch copy. The 10/23 X audit found @selawmqt at 7 followers, about 5 median impressions across its last 20 posts and roughly 23 posts/day, while sampled high-reach builder accounts had reply-heavy timelines. Treat that as a baseline to test reply-first participation, not evidence that posting more will grow reach. Start with 10 real people outside the team who match the supported workflow, offer direct onboarding, record first-use friction and repeat use, and fix the largest measured drop-off. Compare native post metrics and the first-party funnel at 24 hours and 7 days; separate impressions, visits, qualified use, and official Keiki/Maritime counts.

- [ ] D1.1 Reuse the existing /lm product page, article, current X posts and tracked URL patterns. Assign one unique UTM content value per next authorized English post/account; confirm the actual expanded CTA after publishing. Keep one Life Manager product page; do not create a separate pilot page.
- [ ] D1.2 Add or use the existing funnel events for source → landing → confirmed signup → explicit consent → first actual use → completed work → report accepted → repeat use. Reuse T21's existing observer/cookie/store; do not build a second analytics framework.
- [ ] D1.3 Verify source attribution survives email confirmation and later enrollment without placing email, work text, cookies, or credentials in public analytics.
- [ ] D1.4 Run a first 10-person real-user cohort as an internal target after the owner flow works. Record onboarding failures, first task, completed/failed/deferred state, repeat use, and support burden. Do not describe 10 as an official cutoff.
- [ ] D1.5 Fix the largest measured conversion/use failure. Keep an experiment log with hypothesis, one change, dates, source, before/after counts, and uncertainty.
- [ ] D1.6 Repeat with measured cohort targets (50/200/500/1,000). Compute needed traffic from actual visitor→first-use conversion; never assume conversion from X impressions.
- [ ] D1.7 After P1 proof, run a measured reply-first English builder/hackathon participation experiment from the owner-authorized X identity; use the live demo/one tracked CTA only where relevant. Compare reach, profile visits, landing visits, and first qualifying uses against the 10/23 baseline. No paid promotion, repetitive solicitation, duplicate posts, fake users, or unverified outcomes.
- [ ] D1.8 At each checkpoint, reconcile first-party funnel count against Keiki/Maritime project usage and deduplicate by real person according to organizer instructions.
- [ ] D1.9 Keep a daily dated readback of native reach/clicks, unique visits, confirmed signups, explicit consent, first qualifying use, completed work, accepted report, repeat use, official platform count, and cost; keep unavailable fields null and record why. Compare native platform counts at 24 hours and 7 days after each authorized English post.

**DONE when:** dated evidence shows source-attributed real use and the official platform can verify the distinct-user count. Stop growth copy from claiming milestones the receipt does not support.

### P3 — Weeks 2–6 and final verification

- [ ] P3.1 After the Top 30 result, capture the new official Week 2 requirements and update this same plan and the canonical SSOT cursor. Do not create a second tracker.
- [ ] P3.2 Keep a weekly release/demo and measured acquisition cadence. Preserve receipts and participant consent for every cohort.
- [ ] P3.3 Improve onboarding and repeat use from observed drop-off. Prioritize product reliability and first successful work over new feature breadth.
- [ ] P3.4 Review project usage, participant count, cost, repeated use, and competitor/leaderboard status with the organizer at the cadence they provide.
- [ ] P3.5 Before Dec 1, 2026 23:59 America/Los_Angeles, reconcile the final Keiki/Maritime distinct-user count, remove duplicates/invalid activity, and obtain organizer verification.
- [ ] P3.6 Record whether the project reached 1,000 and whether it was among the first three verified projects. Prize/credit/travel receipt is a separate outcome; do not promise cash or international flights not confirmed by terms.

**DONE when:** official project usage and organizer verification confirm the count and rank, or final status is explicitly recorded as not achieved/unknown.

## Dependency Order and Parallel Lanes

1. P0 requirements clarification and P1 source/owner prep start immediately and proceed in parallel.
2. P1.3 trusted binding → P1.5 current-head acceptance → P1.7 deployment → P1.8 owner consent → P1.9 real work → P1.10 report/stop.
3. P0 answers determine P2.3/P2.4 submission details. Prepare the truthful packet while the form is unknown; do not submit to an invented route.
4. D0.4/D0.5/D1.1–D1.3 can proceed alongside P1 without waiting for a revenue outcome. Public claims must continue to say early pilot until P1 is complete.
5. P2.5 gates the Week 2 plan; P3.1 inserts new rules into the same tracker; D1.6 growth continues through the common Dec 1 deadline.

## State Ownership

The integrated SSOT owns current status, task ordering, and the single cursor. This plan contains detailed implementation steps and acceptance evidence only; update the SSOT when a task, requirement, or blocker changes.
