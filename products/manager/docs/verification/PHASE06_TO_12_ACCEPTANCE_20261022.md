# Phase06–12: 原受入条件と実装・証拠の対応

**2026-10-23 現在の有限モデル研究追記:** [PRIVATE train27 SFT実結果](HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)は、実G0–G6/公式CI/config受入後の一attempt学習・単一adapter完全保存/独立検証を記録する。COMPLETED/ARTIFACT_FROZEN、27 backward下限、7 optimizer機会/7 return/global_step7、112finite FP32 tensors。runtime変化112と独立zero-B比の変化下限56を区別する。固定adapterの新規dev8/final16採点はNOT_RUN/G7未受入。全V002/V003はtodo、113件=83 done/20 todo/10 skipped・元依存と下記の歴史的実装/原受入条件は不変。行動変容・便益/一般化・live採用は未受入。

> **CURRENT 2026-10-22 ORDER — V2:** This document's older 54-step financial/indoor mapping is **歴史的な参照記録**であり、現行の実装順ではありません。**E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16** を `docs/roadmap/tasks.json` のカーソルに従って実装します。**F005 → F006 → F008 → F009** は実装の後に証拠で判定するPhase06の受け入れ条件です。F004/F007は `skipped`（未実施）、外部資金・施設操作は必須ルートから除外。P3/P4（人の便益）は `NOT_MEASURED`。Eの詳細は[実装計画](../plans/2026-10-22-manager-core-execution-plan.md)、改訂範囲は[Phase06 v2仕様](../specs/2026-10-22-phase06-owned-public-good-scope-amendment.md)。



**2026-10-22 JST、Manager completion branch の実装確認。** 判定の基準は [原 tasks.json](../roadmap/tasks.json)、[製品仕様](../MANAGER_PRODUCT_SPEC.md)、および [F004–F009 の54分解](../roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md)。この表は受入条件に対する証拠の説明であり、第二のタスク台帳ではない。状態更新は元の `tasks.json` だけで行う。

**現時点で実在する公開成果は、所有する案内ページと研究成果物の配信・読み戻しである。人への経済・身体・精神の改善は NOT_MEASURED。** インターネット上の所有資産に対する通常の技術運用と、旧来の資金介入・施設介入・任意の人への効果研究を分ける。後者の権限や被験者がなくても、既存の所有者権限内の通常運用まで停止する意味ではない。

## 1. 証拠索引

| 記号 | 確認対象 |
|---|---|
| A | [既存の公開6ページ・16 browser checks・外部コミット receipt](PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md)。P2_ARTIFACT_ONLY |
| B | [digital_handoff](../../manager_core/digital_handoff.py)、[kernel release/readback](../../scripts/phase06_kernel_release.py)、`test_digital_handoff.py` / `test_digital_publisher_integration.py` / `test_digital_proof_occurrence.py`。計画、別の公開経路 admission、同一 effect 再試行、元の occurrence、親コミット・実変更範囲・公開 bytes の照合 |
| C | [仕事・OutcomeBench・統治の実装記録](COMPLETION_ENGINEERING_OUTCOMES_20261022.md)。Source、既存 kernel/outbox/PolicyLearner/AuditTrail の再利用。独立認証・実測を自称しない P0 契約 |
| D | [物理測定と実 DoWhy 検証](PHYSICAL_AND_CAUSAL_PREPARATION_20261022.md)。同期・校正・同時対照・電力/騒音と、共通の既存因果分析アダプター |
| E | [研究・発信の受入証拠](COMPLETION_RESEARCH_READY_20261022.md)。D013、Y001、Y004、Y007 の成果物・一次出典・22枚のスライド検証 |
| F | [FIRST_STUDY](../../pilot/FIRST_STUDY.md)、[公表集計協働プロトコル](../../pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md)、[精神面の停止・独立審査](../../pilot/MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md)、[金銭結果の独立観測](INDEPENDENT_FINANCIAL_OUTCOME_PROTOCOL.md)、[第二経路の安全境界](../../pilot/SECOND_DIGITAL_ENVIRONMENT_SAFETY.md)。全て提案・準備 |
| G | [digital_experiment](../../manager_core/digital_experiment.py) と `test_digital_experiment.py`。既存 GrowthBook / SciPy の opt-in・固定割当・SRM 契約。架空単位に限定し、実験の live activation はない |
| H | [短い実行デモと再現手順](../demos/README.md)、[Proof Explorer 説明](../product/PROOF_EXPLORER.md)、[共通 digital 契約](../architecture/PHASE06_DIGITAL_CROSS_DOMAIN_CONTRACT.md) |
| I | [記事パッケージと公開記録](BLOG_PUBLICATION_20261022.md)、[統合実行記録](COMPLETION_EXECUTION_20261022.md)。ローカル package、remote CI、実際の公開読戻しを区別 |
| J | [プログラム資金・置換・受益報告の結合](PROGRAM_FUNDING_PREPARATION_20261022.md)。既存 CostCoverage / Source / spillover 算術を再利用。原資・返金・費用・同時期対照・報告を別保持する P0 契約 |

