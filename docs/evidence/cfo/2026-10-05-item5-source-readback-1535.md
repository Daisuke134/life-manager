# CFO item 5 source readback — 2026-10-05 15:35 JST

## 結論

item 5は未完了です。9月のLife Manager全社settled損益は確定できません。

Stripe、Moneytree、Appleの再読結果を下にまとめます。空の応答、fiscal report、Checkout Sessionの状態を0円や会社売上へ置き換えません。

## 読取結果

| Source | Read-only readback | Attribution / freshness |
|---|---|---|
| Stripe Checkout Sessions | `GET /v1/checkout/sessions`、JST 2026-09-01..09-30、4件、全件`expired/unpaid`、`has_more=false`。paid session 0件。 | このendpoint内で9月のpaid checkoutは確認されない。ただしBalance Transaction、Invoice、他のStripe収益が0という意味ではない。 |
| Stripe B7 | CFOの既存env loader経由でlive Stripe GET。snapshot `2026-10-05T06:26:59Z`、対象は2026-09-05..10-05。`self-build`とcompanyは`unknown`、MRRも`unknown`。 | `self-build`は`browser_cost`、`infra_cost`、`model_cost`、`other_measured_cost`、`tool_cost`が未充足。総netを出さない。 |
| Moneytree | `show_accounts`と`show_transactions`。JPY口座1件。2026-07-06..10-05に167件、最新取引日は2026-08-25。2026-09-01..10-05の照会は0件。 | providerの更新時刻・sync cursor・transaction completenessは応答にない。表示残高はcurrent/freshとは判定できず、空の期間は支出0を意味しない。個人口座額、口座番号、相手先、明細額は保存しない。 |
| App Store Connect | `FINANCE_DETAIL`、region `Z1`、Apple fiscal report date `2026-09`。2行、`Extended Partner Share`合計JPY 1,184。取引日は2026-05-28..06-03、settlement日は2026-05-31..06-05。 | 現行ASC app inventory 24件とのApple Identifier/SKU照合は0件。これはcalendar SeptemberのLife Manager mobile売上でも、銀行着金でもなく、B7へ帰属しない。raw reportはGit外のmode-600 private receiptに保存。SHA-256: `ee1618889cb8155c1a665e87c6ad167d02083cc5c9cb36b214c5d5b27246426f`。 |

## 実施範囲と次のcursor

行ったのはStripe/ASCのread-only GETとMoneytree照会だけです。provider mutation、ledger/database write、CFO配信、production設定変更はありません。ASC raw reportはGit外のprivate stateに保存しています。

次は既存順序の§87-J item 5を続けます。Stripe履歴のProduct Loop crosswalk、Moneytree freshness/cursor、Mobile SKU/RevenueCat coverage、Capafy等のreceipt/payout/cost joinが残っており、item 6以降にはまだ進みません。
