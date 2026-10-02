# Manager 調査 — 企業・実証都市・現在のサイトとソース

調査日: 2026-10-02 UTC。公開一次資料の読解とソース確認。サービスの実行、顧客データへのアクセス、独立した追試は行っていない。以下の業績・精度は各発信者による報告であり、Managerの成果ではない。

## 1. この調査で修正された理解

「Aaru / Simile は予測だけ、Manager は実行まで」という二分法は、競合の公式説明を正確に表していない。両社とも意思決定支援、実際の行動データ、検証を扱う。Simileは顧客データを用いて実際の行動とのループを閉じると説明する。Managerの差別化仮説は、**受益者のアプリ利用・個人認証を必要とせず、許可された環境を継続的に変更し、費用と副作用を含む実測で改善を証明する運用主体**である。まだ実証された差別化ではない。

「Similie」は今回の文脈ではJoon Sung Parkが共同創業した **Simile** と同定した。Praxisはpraxisnation.comのdigital nation構想を対象にした。名前が似た別プロジェクトには一般化しない。

## 2. Aaru

一次資料:
- [公式トップ](https://aaru.com/)
- [About / John Kessler](https://aaru.com/about)
- [Population simulation at the replication floor — research, 2026-09-24](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
- [同じ調査の要約](https://aaru.com/publications/population-simulation-at-the-replication-floor-summary)

### 仕組み

人口・行動・結果のデータで集団を構築し、製品、価格、メッセージ、戦略などの条件を変えて反応を評価する。研究記事は、個々の行動軌跡を予測するモデルと人口生成モデルはlanguage modelではないと明記している。したがって「多数のLLMに人物設定を与えればAaru相当になる」とは言えない。

### 報告された検証

| 検証 | 発信者が報告する値 | 対象と解釈 |
|---|---|---|
| 質問への回答分布 | 2,993 questions、186 studies、13,727 answer shares | 9産業にまたがる質問ごとの一変量分布。複数回答間の相関や個人行動全般を証明しない |
| 未調整の誤差 | mean MAE 3.53 percentage points、mean TVD 7.62 points | TVDは分布の距離。「人間行動を92.38%理解」といった変換は禁止 |
| 標本誤差を差し引いた値 | MAE 2.78 points、TVD 5.98 points | 正規近似、design effect=1、欠損標本数の補完を含む。未調整の実測誤差と分けて表示する |
| 購買の順位 | 100 brand-period observations、14 groups、340 brand pairs。92.4%の順位一致 | カードパネルに対するブランド順位。個人の購入予測や価格介入の因果効果ではない |
| 信頼度で選別 | 高信頼の約51%を残すとmean observed TVD 4.54 points | 精度だけでなくcoverage低下も報告する必要がある |

Exaのタイムスタンプ付き取得、質問の調査開始前の情報制限、発信元ドメインの除外などを説明している。学習混入を避ける設計として参考になる。ただし公開記事の読解だけでは、全データ・重み・追試可能性を確認したことにはならない。

SimileとのAUROC比較は **別の評価セット同士**。同一条件の直接対決として引用しない。0.845 / 0.848の違いは16 TVD pointsの境界条件の違いであり、書き間違いとして扱わない。

### Managerへの示唆

時間で区切ったholdout、分布の誤差、信頼度とcoverage、現実の行動による評価を採用する。既存の回答分布の再現と、未実施の介入効果の予測は別トラックにする。学習資料に答えが含まれる評価を避ける。

## 3. Simile

一次資料:
- [公式トップ](https://www.simile.com/)（simile.aiからredirectを確認）
- [Building confidence in Simile — Andrew Wesel, Sarah Chen, Percy Liang](https://www.simile.com/blog/confidence)
- [Building the What-If Machine — Michael Bernstein](https://www.simile.com/blog/what-if-machine)

### 仕組みと共同創業者

公式サイトはJoon Sung Park / Michael Bernstein / Percy Liangを共同創業者として記載。人間の実データ、観測された行動、アンケート、インタビュー、実験を組み合わせて人間行動モデルを訓練する。データの鮮度、drift、信頼度の推定を明示している。顧客データはopt-in / customer-governedと説明する。Managerが個人情報を集めない場合、この個人に紐づく学習方法をそのまま採用できるとは限らない。

### 信頼度の評価

confidence記事は約8,600の質問、5-fold cross-validationを説明。同一の質問文と同じ実験標本を同じfoldに置く。最良手法としてsimulation modelのcontinued fine-tuningを報告し、AUROC 0.736、Pearson r 0.565、RMSE 0.0776（TVDの0–1スケール）を示す。

TVD < 0.16の「decision-quality」は、14人の社内評価者による約2,750 ratingsを用いた定義。Highの「95%」は、この閾値を満たす率の説明であって、任意の決定が95%成功する保証ではない。外部評価者や評価範囲の拡張が必要であることも記事は認める。

トップページの「7,000以上のweekly evaluations」とconfidence記事の約8,600問は、異なる説明対象。数字を混ぜて独立した検証数を水増ししない。

### Managerへの示唆

モデルの出力とモデルの誤差推定を分離する。自己申告のconfidenceを、そのまま実行許可にしない。外部の実測とholdoutで較正する。集団の行動分布を予測できても「何がよい変化か」は別問題であり、目的・制約・権限の定義が必要。

## 4. Praxis

一次資料: [公式サイト](https://www.praxisnation.com/)。今回取得できたトップ本文に基づく。推測した下位URLは404のため、追加ページを読んだとは扱わない。

digital nation、collective action、都市建設を掲げる。現行トップはUruguay / +Coloniaの開発を記載し、AIがmember preferencesを集約しproposalを作りexecuteする構想を示す。「constitution and human oversight」も明示している。membership、sign in、アプリ、private messagingがある。

Managerとの共通点は、AIによる集団の調整と物理的な環境への作用。違いは、Praxisが会員と都市開発を軸にするのに対し、Managerは受益者が会員にならずに恩恵を受けることを目指す点。Praxisが都市全体を自律制御しているという実証や、well-beingの因果評価は今回の資料から確認できない。

学ぶ点: 環境変更には土地、資金、管理主体、制度がある。AIの能力だけでは実行権限は生まれない。都市建設の大型資本計画を、ソフトウェアv0の前提にしない。

## 5. Toyota Woven City

一次資料:
- [公式トップ](https://www.woven-city.global/)
- [About](https://www.woven-city.global/about/)
- [Co-Creation](https://www.woven-city.global/co-creation/)

公式は「A Living Laboratory」「Human-Centered」「Ever Evolving City」と説明。人・物・情報・エネルギーの移動を扱い、digital twinでシナリオを検討し、実環境での実験とWeavers（住民・訪問者）のフィードバックにつなぐ。2025年にPhase 1の正式開始と記載。

具体例にはDaikinのpollen-less spaces / personalized functional environments、NISSINの食環境、Chubu Electric Power Miraizのdemand responseなどがある。**環境を変えて日常生活をよくする**というManagerの方向に近い。

同じ公式ページは、Woven City ChallengeのNationX（旧PUBLIC Technologies）を「resident / facility等のデータを統合し、都市全体のoptimal decisionsを特定するAI decision-making platform」と紹介する。これはManagerの周辺競合・協業候補として重要。今回確認したのはToyotaによる紹介であり、NationX自身の性能・実行範囲は未検証。

学ぶ点: digital twin → real-world experiment → feedback → evaluation。Woven Cityとの提携、採択、施設へのアクセスがあるとは主張しない。v0は都市規模にせず、ひとつの環境の管理者と始める。

## 6. 現在のAniccaai.com — 直接取得した事実

| URL | 2026-10-02のHTTP取得 | 内容 |
|---|---|---|
| `/` | 200、Next.js payloadに`NEXT_REDIRECT;replace;/en;307` | root metadataはautonomous Buddhist AI entity。rootのテキスト抽出だけで表示内容を判断しない |
| `/en` | 200 | Life Manager、body/mind/money、自己改善・自己複製、Start Life Manager、日次メール等 |
| `/ja` | 200 | 同等の日本語説明、始める、何兆体のAI、日次メール等 |
| `/lm` | 200 | Calendar × Telegram、$29/mo、Google Calendar接続、optional calls |

ブラウザでの目視検証ではなくHTTP本文と公開ソースの確認。レイアウト品質、実際の決済、稼働中バックエンドは未確認。

## 7. 接続GitHubの調査範囲と正本

接続GitHubから100リポジトリを列挙し、次ページは空であることを確認。全100個のコードを読んだわけではなく、今回のManagerとサイトに関係するものを選別した。

- **`Daisuke134/life-manager`**: AGENTS.mdで唯一の現行ソース正本と指定。調査base SHA `2f6012ecee2707c2249631e5ac6e3f1be972e97c`。
- **`Daisuke134/anicca-products`**: `apps/landing`に全サイトのNext.js 14.2.5 / React 18.3.1ソース、Netlify設定がある。現在の公開コピーと`app/en/page.tsx` / `app/ja/page.tsx` / `app/layout.tsx`が一致。どのSHAが実際にNetlifyから公開されたかはホスティング管理APIで未確認。
- **`Daisuke134/anicca-web`**: 別のNext.jsリポジトリ。現行サイトの正本として使う根拠がなく、変更対象に選ばない。
- **`Daisuke134/anicca-genesis`**: genesis個体のlive stateというREADME。状態と能力のソースを分ける考え方は参考。記載された稼働・収益を今回独立検証したわけではない。
- **`Daisuke134/anicca-dais`**: 関連repoとして列挙されたが、調べた`apps/landing`パスは404。別のサイト正本と推定しない。
- **`Daisuke134/anicca-memory`**: root構造のみ確認。会話・個人メモリの深掘りは今回の公開構想調査に必要ないため行わない。

`life-manager/apps/landing/README.md`は、旧anicca-productsの397-file shared marketing siteからLife Managerに結合した部分だけを移したと明記。実際に`/lm`と2つのNetlify関数のみで、top /en /jaやbuild packageは未移行。現行ソース正本と公開サイトソースの不一致が、サイト実装前に解くべき境界。

## 8. 既存実装から再利用するものと更新対象

現行runtimeにはloop registry、finite wake、resource admission、effect fence、receipt / readback、immutable releaseの仕組みがある。これらは変更の実行と証拠を区別する土台。ただし環境介入の因果評価は別に必要であり、receiptがあってもwell-being改善を証明しない。

startup-contextのvalidatorはTelegram linkと3つのorgansを必須にしている。名称だけ変更すると、新しい「no consumer interface」の方向と内部のfundraising生成が衝突する。schema・validator・tests・生成README・応募文まで一貫して更新する設計が必要。

旧loop、課金、既存顧客へのサービスを自動的に停止する権限は、この研究・新規サイト説明の依頼から推定しない。Managerの新規導線を変更することと、運用中サービスを停止することは別工程。

## 9. 根拠の境界

- 公式の説明は、実装済み・運用中・検証済みをすべて意味しない。
- 評価セットが違う値を並べて、会社間の勝敗を決めない。
- 「模倣できる人間の集団」と「介入してよい集団」は別。
- 個人を知らずに環境を制御する場合は、環境の実測と物理モデルから始める方が、個人digital twinのコピーより整合的。
- Managerのworld model、環境効果、AGI、自己資金化、健康・資産・mindfulness改善は現時点で実証されたとは扱わない。
