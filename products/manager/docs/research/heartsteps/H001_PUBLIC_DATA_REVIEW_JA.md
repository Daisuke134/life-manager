# H001 — HeartSteps の公開データ構造・利用条件の監査

**2026-10-20 JST | Manager — End suffering. | status: schema and rights review only**

> L001–L012 はすべて合成データの学習。H001 は本物のデータが「どのように作られ公開されているか」を調べる段階。**生の参加者行データは取得していない。** 現実の予測精度や介入効果を再計算したものではない。

## 1. 何を1件と数えるのか

2019年の HeartSteps 論文は募集44人・解析対象37人・6週間。**データの1行は1人ではなく、1人のある時刻の介入判断**である。研究チームの README は `suggestions.csv` を **8,274 行×86列**と報告している。これは37人×複数の時点を表す。論文の主要解析に用いられた6,061時点とは異なり、選択条件をまだ自分のコードで再現していない。

出典：[https://github.com/klasnja/HeartStepsV1 README](https://github.com/klasnja/HeartStepsV1/blob/3016391de426116bdef41880d72bc8cd4b9b2477/README.md)、[論文](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/)。

## 2. 4つの公開CSVと用途

| ファイル | README記載の形 | 用途 | 最初の方針 |
|---|---:|---|---|
| `suggestions.csv` | 8,274 × 86 | 介入の判断、利用可能性、提案/送信、30分前後の歩数 | **H002以降の読み取り対象** |
| `users.csv` | 37 × 117 | 個人属性、開始/終了アンケート | **取り込まない** |
| `jbsteps.csv` | 237,865 × 10 | Jawboneでの分単位歩数 | **まだ取り込まない** |
| `gfsteps.csv` | 197,524 × 7 | Google Fitでの分単位歩数 | **まだ取り込まない** |

数字は**READMEによる報告値**。実CSVのヘッダー・行数をこちらで検証した値ではない。Wikiの記述は `users.csv` を37×120、`jbsteps.csv` を237,865×11、`gfsteps.csv` を197,524×8としており、READMEと食い違う。どちらも実データの列数としてはまだ確定させずH002で照合する。

公式Gitのソースcommit: `3016391de426116bdef41880d72bc8cd4b9b2477`。各CSVのBlob SHA・サイズは[機械可読マニフェスト](H001_PUBLIC_DATA_MANIFEST.json)へ固定。

## 3. 解析に必要な最小列候補（Wikiに記載された名前）

| 役割 | 最小候補の列 | 注意 |
|---|---|---|
| 参加者の反復を束ねる | `user.index` | 擬似IDでも個人単位のデータ。個別の行は公開しない |
| 判断の順序 | `decision.index`, `decision.index.nogap`, `sugg.select.slot` | タイムゾーンで想定・実際の枠がずれる場合がある |
| 介入できるか | `avail`, `connect` | 介入不可と無介入割付は異なる |
| 抽選・送信 | `is.randomized`, `send`, `send.active`, `send.sedentary` | **抽選・通知送信・提案種類を同一列だと仮定しない** |
| 主要な結果 | `jbsteps30`, `jbsteps30.zero` | 30分歩数。`.zero`は欠測補完済み値 |
| 直前の活動 | `jbsteps30pre`, `jbsteps30pre.zero` | 介入前歩数と欠測補完は別に扱う |
| 取得の鮮度 | `is.prefetch`, `sugg.decision.slot` | 接続不良時の古いコンテキストの可能性 |

**これは列の候補表であり、実際のCSVヘッダーとの突合せはH002/H004で行う**。元の著者Rコードは `user`・`study.day.nogap`・`decision.utime` 等の別名を使う。公開CSVの `user.index` などと一対一に一致するかはまだ不明。

[Wikiの列定義](https://github.com/klasnja/HeartStepsV1/wiki/Documentation-for-suggestions.csv)、[著者の解析コード](https://github.com/StatisticalReinforcementLearningLab/HeartstepsV1Code/blob/c077c86d20b5d9cfa937f7ed1720172d726ba9a0/Main%20Effects%20Analysis.R)。

## 4. 利用条件とプライバシー

- データ公開リポジトリのライセンス原文は **CC BY 4.0**。研究利用は帰属表示などの条件を守り、個人に関する権利を別に検討する。これは法律上の包括許諾や倫理承認を意味しない。[原文](https://github.com/klasnja/HeartStepsV1/blob/main/LICENSE)
- 公開済みのデータであっても `users.csv` の属性、GPS由来の `dec.location.exact` と `response.location.exact`、アプリ名 `front.end.application`、正確なタイムスタンプなどは不要な限り取り込まない。
- 生CSV、参加者の元回答、位置情報・詳細時系列を GitHub、ブログ、Library、共有クラウドへ複製しない。
- 原論文本文と元R解析コードには**データと異なる著作権・再利用条件**が適用される。R006で既にコードの無条件のコピー許諾を保留済み。
- Manager実行製品は公開情報のみを使うという方針。ここで研究方法として歴史的な参加者データの公開スキーマを読む行為を、実際のManager利用者の非公開データ収集につなげない。

## 5. 未解決事項とH002への受け渡し

1. 実CSVヘッダー、データ行数、空欄値の表現、対応する版を正確に確認する。
2. 元RData用の名前 `study.day.nogap` と、新CSV用の名前がどう対応するかをソースで照合する。
3. 介入可能 `avail`、無作為化 `is.randomized`、実送信 `send`、種別 `send.active`／`send.sedentary` の意味を確認する。
4. 論文の解析対象6,061時点になるフィルタを**H005で**再現する。H002の行数が一致しても論文再現完了としない。
5. `jbsteps30.zero`は欠測をゼロ補完した値なので、欠測と真のゼロを別に保存する。

**H002の契約:** 固定commitのrawを読み取り専用で確認し、SHA256とヘッダー・行数を記録する。参加者の行を画面・ログへ表示しない。raw保管が必要ならGit管理外のローカル `data/raw` に限り、再配布しない。H002で改めて取得方針を確認する。

## H001の完了条件

- [x] 公開CSVの種類・用途・バージョンを一次資料で確認。
- [x] 主要データの役割と**必要最小限の列候補**を公式Wikiの列名で記録。
- [x] ライセンス・研究目的の範囲・不要な個人情報・非再配布方針を明記。
- [x] README/Wikiと分析コードの差は推測で埋めず次タスクへ渡す。
- [x] 生データを取得・再配布していない。

**研究の進捗≠本物の人間への効果。** Managerの実世界の介入・人間への便益はまだ実証されていない。