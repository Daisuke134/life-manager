# 投資paper cost-complete P&L 実装計画

## 目的

paper ETFのfilled entry/exitを、公式broker readbackと約定直前quoteに結合し、fee・slippage・model costを全て数値化できる場合だけcost-complete net P&Lとして記録する。costが欠ける場合は従来どおりpartial/unknownに留め、利益やpromotion入力にしない。

## 変更範囲

- `skills/alpaca-investment/alpaca_cli.py`: paper stockのorder、FILL、CFEEをclient order ID単位でreadbackする読み取り専用関数を追加する。
- `skills/alpaca-investment/run.py`: paper ETF effectをsealする直前に`qqq_quote`とdeterministic policyのmodel cost証拠をdecision receiptへ保存する。
- `skills/alpaca-investment/paper_performance.py`: decision receiptのquote/costと公式cost readbackから、round trip別のslippage・fee・model cost・net P&Lを計算する。qualified行のmeasurement ledger登録は後続Atomic Todo `AT-21`で行う。
- `skills/alpaca-investment/test_alpaca_cli.py`、`test_paper_performance.py`、`test_run.py`: 公式readbackの形、cost-complete計算、quote欠落時のfail-closed、effect receiptへの証拠保存をテストする。

## 実行順

1. 公式cost readbackとcost-complete計算の失敗テストを書く。
2. テストが期待どおり失敗することを確認する。
3. 最小実装を追加し、focused testを通す。
4. 全投資focused suite、`git diff --check`を実行する。
5. source branchをcommit・pushする。production release/applyは別のAtomic Todoで実測PASS後に行う。

## 完了条件

- 公式CFEE readbackが空の場合だけequity paper feeを`0`と記録できる。
- entry/exitの両方にexecution quoteがある場合だけslippageを計算できる。
- deterministic ETF policyのmodel costは根拠付き`0`、不明な経路はunknownのままにする。
- `unknown` costが一つでもあれば`measurement_status=partial`で、`net_pnl_usd`を利益として出さない。
- 全costが揃ったround tripだけを`measurement_status=measured`として出力する。measurement ledger登録とreplay identityの結合は後続Atomic Todo `AT-20`〜`AT-21`の責務であり、このsource変更では完了扱いにしない。
