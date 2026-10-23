# AI Monk Factory 利用者の投稿先を既存publisherへ接続する

**目的・範囲・完了条件:** v1 configと生成入口を維持し、利用者の投稿用JSONを既存IntentStore/PostizAdapterへ渡すlocal CLIを作る。新provider/ledger schema/schedulerを実装しない。隔離したsource検証・fresh review・CI/main・main由来固定版までをsource受入とし、実投稿/日次運転/実売上は公式receiptで別に判定する。Daisの未確定費用・停止owner・正規admissionを維持し、live生成/投稿は本実装の検証に使わない。

**入口:** `factory publish --config JSON --script UTF-8 --publication JSON --run-id ID --operation prepare|shadow|upload|draft|promote|route-check|status|postiz-readback|reconcile`。mutationのupload/draft/promoteには既存と同じ`--production`を必要とする。現在のv1 configに追加fieldを混ぜない。

**投稿入力:** 厳密な`ai-monk-factory.publication.v1` JSONはschema_version/native_handle/publisher_provider/provider_settings/publish_enabled/cta/caption/attribution_token/scheduled_at/visual_approval_idだけを持つ。platform/integration/product name/HTTPS URLは既存configから取る。既存Intentのattribution契約に合わせcaptionはCTA、tracking tokenを含むexact product URLを完全なtokenとして1回含める。時刻はtimezone付きで固定する。credential・任意DB path・accepted statusを受け取らない。TikTokは現行のAI表示true/自社商品true/paid partnership false/DIRECT_POST契約を維持する。Instagramは既存video設定を使う。

**共通context:** `publish/publication_context.py`の`PublishContext(account, product, destination_url)`を任意引数`context=None`で既存publish関数へ渡す。未指定なら既存registry/owned redirect/Hook Lab処理をそのまま使う。指定時はaccount_id/product_idをcontextと照合し、同じcontextをcreate/shadow/preflight/live route/reconcile/native candidatesへ伝播する。IntentStore/PostizAdapterのschema・unique dispatch・provider実装は変えない。

**状態とidentity:** account IDは既存stable_idをplatform/integrationから作り、project/state_root/runで変わらない。product IDは商品name/URLから作る。host rootはAM-15bの既存LM_DATA_DIR解決規則を共有する。Factoryの単一IntentStore実体と承認/公開ledger、run別immutable intentは`<host>/marketing/ebook/factory`へ置き、利用者state_rootでDB/fenceを分けない。assetは既存render出力から導出し、生成sidecarのschema/request SHA/output/video receipt/state/output SHAと照合する。completedとcost_reconciliation_requiredは区別を保持し、未知費用を0としない。post/status/readbackから費用を確定した扱いにしない。

**拒否境界:** 既存registryのintegrationまたは同platform/native handleと衝突するFactory routeを拒否し、Daisの停止status/unknownを別名で迂回させない。素材承認は既存record_visual_approvalの記録を参照するだけで自作しない。各live操作前にasset hash/media/承認/routeを既存preflightで再検査する。run ID/台本/設定/本文/slot/assetが変わる同runを拒否する。既存exclusive_lockで同runのintent作成競合を直列化し、別projectの同integration/同slotは共有IntentStoreの既存unique制約が拒否する。unknown/rejectedの同operationを再送しない。promoteのscheduledをPUBLISHEDへ変換しない。

**所有:** bounded workerはpublication_context.py、publish_cli.py、preflight.py、new test_publication_context.pyを所有する。primaryはfactory_publish.py/test_factory_publish.py、bin/lm、factory_render.pyの既存host root resolver抽出、README/example、本plan/S11を所有する。他者の変更を戻さず、共通interface変更はprimaryへ連絡する。

## 実行順

- [x] Worker: contextなしの現registry/Hook Lab経路を保持する。contextありのCTA/宛先/create/preflight/route/reconcileで最小REDを観測し、既存関数への伝播だけでGREENにする。
- [x] Primary: 厳密入力・共有host DB/route identity/承認不足/既存registry衝突/sidecar hash/run replayの最小REDを先に観測し、CLIを既存publisherへ接続する。upload/draft/promoteはstub clientで各1回/unknown再送0を確認する。
- [ ] Primary: 変更に関係する既存Factory/publish回帰とLoop Contract/source-boundary/OSS/diffを一度実行し、source commit/push/remoteを照合する。
- [ ] Fresh read-only reviewerが全差分を確認し、指摘修復後のexact head CIを経てmainへ統合する。main由来固定版のsource/CLI helpを照合し、live provider操作は行わない。
- [ ] S11/本planへsource受入と実事業の残件を記録する。次の実配信は正規admission/承認/費用ガードと公式receiptを使う。

**設計判断:** 新しい投稿adapter、project別DB、既存停止accountの再登録、render成功からの承認生成は採らない。local入力は実際の所有/接続をlive integrationで検査し、hosted tenant隔離・signup・subscription・Factory MCP・事前USD cap・実売上を今回のsource受入へ混ぜない。No-human-loopの委任に従いprimaryが方式を選び、承認待ちは追加しない。

## 実装・検証記録

- Workerのcontext引数未実装15 RED→15 PASS。既存default Hook Lab/intent/preflight/production/reconcile/native/routeを含め45 PASS。preflight旧testは未追跡MP4と古いown-business設定への依存だけをfixtureへ置換し、承認/codec/ratio拒否を保持する。
- Primaryの新Factory CLI/module欠落REDを確認する。run別intent fileのpublish_keyを別の保存済みintentへ付け替える反例はDID NOT RAISEでREDとなり、共有store原本との完全一致で拒否する最小修正を加える。
- Factory render/plan/既存HeyGenとpublisherの関連14files209 PASSに加え、環境credentialを渡さない実CLI prepareの1件もPASS（計210件）。実provider/credential/browser読取0。Loop Contract18業務/192jobs/errors0、source-boundary/OSS/diffがPASS。fresh review・CI/main・固定版・実投稿は未完。
