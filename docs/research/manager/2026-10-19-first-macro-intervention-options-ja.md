# Manager 最初のマクロ介入候補（検討資料・非公開）

2026-10-19 調査。会社 Anicca、製品 Manager（マネージャー）、使命「End suffering.」。
これは設計案であり、実地介入、予測改善、苦しみ軽減の実証ではない。作業順・進捗の正本は既存の統合SSOT一つだけ。本書は新しいTODO台帳ではない。公開記事、サイト反映、英語画像の追加は保留。

## 現在地

研究ブランチの引き継ぎ資料とbuild-first設計を確認。人口合成8A/8Bは評価済みだが観測行動や実地成果ではない。9.1〜9.4は基礎教材と小さな架空例。既存Life Managerに個人向け観測、希望・委任、判断、ジョブ、外部効果、公式照合、証拠と結果確認のソースがある。Managerの共同体・共有環境向けの閉ループはまだ実証していない。

## 候補と七つの比較項目

### A. 共同体の支援枠・共有施設へのアクセス（暫定推奨）
* 誰を助けるか：無料相談、学習支援、コミュニティ施設などを必要とする人。開いている資源と利用希望が合わない、運営調整に時間がかかる問題。
* 実データ：管理者が所有する空き枠、提供可能時間、定員、予約・キャンセル、待機希望、実際の利用・提供記録。権限・同意は未取得。
* 変更できる対象：運営者が許可したイベント種別の営業時間・予約枠・定員、待機者への適切な空き案内。存在しない供給量を増やしたように見せない。
* 再利用：runtime-job-store、effect-reconciler、loop-adapter-registry、agent-graph、証拠処理。Cal.com v2 APIは接続候補で、現在の導入済み部品ではない。
* 足りない接続：実地団体、認証と変更権限、予約システム用read/writeアダプタ、共有資源用の判断規則、実際のサービス提供結果、適切な外部効果クラス。
* 改善測定：所定期間に利用できた割合、待ち時間、未対応件数、運営の作業時間。副作用は過剰予約、偏り、苦情・中止・欠勤を記録する。単純な予約数の増加だけでは便益や因果効果を示さない。
* 最小デモ：管理者の承認した試験用サービスで、実在する追加可能枠を提示→承認→API変更→公式空き枠GETで確認。再生時の重複変更なしを確認。実地便益はさらに実利用と本人・運営者の記録が必要。

### B. 支援団体のシフト・物流・物資配分
* 誰を助けるか：必要な支援を受けられず待つ人、および運営とボランティア。
* 実データ：支援件数、期日、技能、同意した可用時間、提供できる物資・配送・完了記録。
* 変更できる対象：承認された担当表、配送順、受渡し枠、物資の割当。
* 再利用：既存ジョブ・証拠基盤、必要に応じGoogle OR-Toolsの制約付き割当コード。
* 足りない接続：現場の実データと運営権限、本人の割当同意、制約・公平性の定義、作業完了確認。
* 改善測定：期限内支援率、未対応人数、配送・作業時間、ボランティア負担と偏り。
* 最小デモ：運営者が承認する担当変更を反映し、実際の作業記録を確認。オフライン計算だけなら演習と明記。

### C. 支援制度・共有案内・手続きの改善
* 誰を助けるか：支援を受けられるのに案内不足や複雑な導線で断念する人。
* 実データ：公式要件、更新履歴、匿名化した問合せ、申請完了・差戻し、担当者の負担。
* 変更できる対象：所有する案内ページ、FAQ、申請導線、必要な情報の提示順。資格規則自体は無断変更しない。
* 再利用：情報の出典確認、文章・成果物保存、既存の実行・証拠確認。
* 足りない接続：管理者承認、一次資料の更新追跡、誤案内防止、利用までの結果記録。
* 改善測定：正しい手続き完了、問い合わせと差戻しの時間、誤案内、申請断念。
* 最小デモ：管理権限のある検証用ページを一次資料に基づいて修正→公式readback→利用結果を別に確認。公開保留中の記事は投稿しない。

