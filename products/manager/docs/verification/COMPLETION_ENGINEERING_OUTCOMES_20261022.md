# D010–D012 / V001–V006 / G001–G006 engineering evidence

検証日: 2026-10-22 UTC。対象は独立製品 **Manager** のローカル engineering preparation。
実入金、実際の第三者監査、臨床成果、因果的厚生改善、複数地域での実証完了を示す記録ではない。
タスクの唯一の状態台帳は既存の `../roadmap/tasks.json`。この文書は状態台帳を追加・置換しない。

## 1. 対象と境界

開始時のブランチは `research/manager-completion-20261022`、親作業で指定されたベースは `ce75c0a`。
Git root は `/workspace/scratch/38913a404e8d/manager-repo`、origin は
`https://github.com/Daisuke134/life-manager.git` と確認した。
Manager と Life Manager のコード・実行権限・データ・収益台帳は接続していない。

この lane が変更した実装:

- `manager_core/opportunity_outcomes.py`: 公開 OSS 等の機会と入金主張の照合、独立した費用・時間・機会費用の計算。
- `manager_core/outcome_bench.py`: 予測、因果参照、P0–P4 証拠欄、holdout/OOD、再現用メタデータ、portfolio。
- `manager_core/governance.py`: 統治 preflight、既存 learner の昇格前確認、事故記録、coverage、API 契約、運営費モデル。
- `manager_core/adapters/fixtures.py`: 既存の厳密な offline fixture クラスの許可 domain 集合に `opportunity` を追加。kernel/outbox の分岐や許可を追加していない。

対応する新規テストは `test_opportunity_outcomes.py`、`test_outcome_bench.py`、`test_governance.py`。
この lane は task ledger、workflow、kernel、authority、outbox、config、source guard、remote、production を変更しない。
同じ checkout の他 lane の差分はこの文書の所有範囲ではない。

`bash scripts/verify-source-boundary.sh` は exit 2、
`canonical Git root is unavailable=/root/Projects/life-manager-main`。
guard を変更・迂回していない。親作業で明示された隔離 Manager checkout 内の開発だけを行った。
本 lane は commit、push、外部メッセージ、支払、個票取得、publication、production 操作を実行していない。

手順では `AGENTS.md`、`REVIEW.md`、製品 spec、対象 task の original criteria を読んだ。
利用可能な Superpowers `test-driven-development` / `verification-before-completion` skill 本文を読み、
missing implementation の RED、具体的な追加回帰の RED、GREEN を記録した。
`using-superpowers` の dispatched subagent exemption を確認した。
Astra Advisor orchestration はこの harness に公開されていない。

## 2. D010–D012: 機会、承認、入金、純額

`OpportunityRecord` は募集 `posting`、納品 `delivery`、承認 `approval`、入金 `settlement` を別の
`OpportunityStage` として必須化する。各段階の公開可否は `public` / `not_public` / `unknown`。
非公開・不明の段階に source 本体を入れることはできず、公開 source は既存 `Source` の
権利・SHA256・取得時刻・`public_nonpersonal` 契約を再利用する。
この型は source の真実性や匿名性を自動審査する機構ではない。

`SettlementClaim` の amount は宣言された入金額であり、募集の nominal award と別。
照合対象は opportunity ID、公開 aggregate の beneficiary group、納品・承認 artifact hash、通貨、
settlement source。`pending`、`reversed`、`disputed`、receipt 欠落、artifact 不一致、source 不一致を
入金額に変換しない。

すべての欄が揃った場合には次の **宣言されたデータの算術** が利用できる:

```text
declared_cash_net = declared_received - known_expenses
declared_economic_net = declared_cash_net - known_opportunity_cost
net_per_labor_hour = declared_economic_net / (labor_minutes / 60)
net_per_opportunity = declared_economic_net / opportunities_considered
```

例の完全な架空 fixture は nominal award 5,000、declared receipt 2,000、費用 200、機会費用 100、
作業時間 120 分、検討機会数 2。cash net 1,800、economic net 1,700、時間・機会あたり 850 を計算する。
これは USD minor-unit のテストデータであり、実際の Manager 収入ではない。

