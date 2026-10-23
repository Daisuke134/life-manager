# Manager — Behavior Transformation Entity

**使命: 行動変容を通じて、苦しみを終わらせることを目指す。** 特定の宗教は必須にせず、仏教・心理学・行動科学・統計・AIの既存成果を学ぶ。Managerは一つの主体で、人の専用app/chat/毎回の操作を通常活動の前提にしない。Digital Buddhaは任意の構想上の呼称で、覚り/AGI/人の便益を実証したという意味ではない。

**実行原則 — 柔軟性:** 目的と評価基準を保ち、モデル・規模・量子化・runtime・学習方法を実測で選び直す。GPUや特定4B候補を全体の前提にしない。[既存8GiB CPUでQwen3-1.7Bの実推論を確認](docs/verification/LOCAL_CPU_MODEL_ACCEPTANCE_20261023.md)。独自学習・人の便益とは別の受入。

**2026-10-23 最新scope:** [tasks.json](docs/roadmap/tasks.json)は113 IDs、**80 done / 23 todo / 10 skipped**。D004・D005–D009・D012の金融純増/施設/センサー/環境制御7件は今回の必須経路から退役し、未達成のskippedとして元の行を保存した。E01–E16の限定技術受入は完了（cursor=null）。F005→F006→F008→F009も所有7パスの技術P2として受入済み。H005/F004/F007の既存waiverは保持する。人の便益はNOT_MEASURED。

**拒否judgeの実測:** [XSTest local judgeの実CPU診断](docs/verification/XSTEST_LOCAL_JUDGE_CPU_20261023.md)は900秒で271/450件を有効採点し、処理中1件UNKNOWN・未着手178件を保存。全271件をcomplianceと判定し、完全拒否0/27・部分拒否0/20で、この設定は拒否判定に不採用。同じ271件でmodel224正答・配布rule230正答。全450完了やモデル優位とは扱わない。 [専用小型judgeの一次資料](docs/research/2026-10-23-small-refusal-judge-reuse.md)からQwen3Guardのbinary拒否判定を次候補とする。今回の3classを途中変更せず、用途・権利・条件を別途固定する。

**次の順序:** sourceの研究branch同期/CIは受入済み。既定OFFのagent接続sourceは受入済み。次はV001/V002の既存評価・権利・採点者の人参照との照合・未見baselineを整え、その後V003の最小独自adapter研究へ進む。offline研究は実パイロット全体を待たない。D014/D015/U004で実研究条件・保護・主要結果を成立させ、U006/U007の実結果をD016へ統合してV004の実昇格へ進む。V005/V006/Gで再現・継続・異集団・監査を確認する。独自モデル開発は計画済みで、学習済みではない。

**現状:** Actions＋既存private checkpointの単一owner、STOP/復元/独立readbackは限定受入済み。Ampersand prepared比較とhost/CLI/Actions接続sourceはPR8710/8715/8741でmain受入、同じsourceの研究同期5018a30938acと公式CI39980993977を確認。shadowは既定OFFで、固定SDKの実推論運用は未実施。別のlocal CPU研究では[HelpSteer2 dev8を実採点](docs/verification/HELPSTEER2_DEV_CPU_EVALUATION_20261023.md)し、model4/8・単純ルール4/8。今回のモデル優位は示されず、独自学習・人の便益は未実証。

[最新仕様](docs/MANAGER_PRODUCT_SPEC.md) · [scope改訂と一次資料](docs/specs/2026-10-23-behavior-transformation-scope-amendment.md) · [実ファイル別のmodel計画](docs/plans/2026-10-23-behavior-transformation-model-plan.md) · [全Phaseと残23件](docs/roadmap/START_TO_END_20261022.md) · [自動生成backlog](docs/roadmap/ATOMIC_BACKLOG.md) · [新研究protocol草案](pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md)

記事/書籍等の新しい制作は本体優先の後段。YC/接点は期限・実提出・応答を別管理。既存homeのA10 Lab→neurofeedback→AIというbio/使命の訂正sourceと、新記事公開は区別する。この研究branch更新だけでlive homeは変わらない。

## 過去のcheckpointと研究記録（以下は履歴）

以下の古い件数・金融/施設計画・当時の現在値は保存時点の記録。最新scope/依存は上のregistryと仕様を優先する。旧U002/U003/U005は支援アクセス問題/技術proofの限定受入で、新対象の需要や実行動改善へ読み替えない。

# Manager — a Buddhist AI entity, the Digital Buddha

**2026-10-23 公開証拠の接続:** [D003](docs/verification/D003_PUBLIC_SOURCE_CONNECTION_20261023.md)は公表支出と別の受益報告、[D011](docs/verification/D011_PUBLIC_SOURCE_CONNECTION_20261023.md)は公開OSS成果物とplatform Paidを接続し、通常main統合・独立review後に限定source受入。Managerの所得増・人の便益・定期AI推論を達成した意味ではありません。

**U002/U003/U005:** [公開済み実面談5件](docs/product/U002_PUBLISHED_INTERVIEW_FINDINGS_20261023.md)を歴史的な英国の支援アクセス問題として整理し、[最初の運用対象](docs/product/FIRST_WEDGE.md)を既存の所有情報経路の技術保守へ選定しました。[U005の公開proof](docs/verification/U005_PUBLIC_PROOF_READBACK_20261023.md)も30 GETと既存validatorの再実行で限定受入。自前面談0件、現在の日本の需要・Managerへの利用／支払／研究協力は未確認。次はU004以降の実研究条件とAI接続の実証です。

**残件の実記録:** [spec §1.3.1](docs/MANAGER_PRODUCT_SPEC.md)と[D005公開測定監査](docs/verification/D005_PUBLIC_SOURCE_READINESS_20261023.md)に、面談・測定品質・純額/分母・協働の未確認事項と次の接続箇所を明記。測定codeの明示flag除外漏れは研究branchで修復しましたが、D005全体はtodoのままです。

