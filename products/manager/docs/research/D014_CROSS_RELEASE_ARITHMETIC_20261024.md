# D014 — 複数の公開集計の差分リスク（一次資料と合成テスト）

**確認:** 2026-10-24 JST。独立製品 Manager、D014 原子タスク。
**進捗の唯一の正本:** `docs/roadmap/tasks.json`（69 done / 41 todo / 3 blocked）。D014 は `todo`、H005 は `blocked` のまま。個票、実験参加者、外部書き込み、実地介入はなし。

## 問い・仮説・反証（imozuru）

**問い:** それぞれ単独では複数の集計セルを伏せている公開表でも、二つの表を重ねると伏せた集計値が計算できるか。

**仮説:** 「単独表で秘匿セルが複数ある」だけでは、他の公開表との差分から集計値を導く推定リスクを排除できない。

**完全に架空の反例:** 同一集団・同一期間・同一3区分・総数100という未認証の条件を仮定。表Aの alpha=60、beta/gamma=非公開。表Bの gamma=35、alpha/beta=非公開。単独の `preflight_public_aggregate` はどちらも `REVIEW_REQUIRED` だが、二つを合わせると beta=100-60-35=5 と算術上特定できる。現実の人の再識別事例を発見したという意味ではない。

**競合仮説・限界:** 二つの実資料が同じ母集団・期間・定義だと確認できない場合、その引き算は無効。説明文が一致しても、実際の標本・集計方法の同一性は証明できない。丸め値、摂動、時系列の重複、外部知識、別の分類階層などはこの限定検査では解決しない。

## 一次資料（2026-10-24に公式ページを再確認）

1. ONS 公的統計の秘匿方針 https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics — 類似する公開表の差分・リンク・二次抑制の必要性に言及。英国の出生死亡統計に関する方針であり、日本の一般研究の法規則と誤認しない。
2. ICO 匿名化の有効性 https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/ — 他の公開資料との結合で特定できる可能性の文脈的審査を示す。同公式ページは法改訂により見直し中と表示する。

## 今回の技術的原子タスク

- `manager_core/public_aggregate_cross_release.py`: 既存の1表の厳密な `Source` メタデータ検査を再利用し、2表のメタデータ・同一区分・数値整合を確認する純粋関数 `preflight_cross_release` を追加。1表で伏せた数が別表で公開された場合と、統合後の秘匿値が計算できる場合を拒否。異なる期間・区分・数値の表からは推論せず `REVIEW_REQUIRED`。
- `tests/test_public_aggregate_cross_release.py`: 13件の架空データによる反証テストを追加。危険検出、過剰な同一視の防止、秘密の文字列・集計値を結果に戻さないことを確認。
- GitHubコミット: 実装 `e9e4778973a36a927dd1815c6027dcc69fcfa25f`、テスト `907074a3b74c4b7c191a203de999315280af7e52`。
- [GitHub Actionsの実行ログ](https://github.com/Daisuke134/life-manager/actions/runs/40039720581): 成功。 `Ran 500 tests` / `OK (skipped=5)` / `PASS 113 tasks; task JSON untouched`。これはコードの検証であって倫理審査や実世界の便益実証ではない。

## 科学的・法的な非達成条件

検査結果は `can_ingest=false`、`can_publish=false`、`can_execute=false`、`disclosure_certified=false`、`consent_or_ethics_approved=false`、`beneficiary_effect=NOT_MEASURED` を常に保持。発行者・許諾・研究倫理・同一集団・すべての過去の公開物をソフトウェアだけで認証できるわけではない。

したがって**D014の原タスクは未完了**で、適法な協力・倫理判断・公開集計の真正性が必要。2019年HeartStepsの原解析日を復元できないH005は `blocked` のまま。F004/F007の外部権限条件も維持。研究成果P0、実介入P1/P2、独立した人の受益P3、因果的な純便益P4を混同しない。
