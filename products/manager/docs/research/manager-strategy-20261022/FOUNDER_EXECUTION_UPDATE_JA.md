# Manager: 先例から実装・実績・収益・出版・採用・YCをつなぐ更新

確認日 2026-10-22 UTC。既存の[戦略調査](REPORT_JA.md)を置き換えず、今回の追加調査と判断をまとめる。仕様は[製品仕様](../../MANAGER_PRODUCT_SPEC.md)、順序は[実行マップ](../../plans/2026-10-22-manager-founder-execution-map.md)、進捗は[既存tasks.json](../../roadmap/tasks.json)に従う。本稿は追加の状態台帳ではない。

## 結論

既存の部品と成功例を使い、**限定された実問題を解く → 証拠を残す → 同じ成果を教材・顧客・採用・YCへ届ける → 実際の反応と入金から直す**。独自の汎用agent基盤・記憶製品・評価framework・出版基盤を新たに作ることは当面の目的にしない。公開部品が存在することは、自分の顧客需要・動作・権限・収益・人の便益が実証済みという意味ではない。

長期使命は、避けられる苦しみを減らし、福祉を持つ存在の繁栄を支えること。有限の初期製品は、所有する公開情報経路について、観測、限定変更、独立した読戻し、復元、費用・下流結果の評価を回す Digital Autonomy v0.1。世界全体への効果を、この初期製品の実績に含めない。

## 調査で決めたこと

