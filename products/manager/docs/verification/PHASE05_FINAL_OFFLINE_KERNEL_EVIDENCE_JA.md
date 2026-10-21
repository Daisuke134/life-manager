# Manager Phase05 — 最終オフライン検証報告（K001–K014）
**日付:** 2026-10-21 JST  
**正式台帳:** [tasks.json](../roadmap/tasks.json)／[再生成表示](../roadmap/ATOMIC_BACKLOG.md)  
**判定:** K001–K014 **14/14 DONE（ソフトウェア・模擬環境に限る）**。113件中 **59 done / 51 todo / 2 blocked / 1 skipped**。Life Managerとは別製品。**科学 Gate 1 は未達、実世界の受益者改善0件（未測定）**。

## 1. 受け入れ条件を変えずに検証したもの
| ID | 対応コード | 実施したソフトウェア検証 |
|---|---|---|
| K001 | `models/source.py` | 公開HTTPS、使用権、SHA256、PII分類、取得日時・改変の検証。未知/私的/古い出典を拒否 |
| K002 | `models/observation.py` | 数字が同じでも時刻・単位で別観測。欠損は理由を明示し0と混同しない |
| K003 | `models/problem.py` | 因果仮説は観測由来のsource refsが必須。別の因果説明を要求 |
| K004 | `models/intervention.py` | NO_ACTIONを常に1件保持。根拠不足は選択を棄権 |
| K005 | `forecast.py` | 分布予測TVDと無作為化試験効果ATE誤差を型とスコアで明確に区別 |
| K006 | `state_machine.py` | 不法遷移拒否。UNKNOWN_EFFECT→VERIFIEDは不可能 |
| K007 | `authority.py` | 模擬署名、発行者、範囲、期限、失効、予算検査。偽造・期限切れ・別domain・超過を拒否 |
| K008 | `outbox.py` | SQLite永続予約、同一意図10回＋同時実行／再起動でも外部送信最大1回。総額予算をtransactionで保全 |
| K009 | `reconcile.py` | PRESENT / ABSENT / UNKNOWN区分。タイムアウト後に安易な再送を行わない |
| K010 | `verifier.py` | 実行側SUCCESSだけでは不十分。別の模擬センサーの証拠元・時刻・キー・領収書照合 |
| K011 | `evaluator.py` | 比較対照・区間・費用・害・負効果を表現。単なる活動数を因果純改善と主張しない |
| K012 | `learning.py` | train/holdout分離、shadow評価、policy version、悪化時の永続的自動rollback |
| K013 | `audit.py` | source URL/rights/hash→全候補・NO_ACTION→authority→receipt→readback→evaluationの同一run監査。UNKNOWNを保持 |
| K014 | `kernel.py` + `adapters/fixtures.py` | **同一kernel**をfinance/environmentにそのまま使用。コアの権限・証拠・安全性を変更せず |

*このDONEは tasks.json の元の学習/変更/検証条件の **限定されたソフトウェア検証**。原文の条件・依存関係は編集せず、statusのみ更新した。科研/公益の実証と読み替えていない。*

