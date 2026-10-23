# D011 — 公開OSS成果物と別の公表支払証拠の接続

2026-10-23。元D011の「承認された成果物と独立して確認可能な受領証拠を照合」「支払完了を証明できなければ収入増と主張しない」を、歴史的な第三者の公開事例で検証する。これはManagerの受注・所得増・純便益ではない。

## 一次資料と照合の限界

- [JHipster PR34939](https://github.com/jhipster/generator-jhipster/pull/34939)は2026-09-13T20:14:31Zにmerge。head Git SHA1は`3dc3a668b18f11ff8e72c1bf485ad3664132dc12`、merge Git SHA1は`89bf4156f9c1a64a8ac6282908f1fb11cc3a0536`。
- 取得済みdiffは6432 bytes、SHA256は`367e082928145cd09777330dfebaf08357c992d95f8e14c510dd480ca80affda`。Git SHA1とdiff snapshot SHA256は別の識別子。
- [公開comment5655851568](https://github.com/jhipster/generator-jhipster/pull/34939#issuecomment-5655851568)は正確な[Open Collective expense346205](https://opencollective.com/generator-jhipster/expenses/346205)へlinkし、expenseのdescription/itemも正確なPR URLを参照する。
- platformはPAID USD100.00（10000 minor）、承認時刻2026-09-13T20:26:05.492Z、paid activity時刻2026-09-15T17:00:57.283ZとDEBIT -10000 minor USDを公表している。これはplatform上の声明であり、受取人の銀行・processorで認証した実着金ではない。
- bounty labelはmergeの13秒後。事前募集・名目報奨はUNKNOWN。支払providerがdiff hashを認証した証拠はなく、成果物との対応はexact PR URLを用いたadapter側の結合。

原本10件のbytes/hashを取得manifestと照合し、公開packetの5出典も元snapshotと照合した。raw API/HTML/diff、投稿者・受取人のidentity/contact、private invoice/payout情報はGitやモデル入力へ移さない。コードのlicenseを個人metadataへ拡張しない。

## 再利用したsource接続

`manager_core/public_opportunity_payment.py`はD003の固定snapshot方式と既存`Source.verify_content`を再利用する。actual Source型、正確なsource_id/immutable URL、32768 bytes上限、callerのhashと独立したreview済みSHA pinをJSON処理前に確認する。汎用ingestion・PII検出・支払認証engineではない。

- [非個人SAFE packet](https://raw.githubusercontent.com/Daisuke134/life-manager/64914b52904a4a4338fdfa3f2f688cd0843a472c/products/manager/docs/research/JHIPSTER_D011_SOURCE_20261023.json)：8739 bytes、SHA256 `0f6cc6343ca17b24c3f55061e6f38a367d3dde29cc81d0172089106723e2062e`。
- rootは2026-10-23T10:06:19.233694ZのHTTP200で公開bytesとローカルpacketの一致を確認。SourceのURL/hash/実取得時刻はこのpacket自身のもので、upstream原本や派生projectionと混ぜない。
- 出力は成果物、platform Paid、相互link、原本参照、権利・帰属、未知を別欄に保存。P0/NO_ACTION、income NOT_VERIFIED、human welfare NOT_MEASURED、verified income/net benefitはnull。
- `chain_completeness=INCOMPLETE_PRIOR_POSTING_UNKNOWN`は限界を示す固定表示であり、旧reconcilerの実行結果ではない。既存OpportunityRecord/厳密なfour-stage契約は変更していない。

## 実検証と残る統合

worker source `86debf2fbcde891278f6456d9db63665c23a93b7`は実装前RED（4 tests / 8 assertions failures）→4 GREEN、全395 tests / OKを記録した。rootの別runは395 tests / OK（1 skip、-qログにskip identityなし）。これらを同じrunとして扱わない。

独立R1は全差分と原本照合を確認し、0 findings。source/spec・品質をPASS、通常統合後の元D011の限定source接続受入を支持した。D003がmainへ入った後、rootはmain `d57f56f099f44cf90fcf22a834221144560b757b`を通常mergeし、workflowの両focused testと共有boardの全既存行を保全した。**この統合treeでrootが全404 testsを単独実行し18.429秒、失敗・skipとも0**。Manager import境界、loop契約（18 catalog / 192 registry / 113 mapped、errors0）、products/manager範囲gitleaks（検出0）、diffcheckも成功。

source-boundaryはcloudにcanonical checkoutがないFAILを保持する。別hostのPASSへ付け替えず、guardを緩和しない。通常PRのexact-head CI/mainと元registryへの受入は別の外部証拠で記録する。

事前募集、銀行実着金、労働時間、費用、機会損失・分母、Managerの収入・生活改善・因果効果は不明。新たなAPI推論・送金・応募・公開ページへの作用は0。D012や全Managerの完了へ昇格しない。

## 通常main統合と元D011の限定受入

[PR8675](https://github.com/Daisuke134/life-manager/pull/8675)は2026-10-23T10:27:12Zに通常squash mergeされ、main commitは`13b8c12f481fd0dae893ed6ae0b45a33a8c4c00d`。exact head `69a8f904107dc9b913db45213291515a72dbef7c`の15 checksは14成功・意図したPR publisher skip1。必須Security Scan39938409258とManager39938409229も成功。通常helperのexact-head照合でmergeし、admin/forceは使っていない。

公式PR readback後のmain fetchでadapter・test・packet・workflowとreview済みtreeのbytes一致を確認。独立R1/R2の未解決指摘0と実検証に基づき、元D011だけをPUBLIC_SOURCE_CONNECTION_P0_ONLYとして受入する。mainへのsource統合は定期runtime実行や完全chainの認証ではない。事前募集・銀行実着金・Managerの収入増・D012の純額と分母・人の便益は未検証のまま。