ファイル名が54分解の例示と異なっていても、既存実装で同じ契約を満たしていれば対応物として扱う。ファイルが存在するだけでは外部受入条件の達成にならない。

## 2. 原タスクの phase 別受入範囲

### Phase06 — F001–F009：**現行V2の受け入れ判定**（実装順はE01〜E16）

| ID | 実在する証拠・現状 | 残る受け入れ条件 |
|---|---|---|
| F001–F003 | 旧スコープで研究／準備として完了（`done`） | 人間の受益を実測したわけではない |
| F004 | 元は外部資金・第三者承認要求 | **`skipped`（未実施・対象外）**。歴史は `PHASE06_V1_SCOPE_ARCHIVE_20261022.json` に固定。先行実装も要求しない |
| F005 | 所有公開資産の6ページでP2_ARTIFACT_ONLY実績とreadbackが存在 | Eの検証に合格した実際のprovider occurrence・独立GET・再実行ゼロ書込みを受け入れ記録と照合して判定する |
| F006 | 元の実資金アウトカム設計は歴史的研究 | 新スコープではP1/P2技術的状態変化、NO_ACTION比較、費用・害の不明、P3/P4未測定を正確にレポートする |
| F007 | 元は設備所有者・室内センサー要求 | **`skipped`（未実施・対象外）**。室内制御・空気質改善は試験していない。F008の依存先ではない |
| F008 | 既存の精神・身体支援情報ページが存在 | 異なる所有公開ページの固有URL・内容SHA・独立GET・変更履歴・復元可能性の技術的証拠が必要 |
| F009 | 汎用カーネル、所有ページの公開経路、監査部品が存在 | **E01〜E16の後**、F005/F006/F008の証拠と2つの対象を同じkernel/readbackで検証し、P3/P4未測定を維持 |

### Phase07 — C001–C002

| 原 ID | 現在ある実装・証拠 | 原条件に残るもの |
|---|---|---|
| C001 | 既存の source/claim/method/limits 付き研究説明。done の範囲は維持 | 実際の発表・査読・人への効果を追加して主張しない |
| C002 | 原著の英語記事、日本語補助資料、図・スライド、公開パッケージ（E/I） | 原依存 F006 の実研究結果。今回の記事の明示承認はあるが、技術解説の公開で F006 を代替しない |

### Phase08 — U001–U008

| 原 ID | 現在ある実装・証拠 | 原条件に残るもの |
|---|---|---|
| U001 | 既存の三候補以上の機構・公開情報・権限・比較表 | 既存完了の範囲を維持 |
| U002 | 面談で確かめる問い・立場の整理 | **5件以上の実際の同意ある面談**と必要最小限の記録。合成回答で埋めない |
| U003 | [FIRST_WEDGE](../product/FIRST_WEDGE.md)：実行主体、結果、費用上限、代替案、放棄理由を具体化 | U002 と選定根拠。文書は PROVISIONAL、原タスクを完了にしない |
| U004 | FIRST_STUDY と SHA-256：対象案、単位、期間、主要指標、欠測、害、停止、分析（F） | U003、対象と独立実施主体の確定、実行前の外部検証可能な登録、同意・必要な審査。120世帯は提案値、実参加者0人 |
| U005 | 原 receipt/親・子 bundle/公開URLへ遡れる read-only Explorer 生成（B/H） | U003。新 release の Explorer を外部で閲覧できる証拠は、その release の I を参照。説明ページだけを人の結果と表示しない |
| U006–U007 | case・receipt・観測・費用/害・因果診断を分離する契約（B/C/D/F） | U004/F005/F006 に基づく実パイロットと、一次結果の純便益比較。所有 artifact の技術成果だけでは不足 |
| U008 | 運営費・事業収益と受益を分離する経済型（C） | 成果報告を見た実際の協力者の支払/支援または継続意思の出典。未確認収益は unknown、確認された未獲得だけ0 |