## 2. RED→GREENのGitHub実測証拠
| 時点 | 実コミット / CI | 検証 |
|---|---|---|
| Test first | [2ec0f28](https://github.com/Daisuke134/life-manager/commit/2ec0f28dfa0db21442a175578003a6a1177a8220) / [Actions 39576613572](https://github.com/Daisuke134/life-manager/actions/runs/39576613572) | 既存208＋新規17テスト、後者17件が未実装モジュールで失敗（期待通り） |
| K001–K014実装 | [dfff77b](https://github.com/Daisuke134/life-manager/commit/dfff77b2ee93907aead3cd97b41a66c517c9b0ac)、[9a5ea98](https://github.com/Daisuke134/life-manager/commit/9a5ea9804bd88b4abaa6a696ddc4586b26e1d054)、[e6ca4b0](https://github.com/Daisuke134/life-manager/commit/e6ca4b04eb75bdd3388bbcf4845f99cbe5bf3a10) / [Actions 39577386834](https://github.com/Daisuke134/life-manager/actions/runs/39577386834) | 当初の模擬カーネル成功 |
| 敵対的 RED | [63637cc](https://github.com/Daisuke134/life-manager/commit/63637cc42b31e51e0eecb792b5cdbc1af14715eb) / [Actions 39577827173](https://github.com/Daisuke134/life-manager/actions/runs/39577827173) | 偽装fixture、出典鮮度、domain mismatch、監査欠落など7件の失敗を検出 |
| 安全性修正後 GREEN | [4671c15](https://github.com/Daisuke134/life-manager/commit/4671c155cc45146c80e87ce41d87b6547d173e6f) / [Actions 39578067533](https://github.com/Daisuke134/life-manager/actions/runs/39578067533) | 234テスト成功 |
| 最終2領域デモ | [e909b8e](https://github.com/Daisuke134/life-manager/commit/e909b8e9209d6f17f6347d19af2aa8778768582c) / [Actions 39578500491](https://github.com/Daisuke134/life-manager/actions/runs/39578500491) | **234 tests OK**。2領域デモ、boundary検査、Python CLI、ロードマップ整合性もSUCCESS |

CIには `python -m unittest discover -s tests -v`、`python scripts/check_boundaries.py`、`python -m manager_core`、`python scripts/phase05_demo.py --check`、`python scripts/make_roadmap.py --check` を含む。元のPhase04検証も実行。**利用者Macのローカル checkout や実世界の展開はこのセッションで試験していない**。

## 3. 再現可能なデモと失敗パス
```sh
cd products/manager
python3 -m manager_core
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 scripts/phase05_demo.py --check
python3 scripts/make_roadmap.py --check
```
入力はすべて架空のオフラインfixture。プログラムは [scripts/phase05_demo.py](../../scripts/phase05_demo.py)、固定出力は [PHASE05_OFFLINE_DEMO_RESULTS.json](PHASE05_OFFLINE_DEMO_RESULTS.json)。

| 条件 | 実際のオフライン結果 |
|---|---|
| finance / environment | 両方 `VERIFIED_FIXTURE_ONLY`、同一intent再実行でも模擬送信1回、audit chain検証OK、証明レベル **P0** |
| 根拠不足 | `NO_ACTION` / 送信0 |
| 偽造された権限 | `REJECTED` / 送信0 |
| 実行後の通信timeout | `UNKNOWN_EFFECT` / 送信1回、再送禁止 |
| 実行前の通信timeout | `UNKNOWN_EFFECT` / 模擬外部効果0 |
| 独立センサー欠落 | `MEASUREMENT_MISSING` |
| 予め設定した仮想の負の効果 | `NEGATIVE`、模擬net effect -8、P0 |
| 改善後方策が悪化 | safe-v1へ自動rollback、SQLite再起動後も復元を確認 |

## 4. 科学・安全・運用の限界
- `causal_support=True` は**模擬試験だけの注入条件**。実際のRCT因果効果、行動予測の妥当性、受益者の健康・経済・環境改善を示さない。
- 模擬grantはHMACで署名できるが、現実の権限発行元・法的権限・実資金予算・安全審査は不存在。元の`RuntimeDefaults`はすべてのlive write、送金、投稿、物理操作、私的個人データを拒否。
- SQLite outboxは「**最大1回の送信**」契約。クラッシュ前後の外部プロバイダーにおける exactly-once と世界状態の正確性は保証しない。未確認ならUNKNOWNで停止。
- 独立fixtureセンサーは現実の独立検証機関ではない。SHA256 auditはDB管理者が書き換えられるため、第三者の不可変タイムスタンプ/公開監査が未実装。
- まだ現実のcomparison/RCT、害と副作用、displacement、external verification、beneficiaries、P1/P2/P3/P4/P5は不明/未実測。未知の害は0にしない。
- **Gate1 未達成**。製品Gate2はK001–K014に加え`U005`が必要。Phase04 S001–S008の限定的研究完了は変更していない。

## 5. Phase06の具体的な次工程
- **F001:** 金融・環境と権限不要な合法的公開macro interfaceについてoperator、rights、metric、feasibilityと制御境界を列挙。許諾なしでは実行不可を明記。
- **F002:** pilotの一次アウトカム、unit、comparison、sample/n、duration、CI、spillover、cost/harmsを実験前に登録。結果に合わせた指標変更は禁止。
- **F003:** financeの第三者read-only公開台帳adapterを実装し現実の観測をfixtureと区別。
- **F004**（資金・運営主体）と **F007**（施設所有者/物理操作）は現在 **blocked**。具体的な正式許可がない限り解除しない。
- F005–F006は権限が成立した場合にのみP1/P2読戻し→因果・純効果評価。F008–F009は環境権限の取得と二領域のP2+再現が必要。
- 同時に研究Gate1の本来の人間行動予測・元RCT causal validationを独立に解く。既存H005 scientific skipを偽装して埋めない。

**Transparent Blessingを現時点で発行できる件数: 0。End sufferingはミッションであり、今回のsoftware buildがその達成を証明したとは言わない。**
