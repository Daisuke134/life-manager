# CFO live observability readback — 2026-10-05

## 判定

CFO全体のcloseは未達。source-complete ledgerのcursorはunified SSOT §87-J item 5を維持する。candidate projection、部分的に確認できたlocal delivery、cloud pre-effect deferは、それぞれ別の証拠として扱う。

## B7 candidate projection

- `python3 skills/cfo/loop_pnl.py --date 2026-10-05 --json`をread-onlyで実行。snapshotは`2026-10-04T16:08:34.196154Z`（2026-10-05 01:08 JST）。historical/trailing gapsは137/137、14/14 loopsは`unknown`、MRR/runwayは`unknown`。
- gap reasons: `missing_category` 127、`read_failed` 4、`source_unconnected` 5、`missing_coverage` 1。affiliate-financial-record、capafy-orders、actual-cost-readback、stripe-financial-recordはread failure。ASC financialはcoverage不足。x402、Coconala、CrowdWorks、Lancers、Alpacaは未接続。
- これはproduction wrapper/natural reportではない。in-memory duplicate receipt count 0はprovider replay-zeroを証明しない。

## Personal source coverage

- 接続済みread-only Moneytree pluginは銀行口座1件を返したがfreshness timestampは無い。2026-07-05〜10-05 queryの177 rowsは2026-08-25で終わり、monthly summaryも7〜8月のみ。
- 残高はlast-known/stale、2026年9〜10月のtransaction/expense coverageはunknown。plugin tool surfaceにsync/refresh操作は無い。個人残高や取引明細は記録しない。

## Natural occurrenceと配信

- 2026-10-05 00:58 JSTのlocal CFO occurrenceはruntime event exit 78、`effect=unknown`、provider receipt referenceなし。同一occurrenceのlocal result/outbox stateは`sent`/`delivered`。
- MTProto dialogの約00:58:21 JSTのメッセージは先頭500文字が一致したが、保存された本文全体は照合していない。判定はpositive delivery evidence with partial corroboration、runtime telemetry/linkage gap。再送しない。
- 保存reportはhourly cadenceでありdaily CFO reportではない。daily自然run完了として数えない。
- 01:08 JSTのcloud financial-report ownerは`resource_fifo_wait`・exit 75でprovider前にdeferし、receiptは無い。retry/restart/sendは行わない。

## Capafy seller order-count readback — 2026-10-05 02:10 JST

- Same-window read-only queries used 2026-09-04..2026-10-03 UTC. Seller `/app/sales/clickhouse/trend` returned 30 rows, gross USD 82.77, refunds USD 0, and source order sum 81. Its row-order subtotals by daily revenue sign were positive +68, zero +16, and negative -3; these sum to 81.
- Unit-sales `/app/unit-sales/clickhouse/trend` returned 30 rows with total sales volume 81, free-trial count 53, and non-trial units 28. These units are not renamed as paid orders.
- At read time `_seller_money()` filtered row orders to `revenue > 0`, yielding 68; `_window_totals()` sums all rows. `capafy_company_receipt` renders the root receipt's `orders` field, so the filter undercounts a user-visible count. Source correction contract: sum all seller `orders` rows while keeping revenue/refund/unit fields unchanged.
- This was a read-only provider response; no raw row, credential, account identifier, state, ledger, Telegram delivery, retry, or release mutation occurred. `crwl` retrieved only the Capafy app shell, so the exact contract here is grounded in observed API fields and existing same-window unit-sales behavior, not a fetched prose definition.

## Candidate source correction — 2026-10-05

