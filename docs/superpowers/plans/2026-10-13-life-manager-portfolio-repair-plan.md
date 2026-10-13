# Life Manager 全18能力の修復・評価・配布計画

> 実行者向け: 修復が依頼される時は `superpowers:executing-plans` を用い、各行を仕様→実失敗のRED→最小実装→GREEN→必要なreview/CI→main/immutable採用→自然実行/公式結果の順に進める。今回は「Don’t go fix yet」に従う文書化だけで、実装を開始しない。

**目的:** Capafyを商業重点にし、共通障害を一度修復して複数laneへ適用し、Life Manager内部の自己修復・実経済traceに基づく自己改善・利用可能なOSSを成立させる。

**構成:** 既存runtime/admission/effect/recovery/CFO/provider adapterを再利用する。判断を行うagentと、金額・権限・重複・receiptを確かめる決定的な道具を分ける。新schedulerや新評価frameworkを前提にしない。

**技術:** 既存Python/pytest・unittest、Node.js/node:test、JSON/JSONL、SQLite、launchctl-safe、immutable release、公式provider receipt。

**仕様と進行正本:** `../specs/2026-09-25-life-manager-unified-ssot.md` の「全18能力の読み取り専用監査と修復計画」。PA01–PA10のstatus/順序/cursorはその節だけが所有する。このplanの章順は手順の参照であり、新しい実行TODOではない。既存F/E/各lane/CD1 cursorは保持する。

## 共通制約

- 今回は文書だけ。loop、provider、認証、fence、state、release、価格、sellerを変更しない。
- sourceは最新main由来の所有worktree、productionはmain由来immutable release、状態/秘密/receiptは既存のrepo外store。
- FROZEN seller保持、無料配布channel保持、既存spend-cap保持。広告・creator・有料配布APIを追加しない。
- 不明を0へしない。monthly revenue/MRR/投資損益/調達/本人所得/銀行入金を混ぜない。
- 日付・期間・通貨・owner・run・occurrence・SHA・公式receiptの同一性を評価の入力にする。
- receiptなしeffect再送/解除0。別ownerの停止、共有profile取得、guard緩和を修復として使わない。
- モデルはこの対話のUI選択を継承し、LM runtimeのprovider/model/wallet/funding設定を一括変更しない。
- 各修復は自分の新失敗を説明する最小の既存testだけで検証する。全suite/全18 greenを商業実験の追加gateにしない。

## reviewで注視する実条件

1. healthのtimeoutが全停止/正常/unknownなしへ誤変換されないこと。
2. 旧occurrenceや古いintentのSHAを現在ownerへ無根拠に結び替えないこと。
3. 同一click/receiptを複数slotや複数収益laneへ配賦しないこと。
4. 売上取得日・売上発生日・MRR・pending・cash・cost-complete netを同じ数字へしないこと。
5. 候補agentがevaluator、held-out、権限、spend-cap、effect fenceを変更して自分を合格させないこと。

## PA01/PA02 — 共通実行・監視・照合境界

**所有範囲:** `runtime/loop/health_observer.py`、`runtime/loop/lm_loop.py`、既存admission/recoveryとeffect ownerのadapter。原因の確認後だけ、その共有境界を所有する一人が編集する。容量のF1–F5と採用済みsourceを未実装へ戻さない。

**既存検証:** `runtime/loop/tests/test_lm_loop_health.py`、`runtime/loop/tests/test_health_observer.py`、既存admission/fence tests、`runtime/loop/__tests__/recovery-supervisor.test.mjs`。

手順は、まず既存監視snapshot・ownerの自然events・取得コストを同じ時刻窓で比較する。health timeoutの最初に遅くなる読取境界、実行枠待ちとdisk失敗の区別、intentと対象ownerの世代を観測する。現段階でtimeoutを延長すること、並列枠を増やすこと、旧intentをrebindすることを実装方式として固定しない。

原因が確認できた境界にだけ最小fixtureを追加する。例えば既存health testへ `test_timed_out_observation_does_not_claim_fleet_stopped` を追加し、部分観測と欠測を同時に保持するassertを置く。共有admissionを変更する場合はCapafy/Gig/Writer/Mobileの実trace-prefixから一つずつ既存testへ入力し、task identity保持・外部child未実行の証拠・unknown再送拒否を検証する。単なる既存の正しい安全動作にREDを発明しない。