### Phase09 — D001–D016

| 原 ID | 現在ある実装・証拠 | 原条件・repo 内で残るもの |
|---|---|---|
| D001–D003 | program funding 専用型で外部寄付・Manager matching・スポンサー原資、決済/返金/費用、同時期の別 program の置換、別出典の受益報告を結合。unknown、負の差、二重計上・不一致拒否を検査（F/J） | repo 内の専用結合契約は実装済み。実資金・決済・受益・比較可能性の独立観測と F006 は未達。自己供給の出典・coverage は P0/NOT_VERIFIED |
| D004 | holdout・地域別 scope・再現 manifest の器（C） | 別地域/別案件での比較可能な実追試、D003/U007 |
| D005–D007 | 校正/単位/時刻/出典、無効・欠測除外、同時期の対照、電力/騒音/費用の分離と11件のテスト（D） | F008 と実測。差の差の**算術**は識別条件の実証ではない。実地設計に適した依存構造・測定間隔の分析が必要 |
| D008–D009 | proxy と human outcome の別スロット、健康 NOT_MEASURED、施設/人口 scope（C/D） | 実曝露証拠と実健康証拠、許可された複数施設の P2+、D007/U007 |
| D010 | `opportunity_outcomes` の募集・納品・承認・決済それぞれの公開可否と出典。R008 は既存 done（C） | **原「適法な公開情報アダプターの設計」の受入れを満たし、D010 を done に反映済み**。実求人取得、応募、受注、実入金を意味しない |
| D011–D012 | subject/group/artifact/currency/受領状態を照合。未決済は収入 NOT_VERIFIED。費用・労働時間・機会損失・機会数を別保持（C） | 実際の独立受領証拠、正当な比較と完全な原価/分母。名目報奨を収入にしない |
| D013 | 公開集計指標と妥当な尺度の出典・対象単位・妥当性・権利表（E） | **原文献対応表の受入れを満たし、D013 を done に反映済み**。個人測定は実施していない |
| D014–D015 | 役割・同意・匿名集計・訂正、過剰介入/誤評価/不確実性の停止と独立専門家評価の手順（F） | 実際の倫理判断、協力団体、公表可能な集計。自己任命の専門家・同意済み扱いをしない |
| D016 | 金融/身体/精神の証拠階層、指標・単位・費用・害・不明を別保持。共通改善スコアなし（C/D/F） | D015/D012/D009 の実結果と依存。別単位を比較表に置けても、その成果は未測定 |

### Phase10 — V001–V006

| 原 ID | 現在ある実装・証拠 | 原条件に残るもの |
|---|---|---|
| V001 | finance/environment/opportunity を**同じ OfflineFixtureAdapter と kernel**で実行。outbox の exact-class fence を保持（C） | 技術契約は実装済み。D016 が未達のため、原タスク全体の done とはしない |
| V002 | MAE/TVD、正当な合成参照がある場合のみ ATE error、P0–P4 スロット、harms を分離（C/D） | V001 と実世界の真正な読戻し・人の結果。自己供給の welfare packet を P4 にしない |
| V003 | train/holdout 非重複、国・所得層・領域・期間の exact scope、誤差 metric/unit、未知/OOD の停止（C） | 実未見人口の誤差、代表性・適用可能性の独立検証。宣言した scope だけで外挿しない |
| V004 | 既存 PolicyLearner の隔離/holdout/shadow、元 version への rollback、権限/予算/期限の拡張拒否（C） | 適法な限定実運用の評価。offline 昇格で本番の権限を作らない |
| V005 | source/hash/version 付き再現 manifest と公開集計の資料（B/C/F） | V004、各証拠に応じた公開権利、第三者が実際の P1–P4 を同じ結果に照合できる素材 |
| V006 | 正・負・null・unknown の保持、費用を通貨別に保持、効果の無条件合計を禁止（C） | 数十の実案件と完全性。フィクスチャ件数を受益・案件実績に数えない |

### Phase11 — Y001–Y008

