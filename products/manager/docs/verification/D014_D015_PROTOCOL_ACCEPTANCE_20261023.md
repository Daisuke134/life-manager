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
