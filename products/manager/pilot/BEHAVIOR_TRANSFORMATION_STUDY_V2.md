# Behavior transformation study v2 — protocol draft

2026-10-23 UTC。**DRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0**。

使命は「行動変容を通じて、苦しみを終わらせることを目指す」。この草案は覚り・苦の終結の測定や臨床治療の有効性を主張しない。旧`FIRST_STUDY.md` v1.1、120世帯/58日、既存protocol hashは履歴として不変。現在の実行前提は本v2を実条件で完成させるU004。

## 固定した設計判断

- 対象候補: 非臨床の成人が、自分で選ぶ一つの行動を日常で試し、その価値を自ら評価する研究。対象/需要の確認は未完了。宗教的信念を求めない。
- 介入候補: 既存の根拠と利用権に基づく短い説明・任意の実践・振り返り。comedyや物語は本人の好みを確認する探索的な提供形式で、確立した効果としない。
- 対照: 時間・接触量を合わせた既存の一般情報/単純ルール等。既存の支援や医療へのアクセスは保つ。NO_ACTION/撤回を可能にする。
- 通常提供: 参加者が選んだ既存の適切な媒体/環境を使い、Managerの専用app・chat・毎回の操作を必須にしない。研究同意・測定・停止の入口は通常提供面と区別する。現在の7パスpublisherの範囲を自動拡張しない。
- 証拠: 配信、曝露、理解、意図、行動、苦しみ/生活機能、持続、害を別々に記録。観測方法と独立性、自己申告かを明記する。
- 保護: 圧力・依存・悪化・負担・撤回を能動的に確認し、中止と適切な支援への接続を定める。危機/臨床仮説は別protocolと専門的な実施条件へ分離する。

## U004受入前に実条件で埋める欄

| 欄 | 現在 | 解決方法と受入条件 |
|---|---|---|
| 対象行動/参加条件/研究役割 | 未確定 | 現対象の一次的な課題確認と実施協力を得て、本人の目標・辞退条件を具体化 |
| 主要endpoint/単位/尺度の権利 | 未確定 | 妥当性と利用権を確認した行動/機能/苦しみの測定から一つを主要とし、副次・害を分離 |
| allocation/analysis unit | 未確定 | 人物・反復・cluster/spilloverを明示し、無作為化/割付確率/ITT/欠測を定義 |
| 人数・期間・追跡 | 未確定 | 最小重要差、分散/イベント率、alpha/power、脱落の根拠から検出力を計算。旧人数を転記しない |
| content/model/version | 未固定 | 利用権のある介入・base/adapter・prompt・judge版とprovider条件を固定 |
| 独立観測/分析と停止 | 未成立 | 必要な同意・適用判断・観測経路・担当・中止/連絡/復旧を実確認 |
| 実費/compute/媒体 | 未確認 | 利用できる既存資源と費用・個票最小化・アクセス/保管/失効条件を確認 |
| 事前固定/登録 | 未実施 | 全欄の成立後、新v2 hash manifestと適用する登録を開始前に固定 |

空欄がある間は募集・割付・介入を開始しない。将来のmanifestは`pilot/BEHAVIOR_TRANSFORMATION_PROTOCOL_V2.sha256`とし、全欄成立前に受入済みのhashや登録番号を創作しない。公開既存研究のoffline解析は、当該source利用条件の範囲で別途進められる。


## 公開既存研究の有限offline再利用案との関係