`CostCoverage` の既存費用カテゴリを再利用し、1 カテゴリでも不明なら expense total は `None`。
時間は独立に保持し、勝手に金銭へ変換しない。ゼロ時間で割らない。機会費用が不明なら
cash net が既知でも economic net は `None`。負の純額は負のまま残す。
費用に既に計上された額を機会費用にも重複計上しないことは入力側の accounting contract。

**全ケースで `income_status=NOT_VERIFIED`、`verified_income_minor=None`、
`human_welfare_status=NOT_MEASURED`。**
`DECLARED_SETTLEMENT_RECONCILED` は provider 認証完了という意味ではない。
任意の bytes が任意の SHA256 と一致しただけでは、支払の実在や受領を証明できない。
入金額だけでは比較対象に対する収入の増加・生活安定への因果効果も分からない。

## 3. V001–V006: 指標を混ぜない OutcomeBench

### 共通 fixture と再利用

金融・環境・機会の 3 domain が **同じ既存 `OfflineFixtureAdapter`、同じ `ManagerKernel`** を通る。
outbox の `type(adapter) is OfflineFixtureAdapter` fence は維持した。
当初の別クラス fixture はこの fence に拒否されたため、拒否機構を緩めず、親作業で許可された
既存 fixture の domain 集合だけを最小変更した。3 domain とも結果は `VERIFIED_FIXTURE_ONLY` / P0。
これは構造上の共通性のテストであり、仕事支援の live adapter や分野横断の実効性ではない。

既存の `total_variation`、`oracle_ate`、`assert_disjoint_groups`、`Source.verify_content` を再利用する。
新しい予測器、因果推定 engine、個人別 welfare scale は追加しない。

### 予測・因果参照・証拠

- `prediction_metrics` は paired MAE と distribution TVD を別に返す。非数、bool、NaN、長さ不一致、片側だけの分布を拒否する。
- `causal_error` は両方の潜在結果を明示した **架空** `SyntheticCausalReference` のときだけ oracle ATE error を返す。単位が違えば拒否する。
- 実世界の causal reference が未取得・未検証なら ATE error は `None`。URL や「RCT」の自己申告を正しい因果参照へ昇格しない。
- `EvidenceBundle` は同一 intervention に source を束縛する。wrong-subject、重複、snapshot hash 不一致を拒否する。
- `assess_evidence` は P0 simulation、P1 receipt、P2 world readback、P3 human outcome、P4 causal analysis を別欄に返す。
- executor 自身の readback は `EXECUTOR_ONLY`。technical proxy を human outcome とした入力は `PROXY_ONLY`。
- P4 には receipt/readback/human outcome に加えて preregistration、costs、harms、sensitivity、causal analysis の参照を別に要求する。

見かけ上すべて揃った self-supplied packet でも最大の状態は `UNAUTHENTICATED`。
byte/hash consistency は source authentication や独立性・倫理審査・臨床妥当性・因果設計の確認ではない。
`real_world_proof_level` は P0、human welfare は `NOT_MEASURED` のまま。
これは将来の真正な外部検証を拒否する方針ではなく、この offline contract がそれを実施しないという境界。

`reproduction_manifest` は source URL、license/rights/privacy、hash、日時、immutable code commit、
同じ未検証の分類を再現するための情報を deterministic に export する。
raw snapshot を出力せず、public distribution の権限を与えない。

### holdout、OOD、portfolio

`HoldoutEvaluation` は train/heldout ID の漏洩と重複を拒否する。
公開対象の国・所得層・domain・期間の **組合せ** を保持し、error metric と unit を明示させる。
個々の次元が別々に既知でも未知の組合せへ coverage を補間しない。
未知 scope、不明 error、閾値超過は `NO_ACTION`。既知の範囲でも `OFFLINE_CANDIDATE_ONLY` で、
`can_execute=False`。自己申告の良い error から live authority は生まれない。

portfolio は各 case、scope、metric、unit、interval、cost currency、harm metric/unit を保持する。
正・負・ゼロ・不明の **数値的な推定符号** は分類するが、分野ごとに異なる「改善の向き」を自動推定しない。
負と分かる推定値は harms 不明でも負として残す。正の推定で harms 不明なら positive benefit と扱わない。
不明な費用は通貨ごとの集計でも不明のまま。
異なる尺度はもちろん、同じ単位でも重複人口や異なる estimand を確認できないため welfare を単純加算しない。
`cumulative_welfare=None`。実際の数十案件の portfolio は未収集。

