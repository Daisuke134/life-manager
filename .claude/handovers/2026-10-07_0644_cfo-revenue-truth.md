# CFO引継ぎ — 2026-10-07 06:44 JST

メールは送らない。新しいsessionへ渡すgoalは末尾にそのまま記載する。

## 正本とcursor

repo: `/Users/anicca/Projects/life-manager-main`。
Spec SSOT: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cli-native-profile-readback-20261006/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`。
現在のremaining-TODO SSOTは `2026-10-07 06:41 JST — CFO A3 fresh readback / RevenueCat source / atomic cursor` セクション。active orderはA3→A4→A5→A6→A7→A8→A9→A10で、A1 hardeningはnonblocking。

## 引継ぎ時点で検証済み

- Supabase CLI `2.95.4`はcurrent profile storeからaccess tokenを読める。read-only `projects list`はrc=0だがLife Manager target refは出ず、DB `SELECT 1`はlogin-role取得時403でSQL未実行、postgres-config GETも403。migration-write permissionは未検査。
- Production PostgREST OpenAPI GETはHTTP 200、122 paths/60 RPC。`lm_geocode_cache_get`と`lm_geocode_cache_upsert`は未公開。A3 migration適用・schema反映は未確認で、今回production DB/data/provider writeは0件。
- 2026-10-07 06:40 JSTのRevenueCat read-only runは6 appすべてavailable、latest period `2026-10-05`、total MRR USD 20.34。`anicca-ios`はUSD 20.34、残り5 appはUSD 0.00。これはsubscription MRRでcash/settled proceeds/netではない。
- PR #6786は`64895457`でmain統合済み、Railway `life-call` deploymentもそのSHAでSUCCESS。PR #6790は`1305c07`でmain統合済みだが、Railway deploymentはwatched filesに変更がなくSKIPPED。RevenueCat live flagを使うscheduled CFO runは個別readbackしていない。
- CFO current MRR readerとA3 geocode-cache sourceはmain済み。A3 production migration/schema/ACL/restart-safe natural replayは未完。
- このturnではproduction mutation、資金移動、Telegram送信、email送信なし。

## Git状態と所有境界

Spec-only worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cli-native-profile-readback-20261006`。
Branch: `docs/cfo-cli-native-profile-readback-20261006`; upstream/push target: `origin/docs/cfo-cli-native-profile-readback-20261006`。
Spec+handover初回snapshot `20a558c8ee621c9a1adeecf79bd36b6681842d87`はpush済みで、その時点のlocal/remote/PR head一致をreadbackした。その後mainはPR #6792で`9ca3803060938343a8d8a64063f738a52bec573c`へ進み、このworktreeは同mainへrebase済み。現在のrebase snapshotは`957ab546a28af12b987508b16fe462cb55afa15a`、origin branchとPRの旧remote headは`921af7d2b95fccf4076b25f73845d0a492ca3896`。次はこのremote headをforce-with-leaseで更新して最新main由来branchをpushし、新headのCIを確認する。
PR #6780はcapture時点でOPEN。`921af7d2`のCIは全check PASSだったが、baseが更新されたため新headの再実行が必要。CodeRabbitはrepository policyでmanual review requiredとしてskipし、独立read-only reviewはPASS済み。CI未通過を迂回しない。
locked worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-mobile-natural-evidence-20261007` と `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-current-mrr-readback-20261007` は変更しない。implementation workerは稼働していない。source変更は別のlatest-main worktreeでlease/dirty stateを確認してから行い、このspec worktreeでcode変更しない。

## 最初の安全な再開手順

このfileとspecの上記sectionを読み、`git fetch`後にPR #6780の最新head/checks、local HEAD/upstream/dirty state、Supabase schema/permissionsを照合する。A3から続ける。local Supabase link fileがないだけで再ログインせず、対象project authorityと公式migration endpointなしにDDLを再試行しない。

## 新sessionで送るgoal

```text
/goal Life Manager CFOを全14 loopと個人MUFGのreceipt-backed財務SSOTにし、loop/platform/company別のrevenue・refund/fee・actual expense・MRR・bank balance・runway、freshness・coverage・estimate-vs-settled・unknownを報告する。unknownを0や推測配賦にせず、支出最小化と$10k MRR目標を支援するが、settled evidenceなしに達成扱いしない。最初にhandover /Users/anicca/Projects/life-manager-main/.worktrees/cfo-cli-native-profile-readback-20261006/.claude/handovers/2026-10-07_0644_cfo-revenue-truth.md と正本spec /Users/anicca/Projects/life-manager-main/.worktrees/cfo-cli-native-profile-readback-20261006/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.mdを読み、fresh fetch後にHEAD/upstream/dirty state/PR/production/worktree leaseを照合し、順序A3→A4→A5→A6→A7→A8→A9→A10を保つ。Doneは全14 loopのrevenue/refund/feeと銀行・カード・subscription/provider/cloud expense source coverage、official IDs、fresh Moneytree MUFG balance/transactions、既存CLI/panelのperiod一致revenue/expense/net/MRR/runway/partial/unknown、A10の7日natural-run receiptで判定する。A3はsource main済みだがproduction migration/RPC/ACL/restart-safe replayが未完。対象project authorityを確認し、現在profileが許可する時だけ既存SQLを公式migration endpointで適用し、readback後にmain-derived immutable releaseとsame-event replay-zeroを確認する。A1はnonblocking。既存CLI/panel/APIを使い、新UI/CLI/provider/architectureは作らない。broad token、secret exposure、資金移動、公開、production experimental SQL、Codex/ClaudeのTelegram/email送信は禁止。計画/reviewはgpt-6.1-sol/medium、実装はgpt-6-luna/max、5.6系は使わない。life-managerのspec専用worktreeは/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cli-native-profile-readback-20261006、branch docs/cfo-cli-native-profile-readback-20261006、upstream origin/docs/cfo-cli-native-profile-readback-20261006、latest origin/mainは9ca3803060938343a8d8a64063f738a52bec573c、handover前のrebase snapshotは957ab546a28af12b987508b16fe462cb55afa15aで、ここではspecのみ編集する。source変更はlease/dirtyを確認した別のlatest-main worktreeで行い、lockedな/Users/anicca/Projects/life-manager-main/.worktrees/cfo-mobile-natural-evidence-20261007 と /Users/anicca/Projects/life-manager-main/.worktrees/cfo-current-mrr-readback-20261007 は触らない。PR #6780のremote headは921af7d2b95fccf4076b25f73845d0a492ca3896で、fresh branchをforce-with-lease pushした後のCIを確認し、CI未通過を迂回しない。official finance evidenceのfresh read-only reviewにspawn_agentを1回使う。この/goal行を新sessionでユーザーが送信した時だけreviewerが起動する。Doneまで続け、project permission不足なら正確なprovider errorを記録して独立作業を続ける。
```