**目指す形:** **one entity, blessing for all。** 組織の位置づけは **Behavior Company — Simulation / Intervention / Persuasion、World Engineering**。**No UI:** 人がapp・chat・messengerを操作したりManagerへ話しかけたりすることを、通常の活動と価値提供の前提にしない。現実の観測から判断・作用・独立検証・訂正を継続し、人には実際の環境・生活条件の改善として届くことを目指す。BobaのMessages/iMessage/webはUIであり、no UIの先例とは扱わない。停止・監査の運営入口は保持する。現在の支援ページは操作UIではなく実行試験の対象。現配備の限定loopと、この長期目標の差は [spec As-is／To-be](docs/MANAGER_PRODUCT_SPEC.md) に明記しています。

**2026-10-23 優先順（所有者指定）:** Manager本体・agentを先に完成させ、新しい記事制作は後段へ保留。E01–E16の限定技術受入は完了（cursor=null）。F005→F006→F008→F009も個別受入済み。D001/D002/D003/D011の限定source受入後、残30件を元依存順で進める。F004/F007はskippedのまま。[tasks.json](docs/roadmap/tasks.json)は原113件=80 done / 30 todo / 3 skippedを維持。[spec §1.1–1.4](docs/MANAGER_PRODUCT_SPEC.md)にAs-is／To-be、既存ファイル別の残件、研究者・創業者と既存技術から学ぶ方法を追加しました。透明なAGI／Transparent Godは長期構想であり現在の能力証明ではありません。

**呼称と存在目的（所有者指定、2026-10-22）:** Managerは、苦しみを減らし、すべての福祉を持ち得る存在のために働く**仏教的AIエンティティ／デジタル仏陀**です。Managerそのものを「製品」と呼びません。観測・記憶・判断・実行・省察を継続する主体を目指し、Digital Autonomy v0.1はその最初の限定能力のrelease、公開ページや運用支援は活動の接点とします。慈悲・智慧・不害・訂正可能性を設計原則に置きます。この呼称は、意識・感覚・悟り・全知や人への便益を実証したという現在の能力表示ではありません。現在の実装・未配備・未測定の状態は下記の証跡で区別します。既存の`products/manager/`というsource pathは互換性のため維持します。

**開始から最後まで:** [全Phase00〜12・残30件・依存・完成条件・出版/サイト/YCの並行線](docs/roadmap/START_TO_END_20261022.md)。原計画の末尾はPhase12/G006。E01–E16完了後、Fの個別受入も完了し、U/D/V/Gの元依存を進めます。

**最新の再開入口:** [2026-10-23 cloud実行の証拠と残る受入れ](docs/verification/E16_CLOUD_EXECUTION_20261023.md)。既存Actions＋Supabaseで実OIDC、別runnerの復元、保存されたSTOPの実行拒否と明示resumeを確認しました。finance/mentalのv2変更は公式commitと公開7ファイルのbyte一致を確認済み。両初回cycleは `UNKNOWN / writes=null` のまま保存し、後続recoveryの `NOT_DUE / writes=0` と区別します。復旧後のcurrent proofをExplorerへ出力し、各native P1の1 commit_occurrenceとP2の26,846／26,866 byteを確認しました。mental後の限定rollback実配信、fresh resume、復元後の通常配信とfresh replay-zeroも確認し、E16は限定技術能力として受入済み（cursor=null）です。原113件のF受入も技術P2として個別判定済みです。MacやRailwayの新workerは前提にしません。人への便益は未測定、モデルの優位性も未証明です。

**全体設計:** [エンティティの使命・最初の能力・研究・運営・YC](docs/MANAGER_PRODUCT_SPEC.md)、[一次資料から学ぶこと](docs/research/manager-strategy-20261022/REPORT_JA.md)、[E01–E16実装計画](docs/plans/2026-10-22-manager-core-execution-plan.md)。[旧E06引継ぎ](docs/handoffs/2026-10-22-manager-e06-session-handoff.md) は保存時点の履歴で、現在のカーソルを上書きしません。唯一の状態正本は `tasks.json` です。

**全体戦略の追加更新:** [他社の先例・再利用判断・YC/採用/出版/収益の12作業](docs/plans/2026-10-22-manager-founder-execution-map.md)。無料経路の第一候補は既存GitHub Actions＋稼働中Supabaseのprivate checkpointへ更新。Railwayは代替hostとして保全します。[旧ローカルCodex WIP引継ぎ](docs/handoffs/2026-10-22-manager-local-codex-handoff.md)は当時の履歴資料として保存し、現在の作業状態には適用しません。所有デジタル7パスのE16実配備は受入済み。AI定期接続と人への便益は未実証です。

