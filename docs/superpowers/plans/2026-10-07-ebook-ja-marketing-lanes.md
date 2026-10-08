# eBook日本語投稿レーン修復プラン

> **実行者向け:** `superpowers:executing-plans` を使用し、各タスクを順番に完了する。

**Goal:** 既に登録済みの日本語eBook Instagram/TikTokレーンを共有公開ゲートへ通し、既存owner経由で各1回の即時投稿を公式readbackで確認する。

**Architecture:** `config/marketing-destinations.json` の正確な宛先と共有manifestを維持する。Instagramのintegrationが指定されている場合はdistribution workerがPostizへ投稿し、`provider_route=postiz` を記録する。実際のPostiz readbackに成功した投稿を、route metadataの既定値だけでunknown effectにしない。

**Tech Stack:** Node.js、`node:test`、Life Manager `lm-loop`、Postiz公式readback。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

## 共通制約

- ソース変更は最新 `origin/main` 基点の専用worktreeで行う。
- Postizへの直接投稿を使わず、既存のeBook owner経路を使う。
- `effect_status=unknown` は同一occurrenceの公式readbackが済むまで再実行しない。
- 対象は `@obou.anicca` Instagram と `@obou_anicca` TikTok。英語 `@monk_anicca` は別laneで、2026-10-08 17:47ZのreadbackではPostiz integration enabled。English ownerはrelease `64c078b3`へtarget-applyされてloaded-idleで、HeyGen render costと初回PUBLISHED receiptは未計測。
- 両レーンの予定は毎日07:00、12:30、20:00 JST。予定時刻は投稿実績として扱わない。
- 外部投稿の完了条件は各Postiz receiptとnative public URL。1回の成功から毎日の継続成功を推定しない。
- 公開済みreceiptのrouteを直す時はPostiz readbackを使い、同じslotを再投稿しない。
- eBook ownerのstate rootは`0700`を維持し、fence reconcilerはそのownerの`effect-identities`を読む。

## Review Focus

- 先行runが実はPostizへ到達していた場合、同じslotを重複投稿しない。
- 最新integrationのdisabled状態またはintegration IDがdestination契約と異なる場合、対象レーンをarmしない。
- 既存holdを残したままlaneを追加し、重複integrationとして拒否される状態を作らない。
- 即時kickが最新due slotの12:30を選ぶことを把握し、別slotと誤認しない。
- Postiz receiptなし、native URLなし、または1日目だけの成功を継続cadenceの証拠にしない。

---

### Task 1: 既知のローカル拒否をpre-effectとして照合

**Files:**
- Runtime state: `~/.local/state/life-manager/ebook/events.jsonl`
- Modify: `runtime/loop/lm_loop.py`
- Test: `runtime/loop/tests/test_lm_loop_apply.py`
- Owner reconcile: `bin/lm-loop pre-effect-reconcile`

- [x] `marketing publication effect fenced` の日本語eBook occurrenceが `no_pre_effect_terminal` になるREDテストを書く。
- [x] この完全一致エラーを日本語Instagram/TikTok ownerだけに許可する。英語ownerはHeyGen呼び出しがgateより先に起こり得るため未解決のまま保つ。
- [x] 日本語用テストGREEN、英語用テストは拒否を確認。共有ledgerのenqueue/claim拒否はPostiz呼び出しより前であることを既存コードで確認する。
- [ ] テストGREEN後、該当runのenqueue refusalとjobs/receipts不在を確認し、fresh official Postiz GETが0件である証拠を保存する。
- [ ] `lm-loop pre-effect-reconcile ebook-ja-instagram-daily --dry-run` が該当IDをprovableと返すことを確認し、同じowner経路で解決する。

### Task 2: TDDでeBook商品をmanifestへ許可

**Files:**
- Modify: `apps/life-manager/lib/marketing-lane-manifest.js`
- Test: `apps/life-manager/lib/marketing-local-ledger.test.js`

**Interfaces:**
- 既存の `createMarketingLaneManifest()`、`writeMarketingLaneManifest()`、`createMarketingLocalLedger()` を再利用する。
- 対象routeは `config/marketing-destinations.json` のeBook日本語Instagram/TikTok targetと完全一致する。

- [ ] `closed production fence` 下で、正確なeBook Instagram/TikTok laneがenqueueできる回帰テストを書く。各laneの `target_daily_limit` は3、canary状態は未検証と明示する。
- [ ] `node --test --test-name-pattern="eBook Japan lanes" apps/life-manager/lib/marketing-local-ledger.test.js` を実行し、`ebook-ja` が未知の商品として拒否されるREDを確認する。
- [x] `PRODUCTS` に `ebook-en` と `ebook-ja` を追加する最小変更を行う。
- [x] `node --test apps/life-manager/lib/marketing-local-ledger.test.js apps/life-manager/lib/marketing-lane-manifest.test.js` — 44/44 PASS。