| 原 ID | 現在ある実装・証拠 | 原条件に残るもの |
|---|---|---|
| Y001 | 顧客・受益者仮説と証拠レベルを示す英語1文、日本語補助。P002/R004 は既存 done（E） | **原草案受入れを満たし、Y001 を done に反映済み**。資金調達・需要・実受益の主張なし |
| Y002 | 22.96秒の動画、実 public GET の JSON、同じ candidate に NO_ACTION、外部書込み0件（H） | **Y001 の依存を確認し、原デモ受入れを満たす Y002 を done に反映済み**。動画は実行出力の可視化で、受益者や新しい介入の映像ではない |
| Y003 | pitch、デモ、スライドの準備（E/H） | 本人の申請内容・創業者情報/動画の確認と承認、適時の実提出、公式完了確認。採択は別結果 |
| Y004 | 13名の研究・公開活動・企業・公開コード・問いと一次出典。R002 done（E） | **原10名以上の source map 受入れを満たし、Y004 を done に反映済み**。連絡・私生活情報の収集なし |
| Y005 | 各研究者に学ぶ問いを作成（E） | 承認された実際の5件以上の接点、返信/未返信の記録。送信許可は今回の実装/記事承認から推定しない |
| Y006–Y007 | 既存の出典付き英語草案。研究室8/IACS8/YC6枚の英語 deck、22枚の日本語 notes、PPTX/PDF、出典と視覚検証（E） | Y006 の既存 done を維持。**Y007 は準備受入れを満たし、done に反映済み**。発表日時・実登壇は創作しない |
| Y008 | 著作権・出典・リンクを検査した公開 package、今回の記事公開の明示承認（I） | 原依存 C002/F006、実際の公開 URL/日時/訂正/フィードバック。dry run や GitHub PR だけを公開完了にしない |

### Phase12 — G001–G006

| 原 ID | 現在ある実装・証拠 | 原条件・repo 内で残るもの |
|---|---|---|
| G001 | charter/owner/grant/hash、appeal/stop、既存 AuthorityVerifier を使う [preflight](../../manager_core/governance.py)（C）と [公益憲章ドラフト](../governance/PUBLIC_INTEREST_CHARTER_DRAFT.md)。過去の engineering 証拠を保持 | `BOUNDED_SOURCE_DESIGN_ACCEPTED`（root実受入済み）。[限定設計receipt](G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)に実rootイベントを記録した。K007/V001 doneを実確認後、G001を受入済み。運営採択 `UNADOPTED`、実責任者の採択と停止/異議手続の運用は未成立、実外部監査 `NOT_PERFORMED`。通常の standing scope 内の実行に毎回の承認を追加しない |
| G002 | 既存 AuditTrail の無効・悪化・未知・害・異議・解決の保持（C）と [事故・異議・監査手順ドラフト](../governance/INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md)。過去の engineering 証拠を保持し、独立の有限宣言母集団との [ID/trace 照合契約](../../manager_core/governance.py)を設計対象とする | `BOUNDED_SOURCE_DESIGN_ACCEPTED`（root実受入済み）。[限定設計receipt](G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)に実rootイベントを記録した。V001→G001の実受入後、3badaの有限ID/trace欠落検知、既存1088 tests/skip5と独立code/doc reviewを根拠にG002設計を受入済み。90日後の実監査や人研究は原設計受入の前提ではない。運営採択 `UNADOPTED`、実担当・独立監査・保存/訂正/復旧の運用は未成立、実外部監査 `NOT_PERFORMED`。ローカル hash chain は改竄不可能な外部監査ではない |
| G003 | scope/coverage/不公平・未測定分野の inventory、未見 scope で NO_ACTION（C） | G002/V006、複数地域・人口での段階的実検証 |
| G004 | 接続相手・source・permission・budget・currency・responsibility の API 契約型（C） | G003、実相手の条件、承認された endpoint/schema/version の結合と公開。型が外部接続権限を付与しない |
| G005 | 運営原価・測定費・資金・支援と beneficiary portfolio を分離する経済型（C） | 実原価・資金の出典、持続性の検証、G004。会社収益と人の純便益を足さない |
| G006 | 未測定・不公平・失敗・次の課題を保持し、普遍的解消を拒む inventory（C） | G005 と継続した実観測・更新。有限の実験から「世界の苦しみを終えた」と結論しない |

## 3. 歴史的54分解の対応 — **V1参照用、現行実装順ではない**

以下の「準備」は実装・文書の存在を表す。原 F004–F009 の外部・科学条件達成や、原タスクの状態変更を表さない。