| 領域 | 他者の先例と資料 | Managerの判断 |
|---|---|---|
| 永続実行 | [LangGraph checkpointer](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[Temporal retries](https://docs.temporal.io/develop/python/best-practices/error-handling) | 実績ある仕組みを比較した。現在のPython/SQLite/outboxをまず限定運用へ接続し、multi-worker要件が出た時に既成engineを採用評価。外部作用のidempotency/readbackはengineでも必要 |
| 記憶・coding | [Letta active source](https://github.com/letta-ai/letta-code)、[OpenHands SDK v1.57.0](https://github.com/OpenHands/software-agent-sdk/tree/v1.57.0) | 必要時の隔離adapter候補。旧Letta V1はretired、OpenHandsはPython>=3.12。記憶や自由shellを権限/予算の正本へ直結しない |
| 評価・simulation | [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai)、[Simile confidence](https://www.simile.com/blog/confidence)、[Aaru method](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)、[Radiant connector](https://github.com/artificial-societies/radiant-claude-plugin) | 既存eval runner/契約/benchmarkの設計を再利用。異なるbenchmarkを順位表にしない。hosted model/dataの権利・価格・task適合は別確認。予測scoreは実際の介入効果ではない |
| cloud | [Railway volumes](https://docs.railway.com/volumes/reference) | 単一Python worker＋専用永続volumeを初期選択。connectorでproject読取可能、Macは実行の前提でない。専用worker/volumeは未作成、replica不可・redeploy小停止を受け入れる限定構成 |
| 文章・書籍・教育 | [Hamel eval FAQ](https://hamel.dev/blog/posts/evals-faq/)、[Chip book/repo](https://github.com/chiphuyen/aie-book)、[Simon implementation notes](https://simonwillison.net/2025/Nov/6/upgrading-datasette-plugins/)、[Jason archival content](https://jxnl.co/writing/2025/04/04/creating-content-that-converts-my-guide-for-ai-consultants/) | 実装一件と実際の失敗・費用をcanonical caseにし、英日記事→既存bookの章→12slides/8carousel/短いslideshowへ再利用。第三者の売上を推計せず、現在終了したサービスを募集中としない |
| 機会獲得 | [YC apply](https://www.ycombinator.com/apply)、[video](https://www.ycombinator.com/video)、[FAQ](https://www.ycombinator.com/faq)、各社公式求人 | 期限のあるYCと適合職種の準備を実装と並行。応募/採択/就職/売上を別の状態とする。YC採択後のフルタイムと他社フルタイム勤務の両立は約束しない |

実際に採用済みの既存部品と、導入候補のframeworkを区別する。上表は新dependency導入・認証・provider実行を行った記録ではない。著作権・license・hosted契約を守り、本人の文言・非公開データ・売上をコピーしない。

## 何が実績で、何が残っているか

- E01–E15は既存実装・検査の記録あり。E16はsandbox/reference cycleまでで、本番adapterと永続runtime、実際のcanary/readback/restart/rollbackが残る。新workerはまだ配備していない。
- 既存public support prototypeの公開証拠と、新E16 cycleの配備は別。元の6 HTML/16 browser checksは日時付きのソフトウェア検査で、6人/16人の改善ではない。
- 元の113作業は69 done / 41 todo / 3 skipped、technical cursorはE16。この調査で実証/採用/売上taskをdoneへ進めない。
- 五件の同意ある問題確認、支払主体/代替の検証、有償pilot、下流便益・継続は未成立。まず自社owned surfaceで技術を検証し、顧客の業務を勝手に書き換えない。
- Manager売上の真正な決済source coverageは今回取得していない。金額はUNKNOWN。以前の「未獲得なら0」の文言を修正し、対象期間/商品/経路を確認したゼロだけ0とする。給与、受託、製品、content、投資、他製品を混ぜない。

## 期限と優先順位

1. E16の専用runtime/volume/ownerとadapterを用意し、未解決intentを新candidateより先に照合する保証、slot予約直後crash、実host restart/restoreを検査する。元のsource/ref/admissionを緩めない。
2. 同時に、現在のcode/evidence/cost/limitsを2頁のcase studyとYC/CVへまとめる。本人の経歴、移住/就労、commitmentは本人の事実で埋める。
3. YC W27の公式確認値は **2026-11-02 20:00 America/Los_Angeles＝11-03 04:00 UTC＝13:00 JST**。内部目標は11-01 23:59 JST。1分のfounder videoとproduct demoは別。書籍/全実装/売上の完成待ちにしない。
4. 最初の採用候補はSimile eval、Andon safety/evals、Aaru research engineer。Artificial Societies FDE/ML、humans& research、Anthropic post-training evalは職務と経歴を照合して続く。いずれも日本完全remote確認済みではなく、採用可能性は不明。
5. 問題確認→scope固定の2–4週有償pilot仮説→実入金/原価/継続を測る。同じcaseから教材を作り、各公開物には一つの次の依頼を置く。週次では量に加え、技術的な返信、適合会話、提案、支払、継続を見る。

4週間の5面談/2提案/1実入金は検証用の目標で、完了・予測・約束ではない。少数面談で福祉への因果効果を主張しない。期限・本人条件・顧客結果により優先順位を改訂する。

## 読取範囲と出典

- [既存システム・論文・コードの再利用監査](FOUNDER_REUSE_AUDIT_20261022.md): 8系統、20行の資料台帳。公式docs、固定code、metadata、論文の選択passages、既存同日vendor調査の再利用を区別。全文論文をすべて読んだという記録ではない。
- [YC・6社の職務・3イベント・公開連絡経路](FOUNDER_CAREERS_YC_20261022.md): 公式求人/公開規則のlive取得。フォーム未送信、未確認資格・移住・visaを保持。AAMASの既経過author-registration、AI Engineer CFP終了、NeurIPS時刻表記不一致も記録。
- [4人の実装/発信/収益経路とManagerへの適用](FOUNDER_PUBLISHING_REVENUE_20261022.md): 11 first-party pages。本人申告の収入や顧客を独立財務検証としない。
- [機械可読source metadata](FOUNDER_EXECUTION_SOURCES_20261022.json): URL・確認日・読取深度・取得失敗を保存。第三者本文やprivate応募資料をGitへ複製しない。

Web全体の網羅や成功の保証はできない。今回の目的は、判断に必要な先例と制約を具体化し、残る不確実性に検査・担当・期限を割り当てること。source/実装に関する疑問と、顧客需要・人の便益・採否に関する未知は、異なる証拠で解く。
