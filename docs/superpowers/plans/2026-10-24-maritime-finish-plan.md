# Keiki × Maritime: Life Manager Cloud 残作業・初週通過から1,000人までの実行計画

> **For agentic workers:** 実装時は superpowers:executing-plans を使い、各taskを一つずつ完了する。チェックボックスで進捗を記録する。状態と現在cursorの正本は統合SSOTだけに記録する。

**Goal:** 既に開発中のLife Manager Cloudを、Top 30選出に必要な動く証拠、実際に使う人、英語中心の配布につなぎ、公式の実利用者1,000人へ進める。

**Architecture:** Life Managerは一つの製品で、LocalとCloudは実行モード。`aniccaai.com/lm`が唯一の公開製品ページで、同じoriginの`/maritime`は認証・開始・状態確認の経路であり、別製品やpilot pageではない。Netlify rewrite経由で既存Railway `life-call` control planeへ接続し、各顧客の実行は専用Maritime VMに分離する。`/auth/google`と`/auth/google/callback`も同じoriginでproxyし、PKCE cookieとcallbackを同一hostに保つ。Railwayはcontrol plane/workerであり、公開Webサイトや各顧客のVMを置く場所ではない。Google sign-inがWebの入口。Calendar/Gmail inbox権限、task/goal/budget入力、payout情報はsignupで求めない。Capafyは最初のCloud収益workflow。既存queue・tenant store・Capafy factory・Maritime receipt/reconciliation・Resend日報をつなぐ。新しい製品、別のpublic pilot page、fake/demo stateは作らない。

