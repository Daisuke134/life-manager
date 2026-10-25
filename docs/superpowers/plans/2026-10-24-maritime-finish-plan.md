# Keiki × Maritime: Life Manager Cloud 残作業・初週通過から1,000人までの実行計画

> **For agentic workers:** 実装時は superpowers:executing-plans を使い、各taskを一つずつ完了する。チェックボックスで進捗を記録する。状態と現在cursorの正本は統合SSOTだけに記録する。

**Goal:** 既に開発中のLife Manager Cloudを、Top 30選出に必要な動く証拠、実際に使う人、英語中心の配布につなぎ、公式の実利用者1,000人へ進める。

**Architecture:** Life Managerは一つの製品で、LocalとCloudは実行モード。`aniccaai.com/lm`が唯一の公開製品ページで、同じoriginの`/maritime`は認証・開始・状態確認の経路であり、別製品やpilot pageではない。Netlify rewrite経由で既存Railway `life-call` control planeへ接続し、各顧客の実行は専用Maritime VMに分離する。`/auth/google`と`/auth/google/callback`も同じoriginでproxyし、PKCE cookieとcallbackを同一hostに保つ。Railwayはcontrol plane/workerであり、公開Webサイトや各顧客のVMを置く場所ではない。Google sign-inがWebの入口。Calendar/Gmail inbox権限、task/goal/budget入力、payout情報はsignupで求めない。Capafyは最初のCloud収益workflow。既存queue・tenant store・Capafy factory・Maritime receipt/reconciliation・Resend日報をつなぐ。新しい製品、別のpublic pilot page、fake/demo stateは作らない。

