# Maritime pilot接続の実装計画

> 実装Sub-skill: superpowers:executing-plans。multi-agentは使わず、同一worktreeで順に進める。

**Goal:** 既存Telegramの明示的なpilot commandに、ユーザーごとに冪等provisionされるMaritime chat transportを追加し、既定では完全に無効にする。

**Architecture:** 既存slash-command routerに/pilotを追加し、provider固有SDK処理は小さなtransport moduleに置く。既存Calendar・commute・browser-taskの経路は変えず、feature flag・明示的data-handling gate・3 UID以下のallowlist・server-side API keyを満たす時だけ外部SDKをロードする。

**Tech Stack:** Node.js 20.19以上、CommonJS、maritime-sdk 0.9.0のdynamic import、既存node:test。

**Spec:** docs/superpowers/specs/2026-10-16-maritime-pilot-design.md

## 全体制約

- feature flag、API key、3名以下のUID allowlistのどれかが無効ならprovider callをしない。
- `MARITIME_PILOT_DATA_APPROVED=1` がない時もprovider callをしない。これはsource guardであり、法的同意や参加者同意を代替しない。
- API keyはserver環境だけに置き、browser、Telegram、logs、Gitに出さない。
- `LM_UID_SECRET`によるHMACからstable externalId/conversationIdを導出し、PIIはagent metadataへ送らない。
- chatのerrorを検査し、失敗または不明時は自動再送しない。
- SDK `maxRetries: 0` とし、chatの重複送信を防ぐ。`provision`は`externalId`で冪等。
- prompt/response本文はLife Managerのusage ledgerやlogsへ保存しない。
- ToS同意、実API key設定、VM作成、実ユーザー入力、paid plan、production enablementはこの計画で実行しない。

## Review focus

1. feature-offや設定欠落時にSDK import/provider callが発生しない。
2. allowlist外のUIDがprovision/chatを起動しない。
3. 同じUIDの再試行でexternal IDが一定となり、agent/VMを重複作成しない。
4. SDKの非throwing errorやmissing responseを成功扱いせず、chatを再送しない。
5. Telegram HTML出力をescapeし、本文やsecretをlogsへ出さない。

---

### Task 1: provider transport

**Files:**
- Create: apps/life-manager/lib/transport/maritime-pilot.js
- Create: apps/life-manager/lib/transport/maritime-pilot.test.js
- Modify: apps/life-manager/package.json
- Modify: apps/life-manager/package-lock.json

**Interface**
- createMaritimePilotTransport({env, client, loadSdk}) returns isEnabledFor(uid) and chatForUser(uid, message).
- chatForUser returns a typed success/error result, not provider objects or secret data.
- Tests inject a fake client; no real API key or network call is used.

- [x] Step 1: Write failing node:test cases for disabled configuration/data gate, invalid UID allowlist, stable HMAC externalId, provision failure, chat error, empty response and successful response.
- [x] Step 2: Run only node --test apps/life-manager/lib/transport/maritime-pilot.test.js; it fails because the transport module is not implemented yet.
- [ ] Step 3: Add exact maritime-sdk 0.9.0 dependency and implement lazy ESM import, `new Maritime({ apiKey, maxRetries: 0 })`, HMAC identifiers, object-form `provision`, chat error checking and no retries.
- [ ] Step 4: Re-run the focused transport tests and confirm they pass.
- [ ] Step 5: Commit the transport and lockfile change.

### Task 2: explicit Telegram pilot command

**Files:**
- Modify: apps/life-manager/lib/slash-command.js
- Modify: apps/life-manager/lib/slash-command.test.js
- Modify: apps/life-manager/server.js

**Interface**
- /pilot <message> is an explicit user-triggered route.
- server injects chatForUser only; slash-command owns validation, allowlist gate, safe Telegram output and truthful status.
- No database migration, scheduler, loop registry row or background provisioning.

- [ ] Step 1: Write failing tests for flag-off, missing data gate, no key, invalid allowlist, unlinked user, disallowed UID, missing/oversized message, provider error and safe response escaping/truncation.
- [ ] Step 2: Run only the focused slash-command test file and verify failure.
- [ ] Step 3: Add the disabled-by-default branch and pass existing uid/message arguments to the provider transport only after every gate passes.
- [ ] Step 4: Run the focused tests and the Telegram HTTP contract test for routing; confirm existing routes are unchanged.
- [ ] Step 5: Commit the command integration.

### Task 3: source acceptance

- [ ] Run git diff --check and the two focused node:test commands.
- [ ] Confirm no message body, provider response, API key, or participant UID is present in logs/diff.
- [ ] Confirm no loop registry, database schema, schedule, or production env changed.
- [ ] Push the branch and open a PR against the fetched origin/main.

### Separate external gate: not authorized by current goal

- [ ] After legal/data conditions are authorized, provision exactly three participants, verify three distinct agents/VMs through Maritime dashboard, run 7-day use, and read actual billing.
- [ ] Do not run a provider API call, create an account/key/VM, or enable the feature before that gate.