## 4. G001–G006 / V004: 統治の準備契約

**G001/G002 の現行設計範囲の明確化:** 下記の過去 engineering/test 記録を保持したまま、[公益憲章](../governance/PUBLIC_INTEREST_CHARTER_DRAFT.md)・[事故/異議/監査手順](../governance/INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md)の有限 source/offline 設計と実運営採択を分ける。[限定設計receipt](G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)による `BOUNDED_SOURCE_DESIGN_ACCEPTED` は、原依存 K007/V001 → G001 → G002 の実受入と現source確認を経てroot実受入済み。過去の実運営条件を設計doneへ読み替えない。運営採択は `UNADOPTED`、実外部監査は `NOT_PERFORMED`。将来の90日監査や任意の人研究を原設計受入の前提にしない。改訂前の文書 hash と immutable commit は [既存 checksum manifest](../governance/GOVERNANCE_DRAFTS_20261022.sha256) の履歴 comment に保持する。本明確化は新しいテスト実行や運営実績を報告するものではない。

`PublicInterestCharter` は immutable version hash、owner、standing grant、budget unit、audit/appeal URL、
operator stop・unknown effect・harm・revocation・OOD の停止条件を保持する。
これらの URL に実際の法的窓口が存在することや憲章が採択されたことは、このデータ型では確認しない。

`governance_preflight` は既存 `AuthorityVerifier.authorize` を呼び、scope、issuer、grant ID、予算、
有効期間の自己拡張を拒否する。停止中、UNKNOWN effect、不十分な coverage、偽造・失効署名も拒否。
合格しても `OFFLINE_PREFLIGHT_PASSED` で、live `can_execute` は false。
正規の standing grant がある routine 動作に新たな per-action 人間承認を要求する仕組みではない。

`promote_offline_policy` は既存 `PolicyLearner` の isolated candidate / heldout / shadow / previous-version
機構を再利用する。実際に active な baseline を rollback target として確認し、停止・shadow regression を
無視しない。昇格後の adverse loss による rollback と再起動後の永続性をテストした。
live limited rollout、grant 変更、予算増加、production activation は行わない。

事故は既存 `AuditTrail` に append し、`INEFFECTIVE`、`WORSENED`、`UNKNOWN`、害、異議、解決申告を残す。
不明 evidence は `None` のまま。再起動後も事象・参照 hash・時刻・chain を取得できる。
既存 store は operator が SQLite 全体を置換できるため tamper-proof ではなく、
`external_audit_status=NOT_PERFORMED` と報告する。

`coverage_inventory` は対象ごとの結果、未測定分野、不平等、失敗、次の疑問を保持し、
`universal_claim_allowed=False`。有限のデータから「世界の苦しみを終わらせた」と結論しない。

`PublicAPIContract` は接続先種類、公開 source、必要許可の参照、scope、minor-unit budget、通貨、責任者を
記録する設計契約。`DECLARED_NOT_AUTHENTICATED` / `can_connect=False` で、外部 API サーバーの実装や接続ではない。

`OperatingCostModel` は運営原価・継続支援・測定費・資金調達・企業売上を分離する。
企業 margin と資金調達を含む cash delta を別に計算し、どちらも宣言された数値として表示する。
beneficiary portfolio は別オブジェクトとして保持し、利益を human benefit に足さない。
測定費等が不明なら net model も不明のまま。

## 5. テストの実測記録

すべて `products/manager` を cwd として実行した。fixture は架空・非個人データ。

