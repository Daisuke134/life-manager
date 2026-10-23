# U005 — 既存Proof Explorerの公開資料による受入

2026-10-23 UTC。**U005受入：読み取り専用の公開デジタル証拠の範囲。** U003の限定運用対象の選定とK010の完了後、既存のExplorer・collector・validatorを再利用して原条件を確認した。新しいUI・評価器・配信・model呼出しは追加していない。

## 実際に確認したこと

- 11:15:30.176741–11:15:39.477327 UTCに通常の認証なし公開GET30回、HTTP200が30件。元receipt、immutable candidate／parent、現行公開7ファイルを取得した。rootも保存された全30本文のbytes/hash、既存collectorのsource hashを照合し、同じ既存validatorをcached bytesで再実行した。
- 現行[provider commit](https://github.com/Daisuke134/life-manager/commit/faf18b39207be69af89d9b10389a294731288a20)はparent `c6d5de029e91142ef3e0c965f4ef800d37a0f515`、commit時刻06:01:36Z、変更は許可7パスのみ。receiptが示すP1と、後続の配信観測を分けた。
- 同じSHAのimmutable7ファイルと[公開service](https://daisuke134.github.io/life-manager/manager-support/)の7ファイルはbyte一致。6ページ26866 bytes、manifest込み27639 bytes。既存`verify_readback`は`VERIFIED_BYTES_ONLY / P2_ARTIFACT_ONLY / beneficiary_outcome=NOT_MEASURED / causal_effect_verified=false`を返した。
- 保存済みの実Explorerは、P2_ARTIFACT_ONLY、NOT_MEASURED、元release時刻と観測時刻、exact provider／immutable source／public serviceへのリンクを別表示する。form/input/scriptは0。現行の`proof.html`も未測定の人の結果と版固定sourceを明示する。
- 機械可読の[受入観測](U005_PUBLIC_PROOF_READBACK_20261023.json)に各ファイルのhash、公開元URL、P0とP1/P2の区別を保存した。raw本文・private wrapper・実行logはGitへ取り込まない。

## 古いtransitionを現在の成功に変えない

本物の過去original intentとcommit `d33d251ec0b82bf541a727ead7d1ede39f0a8216`で`prove`を1回実行した結果は、**`public live version differs: UNKNOWN_EFFECT; do not resend`**。現行内容が別版のための正しい拒否であり、成功や再公開へ変換していない。同じ取得済みの過去receipt・candidate・parentの実差分は、既存`validate_commit_receipt`で`MATCHED_PUBLIC_COMMIT_DATA`を再確認した。

最新faf18b3のoriginal intent／完全なnative proof packetは許可された保存済み非DB資料に見つからず、公式artifactの取得もcloudで403だった。回避・private DB参照はしていない。**最新original packetによるtransition全体のfresh prove成功は主張しない。** 最新の公開receiptとimmutable/live byte一致、過去のoriginal transitionの照合は、それぞれ別の検証結果である。

保存済み公式[run39909274852](https://github.com/Daisuke134/life-manager/actions/runs/39909274852)自体は`NOT_DUE / P0 / writes=0 / positive_canary=NOT_RUN`で、summaryの`E16_ACCEPTANCE=INCOMPLETE`を保持する。`current_proof_exported=true`は既存成果物のexportであり、当該runが新しいP2変更を実行した意味ではない。E16全体の限定受入は別の受入書に基づく。

## 第三者が再確認する方法

1. JSONに記録した[現行receipt](https://api.github.com/repos/Daisuke134/life-manager/commits/faf18b39207be69af89d9b10389a294731288a20)のSHA・parent・変更7パスを読む。
2. `https://raw.githubusercontent.com/Daisuke134/life-manager/faf18b39207be69af89d9b10389a294731288a20/manager-support/`へJSONの7ファイル名を付けてGETし、bytesとSHA256を照合する。
3. 公開serviceの同じファイルをGETする。将来変わっていれば新しい観測として保存し、過去の変更を失敗や再実行の対象にしない。
4. 過去transitionはJSONのcandidate／parentの版固定URLとreceipt、既存`validate_commit_receipt`で照合する。公開JSONを与えただけで認証済みとは扱わず、collectorが元URLから取得したbytesを使う。
5. 収入・支援到達・症状・負担改善・因果効果はNOT_MEASUREDを維持する。artifact retentionの期限をimmutable sourceの恒久性や最新内容の保証にしない。

この範囲で独立した実readbackとrootの再検証を終え、原U005だけを受入した。原ID・depends・change・verify・externalは変更していない。U004/U006/U007/U008の研究協力・実利用・便益・継続需要は充足していない。