| 分解 ID | 対応する実装・資料 | 残る差分・証拠 |
|---|---|---|
| F004.E01 | 既存 surface inventory、A/B | 確認済みの owned route に限定。別サイトの deploy credential を仮定しない |
| F004.E02 | surface inventory、FIRST_WEDGE、F | 情報摩擦の機構は仮説。実需要は U002 |
| F004.E03 | 既存 `digital_environment.audit_sources`、公開案内の source audit | 名前違いの同等処理。公式先の変化時は再検証が必要 |
| F004.E04 | 既存 Playwright journey と A、[BASELINE_DIGITAL_JOURNEY](../product/BASELINE_DIGITAL_JOURNEY.md) | 6ページ・公式4先・keyboard/mobile/control 手順と実12枚の保存先を索引化。初公開前はページ自体がなく before 画像なし。実利用者の時間/成功率は未測定 |
| F004.E05 | provisional FIRST_WEDGE、A | bounded digital action は具体化。U003 の面談依存は別 |
| F004.E06 | 既存 authority/outbox、B | 所有経路の standing scope に限定。原 finance grant の代替ではない |
| F004.E07 | 54分解自体の明示的 amendment proposal | 適用されていない。元の acceptance を保存 |
| F004.E08 | `test_digital_handoff` / phase05 adversarial / publisher integration | forged/expired/revoked/widened/replay を検査。fixture token を live 権限にしない |
| F004.E09 | actual owned release evidence A、B、authority readiness | 元 finance permission packet は未成立。最新 remote admission は I で照合 |
| F005.E01 | GrowthBook 3.2.2 pin、既存512件の synthetic exercise、G | 実被験者の割当ではない |
| F005.E02 | INTERNET_FIRST_TRIAL_DESIGN、FIRST_STUDY、G | control は変更しない案内。実 cohort 未登録 |
| F005.E03 | 既存 `tests/e2e/environment.spec.cjs` と16 public checks（A） | accessibility の自動検査は実利用者の全体験を保証しない |
| F005.E04 | 公開されている6ページ（A） | 所有する説明・案内の変更。第三者申請/決済ではない |
| F005.E05 | 公開 source/destination を確認する browser journey（A） | 案内到達と公的申請完了は別 |
| F005.E06 | G の固定 opt-in/assignment/SRM/NO_ACTION 契約 | live route への実験 wiring、真正な同意/露出記録、実 cohort は未接続 |
| F005.E07 | A の実配信、B の安定 effect key・bounded publisher・rollback | B を通る最新 hosted run の実証は I。ローカル合格を新規配信と呼ばない |
| F005.E08 | 既存 public GET、B の親/子/実変更/served hash collector | 実読み戻しの timestamp・occurrence を保持 |
| F005.E09 | audit/outcome ladder、A/B/C、実 NO_ACTION demo H | negative/missing/unchanged を保持。P3/P4 未測定 |
| F006.E01 | FIRST_STUDY の JPY 純受給の主要結果案（F） | 実登録・対象・期間の確定が必要 |
| F006.E02 | welfare crosswalk、FIRST_STUDY の別尺度・時間（F） | 同一尺度/単位として合算しない |
| F006.E03 | 同意・対象・除外・撤回のプロトコル（F） | 実 cohort/同意0件。Manager に未公開個票を取らない |
| F006.E04 | FIRST_STUDY / protocol SHA-256、G の固定構成 | hash 作成は外部事前登録ではない。検出力・実日程・追跡は未確認 |
| F006.E05 | INDEPENDENT_FINANCIAL_OUTCOME_PROTOCOL（F） | 正式な outcome provider・実受領が必要 |
| F006.E06 | D の DoWhy 0.14 wrapper、実ライブラリ16件検証 | 推定・CI・placebo・overlap・感度を実装。個票の研究計画には設計適合する別分析が必要。真正な実結果はなし |
| F006.E07 | 金融結果プロトコル、CostCoverage、C/D の unknown 費用・害、J の専用 program funding/displacement/report join | 実測値・真正な決済・置換の把握が必要。限定した宣言上の収支を社会全体の純便益にしない |
| F006.E08 | 既存 welfare proof gate、C/D の独立した P レベル | technical/financial transfer を人への改善へ昇格しない |
| F006.E09 | 本表・A/C/D/F に未測定/不明を明記 | 実 primary causal result は未生成。結果がないため報告値を作らない |
| F007.E01 | 既存 scope proposal と原 blocked 条件 | 元の施設条件を変更していない |
| F007.E02 | 既存 mental/physical public pages、F の安全文書、[SECOND_DIGITAL_ENVIRONMENT](../product/SECOND_DIGITAL_ENVIRONMENT.md) | 摩擦機構・代替理由・control・権限・害を定義。同じ owned bundle/publisher の別テーマで、独立 cohort/channel はなし |
| F007.E03 | FIRST_WEDGE の代替案、F の誤紹介/圧力/アクセス害 | 第二経路の friction/counterfactual 索引は上記設計に接続 |
| F007.E04 | 静的な official-resource 案内の境界、browser checks（A/F） | Inspect AI/MentalHealthBench の対話エージェント評価を実行した証拠はない。静的検査で代称しない |
| F007.E05 | 既存 Playwright/axe と公開ページ検査（A） | 自動 WCAG scan を全利用者の適合認証にしない |
| F007.E06 | SECOND_DIGITAL_ENVIRONMENT_SAFETY、D014/D015 提案（F） | 実 consent/専門家役割は未成立 |
| F007.E07 | welfare crosswalk、D013 map（E） | 尺度の適法な実施と実観測は別。制限された質問項目を転載しない |
| F007.E08 | 共通 owned publisher と G の経路別構成 | 同じ publisher のページ群。独立した第二 cohort/channel の権限・revocation が実証されたとしない |
| F007.E09 | A/F と [第二経路の証拠境界](PHASE06_SECOND_DOMAIN_BOUNDARY.md) | 通常の owned digital 運用に施設/NPO は不要だが、人への効果・独立 cohort・元の施設条件は未達。原 acceptance を保持 |
| F008.E01 | 既存 mental/physical browser journey（A）、[baseline 索引](../product/BASELINE_DIGITAL_JOURNEY.md)、[第二経路設計](../product/SECOND_DIGITAL_ENVIRONMENT.md) | 過去の公開済み版を次変更の baseline にできる。実 artifact の日時/commit を明示し、初公開前の画像や人の測定を創作しない |
| F008.E02 | 既存公開 browser tests（A） | mobile/keyboard/focus の technical 検査。人の臨床 outcome ではない |
| F008.E03 | 実在の mental/physical pages（A） | 変更対象は owned public artifact |
| F008.E04 | G の既存 GrowthBook/SciPy 契約 | live site 配線、真正な exposure/assignment/consent/SRM の運用は未実装 |
| F008.E05 | 全6ページを読む既存 collector、B | 同じ release bundle の別ページ。別の人の試験を実施した証拠ではない |
| F008.E06 | 任意の尺度・倫理・公表集計・停止プロトコル（F） | 実施権利、同意、独立測定、追跡 |
| F008.E07 | D015 停止定義（F）、[第二経路 outcome 報告](PHASE06_SECOND_DOMAIN_OUTCOMES.md)、[領域横断の未測定報告](PHASE06_CROSS_DOMAIN_FIELD_CAUSAL.md) | actual outcome n/effect/CI は null、登録参加者0人、費用 UNKNOWN・害 UNKNOWN_HARMS。負の outcome/非回答も未測定で、ゼロ扱いしない |
| F008.E08 | D の同一 DoWhy 契約 | 身体/精神でも technical proxy を臨床 outcome にしない。適合する設計と真正な結果待ち |
| F008.E09 | A/F と本表の P2 artifact / human NOT_MEASURED | 元の物理 F008 は未達。第二経路の独立した実効果報告はなし |
| F009.E01 | 共通 digital contract と B/H | 分野別の安全迂回なし |
| F009.E02 | 既存 kernel/outbox adversarial、B/C の三領域契約 | at-most-once の境界。別の二つの実 field executor を実証したとはしない |
| F009.E03 | 別テーマの実公開ページを exact hash で読戻し（A/B） | 同じ公開 bundle の technical P2。二領域の実受益は未観測 |
| F009.E04 | welfare crosswalk、C の非合算 portfolio | 通貨/PM2.5/尺度のまま保持 |
| F009.E05 | B/H の read-only proof explorer | U003 依存は未解消。公開は I の実 occurrence と結合 |
| F009.E06 | C の既存 PolicyLearner/holdout/shadow/rollback tests | 実権限・予算の自己拡張なし。実 field learner への昇格は別 |
| F009.E07 | D/F の分析・費用・害の契約 | 両実人口の真正な比較結果と独立評価がないため未実施 |
| F009.E08 | A/C/D/I の技術・負・不明の記録 | 実 causal cross-domain report として公表できるデータはない |
| F009.E09 | 原条件と依存を照合する本表 | 状態・生成 view・exact source CI の統合は唯一の ledger 所有レーンが担当 |

