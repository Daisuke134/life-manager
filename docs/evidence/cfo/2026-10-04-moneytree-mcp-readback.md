# Moneytree MCP readback — 2026-10-04

Status: `partial/stale`; read-only account and transaction calls succeeded on retry, but transaction freshness is not current.

## Sanitized provider observations

- Read window: 2026-07-04 through 2026-10-04, Asia/Tokyo; read around 07:37–07:39 JST.
- Connected accounts: one MUFG ordinary JPY account.
- The account endpoint returned `current_balance=JPY 504,302` and `totalBalance=JPY 504,302`. It did not include a source update timestamp or transaction-completeness cursor.
- The local Financial Manager store's latest durable verified MUFG balance observation is `2026-09-26T12:27:37Z` (21:27 JST), also JPY 504,302. Today's plugin result matches it but does not prove that the bank/provider value was refreshed today.
- The same-window income query returned 11 rows, latest 2026-08-25. Nine rows classified as income sum to JPY 806,201: salary JPY 673,569, general income JPY 130,820, and interest JPY 1,812. Two unclassified transfer rows total JPY 18,455 and are excluded from income.
- The expense query returned 172 rows, latest 2026-08-25. Categorized expenses sum to JPY 205,500: `未定` JPY 200,000, ATM withdrawals JPY 3,000, and social expense JPY 2,500. Unclassified transfers total JPY 425,456; card repayments total JPY 34,164. These are excluded from spending to avoid counting account transfers/card settlement as a second expense.
- The spending-summary response contains July 2026 (JPY 102,000) and August 2026 (JPY 103,500) only; no September or October bucket was returned. A separate transaction query for 2026-08-26 through 2026-10-04 returned zero rows.
- The latest transaction balance is also JPY 504,302 on 2026-08-25. The current plugin value and latest durable balance observation both match that amount, but neither supplies an independent source-updated timestamp.

## CFO interpretation

These are source-returned last-known values, not today's verified personal cash, complete current spending, or Life Manager company revenue. Moneytree did not provide an independent `source_updated_at`, refresh receipt, or complete transaction cursor. Keep the balance and flows `stale/partial`; do not render September/October as zero, and do not treat salary or personal income as Life Manager revenue. Several connector calls transiently failed; later read-only retries succeeded without establishing freshness.

No account number, transaction description, credential, or raw provider payload is stored here.

## Supplemental direct readback — 2026-10-04 08:37 JST

- Read-only `show-accounts` returned one MUFG ordinary JPY account with displayed `current_balance=JPY 504,302`. The MCP response has no source-updated timestamp or bank-sync cursor; the value is not verified as today's bank balance.
- The account-scoped `show-transactions` query for 2026-07-04 through 2026-10-04 reported `totalCount=183` and returned all 183 rows. The newest returned transaction is 2026-08-25, and its row balance is JPY 504,302. The successful query is complete for the connector's returned period, but the data itself stops at 2026-08-25.
- Raw positive rows: 11 / JPY 824,656 (salary JPY 673,569; general income JPY 130,820; interest JPY 1,812; transfers JPY 18,455). Excluding transfers leaves categorized personal income of JPY 806,201; neither figure is Life Manager business revenue.
- Raw negative rows: 172 / JPY 665,120 (transfers JPY 425,456; card repayments JPY 34,164; `未定` JPY 200,000; ATM withdrawals JPY 3,000; social JPY 2,500). Excluding transfers and card repayments to avoid double-counting leaves JPY 205,500 categorized spending; the JPY 200,000 `未定` category remains an expense with unknown purpose.
- The spending-summary payload includes July JPY 102,000 and August JPY 103,500 only. It returns no September or October period bucket; those periods are unavailable, not zero.
- Read timestamp is the MCP call time, not a provider/bank synchronization timestamp. No account number, transaction description, credential, or raw provider payload is stored here.