- Candidate code removes the revenue-sign filter from `_seller_money()` so the root `orders` field sums every seller row. Regression test `test_receipt_counts_orders_from_zero_and_negative_revenue_rows` covers positive, zero, and negative revenue rows while keeping gross unchanged. The initial RED case expected 9 and got 2; the normalized final fixture uses source counts `2 + 3 - 1 = 4` and gross `$9.99`.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest skills/earn/capafy-marketing/tests/test_capafy_hourly_reconcile.py -q` passes 42 tests. This source/test correction remains candidate-branch-only and is not production-loaded; no natural owner run, report delivery, or provider mutation was performed.

## Capafy OpenRouter actual-cost scope — 2026-10-05 02:40 JST

- Existing candidate code queries `/api/v1/activity` with an OpenRouter management key and no filters. Official documentation states this aggregates across workspaces by default; `api_key_hash` and `workspace_id` filters are available.
- Read-only current identity check used the existing mode-600 `.env` in memory only: the host-key label matched exactly one `/keys` row within the same workspace. The filtered activity GET returned 222 rows and USD 25.08 over returned activity dates 2026-09-07..2026-10-03. Key values, hash, label, workspace ID, and raw rows were not printed or persisted.
- USD 25.08 is key-scoped provider usage, not an invoice or paid settlement. The current unfiltered candidate code still does not provide valid Capafy attribution, and this row-extent does not by itself prove an exact seller-revenue profit window. The next source fix is unique host-key-to-key-record matching, filtered activity read, and fail-closed behavior if the mapping is missing/ambiguous.
- Source references: [OpenRouter Activity API](https://openrouter.ai/docs/api/api-reference/analytics/get-user-activity-grouped-by-endpoint), [OpenRouter List API Keys](https://openrouter.ai/docs/api/api-reference/api-keys/list-api-keys), [management-key scope](https://openrouter.ai/docs/guides/overview/auth/management-api-keys).

## Source cursorと次の順序

- 別mobile candidate worktree/branch `feat/lm-mobile-metrics-20261003`のread-only source audit（observed worktree HEAD `1f045eff3d27cfec3945cd8d2dff64f06928c834`）では、candidate側の`business_outcomes.py`がRevenueCat currencyを保存し、exact `revenue_definition` objectが不足すると確認した。lease record HEAD `9be7a8a368f8edab9b1937d0c19cd9253d891b94`とは不一致であり、現CFO branch/productionへの反映は未確認。JSONL round-trip testも不足。mobile worktreeは編集しない。ASC report row SKUとexisting crosswalkの不一致が解決するまで、対象proceedsはunattributed・B7外に置く。
- Google September CSVのinvoice header readbackは既存証拠にある。candidate parserは請求月をまたぐCloud Storage行をservice subtotalから落とすため、item 6でregression testとparser fixが必要。invoiceは支払証明ではない。
- 次cursorは§87-J item 5のsource attribution/coverageとMoneytree freshness/cursor。続いてitem 6のGoogle actual-cost reconciliation、item 7のformal promotionとnatural daily receipt/replay-zero、item 8の7日観測を既存順で進める。
- 参照: [loop_pnl.py](../../../skills/cfo/loop_pnl.py)、Google billing evidenceは[既存readback](2026-10-04-google-cost-table-readback.md)。RevenueCat currencyの所見は別mobile candidate branch/worktree `feat/lm-mobile-metrics-20261003`のread-only audit、observed commit `1f045eff3d27cfec3945cd8d2dff64f06928c834`に限る（lease record HEAD `9be7a8a368f8edab9b1937d0c19cd9253d891b94`と不一致。CFO branch/production反映は未確認）。個人残高、金額、transaction detail、provider IDsは保存しない。
- 2026-10-05 candidate correction: `/keys` is traversed by `offset` until a confirmed empty page (max 100 pages); every row must contain non-empty string `hash`, `label`, and `workspace_id`, otherwise scope fails closed and `/activity` is not called. Activity uses both `api_key_hash` and `workspace_id`; every activity row requires a valid `YYYY-MM-DD` date and explicit finite nonnegative `usage`. Malformed rows, Decimal overflow, and amount-conversion failures remain unavailable, never zero.
- The 30-day actual cost/profit is withheld unless the valid activity date extent matches the seller window. The observed key-scoped USD 25.08 dates 2026-09-07..2026-10-03 do not match the seller window 2026-09-04..2026-10-03; no same-period actual cost/profit is claimed. Per-skill actual allocations use estimated list-price shares and are not agent-level measured bills.
- Fresh focused suite: 62 passed. Independent read-only review: PASS, no Critical/Important/Minor findings in the reviewed source diff. Candidate branch only; no production load, natural owner run, provider call for this correction, invoice, or settlement proof.