## 4. 残作業を混同しない

| 区分 | 具体的な残作業 | 境界 |
|---|---|---|
| repo 内で追加できる限定的な工程 | [統治憲章](../governance/PUBLIC_INTEREST_CHARTER_DRAFT.md)・[監査手順](../governance/INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md)の未採択ドラフトは追加済み。実 source/endpoint 確定後の provider-specific ingestion・public export は別工程。D001–D003 の専用結合契約は J で追加済み | 文書や汎用型の存在を実採択・全 engineering 完了と呼ばない。対象 format/役割が不明な部分を架空の本番接続として実装しない |
| 設計と実条件を決めれば実装できる工程 | GrowthBook の実 owned route wiring、独立側の同意・assignment/露出の真正性を扱う実装、欠測・クラスター構造に適合する既存推定法、実地の電力積算・騒音時間指標の parser | 現コードは inert/synthetic または supplied-data analysis に限定。参加者実験を勝手に開始しない |
| 実 evidence が不可欠な条件 | U002 面談、U004 登録/同意、D011 受領、D014 協働/倫理、実 outcome/害/追試、V006 数十案件、Y003 提出、Y005 接点、継続需要 | コード、文章、合成人数、URL/hash、自分で書いた approval では置き換えられない |
| 運用の続き | 訂正・事故・異議への対応、資料の更新、別地域の coverage、利用や支援の実証 | 一度の pull request で永続完了とはしない |

