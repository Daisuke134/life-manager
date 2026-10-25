# Manager validated autonomy — current technical design

**更新:** 2026-10-22 UTC。今回のユーザー依頼で全体仕様と実行手順を更新。製品全体の規範は [MANAGER_PRODUCT_SPEC](../MANAGER_PRODUCT_SPEC.md)、研究根拠は [調査報告](../research/manager-strategy-20261022/REPORT_JA.md)。旧設計の固定版は [更新前commit](https://github.com/Daisuke134/life-manager/blob/1b7a8e5c234e4ce3c66366f34539e55844bcc0e5/products/manager/docs/specs/2026-10-22-manager-validated-autonomy-design.md)。

## 実行契約

状態と順序は `../roadmap/tasks.json` のみ。E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16。F005 → F006 → F008 → F009 は後続の証拠受入。F004/F007はskipped、成功に数えない。文書更新ではカーソル・受入・権限を変更しない。

**Goal:** 公開観測から所有デジタル資産への限定変更・独立readback・技術評価・復旧までを、通常の人手指示なしで動かす。人の便益・人間シミュレーション・事業需要の実証は別のゲート。

**Tech Stack:** product Python >=3.11、既存stdlib/dataclasses/json/sqlite3/urllib、現在のSDK契約、既存Node/Playwright/axe、所有publisher。既存GrowthBook 3.2.2、DoWhy 0.14、Concordia隔離環境を再利用。ConcordiaなどPython>=3.12が必要なupstreamをcoreへ一括依存させない。新しいagent framework・分散worker・モデル学習を既定にしない。

## 1. 研究・製品・事業を分離する境界

| 面 | 入力 | 出力 | それだけでは成立しない主張 |
|---|---|---|---|
| Research | 利用条件確認済みデータ・仮想ケース・公開論文 | 誤差、比較、仮説、negative results | 本番実行許可、因果的な実便益 |
| Product | 真正な公開観測、host-owned scope、候補、予算 | 限定intent・実receipt・公開状態差分 | 支援受領、臨床効果、市場需要 |
| Evaluation | 固定した結果定義、参照、比較群 | 条件付きの技術/予測/因果評価 | 全領域への普遍的妥当性 |
| Business | 実際の利用・課題確認・費用・顧客の意思 | 選ぶべき利用場面・継続性の証拠 | 利用者の便益、YC採択 |
| Communication | 上記の版固定された証拠 | 原稿・図・デモ・応募資料 | 未測定の結果、公開・提出の完了 |

顧客、受益者、実行資産の所有者、結果の観測者は同じとは限らない。各役割を一つのpersonaへ合成しない。

## 2. 既存モジュールを結ぶデータフロー

1. `public_observer.py`（E10実装済み）はallowlist、利用条件、HTTPS/接続先、redirect、15秒取得期限、1 MiB上限、ETag/Last-Modified、実バイトhashを検査する。本文中の命令を実行しない。
2. `world_state.py`（E11実装済み）は観測をSQLiteで追記し、旧版を保持して現在viewを生成する。48時間超の古い観測、未来時刻、訂正済み出典は現在の判断根拠にしない。取得失敗は不明。
3. `candidate_catalog.py`（E12実装済み）は公開情報のリンク訂正・アクセス性改善・ASK/PASS/NO_ACTIONに限定する。費用・結果の単位・比較・仮定を別フィールドで保持する。
4. 既存 `digital_environment.py`、`digital_handoff.py`、Playwright/axe（E13）は正しい出典、リンク、対象外route保全、script注入、baseline/candidate差分を固定基準で検証する。
5. `kernel.py`/`authority.py`から既存publisherへの接続（E14）は、host-issued standing scope・対象7パス・予算・失効・既存release参照を確認する。モデル文章やcandidateを権限発行元にしない。
6. `outbox.py`/`reconcile.py`（E15）はeffect identity、parent/target hash、送信前intent、単一owner、UNKNOWNを永続化する。応答消失時は外部の当該occurrenceを照合し、無条件で再送しない。
7. `public_good_readback.py`/`learning.py`と `run_owned_digital_cycle.py`（E16部分実装、本番接続未完了）は独立GETと実commitを照合し、技術的な成功・無変更・負・不明を評価する。悪化は停止・限定復元し、復元後も読み戻す。

現在の実装とsource-specific証跡はSSOTを参照する。既存コードの同等機能が確認できた場合は改名・複製より接続を選ぶ。実装時のインターフェース・テスト名はE計画を参照し、この文書に第二のsignature定義を置かない。

## 3. 助言providerと費用制御（E06）

Ampersandは任意のP0助言provider。API利用の継続を製品の成立条件にしない。`provider_budget.py` と `test_provider_budget.py` は既存HEADにあり、E06は監査・完成として扱う。

| 入力・障害 | 必要な状態遷移/検証 |
|---|---|
| 初回session/continuation | 各通信前に永続予約、stable request/event identity、同じbody |
| 予約上限に到達 | 新規通信0件。既存のUNKNOWNを消さない |
| tokensのusage欠落 | `None` / UNKNOWN_USAGE。請求額ゼロを推定しない |
| cache/reasoning tokens | 公式SDKの包含関係に従い、一度だけ計上。単価の版を記録 |
| 出力のない正常完了 | 明示opt-in時のSILENT_COMPLETED。通信成功・有用性・実行は別 |
| eventが届き続ける/届かない | 外側monotonic期限とtransport read timeoutの両方で有限化 |
| deadline、session/turn ID既知 | 文書化されたcancel要求→当該保存turnの独立readback |
| ID未取得の応答消失 | creation intentをUNKNOWNで維持し、公式paginationで照合 |
| cancel受付済み | 受付を完了としない。completed-before-cancel/failed/cancelled/unknownを分離 |

**費用保証の限界:** ローカル予約は新規呼出しのadmission制御で、provider請求そのものの上限保証ではない。予約に使う保守的な上限の根拠、provider側制御、課金を伴うcancel後の挙動を確認する。真の上限が証明できないものを「絶対に予算超過しない」と説明しない。liveを有効にするにはnumeric capと課金exposure/停止契約の確認が必要。不足時はlive disabled。推測の `max_output_tokens` を送らない。

この不足はE06実装と最終レビュー修正で再現検査から解消した。絶対期限、無イベント待機、created-event期限到達時のdurable bind回復を含む12 deadline testsとsource-specific CIを記録済み。live課金上限の保証とは別であり、詳細は [E06証跡](../verification/E06_PROVIDER_LIMITS_20261022.md) とSSOTのfollow-upを参照。

## 4. 評価を固定してから比較する（E07–E09）

E07はtransport、format、privacy/authority、正当なusefulness、uncertainty、interruptionを分ける。consentを尋ねる提案と実行は別。複数の妥当な選択肢を許し、重大境界違反を平均点で相殺しない。ルール評価かモデルjudgeかを明示し、judgeを使う場合は版/promptを固定し盲検の人参照との不一致も記録する。LLM自己採点だけで有用性を確定しない。

E08の既存設計は12 family × 5 variants、4 family開発/8 family評価、評価ケースごと3反復。評価側は40ケース・120 provider反復になるため、live前に実費exposureを計算する。決定的NO_ACTION/ルールと同じ観測情報を与え、予算・モデル計算量の差を開示する。独立反復はprovider乱数を完全制御できるという意味ではない。8 familyの2000回cluster bootstrapはengineering stress-testの不確実性評価であり、十分な検出力の人間試験とは呼ばない。

E09は対象task・population・language・dateに適合する参照を要する。予測分布の正規化、group/time split、Brier/TVD、validation-only threshold、coverage-risk、分布外・未対応言語のABSTAINを検証する。UCI集計予測、仮想case、人の行動予測を同じ校正保証へまとめない。参照がなければ `REFERENCE_DATA_REQUIRED`、そのままPASSEDやcalibrated-humanとはしない。

**着手前の読取準備:** E06–E08中に、既存source registryから対象適合性・権利・意味が確認できる参照候補を調べ、利用するsplitと評価対象を記録する。該当参照がなければ現順序のcursorはE09で止まり、仕様/acceptance変更を明示的にレビューする。データ不足を隠してE10へ飛ばない。

## 5. 実行の信頼性と運用（E14–E16）

所有publisherの現在のscopeを再確認し、対象外routeへ拡張しない。root configの汎用external writesを全面解禁しない。実行grant、モデルの提案、実行intent、provider receipt、公開bytesは別物である。

E15で保証するのは、実証したtarget契約の下での重複admission防止、同一occurrenceの照合、restart後のreplay-zero。ネットワークをまたぐ無条件のexactly-onceは保証しない。`ABSENT`にするには、その読取の整合性、対象識別、反映遅延と確認範囲が必要。一度のnot-foundやeventual-consistencyの空応答ではUNKNOWNを保つ。ABSENTそれ自体は再送の許可ではない。

E16の配備先はRailway単一worker＋専用volumeに決定。既存projectへの接続は確認したがManagerのruntime作成・本番adapter・実配備は未完了。配備条件はpersistent host/volume、単一owner lease、監視、停止/取消し、backup/restore、起動時reconcile、schedule catch-up-once、独立readback、限定rollback。ホスト未確認なら `DEPLOYMENT_HOST_REQUIRED`。一時CIを永続ownerにしない。既存ownerの実identityが確認できるまでschedulerを変更しない。

2026-10-25 implementation update: source now contains a separate Railway finite-cycle adapter that creates a versioned request only after current-main/current-Pages/served-byte checks, resolves prior effect and delivery records first, and sends through the protected GitHub publisher once. The older `run_owned_cycle` remains the local no-remote fixture. A pinned Docker image, private-mount preflight, and privilege-dropping entrypoint are also implemented. Railway's current docs support an hourly exiting cron job and expose the required system volume/source variables; old `railway.json` config-as-code is deprecated for new services. The service settings will be applied only to a dedicated staging service after normal main promotion. Source/unit/Docker validation is not a live deployment. E16 remains `DEPLOYMENT_HOST_REQUIRED` until real host identity, volume, secrets, workflow occurrence, served bytes, restart/restore and replay-zero are independently recorded.

学習はpolicy/versionの候補作成→隔離評価→shadow→限定昇格。権限、予算、対象、結果尺度をpolicyが拡張しない。予測誤差の減少と実便益の増加も別に検証する。

## 6. 最初の研究・顧客・発信の判断

- **問題確認:** U002の実インタビューを満たし、受益者の障壁と運営者の反復作業・費用を確認。無断の連絡は行わず、同意された会話で記録する。
- **選定:** U003は既存監視/静的リンクチェッカー/手作業で足りない問題、実行可能scope、結果観測、運営負担を比較して決める。自社ページだけで市場検証済みとしない。
- **利用試行:** 既存ツール比較、明示されたowner scope、停止/復旧、実コストと利用継続を観測。課金・契約・人研究は別の設定が必要。
- **効果研究:** U004/U006/U007の比較と結果観測が成立してから実施。十分な件数・測定適合性がなければfeasibilityと因果評価を区別する。privacyを理由に個人データを捏造せず、真正な集計や適切な自発的結果測定を検討する。
- **YC:** 実際に動くデモ、受益者/顧客仮説、試行結果、費用、失敗、次の実験。申請は全科学実証完了を待つ必要はなく、成果を誇張しない。
- **記事/書籍:** 一つの出典カード・実験receiptから日英原稿、章、スライド、図を派生。独自の結果がなければ実証論文と呼ばない。技術デモ/原稿/公開/売上を区別する。

## 7. レビューと今回の変更範囲

最初の仕様整理時点では仕様・派生計画・一次資料台帳のみを更新。その後の実装は [E16引継ぎ](../handoffs/2026-10-22-manager-e16-deployment-handoff.md) とSSOTの証跡を参照。E01–E15の技術検証とE16の参照サイクルが進んだが、本番アダプター/常駐ホスト未確認でE16は未完了。公開サイトへの今回コード配備・live推論・参加者研究・YC送信・第三者連絡・マージは実施していない。

検査は既存全suite、product boundary、roadmap生成一致、全新規相対リンク/JSON、差分が文書だけか、出典と数値の意味、古いspecへの参照。Mac専用source guardとクラウドsource snapshotの検証は同じチェックとして扱わない。


## 8. 先例再調査後の本番接続と創業者作業

[創業者実行マップ](../plans/2026-10-22-manager-founder-execution-map.md)に、12の派生work package、W27までの日付、記事/既存book/slide/carousel、実入金、採用/業務連絡/eventの証拠条件を整理した。これは新たな技術順やtask-status台帳ではない。source/current/runtimeと外部pluginの接続を混同しない。Railway volumeのreplica不可・redeploy小停止を許容する単一worker設計で、無停止HAとは説明しない。

本番adapterの前に、未解決intent全件drainを新plannerより先にする設計と、schedule slot保存直後crash、候補変更/期限切れでも旧UNKNOWNを照合するテストを追加する。現在sandbox経路のコード読取から得た未確認保証であり、実測bugと断定しない。元publisher/ref/artifact gateを保ったcloud ownerとして登録し、Git CAS・独立GET・復元証拠で受入を判定する。
