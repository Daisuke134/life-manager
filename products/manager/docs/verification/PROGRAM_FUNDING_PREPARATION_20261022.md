# D001–D003: プログラム資金・置換・受益報告の結合

**2026-10-23 current pointer:** F006受入後、D001は分類実装、D002は比較設計のsource契約として[個別受入](D001_D002_SOURCE_ACCEPTANCE_20261023.md)済み。P0／NOT_VERIFIED／NO_ACTIONと実資金・人の便益未測定は保持。D003以降の実証は未受入。下は2026-10-22の準備記録。

**2026-10-22 JST。独立したManagerエンティティの研究用準備。** [原 D001–D003](../roadmap/tasks.json) に向け、[program_funding.py](../../manager_core/program_funding.py) と [12件の行動テスト](../../tests/test_program_funding.py) を追加した。実際の資金、送金、寄付の純増、受益者、生活改善は観測していない。全ての入力出典と完全性は供給者の宣言であり、出力は **P0 / NOT_VERIFIED / NO_ACTION** のままである。

## 何を結合するか

| 型 | 保持・検証する内容 |
|---|---|
| `FundingWindow` | タイムゾーン付き期間 `[start, end)` と通貨 |
| `FundingReceipt` / `FundingLedger` | program、canonical transfer ID、外部寄付者・Manager matching・sponsor・不明の別、金額、返金、決済状態、時刻、Source、台帳の宣言 coverage |
| `ProgramCosts` | 同じ program/window の既存 `economic_scorecard.CostCoverage` と出典。platform/compute/goods/marketing/labor/refunds/tax/other の全カテゴリを既知または unknown で保持 |
| `ProgramComparison` | 同時期・同通貨の一つの program と一つの対照。それぞれの「返金後の外部寄付額」と Source。独自の因果推定を行わない |
| `DisplacementScope` | 元 program、事前に宣言した他 program 群、期間、coverage、出典。対象 program の重複や、対照を複数ペアで再利用する入力を拒否 |
| `BeneficiaryReport` | 元 program、受益集団、期間、公開報告の Source、独立した metric/unit/value/denominator。資金移動とは別の欄 |

`reconcile_program_funding` は各レコードと出典を結果に保持する。program/currency/window の不一致、重複した transfer ID、同一 Source ID の矛盾する metadata、比較の値や出典が対象台帳と一致しない場合、同時期でない対照を拒否する。任意の supplied snapshot は既存 `Source.verify_content` で照合するが、ハッシュ一致は由来の真正性や独立性を認証しない。

同じ送金を表す入出金の ledger-side row は、上流で同じ canonical transfer ID に正規化する必要がある。現場の provider-specific parser と照合を、この型だけで実施済みにはしない。

## 算術と unknown の扱い

外部寄付と、Manager 自身または sponsor の原資を別集計する。matching/sponsor の金額を増やしても、外部寄付の増加額は変わらない。

返金は各 receipt の gross から一度だけ引き、全 receipt の返金合計を既存 `CostCoverage.refunds` と照合する。食い違えば拒否する。費用合計では `refunds` を除外して二重控除を防ぐ。それ以外の費用カテゴリを operating costs として表示する。出資・移転原資、運営費、返金、受益者の生活指標は別の量である。

完全な架空例の値:

| 項目 | 宣言された値、USD minor units |
|---|---:|
| 外部寄付 gross | 1,000 |
| 外部寄付の返金 | 100 |
| 外部寄付 retained | 900 |
| 対象の同時期対照 | 500 |
| 外部寄付の記述的差 | 400 |
| Manager matching capital | 10,000、外部寄付の差へ加えない |
| sponsor funds | 5,000、外部寄付の差へ加えない |
| 他 program の差 | −200 |
| platform/compute の operating costs | 70 |
| 宣言された範囲の記録上の収支 | **130 = 400 − 200 − 70** |

最後の算術には既存 [spillover.net_additional_resources](../../manager_core/spillover.py) を再利用した。同関数は float を扱うため、全ての中間和が整数として厳密に表現できる範囲を超える入力は、呼び出す前に拒否する。これは独自の因果推定器ではない。

この130は、限定した比較と費用を供給した場合の**記述的な記録上の値**である。社会全体の新たな富、Manager の検証済み収益、因果効果、受益者の純便益ではない。他 program の差が −1,000 なら結果は −670 のまま保持する。悪化した値をゼロで切り上げない。

- pending/reversed/disputed/unknown、金額・返金・出典の欠落は、該当 origin の合計を unknown にする。
- coverage や origin が不明な場合、存在しないカテゴリを0にしない。**出典付きで complete と宣言した空の台帳**だけは、宣言上の0として計算できる。それでも NOT_VERIFIED。
- 費用、対照、他 program の観測、scope の完全性が不明なら、その成分と最終収支は unknown。既知の対象差まで消さず、別表示する。
- scope 外の影響は、この計算に含まれない。complete という入力は、社会全体の置換がない証明ではない。
- 同じ期間の比較でも、割当・比較可能性・干渉・選択・規模・標本の妥当性は実証していない。因果評価は別の登録済み設計が必要。

## 受益報告を資金移動と混同しない

受益報告がなければ `REPORT_MISSING`。program/group/window が一致しなければ `REPORT_BINDING_MISMATCH`。資金移動と同じ出典 hash を beneficiary report として渡した場合は `TRANSFER_REFERENCE_ONLY`。値・分母・適合する出典が欠ければ `INCOMPLETE_REPORT`。

別の報告参照が結合できても `DECLARED_REPORT_NOT_VERIFIED` である。metric/unit/value/denominator を保存するが、資金との合算や病気・困窮の減少への変換はしない。`verified_income_minor` と `verified_net_benefit_minor` は常に `None`、人への改善は `NOT_MEASURED`。

## 実行した検証

cwd は `products/manager`。

| コマンド・段階 | 実結果 |
|---|---|
| `python -m unittest discover -s tests -p test_program_funding.py`、モジュール作成前 | **12 tests / 12 failures**。意図した missing implementation アサーション |
| 同コマンド、実装後 | **12 tests passed / 0 failures / 0 errors** |
| `PYTHONPATH=.:tests python -m unittest test_program_funding test_economic_scorecard test_opportunity_outcomes` | **36 tests passed / 0 failures / 0 errors / 0 skips** |

テストは原資の混同、返金の二重控除、未決済、unknown→0、負の置換、費用欠落、不一致の期間・通貨・出典、重複 transfer/control、支払証拠を受益報告へ転用する入力を含む。架空データ以外は使用していない。

別エージェントによる新規モジュールとテストの読み取り専用レビューは **0 findings / 0 blocking**。原資の分離、program/window/currency の結合、比較単位の重複拒否、返金の単回控除、unknown の保持、受益報告と送金証拠の分離を確認した。レビュー担当による編集や全体テストの再実行は行っていない。

原 D001 は F006 に依存し、D002/D003 もその後続である。今回の結合契約で原タスクの実証条件を満たしたとはせず、[受入対応表](PHASE06_TO_12_ACCEPTANCE_20261022.md) の、このソフトウェア欠落だけを更新する。runtime、network、authority、task ledger、既存モジュール、workflow、Life Manager の経路は変更していない。
