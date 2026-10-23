# 任意Ampersand SDK固定 — source受入（2026-10-23）

Managerの既存advisory adapterが監査済みSDKと異なる版を受け入れる差を修復した。新しいagent framework、scheduler、UI、owner、推論有効化は追加していない。

## 正規統合と検証

- PR: [#8693](https://github.com/Daisuke134/life-manager/pull/8693)。通常の `bin/merge-when-green 8693 --squash` で2026-10-23 11:48:15 UTCに統合。
- reviewed/final CI head: `be055dffd922ba887345183c4e4c192f86a3cef9`。
- main merge: `f29c10074d7ac31327b5d6247d0f656f20d4c4db`。統合後のManager sourceと修復したruntime testがreviewed headと同一であることをGit bytesで照合した。
- 全16チェック終端、15成功／想定内 `publish-owned-prefix` skip1、失敗0。admin override、強制push、失敗した旧headの再試行は行っていない。
- [Manager verify39947891623](https://github.com/Daisuke134/life-manager/actions/runs/39947891623)、[checkpoint contract39947891513](https://github.com/Daisuke134/life-manager/actions/runs/39947891513)、[必須Security Scan39947891423](https://github.com/Daisuke134/life-manager/actions/runs/39947891423)が成功。Loop control contractsも成功。
- SDK差分の独立R1と停止fixture新差分の独立R2は、いずれも指摘0。SDK source上の全410テストと、fixtureの独立17 focusedテストはskip0で成功した。

研究branchへ同じ5ファイルを同期した後、全974テストを実行し969成功／既存skip5、失敗0（21.544秒）。`tests/test_ampersand_integration.py`のbytes不変、Manager境界、原113件の台帳不変も確認した。これはローカル同期後の証拠で、後続の研究branch公式CIや定期推論の結果へ付け替えない。

同期head `b6b5f6a8e34912e4da4dd2d3a0981499207c2d99`の[公式研究CI39949005185](https://github.com/Daisuke134/life-manager/actions/runs/39949005185)も11:51:51 UTCに成功した。Python3.11でE01 contract6件、P0 advisory21件、全suite948件（942成功／6 skip、失敗0）を確認。ローカルPython3.12の974件とは別の母数として記録する。公式logは30,562 bytes、SHA-256 `7f7f0f3b0f6d6c0a910d7b9ceddd653e9542e62a5c70e4348356505285cd5ef3`。この追記は後続の文書更新で、tested headを付け替えない。

件数差26件は、`test_external_behavior_eval.py:12–13`が任意NumPy/SciPy依存の欠落時に研究テスト27件をmodule skip1件へ置き換えることで説明できる。同じPythonでsite packagesの有無だけを変えたcollectionにより、`974 − 27 + 1 = 948`、skip5→6と、残947個のtest ID一致を確認した。テストの再実行はしていない。公式quiet logは個別skip IDや依存一覧を出力しないため、remoteの依存欠落はこの一致と依存を導入しないworkflowからの推定であり、直接のpackage inventory確認ではない。共通の5 skipは既存の任意DoWhy検証。ローカルでは当該27件も実行済みで、新しいSDK6件のskipではない。

## 再利用した実装と修復範囲

`manager_core/ampersand_api.py`の既存lazy client factoryへdistribution metadataの完全一致検査を追加した。任意の `requirements-ampersand.txt` は `openai==3.24.0` の直接依存だけを固定する。推移依存lockではない。SDK欠落・版不一致・import失敗は固定したローカルエラーとし、raw exceptionを表示しない。既存base URL、retry0、timeout、key検査を維持する。

新規 `tests/test_ampersand_sdk_setup.py` は6件。研究branchの既存 `tests/test_ampersand_integration.py` は上書きしない。setup READMEと実装計画を含む5ファイルは、正規mainの同じbytesを研究branchへ同期した。

必須CIで見つかった既存停止テストの期待も修復した。親がTERM後も生存してSIGKILLを必要とする場合、正当なowned-leader停止で子も停止し得る。成功した信号の起点を記録し、この経路だけを認め、未観測groupへのpost-exit drainを禁止する。分離した別sessionの同一性、時間上限、grace、cleanupを保持した。productionの停止実装・workflowは変更していない。

制御した親生存ケースで旧oracleのREDを取得し、修復後にGREENを確認した。Linuxで一度、既存2秒上限を約6ms超えた記録も保持し、その個別・全focused再実行と独立17件は成功した。元のmacOS失敗時の信号履歴は未記録であり、その時系列を断定した修復ではない。最終headのmacOS必須CI成功を別に確認した。

## 実SDK確認と受入限界

公式 `openai-3.24.0-py3-none-any.whl` のSHA-256は `b59703a3e3b5df78b269e90049d383a1dda58c90104cc4be59db21078db4b7a4`。private scratchの隔離venvへ実installし、network接続を禁止したconstructor確認が成功した。network接続試行0、model要求0。SDK resource・設定の確認であり、provider稼働、無料枠、実応答、課金・決済の証拠ではない。

cloudのcanonical-host source guardは既知のFAILを維持し、緩和していない。scheduled ownerへのSDK導入や定期推論は未実施、shadowは既定OFF。実課題での有用性、人の便益、収益はこのsource受入に含めない。原台帳は80 done／30 todo／3 skippedのまま。