| 実行コマンド / 段階 | 実測結果 |
|---|---|
| `python -m unittest discover -s tests -p 'test_outcome_bench.py'` / 初回 RED | 実装未存在を示す assertion failure 12 件 |
| 同 / 3-domain 境界の調査 | 別 fixture class は既存 fence に拒否。original expectation 1 failure。拒否境界を維持 |
| 同 / exact fixture を 3-domain にする RED | missing `opportunity` domain の ValueError を確認後、明示 assertion にして 1 failure を再確認 |
| 同 / 最小 allowed-set 変更後 | 12 tests pass |
| `python -m unittest discover -s tests -p 'test_opportunity_outcomes.py'` | missing implementation 11 failures → 11 tests pass |
| `python -m unittest discover -s tests -p 'test_governance.py'` | missing implementation 12 failures → 12 tests pass |
| `python -m unittest discover -s tests` / 最初の全体確認 | 380 tests pass、0 failure / 0 error、exit 0 |
| OutcomeBench 追加 regression RED | 未指定 error unit、未指定 harm unit、unknown harms 下の負推定保持について 3 failures |
| 同 / unit と負推定補正後 | 15 tests pass。governance 12 tests pass |
| OutcomeBench result への error metric/unit 引継ぎ RED | 1 failure → result に metric/unit を保持 |
| `python -m unittest discover -s tests` / 最終の全体確認 | **383 tests pass、0 failure / 0 error、exit 0** |
| repo root で `git diff --check` | exit 0 |

この lane の新規テストは **38 件** (15 + 11 + 12)。全体 383 件は shared checkout の同時点の tree であり、
他 lane の新規テストも含む。全体確認は既存の unknown-effect、署名、idempotency、権限、runtime deny、
rights、privacy、evidence guards の regression も含む。Hosted CI、merged tree、production dry-run の代用ではない。

## 6. Original acceptance と残る外部・科学的条件

| ID | この差分が実証した範囲 | original completion に残るもの |
|---|---|---|
| D010 | 公開募集/納品/承認/入金を別欄に保存する typed public-only adapter contract | `R008` 依存を親台帳で確認すれば、元の「設計 / 別欄保存」engineering acceptance に最も直接対応 |
| D011 | approved artifact と receipt claim の正確な照合、不明入金を income と呼ばない guard | 独立に認証された実受領証拠。宣言値や example URL を実績にしない |
| D012 | 純額・時間・費用・機会損失・分母の分離と欠測保持 | 実際の機会純増、入力の外部検証、比較対象、生活安定への downstream evidence |
| V001 | 3 domain の同一 fixture/kernel contract test、core domain 分岐なし | original dependency `D016`。外部効果の一般化は示さない |
| V002 | MAE/TVD/ATE-reference-error と P1–P4/harms の独立評価、self-certification 防止 | `V001` dependency と真正な実世界 readback・適切な causal reference |
| V003 | country/income/domain/time holdout、明示 error unit、OOD/unknown 停止 | 実測された unseen population error、外部に確認された対象 coverage |
| V004 | 既存 isolated/shadow/holdout promotion と rollback、権限自己拡張拒否 | 正当な外部権限に基づく limited live execution の evidence |
| V005 | メタデータと code version による同じ未検証判定の再現 manifest | 正当な公開許可、実ソース・集計結果の公開と第三者による P1–P4 再現 |
| V006 | 正・負・不明・ゼロ、費用/harms/単位を保つ portfolio utility | original の数十案件の実際の outcome portfolio |
| G001–G002 | typed charter、preflight、audit/stop/appeal 参照、append-only incident workflow。上記の過去 engineering 証拠を維持 | 有限 source 設計については、[receipt](G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)の `BOUNDED_SOURCE_DESIGN_ACCEPTED` をroot実受入済み。K007/V001→G001→G002の実依存順と現source/code/review/検証のroot確認をreceiptに記録した。実運営としての採択された統治、実際の oversight/appeal・保存/訂正/復旧運用は未成立（`UNADOPTED`）、実外部監査 `NOT_PERFORMED` |
| G003 | 非外挿 coverage contract | 複数地域・人口構成での段階的な実測検証 |
| G004 | 接続先ごとの source/permission/budget/responsibility 契約 | 実際の接続先合意・許可の認証、必要な API delivery |
| G005 | 企業収益/資金/費用と人間への便益の独立 accounting | 実測コスト・外部 outcome での経済モデル検証、先行依存 |
| G006 | 未測定・不平等・失敗・次の疑問の棚卸し、普遍的結論の禁止 | 継続運用での実データ更新と元の先行依存 |

この lane から original acceptance をそのまま完了候補として提案できるのは **D010 の設計条件**。
それ以外を fixture 成功だけで field task 全体の `done` にしない。
最終の dependency/status 判断と台帳更新は親 orchestrator が一つの既存 ledger に対して行う。