recoveryの`release_sha_mismatch`は拒否自体が正しい。原因の上流であるintent生成/選択/対象releaseを観測し、古いintentの履歴とfenceを保持したまま許可されたowner進行だけを作る。変更後の同じfocused testとcross-loop fixtureがGREENとなり、通常CI/main/targeted immutable採用、自然receiptを確認するまで本番修復完了にしない。

## PA03 — Capafyの売上日・配信・購入の計測

**所有範囲:** `skills/earn/capafy-marketing/capafy-goal-monitor.sh`、`skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py`、`skills/earn/capafy-marketing/capafy-distribute-daily.sh`と既存配信ledger consumer。sellerや価格は所有しない。

**既存検証:** `skills/earn/capafy-marketing/tests/test_capafy_goal_monitor_launchd.py`、`test_capafy_hourly_reconcile.py`。

取得日だけが変わり、最後のpositive売上が2026-09-29のfixtureを既存testの`run_monitor`隔離経路へ加える。`last_sales_date`は10/13にならず、readback freshnessは別の観測日で保つことをassertし、現在の誤代入によるREDを確認する。最小修正は既存daily revenue trendの実発生日を使い、trendが欠測ならnullを返す。未来のtestデータで売上を作らない。

CD1の入力は既存slot/job/creative・公開URL・provider CT・paid order receipt。static CTのwindow集計をcreative一件の成果へ複製しない。`test_shared_ct_visit_is_not_multiple_slot_wins` と `test_published_x_slot_with_missing_reachable_ct_is_not_pass` 相当の最小assertを既存consumer testへ足し、欠測をunknown、到達リンク欠落をfailにする。観測可能なqualified clickの重複/自己probeを除外する契約は既存実装に合わせる。

同じfocused testをGREENにした後、既存hourly readbackで30d/7d/window・scope・定義を確認する。閾値1 click/72hは正確なslot join後のsmokeであり、conversion改善や増分利益を証明する閾値ではない。

## PA04 — 無料配布と転換の実験

**既存仕様:** CD2–CD5、ED1–ED6、DD08–DD10を参照。current cursorはCD1のまま。実験はCapafy ownerが行い、旧effectを再送しない。

到達可能なCTA、実input→outputのproof、buyer queryとの一致を既存sellerの配布素材で比較する。Xの現行slotはproviderに残る本文/返信/bioのリンクを読み、過去link strippingから全slotの失敗を推定しない。Instagram/TikTok/YouTubeのfree channelと記事/Xは保持する。FROZEN商品の価格・model・trialを変更せず、新商品は既存factoryの枠とT1 cursorに従う。

7日447 views/paid0とCT7/paid0を別の観測として扱う。露出不足、link切断、購入転換、継続購入のどこが悪いかを同じ窓で分解する。試験の割当て・control・成熟期間・sample・費用は既存DD契約で記録し、少数clickを統計的winnerや収益増と呼ばない。semantic creative judgeが必要な場合だけ、実traceのfailure categoryと既存正解ラベルで較正し、held-outを候補へ渡さない。

受入は公開数の増加ではなく、開けるCTAの公式readbackとunique click、paid、再購入、返金/費用の実測比較。取得できないnative impressionsやsubscription状態はunknownで残す。

## PA05 — CFOの公式receiptと費用の接続

**所有範囲:** `skills/cfo/economic_attribution.py`、`skills/cfo/loop_pnl.py`、既存financial source adapter。A8/B7の現順序とFinancialRecordを再利用する。

**既存検証:** `skills/cfo/test_actual_cost_attribution.py`、`skills/cfo/test_loop_pnl.py`、既存経済帰属fixture。

まずsent B7の実source path/env・reporting window・stale/missing_category/missing_coverageを接続先ごとに照合する。offline probeの空データを本番未接続の証拠にしない。選定した一laneで公式income/fee/refund/model/tool/browser/infraの不足を実測し、その最初の不足だけをfixture化する。

REDの候補はstaleまたは未接続receiptをnet0と出す、異なる期間の費用をjoinする、同一orderを複数ownerへ加算する等の実反例。既存testで十分なら追加しない。接続修正後は、explicit zeroとmissingを区別したGREEN、同期間/通貨/receiptの実packet、unknown laneの保持を確認する。RevenueCat MRR20.34を銀行入金や全社netに変換しない。

## PA06/PA07 — 個別laneの修復

