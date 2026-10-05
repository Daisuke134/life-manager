# CFO item 5のsource readback（2026-10-05 15:35 JST）

## 結論

item 5は未完了です。

9月のLife Manager全社settled損益は確定できません。Stripe・Moneytree・Appleのreadbackに実費coverage不足、freshness不明、商品帰属の不一致が残っています。

このメモは3つの情報源のread-only観測を記録します。provider固有の値を会社売上や支出0円に読み替えません。

## 読取結果

| Source | Read-only readback | Attribution / freshness |
|---|---|---|
| Stripe Checkout Sessions | `GET /v1/checkout/sessions`、JST 2026-09-01..09-30、4件、全件`expired/unpaid`、`has_more=false`。paid session 0件。 | このendpointでは9月のpaid checkoutを確認できない。Balance Transaction、Invoice、他のStripe収益が0という意味ではない。 |
| Stripe B7 | CFOの既存env loader経由のread-only snapshot、`2026-10-05T06:26:59Z`、対象2026-09-05..10-05。`self-build`、company、MRRはいずれも`unknown`。 | `self-build`に必要な`browser_cost`、`infra_cost`、`model_cost`、`other_measured_cost`、`tool_cost`の5カテゴリが未充足。総netを出さない。 |
| Moneytree | `show_accounts`と`show_transactions`。JPY口座1件。2026-07-06..10-05に167件、最新取引日は2026-08-25。2026-09-01..10-05の照会は0件。 | providerの更新時刻・sync cursor・明細の完全性は応答にない。表示残高はcurrent/freshとは判定できず、空の期間は支出0を意味しない。個人口座額、口座番号、相手先、明細額は保存しない。 |
| App Store Connect | `FINANCE_DETAIL`、region `Z1`、Apple fiscal report date `2026-09`。2行、`Extended Partner Share`合計JPY 1,184。取引日は2026-05-28..06-03、settlement日は2026-05-31..06-05。 | 現行ASC app inventory 24件とのApple Identifier/SKU完全一致はない。このreportはcalendar September mobile revenueでも銀行着金でもなく、B7へ帰属しない。raw reportはGit外のmode-600 private receiptに保存。SHA-256: `ee1618889cb8155c1a665e87c6ad167d02083cc5c9cb36b214c5d5b27246426f`。 |

## 範囲と限界

外部状態は変えていません。

Stripe/ASCではread-only GET、Moneytreeでは接続済みpluginのread-only照会のみ実施しました。ledger/database書込み、CFO配信、本番設定変更もありません。

個人口座額、口座番号、相手先、明細額、credentialは保存していません。ASC raw reportだけはGit外のprivate receiptとして保存しています。

9月の会社損益とfresh cashを確定するには、revenue/refund/feeのsettlement receipt、Product Loopとcustomerのcrosswalk、全providerのactual cost、Moneytreeの更新時刻、Apple app/SKU対応が必要です。

今回のreadbackはその条件を満たしません。

次のcursorと順序は、[unified SSOTのCFO-only TODO](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md)に従います。現在cursorはA1〜A5です。