## 第一候補の判断と失敗条件

Aは現実に許された変更の前後をAPIで読めて、実行の誤りも判別しやすい。ただし候補の順位はアクセス・人への意義・実施可能性に依存する。運営者、実利用、比較可能な観測が先にそろうならBやCを選ぶ。現在はどの運営環境の操作権限も確認できていない。個人イベント申込は既存の実行契約の参照例に限る。

## 技術的な一周

Observation（観測）→ ProblemCase（困りごとの定義と根拠）→ ActionProposal（候補、費用、何もしない案）→ Decision（権限・条件・比較）→ RuntimeJob（既存のリースと冪等実行）→ Provider readback（変更先の状態を再読取）→ Receipt（実行証拠）→ OutcomeObservation（実利用、本人の便益、負担、欠測、期間）→ 次の判断。

tenant_id / case_id / action_id / job_id / effect_key / provider_receipt_ref / outcome_windowは区別する。各観測にはsource、observed_at、available_at、鮮度を残す。成功、失敗、未知を分け、未知の外部効果は照合前に再試行しない。人や団体の権限は使命から推定しない。初期外部変更は管理者承認付きとする。

既存opportunity-engineのcategoryはbody/mind/finance/life_adminなので共有環境専用の判断規則が必要。既存runtime-job-storeとadapter-registryのeffect classはnone/publish/message/moneyである。資源更新を既存種別に無理に偽装せず、コードとDB契約を確認して専用種別を追加するか、既存契約で正当に表現できるか決める。daily-preflight-collectorsは通信疎通テストを含むため、共有環境の観測器だと誤認しない。

評価は「モデル予測」「外部の変更完了」「サービスが提供された事実」「利用者の負担や便益」「施策に起因する改善」を区別する。共通資源の介入では相互干渉がある。初期は無変更時の基準を固定し、継続評価で適切な時間・施設単位の対照を検討する。人口合成、行動予測、エージェントシミュレーション、LLMは需要と介入の複雑さが必要とした場合にのみ追加。

## 原文とコード（2026-10-19確認）

* Cal.com公式 v2空き枠GET https://cal.com/docs/api-reference/v2/slots/get-available-time-slots-for-an-event-type
* Cal.com公式イベント種別 https://cal.com/docs/api-reference/v2/event-types/create-an-event-type
* Cal.com公式API認証 https://cal.com/docs/api-reference/v2/introduction （新規Platform signupについて制限がある。通常のAPI利用と区別）
* Google OR-Toolsの制約付きシフト割当（公式コード例） https://developers.google.com/optimization/scheduling/employee_scheduling ；参照元コード https://github.com/google/or-tools/blob/main/examples/python/shift_scheduling_sat.py
* Moura & Pinho (2025) 外来予約の最適化・無料原文 https://pmc.ncbi.nlm.nih.gov/articles/PMC11988311/
* OpenFn（公共サービスのシステム連携、本人による製品説明） https://www.openfn.org/ ; https://docs.openfn.org/
* Food Rescue Hero（寄付食品の人員・配送の調整、製品側の説明であり独立評価ではない） https://foodrescuehero.org/solutions/operational-efficiency/
* Dagstuhl Seminar 25121 (2025) scheduling fairness議論 https://drops.dagstuhl.de/entities/document/10.4230/DagRep.15.3.94
* Nahum-Shani et al. (2018) 介入時点と成果の設計 https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/
* Lee et al. (2026) 待機列を含む研究のプレプリント https://www.alphaxiv.org/abs/2605.25169

原文や第三者全文はGitHubへ転載しない。古い原文の位置と読解範囲は既存のphilosophy-source-mapを参照する。今回の研究は正式な機能完成・公開を意味しない。

## 先の展開

最初の小さな実証の後に、別の共同体、支援分野、インフラへ段階的に拡張する。新しい英語記事・発表資料は実装済み、実行済み、測定済み、未確認を分けて原稿として保存し、公開は別途承認する。