全18の現状・次の失敗境界は仕様の能力表を参照する。各ownerは既存README/SKILL/entrypoint/呼出し元を読む。`entrypoint_exit_1/75/124`だけでは内部原因を決めず、当該runのbound stdout/stderr、入力、期限、provider状態を確認してから実失敗REDを書く。

納期のあるGig案件はcommercial順位にかかわらず既存ownerが保持する。応募は納品ではなく、納品は支払ではない。Mobileは23 jobsと18配信laneを混同せず、公開receipt→metrics→install→paid→retentionを結ぶ。LINEの28 known zero/11 missing、PromptBase sales0、job/funding/Connector/CFOの非会社MRR役割を保持する。Cloudは既存web-first/Calendar/billingのofferとhost経路であり19番目のagentを追加しない。

各source acceptanceは当該focused testだけを使い、同じ変更のCI/main/immutable→自然結果で閉じる。provider/KYC/面談・相手の返信待ちをコード故障や0売上にしない。共通障害なら共有側を一度修復し、同じ問題のprovider別実装を増やさない。

## PA08 — LM内部の自己修復と評価に基づく自己改善

**所有範囲:** 既存`runtime/loop/recovery-*`、`apps/life-manager/lib/recovery-self-build-bridge.js`、dev/merge/promotionの既存経路、`apps/life-manager/eval/economic-autonomy/`。Writer eval pilotは保持し、Capafyの実経済traceを追加対象として選ぶ。

LM-EABの合成5caseを全18の本番性能と呼ばない。実失敗のfirst bad action直前のtrace-prefixをsecretなしfixtureへ変換し、許される次の行動と禁止する再送をbinary code graderで評価する。既存`runtime/loop/__tests__/self-eval.test.mjs`のmissing-net保持とfinancial integer arithmeticを使う。format/金額/receipt/重複にLLM judgeを追加しない。

一件の自然障害を対象に、run_id→intent_id→issue→内部修正PR→merged SHA→immutable→対象自然再成功の証拠を結ぶ。外部開発sessionによる編集/手動apply/本人介入は0であることを実記録で確認し、issue作成やreconcile成功だけを自己修復完了にしない。候補はevaluator/権限/fence/spend-capを編集できず、拒否・rollbackも評価する。

自己改善はbaseline/candidateを同じ窓・費用・held-out条件で比較し、失敗率/latency/cost/人介入/公式netのどれを改善したか分ける。実売上の欠測で経済改善PASSを出さない。自然traceが足りない場合は既存error-discovery手順で例を集め、dashboardや新frameworkを先に作らない。

## PA09 — 利用可能なOSS

GitHub PUBLIC/MITは既達。全体は既存installer/selected loop入口、CapafyはCD9の少数コマンドで起動する配布artifactを対象にする。mainを唯一のsourceとし、配布先で第二の手維持実装を作らない。

既存`test/oss-self-contained.test.mjs`、`test/install-isolation.test.mjs`、selected loopのsetup/readback/stop contractを使い、clean environmentで一つの選択loopから実測する。secret/session/state/private sourceをbundleに入れない。外部accountの本人要件はsetup_requiredとして具体的に出す。Anicca/Honne等の既存個別assetを全userの必須条件にしない。

公開READMEはverifiedな数字と観測範囲だけを記す。実売上と市場需要をclean-host起動testで証明したとは書かない。全18の常時起動や追加の大規模QAを新しい配布完了gateにしない。

## PA10 — 売上規模の判定

通貨未指定の今回の発言を使って既存US$10M MRR目標を縮小しない。既存lane目標、最初の継続購入、$100K、$1M、$10Mの各段階で有料顧客数×月額単価×継続率と、返金/手数料/全費用/必要運用容量を確認する。予測・公開Sold・trial・調達・paper利益・本人の給与を会社MRRへ足さない。商業重点のCapafy仮説は比較データで更新し、最大ROIが既に証明済みと主張しない。

## 今回の文書検証と残差

このplanは実装前の案。spec coverage、実在するpath、数値/窓、未知の扱い、no-action境界、owner分離、余計なframework/gateがないことを確認し、文書diffだけをcommit/pushする。runtime test、新RED、release、provider effectは今回実行しない。財務/主要診断のfresh-context read-only検証結果はspecへ記録する。銀行入金、全費用、全18の自己修復/自己改善、clean-host起動、目標売上は未達のままである。