**D010、D013、Y001、Y002、Y004、Y007 は依存状態と実成果物を照合し、原受入れを満たすため sole ledger を done に更新済み。** 現行台帳は69 done / 41 todo / 0 blocked / 3 skipped（H005の科学的skipとF004/F007のretired track）です。F004資金/F007施設は初回digital releaseの必須条件ではなく、別途その研究を実施する場合にだけ実権限が必要です。残りの準備を「無価値」とはしないが、元の field/science 条件の完了には数えない。

## 5. この照合に使った検証

- 既存 outcomes/governance レーンは先行検証で383 tests passed。現在の全体総数を表す値ではない。
- 新規 physical は **11 RED → 11 GREEN**。新規 causal は **15 RED → 15 GREEN** に加え、数値警告の回帰 **1 RED → GREEN**。実 DoWhy 付き最終 **16 tests passed / 0 skips**。詳細は D。
- 新規2モジュールの独立した限定 read-only 確認は **0 findings / 0 blocking**。追加の承認ゲートを作っていない。
- D001–D003 の追加 join は **12 RED → 12 GREEN**。既存 economic_scorecard / opportunity_outcomes を含む限定実行は **36 tests passed / 0 skips**。詳細は J。
- この照合中の shared 全体実行は **450 tests、1 failure、5 skips**。唯一の失敗は `test_r006_rights...test_task_is_done_and_generator_non_destructive` が検知した **BACKLOG VIEW OUT OF SYNC**。同時進行の sole ledger/generator 統合レーンへ報告済み。5 skip は通常環境にない optional DoWhy の実ライブラリ検証で、上記16件では実行済み。統合後の最新結果は I が authoritative。

本表は source guard、workflow、tasks.json、仕様、既存コードを変更しない。Life Manager の runtime、DB、credentials、個人データ、運用権限を借用しない。過去の scientific skipped を成功に読み替えない。

最終ローカル統合検証では、実 DoWhy/GrowthBook 依存を含む **462 tests、0 failures/errors/skips** が成功した。上記450件の途中結果にあった生成ビューの不一致は原台帳からの再生成と `make_roadmap.py --check` で解消済み。公開・hosted CI の最終結果は I と対応 PR の証拠記録を参照する。


最新の全工程/原41件の依存/旧EBA章との対応は [START_TO_END](../roadmap/START_TO_END_20261022.md) を参照。上の実験件数はそれぞれの履歴runであり、現在の全体test数や新しい実効果を示さない。
