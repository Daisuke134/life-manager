# D014 / D015 — source検証と定義整備（原タスク受入保留）

**判定: SOURCE_AND_DEFINITION_QUALITY_PASS / ORIGINAL_TASK_ACCEPTANCE_PENDING。** 独立reviewで公式原本・数値・権利・定義成果物の品質を確認した。原D014 externalの協力と適切な倫理対応は未検証であり、D014はtodo、D015もD014依存のためtodoを維持する。実際の研究発動・協力契約・人の便益とは分ける。原ID・depends・verify・externalを変更しない。

## D014: Route Aの公開集計プロトコル

依存D013はdone。原changeは公的機関等の公表集計との協働プロトコルの作成、原verifyは同意・倫理・匿名集計を守り非公開個票を取得しないこと。既存Route A/Bを維持し、v2 §8と[固定source record](../research/DCMS_CLS_ROUTE_A_SOURCE_20261023.json)／[rights registry](../research/source-rights.json)で、DCMSの既公表全国集計の文脈引用だけを具体化した。

原externalの「団体の協力」は、正規公開と一般向け再利用表示だけでは成立を確認できない。公開集計の可用性とは別に、実際の協力と適切な倫理対応の根拠が必要であり未検証とする。個別承認・提携はNO_PARTNERのまま。活動は既公表全国数値の読取／引用で、新たな募集・割付・接触・私的回答・個人連結を含まない。正式倫理審査の制度上の適用はUNKNOWN、承認／免除はNOT_OBTAINEDと記録する。原externalの未確認事項をRoute Bだけへ移してD014完了とはしない。一方、新規研究・署名契約・NDA・私的データ・一律の正式承認／免除を新たな必須条件にも加えない。Route Bの実協力・倫理・同意・担当者は将来の該当活動の前提として残す。

ODSの保持bytesとSHA、A1aの全国行とNotes、公式HTMLのライセンス表示を直接照合した。7%は加重・丸め、6.6%は本文、CI6–7%も丸め、10,061はカテゴリ有効回答、170,971は設問ベース。比率を再計算して同じ推定値としない。原本ODS／HTML／個票はGitへ追加しない。原文licenseへのHTTP403を保持し、新しい再配布権や第三者権利の確認へ一般化しない。

## D015: 保護・過剰介入・誤評価・停止の規則

D014の原externalが未達であり、D015の依存完了も保留する。既存安全protocol §2が同意・撤回・接触負担・通常支援の維持、§3が害・不明・監視能力不足で停止／NO_ACTION、§4が分母・UNKNOWN・欠測、§5が独立した専門家評価と再開判断、§6が誤評価・権利・母集団・撤回時の主張停止を定義する。v2は定義と発動を区別しただけで、数値閾値を臨床的に実証したとはしない。

原change/verifyは「停止基準を定義」であり、実reviewerの任命、臨床結果、新規参加者を追加の定義条件にしない。実際の研究を始めるには既存発動条件が別途必要。参加者0、実安全監視なし、臨床推奨なし、Managerによる精神的便益NOT_MEASUREDを維持する。

## 版・検査・限界

v1のimmutable commitと旧SHAは各protocol末尾に保持。v2 bytesは既存 `RESEARCH_PROTOCOLS_20261022.sha256` へ固定した。FIRST_STUDY／既存F002／他protocolは変更しない。このsource作業は定期runtime、モデル推論、公開ページ、研究参加者や外部機関を操作しない。独立R1 reviewは定義とsource品質PASS、原タスク完了への昇格に1 blocking。指摘に従い、協力と倫理対応の未確認を明示し、原D014/D015をtodoに保った。既存rightsテスト3件、protocol manifest5ファイル、diff検査は成功。新しい人研究や人への効果を示す検査ではない。

独立R2は修正文のみを確認して0 findings／0 blocking、R1指摘を解消した。これはsource／定義成果物の品質判定であり、原D014/D015の受入PENDINGを変更しない。


## 行動変容scope改訂後の限定source-design提案（受入記録ではない）

**PRIVATE_FINAL_PROPOSAL / ROOT_CONDITIONAL_PURPOSE_ACTUAL / FRESH_AI_TECHNICAL_REVIEW_R1_R2_ACTUAL / SOURCE_ADOPTION_AND_D014_D015_ACCEPTANCE_PENDING。** 上記の原external・旧R1/R2・v1/v2受入は履歴として保存する。上記receipt作成後の[scope改訂](../specs/2026-10-23-behavior-transformation-scope-amendment.md)と現行[task台帳](../roadmap/tasks.json)は、公開研究再利用と新規参加者研究を区別し、全公開研究へ提携/NDAを一律要求しない。旧「団体協力が未成立」の判断を、公開非個人集計のoffline検証の普遍的な新規協力必須条件へ拡張しない。公開licenseだけで実協働が成立したとも言わない。