[Step-by-Step公表集計のsource-specific protocol案](STEP_BY_STEP_PUBLISHED_EFFECT_AUDIT_V1.md)は、既公表Table3効果・欠測仮定のretrospective auditを候補とする。rootの条件付用途/有限offline技術適用判断とfresh AI technical review R1/source再照合は、同案§4の実receiptにより実施済み。同じ別context AI reviewerの実R2は0 findings/0 blocking、Nit FIXED（私有receipt `task-1-review-r2.md` SHA-256 `79710ab80c7f3bae0a6614b9b2628215a01627a3c6e422435fd553df1aa786fc`）。この公開案作成時のPENDING以降、公開source統合はcommit `4f6a063a0339bd327529659b1c975361476708e7`、D014/D015現scopeの有限source/task受入の台帳記録はcommit `ddcbf91dcd9be0337ede3075a28490e6c3c27f49` で実施し、push・公式readback一致を確認済み（[実receipt](../docs/verification/D014_D015_PROTOCOL_ACCEPTANCE_20261023.md#d015-actual-task-acceptance)）。これは実施済みの新規研究や公開原個票の独立再解析ではない。

このsource案は本v2の対象行動・需要・測定権利・検出力・実施協力・独立した適用判断・媒体・同意/停止・登録の空欄を埋めない。**本v2はDRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0、U004はtodo。** 原著の569人は歴史的なsource母集団で、Manager参加者数へ加算しない。旧FIRST_STUDYや120世帯/58日、旧manifest/hashを置き換えない。

公開非個人集計を読む限定活動に提携/NDA/新規募集/原参加者への再同意を普遍的に要求せず、必要な条件をsource/用途ごとに判断する。その技術設計の受入と、新規参加者を含む本v2の実同意・適用判断・必要な実在する役割、U006/U007の実結果の受入は別である。[offline停止/復旧追補案](STEP_BY_STEP_PUBLISHED_EFFECT_AUDIT_V1.md#5-offline停止復旧)も限定proposalで、臨床承認・実害ゼロ・Manager便益を意味しない。新しい受入済みprotocol hash/登録番号は未発行。


## 将来の行動変容研究の保護定義案への参照

[BEHAVIOR_TRANSFORMATION_SAFETY_V1.md](BEHAVIOR_TRANSFORMATION_SAFETY_V1.md)は、本人の選択/撤回、非応答への追送、圧力/誤断定、排他的依存/判断委譲、支援遮断、本人報告の悪化、privacy/不明についてsignal→停止/支援→実scopeの独立判断と非自動復帰を定義する。別context AIの21:12:45.444261Z実reviewは有限design applicability YES、rootは21:16:58.283242Zにsource採用し、21:16:58.283436ZにD015定義taskを別受入した（[外部実receipt](../docs/verification/D014_D015_PROTOCOL_ACCEPTANCE_20261023.md#d015-actual-task-acceptance)）。新doc内PENDINGは作成時snapshotとして保持し、旧研究の数値triggerを移植しない。本v2のDRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0、上記未確定欄と実役割/同意/測定/登録の条件はそのまま。研究・モデル運用・通知/UI・clinical承認をこの参照で発動しない。


## 追加の測定設計参照 — 行動ログとproxyの分離

[one sec / INA・IntentionBenchの用途別evidence note](../docs/research/2026-10-23-additional-behavior-evaluation-reuse.md)を、上の未確定欄を具体化する際の参考にする。本人の任意goalと変更/NO_ACTION/撤回、実行/中止のevent、観測系と独立性、モデル推定/自己申告、人物内反復・研究・時点、分母/欠測/脱落を区別する。使用中と撤去後の持続、false-positive負担、生活機能・害/依存/置換も別の量として扱い、欠測を0や効果なしへ変換しない。部分reuseは用途別に判断し、全endpointを一つのbenchmarkで満たすことを新たな受入条件にしない。

両先例はapp/UIを持つため、No UIや専用app/chat・スクリーンショット常時監視を導入する根拠にしない。通常提供の媒体は既存方針どおり本人が選び、観測の成立と権利は用途別に確認する。本参照は対象/需要/roles・同意・媒体・尺度権利・人数/期間・登録・独立観測/停止の空欄を埋めず、既存Step-by-Step/SafetyおよびD014/D015有限受入の文面を変更しない。**DRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0、U004 todoを維持**し、data/scorer採用・rights受入・モデル実行・人への介入/運用・便益の受入を発動しない。
