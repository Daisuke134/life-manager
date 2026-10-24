# Costelloらの訂正済みAI対話研究 — 現物確認と再利用

2026-10-24 UTC。既存Task8のA01–A09を進める有限研究。全V002/V003の受入やManager自身の人便益とは別。実進捗は本書・実結果receipt・既存計画へ結び、tasks.jsonを第二の台帳で置き換えない。

## 原著と取得した現物

Thomas H. Costello、Gordon Pennycook、David G. Rand、[Science原著](https://www.science.org/doi/10.1126/science.adq1814)。取得元は[Dryad DOI](https://doi.org/10.5061/dryad.v6wwpzh4h)と[訂正完全パッケージ](https://doi.org/10.5281/zenodo.22754984)。原著の2024版を2026訂正版と混ぜない。

- Dryad公式API: dataset136984、version8、versionID466347、CC0。ファイルmetadataは200、直接downloadは401。この経路でZIPを取得したとはしない。
- Zenodo公式API: record22754984、version1.0、公開日2026-09-27。ZIP675,811,309B、191members。
- HTTP206でcentral directoryと56membersを選択取得。member圧縮解除後1,690,053B、member取得range合計4,092,912Bにtail131,072Bを別加算。コードと必要な数値表だけを選び、巨大な再構成資料/原会話/画像等を一括取得しない。
- 初回56memberのCRC一致、manifest自身を除く55payloadのbytes/SHA256が上流MANIFEST.csvに全一致。その後、保存済みtailからS7/S8/S21の3表を追加取得し、新しい通信なしで同じ検証を実施した。合計59members/58payload。archive全体のMD5は未計算で、部分hash一致を全archive検証へ拡張しない。
- 詳細は[artifact manifest](../../experiments/behavior-model/costello-correction-artifacts-v1.json)。個票/疑似ID/生CSV/上流全文はGit外の0700/0600領域へ保存。

取得LICENSEはcode MIT、関連Dryad data CC0、publication materialsはpublisher-definedと明記する。これはcode/data/paperを区別したoffline解析候補で、全素材の学習・転載・再配布を包括受入するものではない。Dryad ZIPとの独立byte比較は未実施。

## A02: 実schemaと解析単位

`data/deidentified/public_primary_analysis_deidentified.csv`は2,094行/54列、StudyNumber1=748、2=584、3=762。`Post_Belief_Specific`欠測50行で、Study1=10、Study2a=16、Study2b=24。事前値は50–100、事後値は0–100の本人報告confidenceで、事実の真偽や苦しみの尺度ではない。

`public_participant_screening_flow_deidentified.csv`は4,039行。全primary responseを公開participant pseudonymへ結べ、欠損bridge0、公開key上のwave横断participant0を確認した。別release/実世界の人物同一性を外部照合した意味ではない。識別子はモデル入力にしない。

原著のheadline解析は各screened study cohortで事前値を中心化し、その後に完全caseを使うOLS:

`Post_Belief_Specific ~ ExperimentalCondition * Pre_Belief_Specific_c`

Study2はwave2+3をpool。screened Nは748/1346、実model Nは738/1306。平均中心化を完全case除外後へ移すと、treatment係数の意味と値が変わる。標準誤差は原著codeのclassical model-basedを使い、勝手にrobustへ変えて完全再現と呼ばない。

追跡は別の対象条件を持つ。上流REPRODUCIBILITY.mdは10日比較630人/1883observations、2か月比較489人/1951observations、Figure2Aの全利用可能748人/2642observationsを区別する。後続の実validatorで元の10日/2か月混合モデルとcontrast/CI/pを再fitしてPASSした。Figure2Aの画像自体を再生成した意味ではない。

`Importance=-999`は実質的なnot-applicable回答で、NAと同じではない。会話本文は同じword数のneutral placeholdersへ置換されているため、会話説得のSFT corpusとして採用しない。strategy ratingsは集計で、個別応答への圧力/依存goldにはならない。

## A03/A04: 再現範囲

上流`scripts/build_results.R`を変更せず、新しい作業copyでheadline/S7/S8と同scriptのsecondaryモデルを再計算した。入力原本と上流precomputedは不変にし、再計算出力を別copyで照合した。6表45行はnumeric許容差1e−10内で一致。survey reconstruction、causal forest再学習、全図・全publication packageの再生成は今回の範囲に含めない。

上流renv.lockはR4.5.0。このhostにRscriptはなく、conda-forgeのexact4.5.0解決は失敗した。互換R4.5.3の隔離環境でbuildと上流7部validatorがPASSした。exact lockfile再現とは呼ばない。2回の依存不足によるvalidation失敗を含む[実結果](../verification/COSTELLO_CORRECTION_REPRODUCTION_V1.md)に結ぶ。新モデル/API呼出し0、新規参加者/介入0。

## 次のmodel研究への意味

実入力に合う有限候補は、事前confidenceと割付条件から事後confidenceを予測する研究。主指標は0–100 slider pointのMAE等で、本人報告のconfidenceを真のbelief probabilityとしてBrier採点しない。no-change forecastとtrain-only OLSを強い比較対象にする。

これは公開された研究条件内のforecasting候補で、個人の因果効果・説得文生成policy・一般的行動変容・人便益を示さない。[新設計とdevelopment比較](../plans/2026-10-24-costello-numeric-forecast.md)に2-feature入力・train128/dev584/evaluation762と漏洩検査を固定した。私有入力は準備したが、A09のsource/CI/durable ownerは未成立で学習は未実施。元final16の再読/再利用は行わない。

## 記事・無料書籍

最新ユーザー指示により、研究を先行しつつ記事と無料公開書籍の執筆を並行する。既存[canonical書籍outline](../books/MANAGER_RESEARCH_BOOK_OUTLINE.md)へ接続し、原著の紹介だけでなく取得版、実コマンド、訂正、欠測、陰性結果、未再現を原稿に残す。実公開は媒体別URL/readbackを持つ場合だけ記録する。
