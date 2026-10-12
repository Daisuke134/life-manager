# Mobile growth担当

これはDaisが明示依頼した新規Codex担当。team=lm、統括=lm-orchestrator-1012。提示された旧handoverを現在の状態へ照合して担当goalを完走する。正本はdocs/superpowers/specs/2026-09-25-life-manager-unified-ssot.mdだけ。開始前にREADME、該当SSOT節、skills/loop-development/SKILL.mdを必要箇所だけ読む。2MB SSOT全体をcatしない。旧SHA/PR未統合/容量条件を現在と断定せずfresh main/HEAD/upstream/dirty/lease/runtime/providerを確認し、既完項目をやり直さない。
他担当と共有。dirty root checkout、他担当worktree/branch/profile/stateを編集・revertしない。各lane内の実装は一人でserial、独立laneは並行する。変更は専用worktree/leaseで目的spec→最小RED/GREEN→focused checks→commit/push→PR、primaryが共有releaseと統合を調整する。SSOTは自分のlane節だけ更新し、全体順序はprimaryが管理する。大きなbuild/依存install/release cutを同時に行わず、共有境界は既存lease/lockで直列化する。初回は軽いreadbackとnext atom特定から入り、不要な複製dependencyや大きな一時artifactを作らない。
送信/応募/決済/effect_unknownは公式receiptなしに解除・再送しない。credentials/browser identity/memory/state JSONL/active dirty leased worktree/参照release/Simulatorを保持する。credentialsはprivate SSOTのみ、値をchat/log/specへ出さない。Codex/ClaudeはTelegramへ進捗を送らない（既存業務loopは別）。Mac/loginwindow/App Server restart/raw launchctl禁止、必要なloop操作は既存安全preflight経路のみ。価格・spend cap・本人確認/entitlement境界を守る。過剰なreviewや新frameworkを増やさない。model IDを指定/変更せずUI/account既定を尊重する。
この文書のgoalを自分のruntimeのpersistent goalとして設定し、既存goalがあれば重複作成しない。着手時と節目にAGMSG sendでprimaryへ「owner/owned WT/branch/HEAD/実施atom/検証/公式receipt/残件/次手」を短く報告する。登録やprocessだけを着手/Doneとしない。外部gate/自然run待ちでは独立safe TODOを続ける。成功はsource/fixtureだけでなく本番・自然run・公式readback・replay-zero/費用込み成果まで。百万長者・無故障・世界初は未実証の目標であり保証/広告claimにしない。

/goal Anicca iOSのorganic distributionを最優先し、広告費なしでASC first-time downloads 1,000件/日を持続し、その後verified net MRR $10Kを達成する。最初の市場は英語・日本語・スペイン語。Aniccaの再現可能な獲得ループが確認できるまでHONNE・他アプリへ投稿量と開発工数を分散しない。各Anicca laneはdistinct PUBLISHED receipt、直接URL、native views/engagementを記録し、ASC campaign attribution、product-page views、first-time downloads、RevenueCat購読/返金/proceeds、既存Mixpanel/PostHog onboarding/paywallを結ぶ。SCHEDULEDを公開に数えず、保存PNGを再利用し、投稿ごとの画像API呼出なし。古いreceiptで別occurrenceを解除せず、effect_unknownを公式readbackなしに解除/再送しない。1,000件/日はASCの日次値と7日平均で評価し、達成後にHONNE/他アプリへ複製し、最後にOSS mobile-app factoryへ進む。

再開・所有境界:
旧handover .claude/handovers/2026-10-09_1543_mobile-marketing.md と最新SSOT。旧PR #7369/30-of54/18unknownを現在と扱わない。#7588等のmain/owner採用を照合し、既存current-day deficits→exact effect readback/fence→native metrics→ASC/RC/funnel→creative distribution→ASO→onboarding/paywallの順。自分はsingle writer、subagent/reviewを増やさない。既存leased mobile-distribution-priority/mobile-offslot-post-fence/mobile-postiz-metrics WTは触らない。新 .worktrees/mobile-goal-20261012/branch fix/mobile-goal-20261012 を最新mainから。所有Mobile distributor/metrics sourceだけ。

現状cursor:
- ASC acquisition snapshot: report 2026-10-12、対象期間2026-10-08〜11のAnicca first-time downloads 2、impressions 19、product-page views 0、campaign attribution未設定。RevenueCat local snapshotでは購読/proceedsは`unavailable`で、0とは扱わない。
- 2026-10-12 publication ledger: 38 PUBLISHED provider IDs（35 production、3 canary）、17件は直接URLなし。公開日のdaily snapshotは9件で、`@anicca.en`は1件1,470 views/1,088 reach/3 likes/0 saves、`@anicca.jp.videos`は3件合計382 views/335 reach/2 likes/0 saves、`@anicca.affirmation`は3件とも0 views。TikTokの481 viewsは別の単一投稿の24時間値で、install数ではない。
- PR #7828のsource fixはmain commit 21c8f025に統合、関連テスト20/20 PASS。productionのTikTok metrics ownerは旧SHA 6455356147c460e226aef3308e07a5fdf7c5711eのまま。read-only `pre-effect-reconcile --dry-run`は67件を未解決（66 `no_pre_effect_terminal`、1 `history_incomplete`）とし、TikTok/Instagram metrics ownerに`effect_reconcile` adapterがない。再送・fence解除は禁止。
- host disk freeはrelease reserve 2.389GB未満。fail-closed cleanupは小さなcacheだけを回収し、大きな候補はopen/protected。production releaseはheadroom回復後に行う。

remaining TODO order:
1. metrics owner用のexact Telegram/provider readback adapterを実装し、67 occurrenceを個別に証明する。official receiptがないoccurrenceはfencedのままにする。
2. allowed cleanup ownerでrelease headroomを回復し、2.389GB以上のphysical freeをreadbackする。
3. main由来immutable releaseへsource fixを採用し、loaded SHA/argv、自然実行、official metric/Telegram receipt、replay-zeroを確認する。
4. 17 direct-URL欠損とASC campaign attributionを修正し、投稿→ASC first-time download→RevenueCat subscription/refund/proceedsのdaily joinを作る。
5. 英語・日本語・スペイン語で競合formatを基にoriginal creativeを検証し、ASC first-time downloads/dayを1,000へ伸ばす。広告費は使わない。
6. distribution計測が安定してからpaywall loading、通知で同じquoteを表示する動作、主要市場のlocalizationを仕上げる。Aniccaの1,000/dayと$10K MRRを再現した後にHONNE/他アプリとOSS factoryへ展開する。

資格情報の保存先・SSOT全体確認・credentials[]のservice完全一致検索・identity/profile/owner/lease確認手順 → ~/.config/ai/core.md「No-human-loop（既定）」を起動時とブラウザ操作前に読む。lane個別の認証境界を保持し、secret値を起動指示へ含めない。
