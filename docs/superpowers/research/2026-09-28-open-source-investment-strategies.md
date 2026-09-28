# 投資戦略のOSS・公開研究台帳

観測日: `2026-09-28`

## この台帳の役割

この台帳は、投資loopへ取り込む「候補の出所」と「運用上の検証規律」を分離して記録する。公開OSSのstar数、READMEの取引量、第三者のbacktest画面、表示APR、成功談は利益証明ではない。利益の判定は、選択したStrategyCard、cost-completeなout-of-sample結果、paper/shadowとの一致、公式provider receipt、実現net P&Lで行う。

この調査から、監査済みで将来利益を保証するOSS・人物・資料は見つかっていない。したがって、調査結果だけで注文、署名、送金、Binanceからの追加入金、上限拡大を行わない。

## Source ledger

| source_id | URL | license / status | mechanism or operational lesson | reproducibility | adopted_as |
|---|---|---|---|---|---|
| `oss.freqtrade` | [Freqtrade repository](https://github.com/freqtrade/freqtrade) | GPL-3.0 | strategy interface、backtest、dry-run、live運用の境界 | repoと公式docsを再読可能。コードはコピーしない | `reference` |
| `oss.freqtrade-strategies` | [Freqtrade strategy collection](https://github.com/freqtrade/freqtrade-strategies) | GPL-3.0 | 公開strategy例の構造と、教育用・as-isという注意 | sourceとlicenseは再読可能。利益は再現未証明 | `reference` |
| `docs.freqtrade.backtesting` | [Freqtrade backtesting](https://docs.freqtrade.io/en/stable/backtesting/) | docs | fee込みbacktest、dry-runとの差分、過去結果の限界 | 手順を自前harnessへ移植可能 | `reference` |
| `docs.freqtrade.lookahead` | [Freqtrade lookahead-analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/) | docs | future candle参照を検出して不正なstrategyを拒否 | fixtureで再現可能 | `reference` |
| `oss.hummingbot` | [Hummingbot repository](https://github.com/hummingbot/hummingbot) / [official docs](https://hummingbot.org/docs/) | Apache-2.0 | paper trade、controller、executor、position lifecycleの分離 | 概念を自前実装へ移植可能。実績は未監査 | `reference` |
| `oss.nautilus` | [NautilusTrader repository](https://github.com/nautechsystems/nautilus_trader) / [strategy docs](https://nautilustrader.io/docs/latest/concepts/strategies/) | LGPL-3.0 | backtest/liveで同じstrategy sourceを使う。liveはvenue・timing・persistence・reconciliationが異なる | architectureは再現可能。venue結果は未再現 | `reference` |
| `research.jegadeesh_titman` | [Returns to Buying Winners and Selling Losers](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) | published research | 株式の過去winner/loserに3–12か月のmomentum候補があるという研究 | 対象・期間・costを指定した再検証が必要 | `candidate` |
| `research.bailey_overfit` | [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | published research | 多数の候補から最大backtestだけを選ぶとoverfitし得る。holdoutと頑健性を要求 | validation fixtureとholdout gateへ移植可能 | `reference` |
| `reference.berkshire_letters` | [Berkshire Hathaway shareholder letters](https://www.berkshirehathaway.com/letters/letters.html) | company archive | 理解可能な事業を長期保有し、価格・価値・複利を区別するcore wealthの参照 | 考え方は参照可能。短期botのedgeは再現不能 | `reference` |
| `benchmark.spiva_japan` | [SPIVA Japan Year-End 2024](https://www.spglobal.com/spdji/en/documents/spiva/spiva-japan-year-end-2024.pdf) | benchmark report | active運用をbenchmarkと比較する必要を示す。coreを投機loopの実績と混ぜない | 比較指標は再読可能。将来performance保証ではない | `reference` |
| `regulator.fsa_nisa` | [金融庁 NISA investment guidance](https://www.fsa.go.jp/policy/nisa2/invest/) | regulator guidance | 長期・積立・分散をcoreの原則とし、元本割れリスクを明示 | 方針は再読可能。個別商品推奨ではない | `reference` |
| `venue.alpaca.crypto` | [Alpaca crypto trading](https://docs.alpaca.markets/us/docs/crypto-trading) / [fees](https://docs.alpaca.markets/us/docs/crypto-fees) | official venue docs | crypto spot、注文・fee・取引可能条件をcost modelの入力にする | 実行時の公式readbackで再確認 | `reference` |
| `venue.alpaca.paper` | [Alpaca paper trading](https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading) | official venue docs | paperとliveは約定・市場影響が同じではない。paperだけで利益を断定しない | paper receiptは再現可能。live parityは未証明 | `reference` |
| `venue.hyperliquid.carry` | [Funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) / [fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees) | official venue docs | fundingの支払方向、perp/spot feeをcarryのnet計算に入れる | read-only snapshotと公式receiptで再確認 | `candidate` |
| `venue.solana.fees` | [Solana fee structure](https://solana.com/docs/core/fees/fee-structure) | official protocol docs | base fee、priority fee、失敗transactionの費用をcopy tradeのcost modelに入れる | transaction receiptで再確認 | `reference` |

## Clone pins and direct README observations

2026-09-28に、次の4 repoを一時ディレクトリへ `--depth 1 --filter=blob:none --sparse` でcloneした。clone先は作業repo外であり、コードは投資repoへコピーしていない。以下のSHAは、今回読んだREADME/LICENSEの固定参照である。

| repository | observed commit | direct observation |
|---|---|---|
| `freqtrade` | `3c3b7dda0b52271cfaf9709973f873957a5e34da` | READMEはeducational purpose、資金をriskしないこと、まずdry-runすることを明記。LICENSEはGPL-3.0。 |
| `freqtrade-strategies` | `f3340ce11f5bdf62f598522e64d1f5638eaa13f5` | READMEはstrategyをeducational purpose・as-isとして扱い、backtest後にdry-runしてから資金を使うよう明記。LICENSEはGPL-3.0。 |
| `hummingbot` | `9af100d6822da7d2d0291a906c730ef172284ee2` | READMEはlive market dataを使うpaper trading scriptと、API keyを使うlive strategy controllerを分けて説明。LICENSEはApache-2.0。 |
| `nautilus_trader` | `b916d05803474adb37c15b858d7728e323526fff` | READMEは同じstrategy/execution codeをbacktest/liveで使える一方、liveにはvenue・transport・timing・persistence差があると明記。LICENSEはLGPL-3.0。 |

この直接観測は、公開OSS自身が「cloneして即利益」ではなく、paper/backtest/liveの差と資金投入前の検証を前提にしていることを補強する。Freqtradeのsample strategyにあるRSI等の指標構造は、GPLコードを取り込まず、候補仮説を自前のpure policyとして再実装するための参考にだけ使う。

## 「source says / infer / unproven」分離

### Freqtrade系

- **Source says:** strategyをbacktestした後にdry-runや実運用との差を検証する仕組みがあり、lookahead-analysisで未来データ参照を調べられる。strategy collectionは教育用・as-isで、対象pair・期間ごとの自前検証が必要とされている。
- **Our inference:** Alpaca BTC/USDC候補は、同じく明示的なentry・exit・fee・lookahead検査を持つpure policyとして再実装する。GPL-3.0のstrategyファイルはコピーせず、構造と公開された一般的な指標の出典だけを記録する。
- **Still unproven:** Freqtradeのサンプルやcollectionが、現在のBTC/USDC・5分足・Alpaca fee・この資本規模で利益を出すことは証明されていない。

### Hummingbot / NautilusTrader系

- **Source says:** paper/controller/executorを分離し、backtestとliveに共通のstrategy sourceを使える一方、liveではvenue、timing、persistence、reconciliationの差が残る。
- **Our inference:** Life Managerではpure policy、effect owner、official readback、durable receiptを別境界にする。paper/shadowが通ってもliveの利益証拠とは数えない。
- **Still unproven:** 公開repoのarchitectureを採用しても、勝てるsignal、十分な流動性、約定品質、収益は得られるとは限らない。

### Momentum研究と長期core

- **Source says:** Jegadeesh–Titmanは株式の3–12か月のwinner/loser momentumを研究している。Berkshireのlettersと金融庁の案内は、長期・理解可能性・分散・複利をcoreの考え方として参照できる。SPIVAはactive運用をbenchmarkと比較する文脈を提供する。
- **Our inference:** `core-global-index-v1`と短期venue botを別ledgerにし、積立・分散のcoreを、未検証の投機P&Lや取引資金の増加根拠にしない。momentumは株式の長期候補として記録し、5分足BTC・Solanaへの直接移植は候補扱いに留める。
- **Still unproven:** coreの長期方針でも元本割れはあり得る。momentum研究から短期cryptoの利益や`$10,000/month`を導けない。

### Carry / Solana venue rules

- **Source says:** Hyperliquidはfundingとfeeの公式仕様を公開し、Solanaはbase/priority feeを公開している。Alpacaはpaperとliveの差を明示している。
- **Our inference:** 表示APRやquote priceだけでentryしない。funding、fee、slippage、bridge/model cost、失敗費用、exit費用を差し引いたnet期待値と公式receiptを要求する。Hyperliquidのlive候補は当初BTC/ETHのallowlistに限定し、Solanaはentryだけでなくmirror-sale・hard stop・time stopを先に実装する。
- **Still unproven:** positive fundingが将来継続すること、allowlistが利益を出すこと、public-wallet copyが安全であることは未証明。高APR altcoinを選ぶ理由にはならない。

## 採用境界

### 採用するもの

1. StrategyCardに出典URL、対象、entry、exit、cost、sizing、risk、kill条件を固定する。
2. chronological train/validation/holdout、lookahead検査、fee/slippage込みnet P&L、隣接parameterの頑健性を通す。
3. paper/shadow、release SHA、公式receipt、自然wake、replay-zeroを順番に要求する。
4. Life Managerが承認済みreleaseとcap内で無人実行し、Daisへ結果だけを通知する。

### 採用しないもの

1. OSSのコードをライセンス確認なしにclone/copyすること。
2. READMEのvolume、star、他人のbacktest、成功談、APR、AIの説明を利益証拠にすること。
3. free-form modelに銘柄、threshold、exit、leverageを発明させること。
4. entryしかなくexitがないSolana copy trade、cost未知のcarry、holdout失敗のstrategyをliveにすること。
5. 旧Alpacaの`1/30`を、新しいStrategyCardの30-round-trip sampleへ自動的に繰り越すこと。

## 追加候補screen（2026-09-28T15:53:30Z）

公式Alpaca paper endpointをread-onlyでbounded queryし、2026-08-30T00:00:00Z〜2026-09-28T15:30:00Zの5分足を比較した。BTC/USDCは6,855 bars・845 indicator candles、ETH/USDCは7,715 bars・2,021 indicator candlesだった。固定notionalは`$10`、costは片側25bp fee + 5bp slippage（往復の宣言costは60bp）とした。

事前に定義した候補群は、Bollinger/RSI reversion、lower-band reclaim、RSI-open rebound、Donchian 10/20 breakout、trend pullback、volatility breakoutである。chronological 60/20/20の同一screenでは、両symbolともholdout netが正になる候補は0件だった。このscreenはStrategyCardのpassing reportではなく、最良結果だけを後付け採用していない。新cardは追加せず、`NO_STRATEGY`と追加資金停止を維持する。次の候補は、別の出典・timeframe・venueを明示してから、同じcost/holdout/sensitivity gateを通す。

## Long-window official replay（2026-09-29）

同じ公式Alpaca paper endpointでBTC/USDCの5分足を2026-06-30T00:00:00Z〜2026-09-28T15:30:00Zまでread-only取得した。CLIの64KB応答上限を越えないよう、500本chunkでの失敗を観測後、250本chunk・105 bounded queriesへ縮小した。重複を除いたcanonical fields（`t/o/h/l/c`）は20,126 bars、SHA-256は`1a00e5e02496e117419beceaf7626649d34f95d73c381fc4a916be4c97d7f713`。

固定notional `$10`、片側25bp fee + 5bp slippage、chronological 60/20/20で現行カードを再評価した。

| card | train / validation / holdout trades | holdout net | sensitivity | 判定 |
|---|---:|---:|---:|---|
| `alpaca-btc-5m-reversion-v1` | 85 / 34 / 29 | `-$2.18` | incomplete, 0/9 positive | rejected |
| `alpaca-btc-5m-trend-v1` | 23 / 8 / 7 | `+$0.13` | incomplete, 0/9 positive | rejected |

trendのholdoutが僅かに正でも、頑健性gateが不成立なのでpaper/live候補へ昇格しない。これは口座P&Lではなく、既存カードを選択しないための追加証拠であり、新しいStrategyCardや追加資金の根拠にはしない。

## Research-only ETF momentum candidate（2026-09-29）

既存のBTC 5分足とは別の出典・timeframe・universeとして、Jegadeesh–Titmanの株式momentum研究を参考に、`SPY, QQQ, IWM, DIA, EFA, EEM, TLT, GLD`を固定した。各common sessionの126日前closeからのreturnが最大の1銘柄を選び、次sessionのopenで`$10`入り、21 session後のcloseで退出する。commissionは0、slippageは片側10bpと宣言し、chronological 60/20/20、`84/126/168 × 15/21/30`の9点gridを固定した。pure evaluatorは先にテストし、decision closeより前のデータだけをsignalへ使うこと、next-open entry、duplicate/missing/cost/empty-holdoutのfail-closedを固定した。

公式Alpaca paperのIEX・split-adjusted daily barsは、8 symbolのcommon sessionsが2020-07-27〜2026-09-28の1,551件、canonical payload hashは`83d5ba8290d940f63880a2770f846a1addf19ea8632ce9ed626b73cf9490336a`だった。126/21の結果はtrain/validation/holdout `40/13/14` trades、netは`+$2.17 / +$2.21 / +$1.62`、holdout max drawdown `$1.25`、cost `$0.28`。9点gridは`9/9` positive、median holdout net `+$1.62`。片側slippage 25bpではholdout `+$1.20`、50bpでは`+$0.50`、100bpでは`-$0.90`。

これはcandidate research evidenceであり、research-only `alpaca-etf-126d-momentum-v1`を作っただけである。standard validation report、runtime daily ingestion、position ownership、stock order constraints、official paper receipt、release-pinned selectionが未完なので、selected strategy・口座P&L・30往復・追加送金とは数えない。

## 現時点の結論

- OSS・公開研究から得られたのは、候補ルールと検証規律であって、利益保証ではない。
- `alpaca-btc-5m-reversion-v1`、`alpaca-btc-5m-trend-v1`、`hyperliquid-carry-v1`、`solana-copy-v1`は候補名であり、まだ`paper`にも`live_candidate`にも昇格していない。
- 現在の次の実装cursorは、候補を機械的に表現するStrategyCard contractである。StrategyCardとcost-complete holdoutが通るまで、Binance追加資金、cap増額、live canary、30回の新規計測は開始しない。
- `30`は「30回繰り返せば儲かる」という意味ではない。選ばれたstrategyを固定した後、無人loopが自然に生成した完了round tripを測るpromotion sampleである。