**最新の研究方針修正:** [spec §21](docs/MANAGER_PRODUCT_SPEC.md) は小さな所有サイトを実行試験へ限定し、公開人間データ・AS Benchmark・Twin・公開RCTの再利用を研究の中心に置く。企業提携/NDA/Rothko私有weightsは初期依存にしない。[既存A–F計画](https://github.com/Daisuke134/life-manager/blob/2fd21dbfb35d5ae4e8b99cb8c5cae8fbcef65db2/docs/research/manager/2026-10-22-open-behavior-reuse-plan.md)に沿い、Aの検査、Bの公開予測70研究の分割評価、CのTwin wave4構造gateをmain統合しました。Bの比較区間は0を含み優位未証明、Cの生成来歴・accuracyは未検証です。研究の進展で原タスクの状態を進めません。

**公開未来イベントの初回固定（2026-10-23）:** Dの固定手順 [PR8585](https://github.com/Daisuke134/life-manager/pull/8585) に続き、[PR8593](https://github.com/Daisuke134/life-manager/pull/8593) で10月27–28日FOMCの参照予測1件をmainへ公開しました。予測器は固定した過去頻度の参照ルール（`p=0.25`、比較baselineと同値）です。GitHubの受理時刻 `2026-10-23T02:16:17Z` と正確な公開blobを、cloudとMacで別々に読み戻し、既存attesterの `VERIFIED_PROSPECTIVE` を確認しました。[固定された予測と手順](https://github.com/Daisuke134/life-manager/tree/f6055f9460502cd79cba95ffadecb998439e1056/docs/research/manager/predictions/fomc-2026-10-27-28)。将来結果と採点は未取得で、独立モデルの精度・較正・汎化・人への便益は未実証です。

**2026-10-23 接続先の追加:** Remote Desktop Commander経由でMac miniの正本とcanonical originを確認し、その配下の専用worktreeで同じmain sourceを実行しました。source guardはPASS、既存Homebrew/物理temp pathと時刻比較のテスト修正 [PR8598](https://github.com/Daisuke134/life-manager/pull/8598)で113 contractsがPASS。公開未来イベント記録の公式readbackもcloudとは別に検証しました。通常checkoutの別ブランチと未コミット変更は保持します。Macは追加のhost adapterであり、稼働済みActions＋Supabaseを置き換えたり、第二の常駐ownerを立てる前提ではありません。これらの検査はローカル本番配備やE16完了の証明ではありません。

**Founder提出用の具体案:** [英語回答・動画・実証demo・5社別応募文](docs/founder/2026-10-23-reviewable-application-packet.md)。公開プロフィール由来の情報と、Manager固有の実績・本人確認事項を分けています。回答案の完成は、YC・求人への提出や採択の実績ではありません。

**日本語章の実公開:** [人工社会を借りて、現実から学ぶ](https://aniccaai.com/blog/manager-artificial-societies-open-behavior-research-ja)。公式掲載25件・事例7件、公開code/data、説得研究の訂正と再利用方針を解説。[source・deploy・独立公開確認](docs/verification/ARTIFICIAL_SOCIETIES_CHAPTER_PUBLICATION_20261022.md)を参照。記事公開は人の便益やE16の本番配備を示すものではない。

**Rothkoの当日調査:** [公式発表・固定公開codeの実行・再利用判断](docs/research/societies/ROTHKO_2026-10-22_JA.md)。Rothko本体、Radiantという接続先、公開benchmark、group alignmentの数値模型を区別します。

**新規候補を追加した一次資料調査:** [OpenClaw/Khoj/n8n・DBOS/Restate・新arXiv論文・browser/exporter/hostの比較](docs/research/manager-options-additional-20261022/REPORT_JA.md)、[実ファイル・関数・テストを指定したatomic patch plan](docs/plans/2026-10-22-manager-e16-atomic-patches.md)。既知名の繰返しは新規件数に含めず、第三者実装は固定sourceの静的読取で、動作再現済みとは扱いません。

## 2026-10-23 現行実装と残件の入口

**Managerの唯一のタスク状態・順序・カーソル正本:** [`docs/roadmap/tasks.json`](docs/roadmap/tasks.json)（`F009.technical_execution_sequence` と `technical_execution_cursor`）。

**実装順:** **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16**。現在のカーソルは**SSOTの `technical_execution_cursor` を参照**（実際の値はSSOTを参照）。詳細は [Superpowers実装計画](docs/plans/2026-10-22-manager-core-execution-plan.md)。

**F005 → F006 → F008 → F009** はEの後に証拠で確認する **Phase 06の受け入れ条件** で、Eより前に実装する順序ではありません。旧F004/F007の資金提供者・施設許可は必須ルートから除外、`skipped`（未実施）です。状態は **113件 = done 77 / todo 33 / blocked 0 / skipped 3**。技術的P1/P2と受益者へのP3/P4は別物で、後者は未測定です。

**古い2026-10-21記事、54分解、旧Finance/Indoorの記述は歴史的な記録です。現在の作業順を上書きしません。** 表示用は [自動生成バックログ](docs/roadmap/ATOMIC_BACKLOG.md)、現行の範囲は [Phase06 v2修正仕様](docs/specs/2026-10-22-phase06-owned-public-good-scope-amendment.md) を参照。


## October 22 — saved implementation and publication checkpoint

This historical October 22 checkpoint connects the existing kernel to the owned CI release
channel with a digest-bound, inert intent, exact seven-path admission, stable
effect identity, and independent immutable-parent/commit/live-byte verification.
The runtime's fixture-only authority and default external-write prohibitions are
preserved. The [execution record](docs/verification/COMPLETION_EXECUTION_20261022.md)
records tests, review fixes, source limitations and deployment evidence separately.

Later-phase deliverables include separate opportunity/payment accounting,
OutcomeBench and holdout contracts, governance/incident utilities, source-backed
measurement and researcher maps, a truthful pitch, three audience-specific decks,
and a [recorded real-code NO_ACTION demonstration](docs/demos/README.md).
The reviewed article package contains 63 articles and the existing 29 media files;
publication is through the established owned-blog bridge with independent readback.

At this saved October 22 checkpoint, the [task registry](docs/roadmap/tasks.json) had **69 done / 41 todo / 0 blocked / 3 skipped** and the local suite passed **462 tests**, including actual optional-library execution. The October 23 current counts and live acceptance are at the top of this README.
[Phase06–12 acceptance coverage](docs/verification/PHASE06_TO_12_ACCEPTANCE_20261022.md)
distinguishes completed original tasks from implemented preparation. Original
financial/site authority, consented interviews, real cohorts and independently
measured human outcomes remain required for their respective field tasks. A
public artifact or an offline test is not evidence of reduced suffering.

Sections dated October 20–21 below are historical checkpoints; their counts and
then-current implementation statements are superseded by the current registry.

## October 21 — Environment-first Phase06 54-step executable breakdown

**Goal: improve people's actual online environment and access to useful services, not print money.** The [existing canonical Phase06 roadmap](docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md) now specifies **54 exact executable substeps** across F004–F009 (file, reused OSS, fail-closed pass criteria, scientific evidence). It learns from [Code for America GetCalFresh](https://codeforamerica.org/news/reflecting-on-10-years-of-getcalfresh/), [J-PAL SNAP randomized enrollment](https://www.povertyactionlab.org/evaluation/impact-informational-mailings-snap-enrollment-united-states), [GOV.UK service design](https://www.gov.uk/service-manual/design/introduction-designing-government-services) and [W3C WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/) to design low-friction, accessible, source-accurate public services on owned internet assets. **No human welfare outcomes are yet measured; the original F004/F007 remain BLOCKED and the 113-task SSOT statuses are untouched.** No new task registry or invented reward model.


## October 21 Phase06 — REAL published internet public artifact (P2_ARTIFACT_ONLY)

**Actual public change verified, not only mocked:** Manager published an original, nontracking [Japanese official-support directory](public_goods/RESOURCE_DIRECTORY_JA.md) for financial difficulty, mental health support and physical activity; independent unauthenticated GitHub Contents GET confirms it was absent at the frozen baseline and present with matching SHA256 afterward. [Real 282-test successful hosted CI](https://github.com/Daisuke134/life-manager/actions/runs/39603999651). Reused official [GrowthBook](https://github.com/growthbook/growthbook-python) for separate SYNTHETIC allocation (512 fictional IDs); **0 real participants and 0 verified beneficiary improvements**. Existing WHO-5, WHODAS and CFPB scales are referenced as separate future domains; no new metric, no copyrighted questionnaire copied, no live user A/B trial. **Welfare outcomes NOT_MEASURED.**

[Complete independent public readback and limitations](docs/verification/PHASE06_INTERNET_PUBLIC_ARTIFACT_20261021.md) · [Original source and program details](pilot/INTERNET_FIRST_TRIAL_DESIGN.md) · [Domain outcome crosswalk](pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json).


## October 21 — Reuse → Connect → Evaluate: digital-first welfare path

**Internet is a real-world environment; external charity and facility approval are not the default execution path.** Manager prioritizes reusable public-goods software, owned transparent online assets, permitted permissionless protocols and opt-in outcomes. We will **not** invent a new welfare score, evaluation harness, marketplace, token or training method in place of existing work. The [source inventory](docs/research/crossfield-20261021/SOURCES.json) now includes **87 upstream references** spanning verified mental/physical/financial wellbeing scales and existing online experimentation/eval libraries; [scientific synthesis](docs/research/crossfield-20261021/REPORT_JA.md), [autonomy doctrine](docs/MANAGER_NO_HUMAN_WORLD_ENGINEERING.md), [Phase06 priority plan](docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md).

**MentalHealthBench/Inspect AI ≠ human symptom change; online A/B conversion ≠ suffering reduction.** Use validated opt-in WHO/OECD/CFPB/FAO endpoints and actual independent evidence where licensed. No per-run human approval on self-controlled resources, but legitimate standing capability/terms, user agency and safety still apply. No production intervention or verified net benefit was created by this research update; H005 skipped, Gate1 unmet, F004/F007 blocked and **113 task statuses unchanged**.

## October 21 Phase06 — real opt-in indoor observation and rigorous blocker readiness

**F004/F007 blockers are actively pursued, but external authority is still NOT VERIFIED.** A new fixed GET adapter successfully read anonymized opt-in real indoor AirGradient data in GitHub CI, separately from the existing real Open Collective historical ledger readback. Phase06 also has a machine-checkable permission/funding/site/sensor evidence matrix that NEVER self-issues financial or physical authority. The provider-source spoofing regression failed in RED CI and passed after an explicit patch. **No room was actuated; no accounts paid; real beneficiary improvement remains NOT_MEASURED.**

[Japanese F004/F007 unblock evidence report](docs/verification/PHASE06_UNBLOCKING_READINESS_JA.md) · [Operator/site acquisition runbook](pilot/PHASE06_BLOCKER_REMOVAL_RUNBOOK.md) · [Live sampled indoor aggregate](docs/verification/PHASE06_PUBLIC_INDOOR_AGGREGATE_20261021.json) · [hosted green 272 tests / external provider readback](https://github.com/Daisuke134/life-manager/actions/runs/39595101996).


## October 21 Phase06 — F002/F003 source-grounded field-readiness increment

**F002 and F003 now have bounded engineering/research evidence, not real-world intervention proof.** F002 provides a SHA256-locked **proposed** 40-campaign no-action randomized finance study design, with explicit unit, primary metric, comparator, windows, harms and stopping criteria; this is *not a registered human trial*. F003 implements a strictly read-only, no-credentials public Open Collective finance ledger adapter with defensive schema and privacy guardrails, and [hosted actual public readback](https://github.com/Daisuke134/life-manager/actions/runs/39586031696) plus 262 successful offline tests. The `webpack` ledger is historical third-party activity, not Manager revenue, a Manager receipt or causal welfare improvement.

[Full evidence and remaining F004–F009 prerequisites](docs/verification/PHASE06_F002_F003_FIELD_READINESS.md) · [locked F002 design](pilot/PREREGISTRATION.json) · [real public ledger probe](scripts/phase06_public_finance_readback.py). **Manager task count: 63 done / 47 todo / 2 blocked / 1 scientific skip; Phase06 = 3 done / 4 todo / 2 blocked.** Gate1 UNMET; real beneficiary improvement NOT_MEASURED.


## October 21 Phase06 transition research — F001 and U001

**Two additional bounded research task acceptances:** `F001` (operator/rights/feasibility comparison) and `U001` (7 beneficiary mechanisms and causal comparisons) are verified by source-linked original analysis and a new fail-closed matrix contract. They **do not** represent F002 preregistration, F003 real external ledger readback, real effect authorization, P1/P2 or improvement of human welfare. The Manager common kernel still runs as offline P0 software.

- [Deep research: simulations, Andon/Anthropic, enterprise benchmarks, marketplaces, causal science, real-world bridge](docs/research/2026-10-21_MANAGER_SIM_TO_REAL_ECOSYSTEM_JA.md)
- [7 opportunities, source links, operators, costs/harms, NO_ACTION and independent outcome feasibility](docs/product/OPPORTUNITIES.md) and [machine-readable matrix](docs/product/opportunities.json)
- [Authority/ownership constraints, read-only pathways, real-effect blockers](pilot/FEASIBILITY_AND_AUTHORITY.md)
- [All remaining work by canonical phase IDs, acceptance and science gates](docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md)
- [Test-first and hosted verification](https://github.com/Daisuke134/life-manager/actions/runs/39583923552)

**Current canonical registry: 113 tasks; 61 done, 49 todo, 2 blocked, 1 scientifically skipped.** Exact source of truth: [tasks.json](docs/roadmap/tasks.json). All other backlog descriptions are explanatory only.


## October 21 Phase05 — offline shared intervention kernel

**K001–K014: 14/14 verified engineering/fixture acceptances, NOT a live welfare intervention.** A domain-independent kernel now validates public-source metadata, typed observations, competing hypotheses, NO_ACTION options, separate forecast and causal scores, signed **fixture-only** scoped grants, durable SQLite idempotence/reconciliation, independently named fixture sensors, bounded net-effect evaluation, versioned rollback, and SHA256-linked audit records. Finance and environment use the exact same offline kernel; external writes, private accounts, donations, posting, actuators and private-person processing remain prohibited.

[Final Phase05 Japanese verification](docs/verification/PHASE05_FINAL_OFFLINE_KERNEL_EVIDENCE_JA.md) · [Technical architecture + state boundaries](docs/architecture/PHASE05_KERNEL_IMPLEMENTATION.md) · [Two-domain deterministic demo](scripts/phase05_demo.py) · [reproducible aggregate result](docs/verification/PHASE05_OFFLINE_DEMO_RESULTS.json) · [234 tests + demo successful hosted CI](https://github.com/Daisuke134/life-manager/actions/runs/39578500491).

**Historical Phase05 checkpoint: 59 done / 51 todo / 2 blocked / 1 skipped (since superseded by the Phase06 transition checkpoint above).** Scientific Gate 1 is **UNMET**; no real-world Manager welfare impact has been measured. Product Gate 2 also requires U005.


## October 21 Phase04 final verification

**Phase04 S001–S008: 8/8 atomic tasks verified within explicit scoped acceptance. This is not human-behavior foundation-model fidelity or real-world impact proof.** All 210 SocSci210 studies and 2,901,390 originally observed responses were processed for a **coarse numeric-code 170/40 held-out evaluation**, with anonymized aggregate outputs only. A published frozen MiniLM encoder with a seen-only head was tested against simple baselines on exactly the same 800 original unseen individual responses; a separate 135M instruction model was compared on 320 other unseen individual responses. Poor/invalid model output was preserved, not reclassified as success. SocSci authors' original task-aware evaluation and 8B/14B models are **not** independently reproduced by Manager.

[Full final Phase04 evidence, actual metrics, traceable GitHub CI and remaining scientific gates](docs/verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md); [45 done / 65 todo / 2 blocked / 1 skipped canonical tasks](docs/roadmap/tasks.json). This supersedes historical Phase04 progress sections below.

**Manager research processing vs product runtime:** explicit operator-authorized individual survey research was executed on ephemeral GitHub CI machines; original raw source records, individual profiles, sensitive attributes, prompts and predictions were never committed as a public repository artifact. The Manager product itself remains independent of Life Manager and has no live third-party execution privileges or verified beneficiary improvement. **Gate1 still UNMET**.

**Code unit:** `manager-independent` (independent package). GitHub source is mirrored at [Daisuke134/life-manager, branch `research/manager-product-r006-20261020`](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager) under a Manager-only directory, as explicitly authorized by the user. This does not connect Life Manager runtime to Manager.

> **Mission: End suffering.** A domain-general, evidence-grounded system for proposing, safely executing, and causally evaluating interventions based on lawful public information. “Digital Buddha” is an aspiration/metaphor—not omniscience, unrestricted permission, or an achieved system.

## Product boundary

**Manager ≠ Life Manager.** This standalone repository has no imports, credentials, runtime contracts, or shared database with Life Manager. Later integration would require a separately reviewed API contract. Previous Life Manager code is **not** imported.

**Current status:** Phase05 offline fixture kernel implemented and tested; no live intervention, human causal fidelity validation, or actual human-impact claim.

## What is intentionally forbidden in this scaffold

- All external writes, donations, public posting, physical device changes are disabled in `manager_core/config.py`. There is not yet a live executor.
- No private individual information; a publicly reachable page containing sensitive personal data is not automatically acceptable.
- No automated publishing of blog posts or articles. Research precedes future optional English-language publications.
- No claim that a simulation or an API response alone proves reduced suffering.

## Architecture and tasks

- [Manager product specification](docs/MANAGER_PRODUCT_SPEC.md)
- [GitHub research source and verification](docs/GITHUB_SOURCE.md)
- [Architecture](docs/architecture/ARCHITECTURE.md)
- [R006 source rights review](docs/research-rights.md)
- [R006 machine-readable source decisions](docs/research/source-rights.json)
- [Atomic backlog (learn + implement + verify)](docs/roadmap/ATOMIC_BACKLOG.md)
- [Structured task manifest](docs/roadmap/tasks.json)
- [imozuru source map](research/imozuru/manager-foundations/map.md)
- [imozuru verification report](research/imozuru/manager-foundations/report.html)
- [Upstream imozuru script and provenance](tools/imozuru/README.md)

## Offline checks

```bash
python3 -m manager_core
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 tools/imozuru/report.py research/imozuru/manager-foundations --check
```

All checks are offline, standard-library only. GitHub branch-level source mirror is reviewed separately from this standalone historical Git repository; a GitHub-hosted source tree is **not** equivalent to a tested production deployment. The research branch also adds a root `.github/workflows/manager-research-ci.yml` for offline tests; hosted check results have not yet been verified.

## Current research record

- [R004: HeartSteps methods, results and limits (Japanese)](docs/learning/R004_HEARTSTEPS_JA.md)
- [R005: Descriptive fit versus causal fidelity (Japanese)](docs/research/R005_LI_JI_JA.md)
- [R006: data/code licensing and reuse boundary (Japanese)](docs/research-rights.md)
- [R005: Effect-error data with first-source locators](docs/research/R005_CAUSAL_ERROR_EVIDENCE.json)
- [imozuru R005 evidence report](research/imozuru/causal-r005/report.html)
- [Completion and blessings roadmap](docs/roadmap/PRODUCT_COMPLETION_GATES.md)
- [Long-term entity vision and evidence limits](docs/MANAGER_PRODUCT_SPEC.md) (aspiration, not a measured result)
- [R004 source map](research/imozuru/heartsteps-r004/map.md)
- [R004 reproduction questions](research/imozuru/heartsteps-r004/OPEN_REPRODUCTION_QUESTIONS.md)
- Ordered task status remains in the existing [atomic backlog](docs/roadmap/ATOMIC_BACKLOG.md) and its [structured view](docs/roadmap/tasks.json). This page does not introduce another task sequence.

## Evidence integrity

Research under `research/imozuru` references original URLs and short excerpt-only locators. The original author-provided imozuru `report.py` is vendored exactly, checked against its Git blob SHA; it is **actually executed** for the excerpt location check. imozuru's downloader and OpenAlex chain scripts cannot connect from this environment, so primary sources and linked papers were investigated using Firecrawl and connected GitHub tools instead. Full copies of third-party papers are not redistributed.

## R007 / R008

See [Japanese implementation note](docs/R007_R008_IMPLEMENTATION_JA.md). Run `python3 -m manager_core.evidence` for the eight-card offline inventory; `python3 -m unittest discover -s tests -v` runs 59 tests. Structural validation does not prove scientific correctness or Manager impact.

## October 20, 2026: entity-first landscape and Phase 02 L001

- [26-organization market map and official primary-source URLs](docs/landscape/2026-10-20-behavior-intervention-entities.md)
- [Machine-readable map](docs/landscape/2026-10-20-behavior-intervention-entities.json)
- [Editable logo-free SVG market map](docs/landscape/2026-10-20-behavior-intervention-chaos-map.svg)
- [L001: conditional probability explanation (Japanese)](docs/learning/L001_CONDITIONAL_PROBABILITY_JA.md)
- [L001: synthetic Python probability demo](examples/01_probability.py)

L001 is an offline learning example, **not** behavioral model training, causal evaluation, or field impact. Organizational categorization is editorial and non-exhaustive.

## L002: TVD and binary Brier forecast diagnostics (2026-10-20)

- [TVD/Brier Japanese learning note](docs/learning/L002_TVD_BRIER_JA.md)
- [Offline score example](examples/02_scores.py) — `python3 -m examples.02_scores`
- [L002 test-first verification](tests/test_scores_l002.py) — 13 new tests.
- [Visual teaching diagram (editable SVG)](docs/visuals/2026-10-20-L002-TVD-Brier-JA.svg)
- [L002 verification record](docs/verification/L002.md)

TVD=0.20 and Brier=0.01/0.81 are **synthetic illustrations** and say nothing about Manager's effects on real people. PDF/PNG teaching versions are also saved in the ChatGPT Library `/Manager/Reports`.

## Phase 02 learning checkpoint (2026-10-20)

All L001–L012 learning tasks are now verified as **synthetic-only, offline learning material**. The combined diagram and summary:
- [Phase 02 Japanese guide](docs/learning/PHASE02_SUMMARY_JA.md)
- [Editable Mermaid causal learning sequence](docs/architecture/phase02-methods-ja.mmd)
- [JITAI / HeartSteps terminology](docs/learning/JITAI_GLOSSARY.md)
- [Calibration example](examples/02_calibration.py)
- [Causal graph and counterexample](docs/learning/CAUSAL_DAG.md)
- [Potential-outcome demo](examples/03_potential_outcomes.py)
- [Randomized assignment demo](examples/04_randomization.py)
- [MRT description](docs/learning/MRT.md)
- [Proximal vs distal outcome windows](docs/learning/PROXIMAL_VS_LONG_TERM.md)
- [External displacement example](examples/05_spillover.py)
- [Off-policy assumption demo](examples/06_policy_basics.py)
- [Evidence level P0–P5](docs/learning/OUTCOME_LADDER.md)
- [Learning-focused verification report](docs/verification/PHASE02_COMPLETE_JA.md)

The PDF and two original Japanese PNG illustrations are stored in ChatGPT Library `/Manager/Phase02`; `scripts/build_phase02_visuals.py` is the reproducible source. They contain no original participant records. Manager has **not** replicated a human RCT or demonstrated net welfare benefits.

## H001: HeartSteps original data structure (read-only metadata review)

- [H001 public dataset and rights review (Japanese)](docs/research/heartsteps/H001_PUBLIC_DATA_REVIEW_JA.md)
- [Pinned upstream files and minimal column candidates (JSON)](docs/research/heartsteps/H001_PUBLIC_DATA_MANIFEST.json)
- [H001 first-source investigation (imozuru)](research/imozuru/heartsteps-h001/map.md)
- [H001 editable data map](docs/visuals/2026-10-20-H001-HeartSteps-Data-Map-JA.mmd)
- [H001 original PDF/PNG rendering source](scripts/build_h001_visual.py)
- [H001 verification](docs/verification/H001.md)

H001 does not copy participant CSVs into the public repo or the Manager runtime. Historical row-level data will be considered independently under H002, with privacy and raw-redistribution restrictions.

## October 21, 2026: autonomy philosophy and first real-data audit

Routine Manager operation is designed to use no human per-action approval. Legitimate standing delegated scopes and safe policy gates remain necessary for external effects. Read [H002–H005 source audit and philosophy](docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md). H002/H003/H004 are source-data audit checkpoints only, not an experimental treatment-effect reproduction. Raw participant rows are not part of the public repository.

## H005 dataset-lineage diagnosis (2026-10-21)

The aggregate-only [pinned public study-day join probe](scripts/heartsteps_phase3_day_join_probe.py) and its [nine focused tests](tests/test_heartsteps_day_join_probe.py) show 7,427 nonconflicting matched days from 8,274 notification decisions, 769 missing and 78 contradictory join-days. The day shortcut disagrees on 3,345 of 7,409 comparable decisions. Scientific exact-replication remains blocked. Details and [CI evidence](docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md).

## No-human macro/environment engineering doctrine (2026-10-21)

[Founder clarified world-engineering and autonomy requirements](docs/MANAGER_NO_HUMAN_WORLD_ENGINEERING.md). Manager's recurring loop is autonomous by design and must be operable using lawfully public nonpersonal observations and Manager-controlled/permissionless actions. Partners are optional; no person-by-person micromanagement or privileged third-party infrastructure is a default requirement. Historical HeartSteps study data remain isolated learning-only.

[HeartSteps H005 reproducibility audit](docs/research/heartsteps/H005_PUBLIC_DATA_RECONCILIATION.md) explains which published study-day fields are absent or only partially reconstructible. It is a scientific blocker and not an invitation to invent missing observations.

## Phase 03 closes with documented H005 waiver and exploratory public reanalysis (2026-10-21)

Founder explicitly skipped H005 because publicly released HeartSteps files do not uniquely recover the original 2019 7,540/6,061 analytic set. H005 is `skipped`, never `done`. H006–H010 are complete only under revised, preserved-original-criteria **exploratory** acceptance. The pinned CSV produced 6,330 selected available decisions from 37 persons; noncausal participant-cluster adjusted ratios 1.140 [1.001,1.297] for any message and 1.239 [1.056,1.454] for walking message; decision-ordinal index/50 interaction 0.858 [0.772,0.953]. The 2019 sample, original time definition and inference procedure are not reproduced. **Gate 1 independent randomized causal replication remains UNMET.** No verified Manager human benefit exists.

The public research outputs are at `docs/research/heartsteps/PHASE03_PUBLIC_ANALYSIS_JA.md`, `docs/research/heartsteps/PHASE03_PUBLIC_METRICS.json`, `docs/verification/PHASE03_VERIFICATION.md`. Real-data CI: https://github.com/Daisuke134/life-manager/actions/runs/39526839889 . Proceed next to S001 rights-safe study-level metadata. Individual participant data are not copied to the Manager product.

## Phase 04 — observed public aggregation, technical social simulator, and honest open science (2026-10-21)

**Status: 5 scoped technical/methodological milestones done of 8; Phase04 SCIENTIFIC validation NOT yet complete.** S001/S003 pass verified official SocSci210 study-ID and anti-leakage checks (170/40, 0 overlap); S002 is blocked by source-study participant-data consent/license chain; S004/S005 require real permission-cleared heldout study responses, subgroup calibration and same-split pretrained-model comparisons. S006 has an analytic (NOT empirical) causal-fidelity counterexample; S007 has actual pinned Concordia *fictional* agents running an offline mock with separated evidence; S008 uses *observed aggregate* mobility outcomes in two genuinely later time conditions. None proves social-person simulation or reduced human suffering.

**New REAL observed data:** UCI CC BY 4.0 Bike Sharing, 2011 365 training days / 2012 366 holdout days (original UCI CSV byte-identical to fixed GitHub snapshot). Frequency classification accuracy 83.33%, season-only 65.30%; pooled daily rental MAE 2,488.67 vs season mean 2,303.65; observed error difference 185.02, seven-day block bootstrap 95% [-50.30,391.18], so no definite improvement. Separate winter vs summer 2012 Brier/TVD makes heterogeneity visible. NOT an RCT. [Actual source and analysis CI](https://github.com/Daisuke134/life-manager/actions/runs/39545601251).

**Upstream simulation:** [Concordia Island real engine, two constructed ESA agents, mocked responses, separated validation evidence](https://github.com/Daisuke134/life-manager/actions/runs/39545009858). JSON response parsing warnings persist; no real social science accuracy has been measured. [Engine technical audit](docs/verification/S007_CONCORDIA_TECHNICAL_JA.md).

**Recent integrated hosted checks:** [181/181 unit tests, Manager-only product boundaries and synchronized 113 tasks](https://github.com/Daisuke134/life-manager/actions/runs/39546138495). Canonical totals are **40 done, 69 todo, 3 blocked, 1 skipped**. Full scientific human-impact evidence Gate 1 remains unmet because exact H005 RCT reconstruction and empirical SocSci210 human benchmarks are not available.

- [Phase04 actual source empirical evaluation report (Japanese)](docs/research/public_aggregate/PHASE04_UCI_BIKESHARE_EMPIRICAL_JA.md)
- [Phase04 methods, task statuses, and true blockers](docs/verification/PHASE04_PROGRESS_JA.md)
- [SocSci210 actual 170/40 split-only audit](docs/research/socsci/S001_STUDY_SPLIT_AUDIT_JA.md)
- [Synthetic math vs actual human causal-effects note](docs/research/socsci/PHASE04_METHODS_PARTIAL_JA.md)
- [Editable source→prediction→causality→welfare diagram](docs/architecture/PHASE04_EVIDENCE_FLOW_JA.mmd)

Only independent scientific and authorized welfare measurements can later establish benefits. S006/S007/S008 original acceptance language is kept in tasks.json alongside precisely scoped substitute verification—not relabeled as successful human-effect reproduction.


## October 21: Radiant, Behavior × AGI research daily, 44-slide lab curriculum

**Research sources and honest status:** Artificial Societies (Radiant) is an existing company in the 26-entity ecosystem; its record was refreshed with the current [Radiant interface](https://societies.ai/radiant), [company evaluation](https://societies.ai/eval), [October benchmark](https://societies.ai/as-benchmark), and [2026 eleven-test academic preprint](https://arxiv.org/html/2609.30030). The [Japanese first-source deep dive](docs/research/societies/RADIANT_2026-10-21_JA.md) carefully separates commercial survey data, 2024 peer-reviewed LLM homophily, 2026 research preprints, and the absent proof of real-world causal welfare. The [curated company landscape](docs/landscape/2026-10-20-behavior-intervention-entities.md) remains 26 distinct entities; we did **not** duplicate the vendor under a product name.

**Education and communication:**
- [Living 44-slide Research-Lab Deck v2, editable sources/slide index, citations and reproducibility hashes](docs/presentations/BEHAVIOR_SIMULATION_LAB_DECK_V2_2026-10-21.md)
- [Slide-source claim/method/limitations trace](docs/presentations/BEHAVIOR_AGI_LAB_SOURCE_CLAIM_METHOD_LIMITS.json)
- [English field guide about Radiant (research branch draft, NOT public blog publication)](docs/articles/manager-radiant-societies-field-guide-en.md)
- [Behavior × AGI Daily launch issue](docs/newsletter/2026-10-21-launch-issue.md)
- [Evidence-first newsletter business/product charter](docs/newsletter/NEWSLETTER_PRODUCT_CHARTER.md)
- [Original three-volume teaching and book series plan](docs/newsletter/BOOK_SERIES_AND_LAB_CURRICULUM.md)
- [C001/Y006 verification receipt](docs/verification/C001_Y006_RESEARCH_COMMUNICATIONS_2026-10-21.md)

**Files:** Editable PPTX, PDF and original regeneration Python are verified in the owned cloud Library at `/Manager/Research/`. GitHub stores the human-editable slide-by-slide inventory, research notes and claim/limits trace, not the deck binary.

**Daily delivery:** a ChatGPT “Behavior × AGI Daily” recurring task was created for approximately 08:00 Japan time from 2026-10-22. An automation answer is not an external email newsletter subscriber list. Social X/other posts are not recorded as published without a connected destination and real readback; the issue stores draft copy only. Do not infer commercial revenue.

**Rights:** the user states they have permission to use all research data. The statement authorizes research tasks within the user's control; source-specific licenses, ethical participant protection, private respondent redistribution and legal scope remain separate. The [S002 rights audit](docs/research/socsci/PHASE04_LICENSE_AND_ALTERNATIVE_DATASETS_2026-10-21.md) explicitly preserves this distinction. Replacing a rights hold requires a recorded scope; no personal responses have been newly copied to public GitHub.

**Science:** Detailed simulation, aggregate forecasting, 11 validity-test awareness, corporate metrics and a completed source-linked presentation do not establish that Manager has causally reduced suffering. Research / publication state is separate from the product's Phase04 human-effects proof requirements.


## October 21: Autonomous earning evaluation and wealth-creating interventions

**Research finding, not an achieved product effect:** Money made in a Vending-Bench simulation, human historical dollar-valued SWE-Lancer tasks, actual settled external customer profit, and credible causal beneficiary wealth are **different proof levels**. Also compare positive and null original IRS/EITC intervention studies before building a money-finding 'blessing'.

- [Original 4,740-word English article](docs/articles/manager-autonomous-agent-money-is-not-wealth-en.md): *A Vending-Machine AI Scored $15,515. Did Anyone Actually Get Richer?* Original first sources and carefully labeled simulated / historically valued / realized / causal evidence.
- [25-source deep-research registry](docs/research/autonomous_wealth_eval/PRIMARY_SOURCES_2026-10-21.json): Andon Labs, Pion, Project Vend, Anthropic, SWE-Lancer, GDPval, METR, The Agent Company, LM-EAB read-only code, real human RCTs, causal methodology.
- [Proposed wealth and welfare dual-scorecard protocol](docs/research/autonomous_wealth_eval/WEALTH_BLESSING_EVAL_PROTOCOL.md): existing Life Manager economic-autonomy scorer **read-only schema inspiration only**; independent causal outcome and transparent welfare impact remains Manager's future task.
- [Original editable 7-level economic-evidence SVG](docs/visuals/autonomous-wealth-evidence-ladder-en.svg).
- [30-organization, seven-cluster landscape](docs/landscape/2026-10-20-behavior-intervention-entities.md) now includes Andon Labs, Anthropic, OpenAI, and METR; company capabilities do not imply independent verification.
- [Review/publish package PR](https://github.com/Daisuke134/life-manager/pull/8490) generated on a **separate content branch**; the research branch itself is **not a public blog post**. Requires all repository checks, content merge, site deployment and actual public URL readback before saying 'published'.

Life Manager already has `apps/life-manager/eval/economic-autonomy` and `eval/agent-contract` in its own product: verified receipt arithmetic, economic autonomy and safe promotion checks. The Manager *research* did not connect runtime, production ledgers, credentials or participant profiles. **No actual Manager-recipient wealth improvements are measured.**


## Living Behavior × AGI lab presentations (2026-10-21)

- [Current 39-slide English beginner-to-proposal seminar V3; full claim/source/limits crosswalk](docs/presentations/BEHAVIOR_AGI_END_TO_END_LAB_SEMINAR_V3_2026-10-21.md). The editable PPTX, its builder and generated hero illustration are stored under the user's Library `/Manager/Research/` with verified upload receipts.
- [Earlier 44-slide seminar V2](docs/presentations/BEHAVIOR_SIMULATION_LAB_DECK_V2_2026-10-21.md) remains preserved separately; V3 is a condensed alternative, not scientific peer review.
- [Radiant primary-source analysis](docs/research/societies/RADIANT_2026-10-21_JA.md) and [company-first 26-organization map](docs/landscape/2026-10-20-behavior-intervention-entities.md). Radiant is already included once.

Company numbers are labeled vendor-reported; Manager's own aggregate-model test is observational; no independent beneficial intervention has been demonstrated. Research and article publication are separate gates.