### Task 3: 仕様を実測に揃える

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- Modify: `docs/superpowers/specs/2026-07-29-life-manager-finance-marketing-platform-design.md`

- [x] 20:00待ちを即時kickへ入れ替えた理由、旧順序、新順序、現在cursorを同じ差分に記録する。
- [x] 「即時kickstart」は明示指示がある場合に今すぐownerを起動する運用規則として記録し、通常cadenceの検証と分離する。
- [x] eBook日本語Instagram/TikTokを0/day hold一覧から外し、`ebook-en` / `ebook-ja` が共有manifestで許可される契約を記す。
- [ ] 実行結果、receipt、public URLが得られるまで未完として記録する。

### Task 4: main統合とimmutable release

- [x] focused test、`git diff --check`、Loop Control CIを通す。既存mainと同じOSS inventory/Gitleaks baseline failureを確認する。
- [x] PR #6842をmainへ統合し、main SHA `84261ec74ebd13f8e49753c48c741cccafcf8863` 由来release `20261007T152543-84261ec7` を作成する。
- [ ] pending admission解決後、日本語ownerだけを新SHAへtarget-applyしてloaded argv/SHAをreadbackする。

### Task 5: 日本語2レーンのみをmanifestへ昇格

- [ ] 新しいPostiz integration GETで対象2 integrationがenabledかつID一致を確認する。
- [ ] 正規manifest writerで対象2 holdのみを解除し、契約どおりのeBook target laneを追加する。日上限は3、状態は `authorized-canary-pending` とし、canary成功前にverifiedと記録しない。
- [ ] manifestの重複なし、mode `0600`、他のlane/hold不変をreadbackする。global fenceはclosedのままにする。

### Task 6: 即時投稿と公式確認

- [x] fresh read-only reviewでowner SHA、manifest、今日のPostiz対象投稿0件を確認する。
- [x] Japanese TikTokを起動。Postiz receipt `cmuxrb6du00eeqh0yp4al5n67` と公開URL `https://www.tiktok.com/@obou_anicca/video/7693816142606960646` を確認する。
- [x] Japanese Instagramを起動。receipt `cmuxrfync00igs40yv54ve5yh` と公開URL `https://www.instagram.com/reel/DeLxu4Kihsg/` が記録され、Postiz adapterが`PUBLISHED`を読み戻す。
- [x] Instagram occurrence `ebook-ja-instagram-daily:18dc2b149c572198-58370` を既存Postiz readbackで解決する。再投稿なし。
- [ ] 旧releaseは同じslotの保存済みreceiptを再利用してroute検証に失敗し、追加のowner failureを記録する。distribution ledgerにはInstagram投稿が1件だけで、これらの再試行はPostizへ送らない。route正規化を含む新releaseでownerをPASSにする。
- [x] English Postiz routeをofficial APIで再確認する。`cmo5rwq2p00twn10yrsdglng3` (`Monk Anicca`) は`disabled=false`、全31 integrations中30件enabled。既存integrationをそのまま使い、新規channelや課金は不要。これはEnglish ownerや投稿のreadbackではない。証拠: `/Users/anicca/.local/state/life-manager/ebook/evidence/postiz-readback-ebook-live-20261007T172623Z.json`。
- [x] HeyGen walletはUSD 12.30、Auto ReloadはUSD 5 threshold / USD 10 top-up。launchdのdisabled overrideを正確なlabelのみ`launchctl-safe enable`で解消し、English ownerをmain-derived release `64c078b3`へapplyした。Loaded-idle、state root `~/.local/state/life-manager/ebook`、rollback record `/Users/anicca/.local/state/life-manager/ebook/reconciliation/owner-applies/ebook-en-tiktok-daily-20261007T174912Z.json`。HeyGen render-cost receiptは初回自然slot待ち。
- [ ] 英語の次自然slot 08:00 JSTにHeyGen wallet deltaを測定し、同occurrenceのPostiz receiptとnative TikTok URLをreadbackする。eBook投稿は2026-10-08 17:47Z時点で0件。証拠: `/Users/anicca/.local/state/life-manager/ebook/evidence/heygen-wallet-readback-20261007T174700Z.json`。
- [ ] Japaneseの自然cadenceを07:00/12:30/20:00 JSTで追跡する。次アカウントを始める条件にはせず、各occurrenceのreceiptで実績を記録する。

