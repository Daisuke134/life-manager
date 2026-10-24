# D011 — 同一の決済証憑を複数の機会で数えない (2026-10-25 JST)

**Status:** D011 original acceptance remains **todo**. This is one *offline, metadata-only atomic engineering increment*, not bank settlement verification or human benefit. Sole progress authority: `products/manager/docs/roadmap/tasks.json`. H005 remains **blocked** because the original 2019 HeartSteps research-calendar population cannot be reconstructed from the released dataset.

## 1. 問い → 仮説 → 反証 (imozuru)

**問い:** 個別の募集案件がそれぞれ「支払済み」を宣言している場合、複数案件の受領申告を合計してよいか。

**危険な仮説 H0:** 案件ごとの `reconcile_opportunity` に成功したなら、別案件で同じ公開決済証憑を再利用していても、件数分の受領とみなせる。

**反証ケース:** 完全に架空の job_a / job_b に同一 `receipt_source` を宣言する。案件内では証憑と承認資料を異なるファイルにできるが、案件間で同じ決済証憑を二重計上できてしまう。源泉IDだけ違う場合、URLだけ同じ場合、証憑のSHA-256だけ同じ場合も個別に検査する。

**正しい限定命題 H1:** 同じ `source_id`、URL、SHA-256が複数案件の決済証憑として現れる場合は独立性未確定として保留し、決して実入金に算入しない。一致がなくても真正な決済機関の取引ID・相手・期間・取消状況は未検証であり、入金や生活改善は証明できない。

## 2. 一次資料と代替解釈

- **Stripe公式 Webhooks — Handle duplicate events**: https://docs.stripe.com/webhooks — 同じイベントが複数回配信されうるため、処理済みイベントIDを記録して重複処理を防ぐ。これは署名検証されたプロバイダーイベント処理の話であり、Managerの公開URL/ハッシュ検査はStripeイベントの真正性検証の代わりではない。
- **Stripe公式 Balance transaction types**: https://docs.stripe.com/reports/balance-transaction-types — 返金、取消、失敗、紛争、調整などの状態を区別する必要がある。単一の「settled」申告を永続的な最終受益と同一視しない。
- **Open Collective公式 Transaction pairs/groups/perspectives**: https://documentation.opencollective.com/advanced/ledger/transaction-pairs-groups-and-perspectives — 元帳ではcredit/debit対やグループがある。表示上の行数は独立した銀行入金回数ではない。単一元帳ページに複数の正当な取引も含まれ得るため、同一URLの検出は犯罪や不正の立証ではない。

出典は公式ページへの locator。原文の長文・原著コード・第三者データを転載しない。2026-10-25時点の読取りであり、別法域への法的主張ではない。

## 3. 実装した原子的工程

- `manager_core/opportunity_receipt_portfolio.py` に `preflight_receipt_portfolio(records)` を追加。既存 `OpportunityRecord` を1–128件受け取り、同一案件スコープ・決済source ID・URL・ハッシュの重複、未受領・未決済・source不一致を固定理由コードで検出する。戻り値は **URL、金額、人数、案件ID、原票を含まない**。
- `tests/test_opportunity_receipt_portfolio.py` に架空データだけの反証テストを追加。同一決済の再使用、ID/URL/hash単独の衝突、違う証憑だが同額、未決済、同一案件、入力上限、機密文字列非出力を検証する。
- 返り値は `verified_income_minor=None`、`income_status=NOT_VERIFIED`、`beneficiary_effect=NOT_MEASURED`、`can_count_declared_receipts_as_income=False`、`can_execute=False` のまま。外部読み出しも送信も行わない。

**設計の限界:** source metadata の一致は取引IDの一致を保証しないし、独立したsource metadataでも実際の入金は保証しない。複数の取引が一つの元帳ページにあることは正常な可能性がある。したがって重複検出は独立照合に回す conservative screening であって、支払済み判定ではない。

## 4. 検証・残件

検証対象: `python3 -m unittest tests.test_opportunity_receipt_portfolio -v`、`python3 -m unittest discover -s tests -v`、`python3 scripts/check_boundaries.py`、`python3 scripts/make_roadmap.py --check`（`products/manager`から実行）。実際の hosted CI の成功/失敗とSHAはGitHub Actionsおよび実行報告を正とする。未確認のテストをここで合格と称しない。

D011原受入れには、真正な独立受領証拠、プロバイダー固有の安定取引ID、返金・重複・費用の長期的照合、合法的に公開された出典が必要。内部の宣言に追加の「支払済み」を生成しても原タスクは完了しない。

**No Human in routine loop** は外部認証情報・施設権限への依存を作らない設計原則だが、人の資金や個人記録を無許可で扱う権限を意味しない。Managerは公開非個人情報から現実のマクロ環境改善を目指し、研究、シミュレーション、現実の便益を別々に記録する。