**利用体験:** Googleログインは本人確認だけでCalendar/Gmail inbox権限を要求しない。保持条件と自律実行への同意後、Managerはtask/goal/budgetを聞かずにCapafy収益workflowを開始し、確認済みの仕事・結果をログインメールへ送る。Webは入口と実際の状態確認に使う。最初の検証済みwork-to-email loopに会話UIは必須ではなく、会話は実APIとtenant-bound durable stateにつながり、測定した利用者ニーズを解く場合に限って追加する。Calendarは必要な仕事が出た後にのみ接続する。Capafyのpayout/bank detailsはsignupで要求せず、Publisher Certification後に追加できる。実際のjob/receiptに結びつかないchatやdashboardを公開しない。

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
- CapafyのPublisher Agreement §2.9は「one Publisher Account per Publisher」を定め、書面承認なしの複数Publisher Accountを認めない。新規登録は、このPublisherに許された唯一のaccountか、Capafyの書面例外がある場合に限る。最初のSkill公開前にPublisher Certification、本人確認資料、返金不可US$0.99申請料が必要。振込先はCertification後に追加でき、公開前には不要。[Publisher Agreement](https://capafy.ai/publisher-agreement/) · [Certification](https://capafy.ai/developer/doc/1.3) · [Payout setup](https://capafy.ai/developer/doc/3.5)
- Cloud account開始時にCalendar/Gmail OAuth scopeやpayout accountを求めない。Google OAuthで得るのはverified identity/emailだけ。日報はアプリのemail providerからverified addressへ送る。
- 新しい利用者の私的な業務データを送る前に、保存条件と送信対象を示し、明示同意を記録する。
- 英語をglobal product、submission、demo、今後のlaunch assetの主言語にする。過去の日本語投稿は削除・再投稿せず、独立したconversionとして数えない。
- Distributionは既存アカウントと無料の所有チャネルを使う。広告・新規アカウント・複数回の不確かな投稿は行わない。
- 成功を主張する前に、native/provider receiptと公開先を再読する。記録のnullはunknownであってzeroではない。
- 正式提出は公式routeと必須fieldを確定して一度だけ行い、受付receiptを読む。既存project entryを重複登録しない。

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
| Signup | Verified Google identity. Signup is not product usage. | Existing auth/enrollment store |
| Consent | Current product/data retention notice accepted through the explicit Manager action. | Tenant-bound consent record |
| First real use | Distinct human makes an actual request/action to the Life Manager; confirm that this precise event qualifies with organizers. | Keiki or Maritime project-level usage |
| Completed work | A bounded external task completes and has an authoritative provider receipt. | Central job/receipt chain + provider readback |
| Report delivered | Daily outcome email has an accepted provider receipt; accepted send is not inbox read. | Existing CFO/Resend receipt |
| Repeat use | Same authorized user returns and completes another qualifying use. Internal retention measure, not a separate official rule. | Tenant event + platform readback |
| Official competition count | Distinct real people with project-level Keiki or Maritime usage, after organizer verification. | Platform usage and organizer readback |

Do not present internal user cohort goals as organizer thresholds. Snapshot refresh: 2026-10-24 11:47Z, about 38.84 days remain to the official final deadline; verified user count and conversion remain unknown, so compute pace as (1,000 - N) / D only after obtaining N.

## Atomic Work Plan

### P0 — Resolve Round 1 unknowns through written organizer channels

**Owner:** Codex reads public official updates and the existing organizer email thread. The owner clarified that the Oct 25 10:00–10:15 JST office-hours conversation is about the future of the company, not Maritime rules or submission. Keep it separate and out of P0. The 10/24 10:56:44Z organizer email follow-up already asks for the Round 1 cutoff, Top 30 criteria, official form/fields, counting rule, and Week 2. Do not send a duplicate inquiry. Record an organizer reply or a dated no-reply readback for each field.

- [x] P0.1 Asked in the 10/24 10:56:44Z organizer follow-up; reply not found as of 11:47Z. Exact cutoff/timezone and Top 30 rubric remain UNKNOWN.
- [x] P0.2 Asked in the same follow-up; reply not found as of 11:47Z. Formal route, fields, and whether the Oct 21 channel entry is sufficient remain UNKNOWN.
- [x] P0.3 Asked in the same follow-up; reply not found as of 11:47Z. Qualifying activity, platform readback, founder/team treatment, and any repeat-use criterion remain UNKNOWN.
- [x] P0.4 Asked in the same follow-up; reply not found as of 11:47Z. Week 2 milestone and deadline remain UNKNOWN.
- [x] P0.5 Recorded the follow-up questions and dated no-reply status in requirements.json, the live readback, and the current tracker. Unknown fields remain UNKNOWN; do not duplicate the existing posts.
- [x] P0.6 Recalculated the planning estimate: seven calendar days after the Oct 20 kickoff is Oct 27. Exact official cutoff and timezone remain UNKNOWN.
- [ ] P0.7 Refresh the official competition page and existing organizer email thread before submission. Confirm the current cutoff/timezone, Top 30 rubric, Week 2 milestone, official counting rule, and form/required fields. If still unanswered, preserve UNKNOWN and prepare no unsupported submission claim.

**DONE when:** written organizer answer or a dated “no answer yet” readback exists for each field. This task does not block independent product/source work.

### P1 — Finish the already-started Cloud product path

**Product acceptance:** One Life Manager product, with Cloud running in a tenant-isolated Maritime VM. Netlify serves the product site at aniccaai.com/lm; the same-origin /maritime route handles Google sign-in, consent, start, and state. Google login is identity-only. Do not ask for Calendar/Gmail permissions, a task/goal/budget prompt, Telegram, or bank details during signup. Result reports use Life Manager's email provider at the verified sign-in address. A chat UI is optional after measured need; it must connect to real tenant state and receipts.

- [x] P1.1 Identify the source and runtime blocker. Latest successful production readback at 2026-10-25 13:56Z: /lm and /lm/ja were old, Calendar-focused pages (HTTP 200); same-origin /maritime was HTTP 404. This turn's follow-up HTTP fetch failed. The last Railway config readback at 11:48Z had no LM_MARITIME_WEB_ORIGIN. No current Supabase redirect allowlist readback.
- [ ] P1.2 Finish and manually review source PR #8986 at 6c8d3259f61e03fa773c47b4b1320a4f6a09d254. Local tests: marketing 3/3, web-auth/distribution 34/34. Most CI checks pass, but arm64 and x86_64 loop-control checks were still running at the 14:03Z readback; CodeRabbit says manual review required and GitHub reviewDecision is empty. Merge only after exact-head CI and review complete.
- [ ] P1.3 Sync provider PR #8745 at 3703b161205180555f0dd96af63131720bcc0e3e to the accepted current main and resolve overlapping onboarding code without losing Google-first copy or the Capafy UI. The branch includes tenant-bound Capafy credential storage, policy consent, trusted receipt chain, fail-closed admission, and bounded recovery. Its source tests passed: focused 85/85, runtime-up 76/76, runtime-adapters 377 PASS/1 SKIP, PostgreSQL binding/RLS migration integration PASS, source-boundary PASS. At 14:03Z the x86_64 loop-control CI job still ran; reviewDecision was empty and PR remained Draft.
- [ ] P1.4 Complete the missing production Capafy host executor/provider injection and deploy-safe secret/migration configuration. Resolve credentials only through the authenticated tenant binding; never send tokens to the model, VM prompt, artifacts, logs, UI, or email. Keep provider flags OFF until a current-image real receipt/reconciliation test passes. Capafy actions must use official endpoints and stop when publisher confirmation is required.
- [ ] P1.5 Deploy accepted backend/runtime through current Maritime configuration. Configure Railway origin and the exact Supabase redirect URL for https://aniccaai.com/auth/google/callback. Verify Google identity-only PKCE, tenant-bound enrollment, dedicated VM readiness, activation/state/stop, tenant isolation, and rollback. A successful web login or VM provision is not a Capafy earning result.
- [ ] P1.6 Obtain publisher-controlled Capafy account and policy prerequisites: confirm it is the person's/entity's first and only Publisher Account or obtain Capafy's written exception; explicitly accept Capafy Terms of Service and Privacy Policy before OTP login; complete Certification, required evidence, and the non-refundable US$0.99 fee before first Skill publication; confirm Skills/configuration on Capafy's website for every Agent/version. No duplicate account and no payout/bank request at signup. These vendor confirmation steps mean the product cannot claim fully no-human-loop publication.
- [ ] P1.7 Run one bounded real test through the whole chain: Google login → retention/autonomy/email consent → one tenant VM → actual Capafy work and official publication receipt → matching Life Manager receipt → accepted verified-address report email → Stop and replay-zero. Capture usage, cost, uncertainty, and each boundary separately. Do not report mock/demo state as success.

**P1 DONE when:** a production current-main build completes one owner-authorized tenant cycle with a native Capafy effect receipt, matching Life Manager and email receipts, and verified Stop/replay-zero. Source checks do not close this gate.

### P2 — Ship one real public Cloud route and turn verified use into contest proof

- [ ] P2.1 Netlify PR #743 is Draft at head 4990c5617eacbfe961e23b97f210d15841d0eebf. It pins Life Manager marketing source 6c8d3259f61e03fa773c47b4b1320a4f6a09d254 and adds same-origin proxy rewrites for /maritime and Google OAuth. The routing contract passed 51/51 locally; exact-head Landing CI is pending. Keep this draft until the backend is deployed and its same-origin behavior can be verified.
- [ ] P2.2 After P1 passes, merge/deploy the Netlify PR, then smoke-test English/Japanese /lm, same-origin /maritime and OAuth callback, PKCE cookie, user state, Capafy result/email, rollback. Do not expose the old Railway pilot through the new public route.
- [ ] P2.3 Refresh the official Maritime competition page and the existing organizer channel for the current form, deadline/timezone, counting rule, Round 1/Week 2 criteria, and required fields. The owner reports the form opens 2026-10-26; this is not yet independently verified. Preserve UNKNOWN where the official source has no answer.
- [ ] P2.4 Prepare one English submission from the real flow: what Life Manager does beyond travel-time planning, live product URL, truthful demo, receipt links, limits, and date-stamped usage/counts. Submit once only through the confirmed official route and preserve its receipt. Do not infer submission or advancement from social metrics.

**P2 DONE when:** the real product route is public, the organizer confirms the submission route, and the official receipt and advancement status are read back separately.

### D0 — Current distribution inventory (already completed)

- [x] D0.1 One English X launch post on @selawmqt with a direct tracked English pilot link; expanded destination returned HTTP 200 on 10/23.
- [x] D0.2 One @diceai0 Japanese awareness post that clicks through to the English post and pilot. It does not have independent Japanese conversion attribution.
- [x] D0.3 Existing English manager article is public and returned HTTP 200 on 10/24.
- [ ] D0.4 Refresh current impressions/clicks/landing/signup/first-use/cost readbacks. Existing post receipts are not user receipts.
- [ ] D0.5 Read Muse's response to the English Threads authorization and confirm author, existing account and destination before counting a post. If there is no confirmed publish receipt, leave pending. Instagram remains blocked pending owner SMS reconnect.

### D1 — Build a measurable English acquisition loop

**Distribution strategy:** Use one verified Life Manager workflow as the English anchor story. The existing EN X post and article are already live; once P1 proves the hosted cycle, create one honest 2–3 minute product demo and one tracked CTA, then adapt it for verified existing X, Threads, and Instagram identities. No duplicate launch copy. The 10/23 X audit found @selawmqt at 7 followers, about 5 median impressions across its last 20 posts and roughly 23 posts/day, while sampled high-reach builder accounts had reply-heavy timelines. Treat that as a baseline to test reply-first participation, not evidence that posting more will grow reach. Start with 10 real people outside the team who match the supported workflow, offer direct onboarding, record first-use friction and repeat use, and fix the largest measured drop-off. Compare native post metrics and the first-party funnel at 24 hours and 7 days; separate impressions, visits, qualified use, and official Keiki/Maritime counts.

- [ ] D1.1 Reuse the existing `/lm` product page, article, current X posts, and tracked URL patterns. Assign one unique UTM content value per next authorized English post/account; confirm the actual expanded CTA after publishing. Keep one Life Manager product page and one same-origin Cloud route; do not create a separate pilot page.
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
4. D0.4/D0.5/D1.1–D1.3 can proceed alongside P1 without waiting for a revenue outcome. Public claims must describe only the live, verified behavior; do not claim completed income work or customer revenue until the same-tenant provider/report receipts prove it.
5. P2.5 gates the Week 2 plan; P3.1 inserts new rules into the same tracker; D1.6 growth continues through the common Dec 1 deadline.

## State Ownership

The integrated SSOT owns current status, task ordering, and the single cursor. This plan contains detailed implementation steps and acceptance evidence only; update the SSOT when a task, requirement, or blocker changes.
