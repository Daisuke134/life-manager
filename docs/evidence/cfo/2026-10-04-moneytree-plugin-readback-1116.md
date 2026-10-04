# Moneytree plugin readback — 2026-10-04 11:16 JST

状態: 接続済み、個人cashの鮮度は`partial/stale`。

## 読み取り結果

- 接続済みMoneytree pluginのread-only `show-accounts`は、MUFG普通預金（savings/ordinary）のJPY口座1件を返した。
- `current_balance`と`totalBalance`は返ったが、口座responseにsource-updated timestampは無い。個人残高の正確な値はrepository evidenceから除外する。
- read-only `show-transactions`の検索期間は2026-07-04..2026-10-04。`totalCount=183`だが、降順クエリで今回取得したのは最新10件だけであり、183件全件を取得・再集計したものではない。
- 最新の取引日は2026-08-25で、従前の読み取りから新しい取引行は確認できない。sync cursorやsource freshness timestampも無い。11:16 JSTは読み取り時刻であり、銀行/providerの同期時刻ではない。

## CFOへの反映

- Moneytreeの表示残高はlast-knownとして扱い、今日の検証済み銀行残高とは扱わない。鮮度項目は`partial/stale`のままとする。個人残高の正確な値はrepository evidenceに保存しない。
- これは個人cashの観測であり、Life Manager売上・利益の証拠ではない。欠落した期間をゼロへ置き換えない。
- login、phone、pairing、設定・account dataの変更は行っていない。口座番号、取引description、credential、raw payloadは掲載しない。
- TODO・順序・状態の正本 → [統合SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md)。この文書に別のTODOを作らない。

## 2026-10-04 transaction-coverage follow-up

- 14時台のread-only `show-accounts`も銀行口座1件・投資口座0件を返した。残高のsource-updated timestampは引き続き無く、fresh判定にはならない。
- `show-transactions`を同じ2026-07-04..2026-10-04期間で`limit=1000`指定すると`totalCount=183`かつreturned rows=183となり、このqueryの全行を取得できた。ただし実データの最古日は2026-07-04、最新日は2026-08-25で、9月・10月の銀行取引は含まれない。sync cursor/source timestampは無い。
- Spending summaryは7月・8月の期間bucketだけを返し、9月・10月は欠落。取引明細には`振替`・`返済`と`未定`があり、銀行のinflow/outflowをそのままLife Manager売上・実費へ分類できない。個別の金額・取引内容・口座番号はこのfollow-upに保存しない。
- 接続・設定・account dataに変更なし。Moneytreeの表示残高と銀行明細はlast-known/partialのままとし、Life Manager日次CFOのfresh cashや全期間支出とは扱わない。

## Life Manager adapter path follow-up

- `origin/main` and deployed source SHA `655b2cf2001ad54ce70cb975910f363091052651` contain the same `moneytree-local-adapter.js` blob. A local read-only invocation through `codex app-server` and `codex_apps` returned one account and 183 normalized transaction rows for the requested range; this did not persist a report or write a financial ledger.
- The deployed-source adapter records retrieval time and payload digest but does not carry provider `source_updated_at` or explicit transaction-completeness metadata. Therefore adapter output alone cannot prove fresh balance or complete current-period transactions.
- At the deployed source SHA, only transactions whose exact category name is `振替` receive `transfer_id`; rows classified under parent category `返済` do not. The unmerged CFO candidate branch adds fail-closed source-freshness/completeness fields and treats parent `返済` as transfer. This candidate improvement is not production behavior until the approval gate, branch synchronization, acceptance, and merge are complete.
- The current local read-only probe confirms tool reachability only; no scheduler occurrence, persistent evidence write, report delivery, or production behavior was verified.

## 2026-10-04 one-year coverage follow-up

- A fresh read-only `show-accounts` still returned one MUFG bank account; the response still has no provider source-updated timestamp. The displayed amount is intentionally omitted from this repository evidence.
- `show-transactions` was read across four non-overlapping windows covering 2025-10-04..2026-10-04. All four queries succeeded and returned 178, 311, 316, and 183 rows (988 total). The returned transaction dates span 2025-10-04..2026-08-25; no transaction dated after 2026-08-25 was returned despite the requested end date of 2026-10-04.
- The 12-month spending-summary query returned 11 monthly buckets, 2025-10 through 2026-08. September and October 2026 buckets are absent. This is not a complete current-period expense total.
- No account numbers, transaction descriptions, individual rows, or private amounts were stored. No Moneytree setting, account data, login, or sync state was changed.
- Extending the query window does not fix the source freshness/completeness gap. Keep personal cash and bank spending `partial/stale`; do not treat bank inflows/outflows as Life Manager revenue or provider cost. The readback is source evidence, not a persisted CFO report or ledger write.