**利用体験:** Googleログインは本人確認だけに使用する。Calendar/Gmail inbox、タスク・目標・予算の入力、Telegram、銀行情報はsignupで要求しない。ログイン後に、データ保持・自律実行・確認済みメールへの状況報告を一度だけ明示確認し、その後は追加の目標入力なしで最初のCapafy workflowを開始する。Webは単一Life Manager Cloudのphone-first workspace。初回リリースは、実行状態・実結果・メールreceiptを表示するworkspaceで成立させる。ChatGPT風の会話UIは必須にせず、後続の任意機能とする。追加する場合は、入力を認証済みtenantのdurable jobへ結び付け、受付・実行・結果の各状態を実データから表示する。実ジョブへつながらないcanned chatやmock activityは出さない。初回の自律実行はユーザーが何も入力しなくても始まる。Calendarは実タスクに必要な時だけ後から接続する。確認済みの仕事・結果はGoogle inbox権限を使わず、確認済みlogin emailへ送る。Payout情報はsignupで要求せず、Capafyが実際の出金時に求める場合だけその時点で案内する。

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
- Capafyの公式Publisher Guideは、Agent Cardの確認、実行資格情報の選択、Publisher Certification、review提出を新規公開の手順としている。初回Certificationには返金不可US$0.99が必要。よって新規versionの公開を「完全無人」とは説明しない。自動作業は公式confirmation/Certification gateまで進め、未完了状態をUI・メール・receiptで明示する。[Publisher Guide](https://capafy.ai/developer/doc/2.2)
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
- [x] P0.7 Read the official competition home/Terms and existing organizer thread on 2026-10-25. The Apply button opens a general program application, not a confirmed Week 1 project-submission route; the 10/19 kickoff email says the project is already in, so do not resubmit. Current Terms (updated 10/15) say 1,000 distinct real users, the first three verified projects win, and the program ends 12/1 at 23:59 Pacific. Exact Week 1 cutoff, Top 30 rubric, Week 2 milestone, project route, and formal receipt remain UNKNOWN. The kickoff says product by end of Week 1, users are bonus points, and only Top 30 advance. Terms/email start dates differ by one day (10/20 vs 10/19). Dated readback is in requirements.json and live-readback-20261025-1434Z.json; no application was sent.

**DONE when:** written organizer answer or a dated “no answer yet” readback exists for each field. This task does not block independent product/source work.

### P1 — Finish the already-started Cloud product path

**Product acceptance:** One Life Manager product, with Cloud running in a tenant-isolated Maritime VM. Netlify serves aniccaai.com/lm; same-origin /maritime handles Google sign-in, consent, start, and real state. The primary phone-only interface is the web app. A real status/results workspace is enough for the first release; a ChatGPT-style request surface is optional and must not delay the prompt-free first Capafy cycle. Any conversation feature must use authenticated tenant request/job/result state; no mock activity. Google login is identity-only. Signup does not ask for Calendar/Gmail inbox access, a task/goal/budget prompt, Telegram, or bank details. Capafy is the first earning workflow. Calendar can be connected later only when an actual task needs it. Verified progress and results go to the verified sign-in email; Telegram is optional.

- [x] P1.1 Public/runtime readback: at 2026-10-25 16:10Z, Netlify `/lm` returns 200 and still contains the old “full cloud runtime is in development” Calendar-first offer; Netlify `/maritime` returns 404. Direct Railway `/maritime` returns 200 with `<title>Life Manager · Maritime pilot</title>`. Production backend and worker deployments are healthy, but production worker still lacks the Capafy connection/provider/encryption-key variable names. The page and route are source candidates only; do not route acquisition based on service health.
- [ ] P1.2 Integrate Life Manager source PR #8986. The PR is OPEN, non-Draft, and mergeable; re-read its exact head and checks before integration because this doc sync also updates its branch. Application code remains candidate `e18237c795326e3a7a1f3467a9d7b5a44cbfa1f6`; it implements identity-only Google onboarding, one retention/autonomy/report consent, automatic first cycle, and a tenant-job/report receipt workbench. Candidate checks: focused Cloud tests 65/65 and runtime adapters 351 PASS / 1 SKIP. At 16:06Z, pre-doc-sync exact head `0b48ade371885289e4c69cad7f3613e1c7b0efad` had Cloud reminder contracts and CodeRabbit SUCCESS, Security Scan QUEUED, and no GitHub review. Keep this cursor at exact-head Security Scan; use `bin/merge-when-green 8986` only after all required checks finish green.
- [ ] P1.3 After #8986 is accepted, sync provider PR #8745 (current head `7c23f58246fc75560d24f78d972868785a664801`, based on `6069838c4d687b1d2204aaff240967170d3adfcc`) to accepted main and preserve Google-first onboarding. Exact-head Cloud reminder contracts, Security Scan, and CodeRabbit are SUCCESS; PR remains OPEN/DRAFT with no review. Existing binding, receipt contracts, migration, and RLS integration tests pass; production host `prepare`/`publish` transport injection is absent.
- [ ] P1.4 Finish the tenant-bound host executor, migrations, and deploy-safe secret wiring. Resolve tokens only inside authenticated tenant bindings; never expose them to a model, VM prompt, artifact, log, UI, or email. Keep provider flags OFF until real receipt/reconciliation checks pass. Capafy’s official [Publisher Guide](https://capafy.ai/developer/doc/2.2) requires the publisher to confirm the Agent Card and credentials and explicitly submit for review; first publication also requires identity certification and a non-refundable US$0.99 fee ([Certification](https://capafy.ai/developer/doc/1.3)). Automate preparation and state readback, but pause for those publisher-controlled steps; do not simulate their confirmation or promise unattended approval/publication.
- [ ] P1.5 Configure and deploy the accepted backend/runtime through Maritime. Match the active Supabase project and exact Google redirect URL; configure the first-party Cloud origin, tenant VM image/source archive, and provider secrets. Verify identity-only PKCE, tenant isolation, VM readiness, start/state/stop, and rollback.
- [ ] P1.6 E2Eでは新しいLife Manager Cloud tenantを使う。各顧客は本人が所有する既存または新規のCapafy Publisher Accountを接続する。owner testでは既存Publisher Accountのみを使い、Publisher Agreement v1.2 §2.9（2026-09-28発効）に従って同一Publisherの二つ目を作らない。Capafy OTP/login前に本人が現行TermsとPrivacy Policyへ明示同意する。Certificationの本人確認と返金不可US$0.99申請料はCapafy側の手続きとして正直に案内し、本人に完了してもらう。銀行/payout情報はsignupでは求めず、Certification後の出金設定時にのみ案内する。
- [ ] P1.7 After production config and owner-controlled Capafy consent, run one bounded real test using a new Life Manager Cloud tenant: Google identity → one retention/autonomy/report consent → dedicated tenant VM → one real Capafy action → official provider receipt → matching Life Manager receipt → verified-address report email → Stop and replay-zero. The automatic preparation cycle must start without Calendar/Gmail access, a task/goal/budget prompt, Telegram, payout details, or a ChatGPT-style prompt. Chat may be added only as a real request/job/result surface. Signup, draft creation, VM provisioning, “under review,” and unverified sales are not completed earning results; preserve costs and distinguish sales, proceeds, settled payout, and actual cash received.
- [x] P1.8 Implement the phone-first source workbench backed by tenant job and report receipts. It displays real records only and does not invent activity or revenue. This code is in source PR #8986 and is not live until its integration/deployment.
- [ ] P1.9 Optional after P1.7: add a ChatGPT-style request surface only if it writes an authenticated tenant request record, dispatches the matching real manager job, and displays the real receipt/result. This is not a launch gate. The first Capafy work must not depend on a user prompt, and unsupported assistant replies must not be displayed.

**P1 DONE when:** the one-product phone-first workspace completes real work in an isolated customer VM, reports matching Capafy/Life Manager/email receipts, and verifies Stop/replay-zero. A chat surface is not required; if shown as working, it must write and read tenant-scoped request/job/result state with no canned replies or mock history. Source checks or a login alone do not close this gate.

### P2 — Ship one real public Cloud route and turn verified use into contest proof

- [ ] P2.1 Netlify PR #743 is Draft at head `c068f83c83a360595eeb573cc39254c1c3490b5e`, OPEN/mergeable on latest readback. It pins the reviewed Cloud-first Life Manager source at `e18237c795326e3a7a1f3467a9d7b5a44cbfa1f6`, preserves the product catalog pin, routes `/maritime` and Google OAuth through Netlify, and removes Calendar-first signup copy. Landing build and calendar eval passed (workflow runs `40207493678` and `40207493690`); CodeRabbit is successful. The live `/lm` still shows old Cloud/Calendar copy and `/maritime` remains 404, so this candidate is not deployed.
- [ ] P2.2 After the source/provider paths and production configuration are accepted, merge/deploy Netlify PR #743; verify English/Japanese `/lm`, same-origin `/maritime`, OAuth callback/PKCE, real tenant state, Capafy receipt/email, Stop, replay-zero, and rollback. Do not route acquisition to a 404 or publish a mock/pilot page.
- [x] P2.3 Refresh official Maritime sources and the existing organizer thread. The public form is a general application and not confirmed as Week 1 submission; organizer kickoff confirms accepted participation. Exact Week 1 deadline/rubric/Week 2 milestone and formal submission route remain UNKNOWN. Preserve these unknowns and do not duplicate-submit.
- [ ] P2.4 Keep the truthful English competition packet ready, based on the one public product URL and dated receipts. Submit once only through a confirmed Week 1 route and save the official receipt; do not use the general program application or infer advancement from social metrics.

**P2 DONE when:** the real product route is public, the organizer confirms the submission route, and the official receipt and advancement status are read back separately.

### D0 — Current distribution inventory (already completed)

- [x] D0.1 One English X launch post on @selawmqt with a direct tracked English Life Manager link; expanded destination returned HTTP 200 on 10/23.
- [x] D0.2 One @diceai0 Japanese awareness post that clicks through to the English post and Life Manager page. It does not have independent Japanese conversion attribution.
- [x] D0.3 Existing English manager article is public and returned HTTP 200 on 10/24.
- [ ] D0.4 Refresh current impressions/clicks/landing/signup/first-use/cost readbacks. Existing post receipts are not user receipts.
- [ ] D0.5 Read Muse's response to the English Threads authorization and confirm author, existing account and destination before counting a post. If there is no confirmed publish receipt, leave pending. Instagram remains blocked pending owner SMS reconnect.

### D1 — Build a measurable English acquisition loop

**Distribution strategy:** Use one verified Life Manager workflow as the English anchor story. The existing EN X post and article are already live; once P1 proves the hosted cycle, create one honest 2–3 minute product demo and one tracked CTA, then adapt it for verified existing X, Threads, and Instagram identities. No duplicate launch copy. The 10/23 X audit found @selawmqt at 7 followers, about 5 median impressions across its last 20 posts and roughly 23 posts/day, while sampled high-reach builder accounts had reply-heavy timelines. Treat that as a baseline to test reply-first participation, not evidence that posting more will grow reach. Start with 10 real people outside the team who match the supported workflow, offer direct onboarding, record first-use friction and repeat use, and fix the largest measured drop-off. Compare native post metrics and the first-party funnel at 24 hours and 7 days; separate impressions, visits, qualified use, and official Keiki/Maritime counts.

- [ ] D1.1 Reuse the existing `/lm` product page, article, current X posts, and tracked URL patterns. Assign one unique UTM content value per next authorized English post/account; confirm the actual expanded CTA after publishing. Keep one Life Manager product page and one same-origin Cloud route.
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

1. Resolve the current `main` sync and exact-head review for source PR #8986.
2. Sync provider PR #8745 to accepted main; finish the Capafy host executor, tenant secret path, migration, and receipt/reconciliation tests with external effects OFF.
3. Configure the correct Supabase identity, first-party OAuth origin, Maritime image/source archive, tenant VM lifecycle, and rollback.
4. Integrate/deploy Netlify PR #743 and read back `/lm`, `/lm/ja`, `/maritime`, and Google callback on the first-party origin. Do not acquire traffic through a 404.
5. Owner accepts current Capafy Terms and Privacy, connects the existing Publisher Account, completes Certification and required publisher confirmations. A test needs a new Life Manager tenant, not a duplicate Capafy account.
6. Run one bounded E2E: new Life Manager tenant → identity + one consent → real Capafy work → official receipt → Life Manager state → accepted result email → Stop/replay-zero and cost readback.
7. Ship a ChatGPT-style web request interface only when its request-to-job-to-result chain is live and tenant-bound; it is not a signup requirement or a substitute for the automatic first earning cycle.
8. Confirm the official competition route/cutoff/counting rules, submit truthful English product evidence once, then run tracked English distribution and iterate on verified use and settled MRR.

P0 organizer unknowns and source implementation can proceed in parallel. Do not claim MRR, qualifying competition users, or a successful earning path without authoritative receipts.

## State Ownership

The integrated SSOT owns current status, task ordering, and the single cursor. This plan contains detailed implementation steps and acceptance evidence only; update the SSOT when a task, requirement, or blocker changes.