### Task 7: Postiz route metadataの修復

**Files:**
- Modify: `skills/video/lm-distribution/distribute.py`
- Test: `skills/video/tests/test_lm_distribution.py`
- Modify: `apps/life-manager/scripts/ebook-distribute-daily.js`
- Test: `apps/life-manager/scripts/ebook-distribute-daily.test.js`
- Modify: `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py`
- Test: `apps/life-manager/scripts/test_mobile_postiz_provider_reconcile.py`
- Update: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- `distribute_platform(config, "instagram")` が `config.instagram_integration` を受け取る時は `config.postiz_adapter` を呼び、ledger receiptの`route`を`postiz`にする。
- integrationがない既存Instagram file-script経路は`instagram_file_script`を維持する。
- eBook ownerは、owner/occurrence/job/slot/hash/account/integration/post ID/public URLが一致するfresh official Postiz proofを取得した時だけ、既存Instagram receiptのlegacy routeを`postiz`へ正規化する。再投稿しない。

- [x] `test_instagram_postiz_integration_is_recorded_as_postiz` を追加し、fake Postiz adapterの`PUBLISHED`/URL/post ID/`reconciled=true`でledger routeを確認する。
- [x] `python3 -m unittest discover -s skills/video/tests -p test_lm_distribution.py` のREDで`instagram_file_script`誤記を確認する。
- [x] route defaultを実際に選んだadapterから決める。明示されたadapter routeは保持する。
- [x] distribution tests 41/41、Postiz provider tests 24/24、`git diff --check` PASS。
- [x] `an idempotent Instagram replay normalizes only an exact Postiz readback` を追加する。exact official proofがreceipt identity/account/integration/post ID/URL/hashesと一致した場合だけlegacy routeを`postiz`へ正規化する。
- [x] Node REDでlegacy receiptが拒否されることを確認する。
- [x] legacy receiptを再利用する時はowner identityを生成し、`mobile-postiz-provider-reconcile.py --verify-only` のfresh exact Postiz GETが一致した後にだけrouteをnormalizeする。Node tests 9/9 PASS。
- [x] `verify-only` CLI testはresolved stateを変えず、exact Postiz proofを返す。owner identity pathの`~`展開testもPASS。
- [ ] main由来branchをpush/mergeし、immutable releaseへ反映する。fresh read-only Postiz GETで同じslotの既存receiptを完全照合し、ownerをPASSにする。投稿は再作成しない。

### Task 8: eBook effect identityの保存と読戻し

**Files:**
- Modify: `config/loop-registry.json`
- Test: `runtime/loop/tests/test_macos_loop_registry.py`
- Modify: `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py`
- Test: `apps/life-manager/scripts/test_mobile_postiz_provider_reconcile.py`

**Interfaces:**
- `ebook-en-tiktok-daily`、`ebook-ja-instagram-daily`、`ebook-ja-tiktok-daily` の各`effect_reconcile.argv`は `--identity-dir ~/.local/state/life-manager/ebook/effect-identities` を渡す。
- eBookの`state_root`は`~/.local/state/life-manager/ebook`で、runtime identity writerが必要とするdirectory modeは`0700`。

- [x] `test_ebook_postiz_reconcilers_use_owner_identity_dir` と `test_pending_owner_expands_tilde_identity_directory` を追加する。
- [x] REDで3 ownerともidentity directoryを指定していないこと、およびtilde pathが展開されずidentity scanが空になることを確認する。
- [x] 3つのexact eBook ownerに`--identity-dir`を加え、`runtime/loop/tests/fixtures/macos-loop-jobs.json`を正規rendererで再生成する。
- [x] Reconciler tilde/read-only proof tests 7/7 PASS。Registry tests 136/136、`./bin/lm-loop-contract` PASS。
- [x] eBook state rootを`0700`へ修正し、exact Postiz official GETで最初のInstagram occurrenceをresolveする。
- [ ] main由来releaseを適用後、same-slot owner reportがPASSになり、admissionにunknownがないことを確認する。

**順序変更・現在cursor:** 旧順序は1件目のInstagram readback解決後に次アカウントへ進む。新順序はroute誤記、same-slot receipt再利用、effect identityのmode/path不整合を直し、fresh exact Postiz readbackで同一integrationとreceiptを結合してからlatest-main releaseを反映する。理由は、公式Postiz投稿1件を旧releaseが毎回`instagram_file_script`と誤認し、同じslotの再試行をreport failureにしているため。現在はPRのfresh review/CI結果を受けて必要なfixを反映し、merge/release/apply後にInstagram ownerをPASSにしてから英語へ進む。
