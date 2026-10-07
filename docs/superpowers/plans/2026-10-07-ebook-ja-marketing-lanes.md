# eBook日本語投稿レーン修復プラン

> **実行者向け:** `superpowers:executing-plans` を使用し、各タスクを順番に完了する。

**Goal:** 既に登録済みの日本語eBook Instagram/TikTokレーンを共有公開ゲートへ通し、既存owner経由で各1回の即時投稿を公式readbackで確認する。

**Architecture:** `config/marketing-destinations.json` の正確なeBook宛先を維持し、共有manifestの許可商品に `ebook-ja` を追加する。失敗済みoccurrenceをPostiz公式readbackで照合し、最新integration一覧とmanifest writerで日本語2レーンだけをproduction targetへ移す。グローバル公開fenceはclosedのまま保つ。

**Tech Stack:** Node.js、`node:test`、Life Manager `lm-loop`、Postiz公式readback。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

## 共通制約

- ソース変更は最新 `origin/main` 基点の専用worktreeで行う。
- Postizへの直接投稿を使わず、既存のeBook owner経路を使う。
- `effect_status=unknown` は同一occurrenceの公式readbackが済むまで再実行しない。
- 対象は `@obou.anicca` Instagram と `@obou_anicca` TikTok のみ。英語 `@monk_anicca` はdisabledのまま別TODOとする。
- 両レーンの予定は毎日07:00、12:30、20:00 JST。予定時刻は投稿実績として扱わない。
- 外部投稿の完了条件は各Postiz receiptとnative public URL。1回の成功から毎日の継続成功を推定しない。

## Review Focus

- 先行runが実はPostizへ到達していた場合、同じslotを重複投稿しない。
- 最新integrationのdisabled状態またはintegration IDがdestination契約と異なる場合、対象レーンをarmしない。
- 既存holdを残したままlaneを追加し、重複integrationとして拒否される状態を作らない。
- 即時kickが最新due slotの12:30を選ぶことを把握し、別slotと誤認しない。
- Postiz receiptなし、native URLなし、または1日目だけの成功を継続cadenceの証拠にしない。

---

### Task 1: 先行失敗を公式readbackで照合

**Files:**
- Runtime state: `~/.local/state/life-manager/ebook/events.jsonl`
- Owner reconcile: `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py`

- [ ] 対象の日本語Instagram/TikTok occurrenceをそれぞれowner指定で公式readbackする。
- [ ] 公式Postiz証拠がpre-effectを確定した場合だけresolveする。結果がunknownのままなら次の投稿を起動しない。

### Task 2: TDDで `ebook-ja` をmanifestへ許可

**Files:**
- Modify: `apps/life-manager/lib/marketing-lane-manifest.js`
- Test: `apps/life-manager/lib/marketing-local-ledger.test.js`

**Interfaces:**
- 既存の `createMarketingLaneManifest()`、`writeMarketingLaneManifest()`、`createMarketingLocalLedger()` を再利用する。
- 対象routeは `config/marketing-destinations.json` のeBook日本語Instagram/TikTok targetと完全一致する。

- [ ] `closed production fence` 下で、正確なeBook Instagram/TikTok laneがenqueueできる回帰テストを書く。各laneの `target_daily_limit` は3、canary状態は未検証と明示する。
- [ ] `node --test --test-name-pattern="eBook Japan lanes" apps/life-manager/lib/marketing-local-ledger.test.js` を実行し、`ebook-ja` が未知の商品として拒否されるREDを確認する。
- [ ] `PRODUCTS` に `ebook-ja` を追加する最小変更を行う。
- [ ] `node --test apps/life-manager/lib/marketing-local-ledger.test.js apps/life-manager/lib/marketing-lane-manifest.test.js` を実行してGREENを確認する。

### Task 3: 仕様を実測に揃える

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- Modify: `docs/superpowers/specs/2026-07-29-life-manager-finance-marketing-platform-design.md`

- [ ] 20:00待ちを即時kickへ入れ替えた理由、旧順序、新順序、現在cursorを同じ差分に記録する。
- [ ] 「即時kickstart」は明示指示がある場合に今すぐownerを起動する運用規則として記録し、通常cadenceの検証と分離する。
- [ ] eBook日本語Instagram/TikTokを0/day hold一覧から外し、`ebook-ja` が共有manifestで許可される契約を記す。
- [ ] 実行結果、receipt、public URLが得られるまで未完として記録する。

### Task 4: main統合とimmutable release

- [ ] focused test、`git diff --check`、必要なLoop Control CIを通す。
- [ ] task専用branchをcommit/pushし、PRをmainへ統合する。
- [ ] pushed main由来releaseを作り、日本語ownerだけを新SHAへtarget-applyしてloaded argv/SHAをreadbackする。

### Task 5: 日本語2レーンのみをmanifestへ昇格

- [ ] 新しいPostiz integration GETで対象2 integrationがenabledかつID一致を確認する。
- [ ] 正規manifest writerで対象2 holdのみを解除し、契約どおりのeBook target laneを追加する。日上限は3、状態は `authorized-canary-pending` とし、canary成功前にverifiedと記録しない。
- [ ] manifestの重複なし、mode `0600`、他のlane/hold不変をreadbackする。global fenceはclosedのままにする。

### Task 6: 即時投稿と公式確認

- [ ] fresh read-only reviewでowner SHA、manifest、先行effectの解決、今日のPostiz一覧を確認する。
- [ ] 2つの日本語ownerを今すぐ各1回kickする。現行schedulerが最新dueの12:30 slotを選ぶことを記録する。
- [ ] Postiz receiptと各アカウントのnative public URLを取得し、別々に成功を記録する。
- [ ] その後の自然cadenceを7:00/12:30/20:00 JSTで追跡する。単発投稿だけを毎日継続の証拠にしない。