限定候補は[Step-by-Step source-specific protocol案](../../pilot/STEP_BY_STEP_PUBLISHED_EFFECT_AUDIT_V1.md)のStep-by-Step原著Table3。source取得/engineeringは実AI agent `/root/public_behavior_reuse_applicability` が実施した。root AI `/root` の条件付用途/有限技術適用判断はUTC `2026-10-23T20:11:35.036894+00:00`、私有decision `root-purpose-and-technical-applicability-decision.md` SHA-256 `1d79b26cd6e3423d9b49ca4621f59d9b110917a9b9b6aeed1672325c8d4af31a` に実記録された。fresh別context AI `/root/public_behavior_protocol_task_review` のR1は1 Nit/0 blocking、私有receipt `task-1-review.md` SHA-256 `2cbaf08fcc2fcb4c544eafc8be69c7b204eb0b63e244fad0558d92982d592732`。3公式GETの実UTC/raw hashesと36/36値照合は新protocol §4に記録。唯一の参照語Nitは実R2でFIXED/CLOSED。実R2は同じ別context AI `/root/public_behavior_protocol_task_review` のdelta-only read-only reviewで0 findings/0 blocking、私有receipt `task-1-review-r2.md` SHA-256 `79710ab80c7f3bae0a6614b9b2628215a01627a3c6e422435fd553df1aa786fc`。source統合/実source採用とD014/D015 status受入はPENDING。この節はsource採用やtask完了を記録しない。

rootの条件付技術設計判断のscopeを保持し、今後のsource採用/受入では、原著とDANS restricted個票を別artifactとして扱うこと、固定XML/license/metadataとの実再照合、4行のendpoint/timepoint/分母/MI/RFLBの一致、UNKNOWNと著者報告の限界、[offline停止/復旧](../../pilot/STEP_BY_STEP_PUBLISHED_EFFECT_AUDIT_V1.md#5-offline停止復旧)、既存の実fresh R1/実root用途判断と最終差分確認を照合する。AI技術reviewはこの非個人sourceの技術適用範囲に限り、clinical/legal/IRB署名・原著者協働を創作しない。正式制度適用はUNKNOWN、承認/免除NOT_OBTAINEDで、制度上必要かを未確認のまま必須とも承認済みとも扱わない。

D014/D015は現在 **todo / ACCEPTANCE_PENDING**。本節は上記の実用途/技術reviewだけを反映し、新たなtask完了/検査成功/source採用eventを記録せず、状態・件数・既存依存を変更しない。[U004新規v2](../../pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md)はDRAFT/NOT_REGISTERED/参加者0のままで、公表結果の抽出能力をManagerの行動/苦しみへの効果や独立raw再現に昇格させない。source採用時の新protocol version/hashはrootの後続adoption receiptで外部から固定する。旧2protocolと5項目manifestは全文bytes保持し、旧受入を本案へ遡って適用しない。

本追記のproposal/PENDING表記と固定rights recordのR2反映前欄は作成時snapshotとして保持する。上記実R2受領を反映するが、後続source採用event・新protocol hash外部pin・task完了を先書しない。今後実採用を記録する場合も、ここより前の歴史部bytesは保存する。


## 実source採用 — 公表済み集計の有限offline protocolのみ

**ADOPTED_FINITE_PUBLISHED_SOURCE_PROTOCOL_ONLY。** root AI `/root` はUTC `2026-10-23T20:56:25.303958+00:00` に、上記最終案の正確な5paths適用・readbackと独立source統合reviewの受領後、既公表非個人Table3の出典付きretrospective検証・停止/訂正protocolをsourceとして採用した。私有実receipt `root-actual-finite-published-source-adoption.json`、SHA-256 `ba346b61ffff3b84ef0adf5c726562930b292da405348f166e24966c413a2363`。新protocol `MGR-D014-STEP-PUBLISHED-EFFECT-AUDIT-V1` の最終SHA-256は `f9154230d622965ddc82c14340b0661dbd9717e2210f2b97b2ad868d01e9e7b1`。この外部receiptから固定し、科学定義やrightsへ未来hashを逆pinしない。上のproposal/PENDINGは作成時snapshotとして保存する。

別context AI `/root/public_behavior_source_integration_review` の有限統合reviewは0 findings/0 blocking、独立静的46/46一致、receipt SHA-256 `915b0ca0c06cdb4fdee18d6365a238e4a578f185f20db3ac81d1e47f4816b20e`。実R1の36公表セル照合とR2完了を保持し、新たな原著再GET・raw統計再現・人間/臨床審査とはしない。既存rightsテスト3件、roadmap全113件、manager_coreのimport境界検査は実成功。旧16rightsのraw/canonical/順序とtop-level、旧manifest本体/全5entryを保持し、新record canonicalは `be3237789c2d498f3d31987d33a344626e425692629cc91b325729452cfddaa9`。

study_read/local_researchはこの正確なsource統合と実採用/readbackで限定条件を満たす。他用途の範囲は従前どおり。原569人をManager参加者へ数えず、著者報告B/g/CIや欠測感度分析をManagerの効果・独立したraw再現へ昇格しない。費用UNKNOWN、害の関連性は著者assessment、制度適用UNKNOWN・正式承認/免除NOT_OBTAINED・臨床承認NOT_GRANTEDを保持する。

**D014/D015はtodo / task受入PENDING、U004はDRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0、83 done /20 todo /10 skippedのまま。** 今回は限定source protocol採用であり、人研究の準備完了、実行動変容、苦しみへの便益、モデル採用や全体完成は記録しない。モデル採用HOLD、親目標ACTIVE。commit/pushの外部確認はこの実eventより後に別記録する。
