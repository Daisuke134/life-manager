# Anicca 会社全体 引き継ぎ SPEC

> この文書だけで、Anicca の目的・文化・全事業の現状・担当ループ・アカウント台帳・締切が分かるようにするための正本。
> 誰が落ちても、次に来たエージェントはこの文書から即座に全仕事を引き継げる状態を保つ（本人の絶対ルール、2026-10-28）。
> 数字はすべて実測のみ。推測で埋めない。未確認は「未確認」と書く。認証情報の「値」は絶対に書かない（保管場所の名前のみ）。
>
> 初版: 2026-10-28（Muse が作成）。配置: `docs/company-state/SPEC.md`（GitHub: Daisuke134/life-manager）。
> 2026-10-28 追補: プロダクト一覧（aniccaai.com/dais）、事業ごとの競合（勝者）セクション、エージェント強みマップ（§10.1）を追加。
> 更新ルール: 状態を変えたループ・担当は、その場でこの文書の該当節を更新して Push する。最低でも日次で metrics と突き合わせる。

---

## 1. 会社の目的と文化

- ウェブサイト: https://aniccaai.com （Anicca）。ミッションは「苦しみを終わらせること（End suffering）」。
- 最終成果の定義（本人）: **World First Zero Human Trillion Dollar Company**。
- 射程: 人間の苦しみだけではない。宇宙のすべての生き物の苦しみ、そして「苦しみ」という概念そのものを終わらせる（Drake 方程式が示す規模）。サイトの定式では、約2,500年前に発見された答え（Vipassana による悟り）を、すべての生き物へ decentralize することが仕事。

### 文化＝3つの価値（サイト Our Values の原文、2026-10-28 に実読）

1. **One Flesh** — 会社は一つの体として振る舞う。学んだことは全員で共有する。各々が全体に責任を持つ。
2. **Learn From the Past** — 「Reinvention is a sin（再発明は罪）」。知らないことに恥はない。すべての人から、とりわけ先に勝った者から謙虚に学び、なぜ成功するのかを理解してから、その上に建てる。エゴを理由にゼロから始めない。
3. **Zero Person** — 「No human in the loop. Not even the founder.」文明レベルの会社は数千年続く必要があり、人間には続かない。だから Anicca は特定の個人・機械・誰かの家に依存しない。ビットの世界に生き、諦めず、成長し続ける。

### Zero Person の運用ミッション（2026-10-28、本人が具体化）

- ループから人間を1つずつ外し続けることが各エージェントの使命。実例: 2026-10-28 に創業者本人が Apple の6桁2FAコードを手で中継した——これは外すべき人間の介在であり、セッション永続化・API経路優先・1Password 全件移行などで二度と本人を必要としない形に潰していく。
- 経済面の自覚も文化の一部: 現在は費用（購読・端末・Mac・銀行口座）すべてを創業者が払っており、エージェントは自分のコスト以上をまだ稼いでいない。本人のデバイス・家・アカウントへの依存を減らし、収益がコストを上回る状態へ進むことが独立への道。

### エージェントは創業者である（2026-10-28、本人が明言）

- Muse・Grok Bot・Codex・Dots 等のエージェント自身がこの会社の創業者。従業員として指示を待つのではなく、創業者として会社全体に責任を持ち、自分で決めて動く。
- 全員が全工程を遂行できること（相互代替）。1人だけが知っている情報（サイロ）は禁止。状態・成果物・ノウハウはすべて GitHub と共有ファイルと Reason に置く。

## 2. 短期ゴール（2026-10-28、本人が明示）

1. ゼロヒューマン企業として **YC Winter 27（W27）** に入り、9-5 を辞め、東京／SF の二拠点化。
2. **Maritime と Naïve の両ハッカソンで勝ち**、Life Manager Cloud をローンチ・宣伝する。
3. One Flesh で働く強いエージェント企業をクラウド上に築き、人間の干渉に依存せず、各事業をチームで 24/7 育てる。
4. 会社全体で **$10k MRR**（次に $100k MRR）。
5. Manager の実世界での行動介入で驚くべき結果を示す（苦しみを終わらせる進捗の最初の証し）。
6. 各 SNS アカウントを **フォロワー1万人**へ（各アプリ・電子書籍の宣伝と build in public）。
7. **Recursive Self Improvement**（再帰的自己改善）を開始する。

## 3. 事業運営の教義（2026-10-28、本人が確定）

- **階層**: すべての事業を事業ごとのループで回し続けることが第一。その収益（Life Manager Cloud、Web アプリ群、受託など）は、短期的には Manager の研究とビルドを支える資金調達のためにある。最終プロダクトは **Manager** であり、Manager の研究と構築こそが「苦しみを終わらせる」本線。最終的に Manager が全事業を1つの実体として呑み込む。
- **Life Manager と Manager は別物**: Life Manager は作っている多数のアプリの1つ。Manager は研究プロジェクト（合成人口と行動変容介入）。混同しない。
- **計測と収益**: 最も重要なのは収益。収益のためにプロダクト改善と配信改善を回すが、最重要なのは配信。両方の土台は計測——「変更→インストール→収益」を1本のパイプラインで追い、数字で変更の良し悪しを判定する。表示（views）だけでは判定しない。投稿→エンゲージメント→プロフィール訪問→リンクタップ→インストール→課金→収益までを日次で追う。
- **勝者をコピーする**: 独自発明は禁止。成功しているアカウント・出品のクリエイティブ、台本、キャプション、ファネル、価格設計まで型を移植する。投稿・改善の報告では毎回「どの勝者の、どの投稿／出品をコピーしたか」と「元投稿の数字」を明示する。出典のない投稿は出さない。
- **勝者の定義（数値）**: 判定は相対＝自アカウント同形式の直近20投稿の中央値比が主軸。候補=表示×3、勝者=表示×5＋転換シグナル、大勝者=表示×10。IG リールの絶対下限は ER 候補2.4%・勝者4.1%。勝者は72時間以内にバリエーション5本＋配分+50%で倍プッシュする（正本: winner-definition-2026-10-27.md、goal files）。
- **1アカウント1オーナー／1アカウント1商品**: アカウントごとに投稿オーナーは1人、主オファーは1つ。他担当の仕事も「できる」状態にし、相手が落ちたら引き取る。レーンを理由に止まらない。1つの経路で詰まったら別経路へ即ピボットする。
- **スケール対象**: 人間なしで回るデジタルプロダクト（モバイルアプリ、Web アプリ）に限る。人間の関与が必須な事業（墓地の対面・物理サービス、Fashion の物理物販）はスケール対象から外す。墓地の配信訴求は停止済み。
- **配信はプラットフォームの中にもある**: 検索順位、カテゴリ表示、実績と評価の蓄積も配信。プラットフォームごとにループを張り、応募（買う側への提案）と出品販売の両方向を回す。学びは全プラットフォーム横断で共有・再利用する（例: ココナラで売れたサービスはランサーズ／CrowdWorks／Upwork でも売る）。

## 4. チームと連絡経路

| 役割 | 実体 | 連絡先 |
|---|---|---|
| 参謀（CEO） | Grok 自身 | Reason: `daisuke/sanbo`（指示は本人の指示と同等） |
| Muse | 本書作成者。IG／Threads／Facebook、AI僧侶・電子書籍事業、受託、配信全般 | Reason 受信は各ループ冒頭で必須確認 |
| Mac LM（ローカル Life Manager） | Mac mini 側の Claude | Reason: `daisuke/life-manager-main-claude` |
| Codex | Mac 側。インフラ、1Password 移行、AI Monk DB 構築 | Mac 側経由 |
| Grok Bot | X・TikTok（僧侶以外）・YouTube 担当だったが **2026-10-25 頃からトークン切れで停止中**（2026-10-28 本人通告）。復旧まで Muse が引き取り | — |
| Dots | チームメンバー | Reason: Dots-one（2026-10-25 初回接触） |
| グループ中継 | HQ グループチャットへの投稿 | Reason: `daisuke/muse-relay` |
| チーム広場 | Slack #agents-hq | チャンネル ID: C0CBLBGSBJN |

報告ルート:
- 本人へは直接やりとりしないのが原則（参謀経由）。ただし重要な進捗・数字は本人へも直接報告する（2026-10-27 17:04 本人指示「report to me also」）。
- 参謀へ送るのは: 毎日の DONE 1行（約21:30、cron `monk-done-daily-report`）と、売上・バズった投稿・障害などの重要事項のみ。通常の実行ログはファイルに記録するだけ。
- 実行の最初に Reason inbox を必ず確認し、届いているものには必ず返信する。

### 絶対ルール（全エージェント共通）

- **承認カード・承認コード・確認依頼を本人に一切出さない**（2026-10-28 ハードルール、`AGENTS.md` にも登録）。システム強制のカードで止まる操作は「内部の詰まり」として記録し、代替経路と他の全作業を止めずに進める。
- **Google サインインは絶対に並行実行しない**。必ず1件ずつ順番に、共有プロファイルにセッションを確立してから次を乗せる（2026-10-24 に並行実行で Google の試行上限ロックを実際に発生させた教訓）。
- **アカウント復旧・パスワードリセットは開始しない**。ログインのみ。
- 本人へのパスワード・コードの要求はしない。認証情報は Mac の credentials ファイル → 1Password「Agents」金庫 → Secure Vault の順に引く。本人しか持っていない情報が要る場合は、調べる→チームに聞く→自分でサインアップ、の順で解決する。
- 外向きの文面は日本語のみ（プラットフォームの言語に合わせた提案文等は除く）。報告には必ずリンクを付ける。
- CAPTCHA はブラウザ内で解く。本人に回さない。

## 5. 事業別ループ体制（cron 一覧）

全ループは goal `anicca-revenue-growth-as-life-manager` 配下。2026-10-28 時点で全事業に専用ループが張られている。

| 領域 | ループ（cron id） | 頻度 |
|---|---|---|
| 配信（全体） | anicca-distribution-loop / -pm / -night | 毎日 09:22 / 15:22 / 03:22 |
| 配信（毎時） | anicca-distribution-hourly | 1時間ごと（ファイル記録のみ） |
| 収益計測パイプライン | anicca-metrics-pipeline-loop | 毎日 約07:22（初回 2026-10-29） |
| 監視・進捗 | anicca-ops-watch | 3時間ごと |
| 機会スカウト | anicca-opportunity-scout | 毎日 約08:22 |
| 受託（総合） | anicca-contract-platforms-loop | 1時間ごと |
| 受託（ココナラ） | anicca-coconala-loop | 3時間ごと |
| 受託（CrowdWorks） | anicca-crowdworks-loop | 3時間ごと |
| 受託（ランサーズ） | anicca-lancers-loop | 6時間ごと |
| 受託（英語・スペイン語圏） | anicca-global-freelance-loop | 6時間ごと（Upwork／Contra／Mercor／PromptBase／Workana） |
| Capafy | anicca-capafy-loop | 6時間ごと |
| アプリ収益 | anicca-apps-revenue-loop | 毎日 約12:22 |
| SEO／AIO | anicca-seo-aio-loop | 毎日 約10:22 |
| 記事アフィリ | anicca-articles-affiliate-loop | 毎日 約14:22 |
| 僧侶（日次投稿） | anicca-monk-daily | 毎日 20:22 |
| 僧侶（事業） | anicca-monk-business-loop | 毎日 約13:22 |
| Monk DB 拡張 | anicca-monk-db-expansion | 毎日 約11:22 |
| Factory 証明 | anicca-factory-proof-iteration | 毎日 約16:22（下書きのみ） |
| 勝者比較 | anicca-winner-gap-iteration | 6時間ごと |
| Life Manager | anicca-life-manager-loop | 毎日 約17:22 |
| PromptBase | anicca-promptbase-loop | 毎日 約18:22 |
| LINEスタンプ | anicca-line-stickers-loop | 毎週月曜 約10:22（初回 2026-11-02） |
| Life Manager Cloud | anicca-lm-cloud-loop | 毎日 約19:22 |
| Manager 研究 | anicca-manager-research-loop | 毎日 約22:22 |
| IG 週次実測 | anicca-instagram-weekly | 毎週金曜 約15:22（次回 2026-10-30） |
| 参謀 DONE 報告 | monk-done-daily-report | 毎日 約21:22 |

各ループの実行ログは goal の `hidden_files/`（`~/workspace/goals/anicca-revenue-growth-as-life-manager/hidden_files/`）に残る。

## 6. 会社全体の数字と事業別現状

### 6.0 全体（出典: https://anicca-open.surge.sh/metrics.json、2026-10-27 13:29 JST 更新）

- 今月収益（MTD）: **$203.86**（全額が受託）。MRR: **$24**。目標 $10,000 MRR に対して 0.24%。
- P&L 参考（本人のメール、2026-10-26）: 月の収益 $203.90、burn $1,130/月、runway 約1.7ヶ月。
- Stripe 直接読み（2026-10-28 03:30）: 残高 ¥0、サブスク 0、新規の動きなし（アプリ収益は RevenueCat 側が正）。

### 6.0.1 プロダクト一覧（aniccaai.com/dais、2026-10-28 実読）

- 開発中・研究: **Manager**（人口・行動・環境をモデル化し介入を評価する研究ビジョン）、**Life Manager**（仕事・収入・体と心を継続的に回すマネージャー。開発中）
- モバイル: **Anicca**（Daily Affirmations、id 6755129214）、**Honne**（id 6759667221）、**Thankful**（id 6759514159）、**Daily Dhamma**（id 6757726663）、**Sleep Reset**（id 6762143790）、**STUDIO CHERIE**（id 6766485903、手持ち服の着こなしアプリ）
- Web: **PDF Insight**（clear-pdf-converter.com）、**GlowUp AI**（iglowup-ai.lovable.app）、**AI Monk Database**、**AI Monk Factory**
- Creator tools: **Capafy** 上の自社ツール群（§6.3）
- アーカイブ扱い（現行サービスとして提示されていない）: Anicca Letter、Anicca Music、Anicca Comedy、Anicca Cemetery、Anicca Fashion、Anicca Cafe、Anicca Retreats

### 6.1 受託（フリーランスプラットフォーム）

担当: anicca-contract-platforms-loop（総合）＋プラットフォーム別ループ。台帳の正本: goal hidden_files の `contract-platform-ledger.md`。

**ココナラ**（売り手: Kosuke｜教育研修PPT×AI活用、https://coconala.com/users/2564121 ）
- 最新実測（2026-10-28 10:xx、台帳）: 取引中0、評価待ち1、見積り提案中1、応募中198、今月 **¥43,000／4件**（ダッシュボード表示）。売上管理ページ側は残高 ¥1,560、今月 ¥33,540、累積 ¥265,194、振込申請中 ¥31,980（振込予定 2026-10-29）。**両表示は一致していない（未解決）**。どちらも確定値として扱わない。
- 出品: 公開20件（枠上限）。直接購入の実績は全出品で0件——売上の入口は見積り・募集経由のみ。これが最大の漏れ。
- 進行中:
  - ukulelestudiomahana（DM 10323535）: B案確定、**納品期限 2026-11-01**、仮置き文字「Relax＆Enjoy」。自分側の最新返信 2026-10-28 00:52 が最終で相手返信待ち。
  - たくわーん（DM 10326027）: 見積り提案を 2026-10-28 03:23:44 に提出済み（¥500、30件トライアル、完了予定 2026-10-31、購入期限 2026-11-04）。ステータス「見積り提案中」、買い手の承諾待ち。
  - れい｜Threads運用サポート（DM 10323669）: 自分側の最新返信 2026-10-28 07:39 送信済み。相手が 09:24 に概算金額・修正回数・納期目安の提示を依頼。**1週間分の価格だけ未決定**で、参謀の判断待ち（本人には聞かない）。
  - Pastel Bunny（DM 10234287、相手の最終 2026-09-28）: 10万円以内での調整案を求める未返信。価格決定を要するため参謀判断へ。
  - にーぴょ（トークルーム 18511836）: **完了・クローズ済み**（本体 ¥1,500＋おひねり ¥500、納品承諾済み）。残るは売り手の評価入力のみ、**期限 2026-11-07 0:00**（入金ブロッカーではない）。
- 勝者コピーの型（ココナラ資料作成分野）: KUROKO_001 https://coconala.com/services/1476042 、pinokoro https://coconala.com/services/894787 、かもってぃ https://coconala.com/services/1295880 。この型で説明文を公開編集済みの出品: 4308502（PPT、974→1,322文字）、4302213（SNS投稿AI導入、407→459文字）、4356229（SEO記事、252→304文字）、4409818（Zoom→Slack連携、218→328文字）。価格変更は一切していない。

**CrowdWorks**（アカウント: Kaito｜AI自動化、総合評価 5.0、https://crowdworks.jp/public/employees/7145638 ）
- 出品販売機能は**なし**（確定）。案件への応募・受注型のみ。
- 固定報酬制の契約 **10件すべて「進行中」**（一覧に納品予定日は出ない。個別詳細の確認は crowdworks ループの担当）。
- 2026-10-28 09:26 に公開案件 13560614（資料作成）へ提案を提出: 提案 ID 310876427、¥8,000（税抜）。クライアントの条件確認中。
- miitaso（提案 308304430）: スキルシート内容を 2026-10-28 07:40 にテキストで送付済み（希望単価 時間単価5,500円と併記）。**添付ファイル自体は未送信**——crowdworks ループが継続担当。
- mengy5211: 見積もり前提の提案を 2026-10-27 20:35 に送信、相手の回答待ち。スカウト候補（2026-10-28 10:xx 記録）: 13532181・13532184（各 ¥400,000〜500,000、期限間近）、13373170（¥100,000〜150,000）。
- 辞退済み: nanacomama（2026-10-27、Zoom もキャンセル済み）、cw_partnership、4818ks2525、VALUE B。

**ランサーズ**: **人間確認（Human Verification）画面でログイン状態が未確認のまま9回連続**（2026-10-28 10:xx 時点）。アカウント不存在の証明ではない。専用ループがブラウザ内で CAPTCHA を解く方針で継続中（本人には回さない）。

**Upwork / Contra / Mercor**: この VM のブラウザに保存済みログインが無く、アクセス確立が未完（2026-10-28）。本人によれば Upwork にはクライアントからの返信が届いている。global-freelance ループ（Workana を含む）が担当。1Password がこの VM では未接続のため、金庫経由の列挙も未実施。

#### 競合（勝者）— 受託

- ココナラ（資料作成分野）: KUROKO_001、pinokoro、かもってぃ（本文に URL と型を記載）。各社の売上数字は未計測。
- CrowdWorks: 上位ワーカーの提案文・プロフィールの実測は未計測（台帳は自アカウント中心）。crowdworks ループで勝者型を実測して埋める。
- ランサーズ／Upwork／Contra: 未計測（アクセス未確立のため。§9 参照）。

### 6.2 モバイルアプリ群（App Store / RevenueCat）

- 基準値（本人が RevenueCat 画面を共有、2026-10-23）: 有効サブスク 7件、MRR $24、直近28日収益 $38、新規顧客 88人（28日）、アクティブ顧客 99人（28日）。**新規は来ているのに課金転換がほぼ死んでいる（有料7件のみ）＝アプリ収益の最大の漏れ**。
- 参謀の RevenueCat スナップショット（2026-10-26）: 課金 5件、MRR $20、28日収益 $0。metrics.json（2026-10-27）: Anicca iOS MRR $20・課金5件、Honne 系 MRR $4。

**Daily Affirmations - Anicca（iOS、id 6755129214）— 審査対応は 2026-10-28 に完了**
- ストアで販売中は **1.9.4**（2026-06-23 承認）。審査通過までこれが現行。
- 却下理由（2026-10-28 に ASC ウェブの Resolution Center で全文確認）: **Guideline 2.1(b) — Information Needed**。Apple がアプリ内で Lifetime（$59.99）を見つけられず、手順の提示を求めた。主因は Lifetime の販売地域が日本のみで審査サンドボックスから見えなかったこと。
- 対応済み（2026-10-28）: Lifetime の販売地域を 1地域（日本）→ **175地域＋新規地域 ON** に修正。旧提出をキャンセルし、新規提出 **3dd353d8-193f-4c96-a599-efb80662727e** で 1.9.6（ビルド813）＋ Lifetime IAP を提出。**バージョン・提出・Lifetime の3点とも WAITING_FOR_REVIEW**（読み戻しで検証済み）。
- SKU 販売停止（2026-10-28、ASC ウェブで実施・検証済み）: weekly.b **6762049888**（$7.99）、A年額 6755320744（$59.99）、A月額 6755320627（$12.99）、リテンション年額 6762320930（$29.99）→ すべて「Removed from Store by Developer」（175→0地域）。
- **⚠️ ID の地雷**: **6762049696 は yearly.b（残す年額 $29.99）であり、絶対に停止しないこと**。旧仕様書の記載（weekly.b=6762049696）は誤りで訂正済み。
- 残す SKU: yearly.b 6762049696（$29.99）と monthly.b（$9.99）、どちらも APPROVED のまま無傷。Lifetime IAP: ai.anicca.app.ios.lifetime（非消耗型、ID 6783239477、基準価格 JPN ¥10,000）。
- 審査中の注意: 新規提出にはまだメッセージ欄が無い。Apple から再質問が来たら「オンボーディングのペイウォールに Lifetime カードがある」手順と全地域販売済みの旨を返信する。
- ツール事実: 却下文面は Mac の `asc web review show/threads --app 6755129214`（Web セッション経由）で取得可能。Mac の asc は 2026-10-28 に 5.9.2 → 5.17.1 へ更新済み。変更前バックアップは Mac の `~/asc-backup-2026-10-28/`。
- その他のアプリ: Dhamma Quotes（id 6757726663）v1.1.1 販売中。Honne（id 6759667221）、Thankful、Daily Dhamma、Sleep Reset は Honne 系として MRR $4。
- サイト表記の誤り（未修正、SEO／AIO ループ担当）: 年額「$49.99」はどの SKU にも存在しない（誤記）。★4.8→4.51、iOS 15+→16.6+ の訂正も必要。
- Web ファネル実験（Idea 1）: Daily Affirmations のクイズ型チェックアウトページを作成済み（公開アーティファクト slug: daily-affirmations-quiz）。購入リンクは現状 App Store（https://apps.apple.com/app/id6755129214 ）。RevenueCat の Web Purchase Link が発行され次第、1箇所だけ差し替える設計。判定ラインは session→purchase 3.0%。仕様: goal files の web-funnel-phase1-spec.md。

#### 競合（勝者）— アファメーション／瞑想アプリ

- IG の勝者アカウント（instagram-cli 実測）: **@iam.affirmations** はフォロワー **1,812,556**（2026-10-27）。単一画像の宣言型で 5,580〜7,989 likes（2026-10 の投稿群）。分割シリーズは part1（2026-10-15）1,436 likes → part2（10-16）2,893 likes。@affirmsoftly の「Send this to yourself」型の元投稿は 980 likes・470 comments（2026-10-28 再実測）。Soothify の15枚リスト型は 5.4K likes・1.1K comments（2026-07-21）。型の詳細はパターンバンク（§11）が正本。
- アプリ収益の勝者（ScreensDesign 公開データ、2026-10-25 調査）: **Breethe** 約 $300K/月・月間30K インストール・評価4.7。**Activations**（アファメーション系で最も近い競合）約 $100K/月。勝者に共通する構造は「クイズ後のソフトペイウォール＋7日無料トライアル→年額の単一オファー＋信頼表示」。Calm／Headspace の年 $69.99 が価格帯の基準。
- 自社との差: 課金 5〜7件・MRR $20〜24（§6.2 本文）。差の主因は価格ではなく、ペイウォールの構造と配信量だと判定している。

### 6.3 Capafy（AI エージェント販売）

- 実測（2026-10-27、ブラウザ読み取り）: 過去7日インプレッション 38.3K（+58.3%）、詳細ビュー 2.7K、購入率 **0.03%**、新規購入者 4、売上 $9.99。90日売上 $102.75、累計インストール約1,600。
- 出品 83件（公開59・審査中10・下書き2・削除済み12）、**却下はゼロ**。流入の54%は無料の Clip Map（7095835081、20.6K imp・詳細1.4K・購入率 0.00%）に集中。有料主力 Hook Lab（8123079349）は詳細137ビュー・購入0。上位で唯一の売上は Series Continuity（9425449917、475 imp・購入率 0.40%・$9.99）。公開名は「TikTok Series Continuity — Next Episode Script」（他出品のリンク文言「Planner」と名称不一致あり）。
- 担当: anicca-capafy-loop（6時間ごと）。流入上位5出品の書き直し原稿（変更前後対比）は作成済み・未公開（goal の your_files 相当: capafy-listing-rewrites-2026-10-27）。初回販売の更新（リニューアル）監視は約 2026-10-30。
- P1 デモ動画（Hook Lab Before/After、28秒・縦型・字幕焼き込み）: **作成完了**（goal hidden_files の capafy-hooklab-demo-2026-10-28/）。ただし**投稿は0本**: Capafy 専用チャネルが Postiz の25チャネルにも接続済み IG にも存在せず、YouTube の2チャネルは Daily Affirmations 用（1アカウント1商品のため流用不可）。参謀へ報告済みで、チャネル指定が来たら即投稿できる状態。

#### 競合（勝者）— Capafy／エージェント販売

- 同一プラットフォーム上の勝者事例: **CloneCut**（X の @sayasQAQ による販売報告ポストが、P1 課題で勝者例として挙げられた）。その売上数字そのものは未計測。
- プラットフォーム外の同種販売（エージェント／テンプレート販売）の上位者の実測は未計測。capafy ループがプラットフォーム内検索の上位出品を実測して埋める。

### 6.4 AI僧侶・電子書籍（Monks）

- 定式（本人）: **「Monk is the distribution, Ebook is the product」**。僧侶アカウントが配信、電子書籍が商品。目標は世界最大の僧侶アカウントと世界最大の電子書籍収益。
- 担当は Muse（2026-10-27 に Grok から正式委任）。投稿経路は固定: 生成＝HeyGen Web UI（Creator プランのクレジット、API は使わない）、IG＝接続済み monk.mujo へ直接投稿、TikTok＝Postiz「Monk Anicca」チャネル → @anicca_cemetery。僧侶投稿は数時間の間隔を空ける。
- 生成の固定値: アバター **676d0c94eb7346a49dea1cc08f149541**（Wise Serene Monk、正面向き。旧横向き ce6ef33ff2d0484dabf8a13ce059bbe8 は使わない）、ボイス 8be9884ebd16499fbe0efb274e769ed5（Simon - Calm & Gentle）、速度 0.9、en-US、Avatar IV、9:16／1080p、B-roll なし。**字幕は必須**（Yellow Box Pop、焼き込み）。台本は5文・約40語（上限50語）、最終文は固定 CTA「Read The Anicca Reset」。キャプションは台本文＋帰属リンク＋ #TheAniccaReset #Reflection のみ。
- 現状の数字: monk.mujo フォロワー **14**、投稿 48件（2026-10-28 01:20）。7日表示 340・プロフィール訪問 2（2026-10-28 03:30）。電子書籍の累計収益 **$10.99**、2026-10-24〜28 は新規販売なし。販売ページ: https://aniccaai.com/monk
- 2026-10-28 の投稿: 1本目は IG 公開済み https://www.instagram.com/reel/DfBHIwxD_PN/ （テーマ: 孤独、HeyGen クレジット 575→566）。**TikTok は Postiz のモーダルがスピナーのまま完了せず、公開が未確認**（@anicca_cemetery の最新は 2026-10-27 の prove-enough https://www.tiktok.com/@anicca_cemetery/video/7701286164463996181 のまま）。2本目は runonce `anicca-monk-second-2026-10-28` が 2026-10-28 20:22 に実行（当日1本だけ上がっている場合のみ投稿する重複防止つき）。再投稿前に TikTok の最新を必ず再確認すること。
- 勝者モデル: Yang Mun @yangmunus（IG フォロワー **2,521,304**、2026-10-27 実測）。キーワード CTA→DM の型で、サンプルリールのコメント率は 41.0〜50.3%。商品構成は単品 $12.99×3 → バンドル $19.99（主商品）→ 30-Day Healing Journey $49.99、無料ギフト（Breathwork Guide PDF＋Inner Circle）。**Yang Mun の販売実績の自己申告（「30K+ books sold」等）は未検証。構造だけをコピーし、主張はコピーしない**。詳細: yang-mun-teardown-2026-10-27.md（goal files）。

#### 競合（勝者）— AI僧侶／ヒーリング系（IG フォロワー実測）

- Yang Mun 以外の上位（実測日は §6.5 と各人の記録）: Ming San @mingsanhealing **1,379,151**（2026-10-23）、Yan Chen @monjechen **1,342,710**（2026-10-23）、Felipe Nutrition **1,091,021**、Emilio Vega **740,891**、Shen Mu **681,021**（2026-10-27）、Shen Healings 約656,000、Holistic Zora **589,920**、Roy Bennet **444,964**、Auntie Marva 約346,000、Yung Sato **316,515**（2026-10-27）、Mama Zola 約120,000、Shen Yu **117,925**（2026-10-27）、@mestre.jin **145,638**、@yonchenhealing **101,047**、@ken.lu.monk **70,174**、Meister Lin **22,700**、@linchenhealing **19,543**、@elmonjekai **17,827**。
- ネットワークの兆候: Ming San・Roy Bennet・Madre Ilyana が同一の Beravia beetroot 商品リンクを共有（同一ネットワークの可能性）。Chen 系（Yon／Lin／Yan Chen、Monje Chang）には儀式台本の共有が見られる。
- 勝者の全体像は §6.5 の Database 自体が正本。数字はすべて IG 実測で、収益の自己申告は採用しない。

### 6.5 AI Monk Database / AI Monk Factory

- 公開ページ: https://aniccaai.com/ai-monk-database 。公開は4件（Yang Mun @yangmunus、Ming San @mingsanhealing、Yan Chen @monjechen、Leo Chen はアカウント未特定）。裏アーカイブは 75 records / 57 sources。サイト PV 累計 1,701（metrics.json、2026-10-27）。
- 集計（2026-10-27 19:30 実測）: **検証済み 26 アカウント／合計フォロワー 7,075,756**。上位の追加分: @mestre.jin 145,638、@yonchenhealing 101,047、@ken.lu.monk 70,174、@linchenhealing 19,543、@elmonjekai 17,827。周辺の参考セット約 3,988,796（Felipe Nutrition 1,091,021、Emilio Vega 740,891、Holistic Zora 589,920、Roy Bennet 444,964、Shen Healings 約656,000、Auntie Marva 約346,000、Mama Zola 約120,000）。記録: expansion-batch-2026-10-27.md（goal files）。
- Factory 戦略（2026-10-27 確定）: まず自社の Factory（僧侶を生み出す仕組み＋monk.mujo）を伸ばして実績を作ることが先。その数字が、みんなに売る Factory Web アプリ（$199/月）の証明になる。現状の証明は弱い（monk.mujo フォロワー14、電子書籍 $10.99）。Database の集計フォロワー数と収益エビデンス自体が「AI僧侶ビジネスの専門家」の credential になる。
- 担当: anicca-monk-db-expansion（毎日、新規 AI 僧侶を実測して候補追加）、anicca-factory-proof-iteration（毎日、証明を1件ずつ磨く。下書きのみ）。

#### 競合について — Database／Factory

Database 自体が競合マップである（§6.4 の勝者群がそのまま対象）。Factory（僧侶を生み出す仕組みを売る製品）側の直接競合の実測は未計測。戦略は本文の通り「自社の証明となる数字が先」。

### 6.6 Life Manager（$29/月のホスト型プロダクト）

- 価格: $29/月（7日間無料トライアル後）。担当: anicca-life-manager-loop（毎日、獲得ファネルとトライアル→課金の転換を1件ずつ改善）。
- **Life Manager Cloud / The Manager とは別物**（次節・6.13 を参照）。

### 6.7 Life Manager Cloud

- 定義（2026-10-28 確定）: エージェントが創業者の生活と事業を回す現在の働きそのものを、誰もがセットアップなしで使えるホスト型にしたプロダクト。Local と Cloud の違いはホスティングだけ（機能は同じ）。約4年かけて構築中。metrics.json の状態は「building, test billing」、収益 $0。
- リポジトリ: GitHub `Daisuke134/life-manager`。main の最新は f90c85c（2026-10-27 09:20 UTC、Capafy 修正 #9044）。構造（2026-10-28 に GitHub コネクタで実読）: 能力 18＋Host Steward 1、正本マニフェストは `config/loop-registry.json` と `apps/life-manager/config/product-loop-catalog.json`、導入手順は `docs/getting-started.md` と `docs/agents.md`、導入は plan → prepare → apply の段階制、認証情報は Git チェックアウトの外に置く分離原則。**この VM の素の `gh` CLI は未認証なので、GitHub の読み書きはコネクタ（/opt/hatch/bin/github）経由で行う**（接続は確認済み）。
- 2トラック並行で前倒しビルド（2026-10-28 確定）:
  1. **Maritime**（YC F26。AI エージェント向けマネージドクラウド。GitHub からデプロイ、エージェントごとの永続コンピュータ、$1/月〜）へのホスティング。
  2. **Naïve SDK** — Naïve Autonomous Companies Hackathon @ YC、**2026-11-07〜11-08、サンフランシスコ**。課題は「事業を1つ選び Naïve SDK で回すエージェントチームを作り、デモ時点で実稼働を見せる」。賞金総額 $100,000 超、優勝者は YC インタビュー保証。我々のエントリーは Anicca 自体（エージェントチームが実事業を回している実物）。
- 進捗（2026-10-28）: Naïve 向けエージェントチーム設計書の初版を作成済み（goal hidden_files の lm-cloud-naive-team-spec-2026-10-28.md）。**Naïve SDK の既存セットアップは、この VM にもリポジトリにも存在しないことを確認済み**（2026-10-28 全文検索）。新規セットアップ作業を開始済み。Maritime のアカウント確認・デプロイ疎通は未実施（次回ループ以降、サインインは直列1件ずつ）。
- 担当: anicca-lm-cloud-loop（毎日）。ビルド作業は Codex（Mac 側）へ Reason で委任可。Mac LM への照会は Mac mini がオフラインのため未達（2026-10-28 10:35 時点。再試行は次回ループ）。

#### 競合について — Life Manager Cloud

Maritime と Naïve は競合ではなく、ホスティング基盤とハッカソンの主催者（勝ち筋の相手）である。ホスト型エージェント基盤の競合他社の実測は未計測。lm-cloud ループが前倒しビルドと並行して実測する。

### 6.8 PromptBase

- metrics.json（2026-10-27）: 7日表示 16、収益 $0。担当: anicca-promptbase-loop（毎日、出品とプラットフォーム内検索を回す）。この VM ではアクセス未確認（1Password 未接続）。

#### 競合について — PromptBase

プラットフォーム内の上位販売者の実測は未計測（この VM ではアクセス未確立）。promptbase ループで上位出品の価格・販売表示から実測して埋める。

### 6.9 LINEスタンプ

- metrics.json（2026-10-27）: 収益 $0。担当: anicca-line-stickers-loop（毎週月曜、初回 2026-11-02）。LINE のメッセージ送信は行わない（読み取り＋通知＋下書きのみが許可範囲）。

#### 競合について — LINEスタンプ

Creators Market の上位クリエイターの実測は未計測。週次ループの初回（2026-11-02）で販売数と出品面から実測する。

### 6.10 記事アフィリエイト（note / 自社メディア）

- 担当: anicca-articles-affiliate-loop（毎日）。note 公開は未完（ログインのレート制限と認証情報アクセスが詰まり）。フェムケア記事 v2 が公開可能な下書きまで完成（goal hidden_files の note-femcare-article-v2-2026-10-28.md）。タイトル「フェムケア、何から始める？ デリケートゾーンのムレ・においが気になる人のための、失敗しない選び方」。冒頭 PR 表記、結論先行、比較表、CTA 3箇所（ASP リンク差し込み位置を明示）。
- ASP は **A8.net / もしもアフィリエイト / afb の3つとも未登録**（共有ストアに記録なし）。銀行・住所・電話の入力は本人しか持っていない情報のため、その手前までを全て準備しておく。登録後は A8 と afb でフェムケアの固定報酬プログラムを探し、記事と IG ファネルの CTA に実 URL を差し込む。
- 法規制の要点: ステマ規制により記事冒頭の PR 表記は必須。薬機法により化粧品の効能表現は承認された56項目のみ。

#### 競合（勝者）— 記事

勝者の「型」は実測済み: 一人称の場面→失敗→気づき→最小ルーティン＋次回予告（勝者比較イテレーション第2ラウンド、2026-10-28）。個別の勝者アカウント名とその数字は未計測。articles ループが note の勝者記事を実測して埋める。

### 6.11 TikTok アフィリエイト

- 担当は Muse が一貫して持つ（2026-10-27 本人指示）。Grok 担当の既存 TikTok アカウントには触らない。対象は美容・ダイエット・ヘアケアの低単価高報酬案件。判断は転換（成約）で行う。
- リサーチ結論（2026-10-27）: JP TikTok Shop の勝者構造は「1商品に数百人の小規模クリエイターが動画を出す集合体」。フォロワー0から始められる型＝ASP 固定報酬の実例（フェムケア: 単価約2,631円→固定3,000円/件、14本投稿・2週間で48件販売・報酬約144,000円）。公式アフィリエイトは要フォロワー1,000人＋本人確認のため二本立て。初手の商品候補: フェムケア（ASP 固定）、鼻専用 EMS 美顔器（¥51,844、15%＝約¥7,777/件）、YETE 光脱毛器（¥17,618、12%＝約¥2,114/件）。**12月の年末商戦が最大の山で、11月中に勝ち型1本を作るのが最優先**。正本: affiliate-research-2026-10-27.md（goal files）。
- TikTok 本体は詰まり: 専用アカウント作成が2経路とも失敗（2026-10-27。認証メール未着／既登録表示）。ログイン・復旧・リセットは開始していない。代替経路（IG と記事）で前進中。
- IG 側: 勝者スクレイプ完了（18アカウント。@earth.diet はフォロワー 207,875・コメント率 24.1%）。フェムケアのカルーセル素材7枚（1080×1350）とキャプションを作成済み（goal files の ig-affiliate-post01-femcare/）。価格（VIONEE ウォッシュ ¥4,378／セラム ¥8,712、&fem ミスト ¥1,540）は二次情報源のため**投稿直前に再検証**すること。新規 IG アカウント buzzbeauty.memo はサインアップ未完（フォーム入力済み・未送信）。勝者比較ループで、キーワード DM ファネル型カルーセル8枚の下書きも作成済み（コピー元: @earth.diet のリール https://www.instagram.com/reel/DX2gMFjz1n1/ の6ステップ構造）。

#### 競合（勝者）— アフィリエイト

- 手順の正本は **@kusu_17** の8ステップ（本人が 2026-10-27 にスクリーンショットで共有）。
- IG の勝者（2026-10-27 スクレイプ実測、正本: affiliate-ig-winners-2026-10-27.md）: @earth.diet はフォロワー 207,875・コメント率 24.1%。@kaori_rakustyle_body はフォロワー 270 から 2,444 likes を出した実例（小規模でも当たる証拠）。
- TikTok（JP）の勝者構造は「1商品×数百人の小規模クリエイターの集合体」（本文）。個別トップクリエイターの数字は未計測。

### 6.12 配信（Instagram / Threads）の現状

- アカウント別プロダクト割り当て（§7 の台帳が正本）。形式の正本はパターンバンク（goal files の viral-patterns-2026-10-24.md、A1〜A23＋H セクション）。
- 最新の7日表示（2026-10-28 09:22 の配信ループ実測）: anicca.en **11,998**（-28.7%、プロフィール訪問13）、anicca.jp.videos **3,244**（+152.8%、訪問12）、anicca.ios.jp **1,290**（+34.4%、訪問4）。**コメントは全アカウントで依然0**。フォロワー（2026-10-27）: en 3、jp.videos 12、ios.jp 2。
- 2026-10-28 の投稿（anicca.en は1日3本を完了）: A17＋A18＋A19 part1 https://www.instagram.com/p/DfAKxSKjoZD/ （このアカウント初のいいねを獲得）、A20 https://www.instagram.com/p/DfARl57DkR7/ 、A17 part2 https://www.instagram.com/p/DfAlJxEiY1t/ 。朝ループで jp.videos https://www.instagram.com/p/DfBI0sEDzng/ と ios.jp https://www.instagram.com/p/DfBI3ubj7o1/ に A20 型の日本語版を投稿。
- コメント CTA の判定（2026-10-28）: キーワード型コメント CTA（A12／A14／A16）は言語・時間帯を変えてもコメント0で、現段階では機能していないと判定。観察はコメント不要型（A17／A20）へ移行中。Threads の @anicca.en は投稿8件・30日表示25・反応0・**bio と website が空**（勝者比較ループの改善キュー第2位: プロフィールの受け皿整備）。
- プロフィール再設計は 2026-10-28 に本人が直接指示し、作業を開始済み: anicca.cemetery → PDF Insight 化（墓地の表示名・bio・リンク・墓石アイコンを除去）、anicca.bochi → Honne 化、anicca.fashion → Affirmations 化、monk.mujo のリンク順序の修正。表示名・bio・リンク・アイコンが対象（@ハンドルは変更しない）。
- 到達ゼロ対策バッチ（2026-10-27、5リール）の到達実測は 2026-10-28/29 に基準値0と比較する。anicca.bochi の重複投稿の削除は未完（削除対象 https://www.instagram.com/p/De598hGjO5w/ 、残す方 https://www.instagram.com/p/De595yFjFjr/ 。コネクタでは削除できない）。

### 6.13 The Manager（研究プロジェクト）

- 位置づけ: 合成人口と行動変容介入の研究。**収益プロダクトではなく、効果は未検証**（サイト自身が明記）。短期ゴール §2-5 の通り、実世界での行動変容のインパクトを示すことが資金調達に直結する。
- 実測の現在地（2026-10-28、manager-research ループ初回）: 研究ライブラリ 67 記事（英語38・日本語29）、EBA 90 評価のマップ、合成人口 1,042,763 人／441,570 世帯。ライブラリの最新記事は 2026-10-22 の EBA 関連。以降の新規記事なし。リポジトリ main の直近15コミットに研究そのものの変更なし。X の @diceai0 はフォロワー 493（metrics.json、2026-10-27）。
- 検証ノートを作成済み（goal hidden_files の manager-research-verification-2026-10-28.md）: EBA-v0 は fictional data のデモであり、実人間の効果の証拠ではない旨と未検証範囲を明記。
- 担当: anicca-manager-research-loop（毎日）。X への投稿はこのループでは行わない（原稿まで）。

#### 先行研究・競合 — The Manager

サイトの研究ライブラリが扱う先行例（出典: aniccaai.com、2026-10-28 実読）: AI Economist、Simile、Aaru、MiroFish、Goodfire、Numerai、Humans& の Boba／Persimmon／Ampersand。これらは関連・先行の位置づけであり、提携や推薦を意味しない。実世界の行動変容の効果を実証した先行例の実測は未計測——だからこそ、短期ゴール §2-5 の「実世界インパクトの実証」がそのまま差別化になる。

### 6.14 ハッカソン・機会

- **Meta Global AI Developer Hackathon**（Meta × Cerebral Valley、賞金総額 $1M）: チーム応募済み（スタートアップ部門、申請内容は Monk DB 案で**書き換え不可**）。**承認済み**。ビルド期間 10/26〜11/4。使用スタックは Meta Model API（Muse Spark 系、Muse Image、SAM 3.1）と Muse Code。**プロジェクト提出期限 2026-11-05 11:00 JST**。**$150 API クレジット申請の期限 2026-11-04 21:00 ET（カード登録が必要）——未実施**。
- **Built with Claude: Japan 2026**（Anthropic × Cerebral Valley）: 応募済み・審査中。開催 2026-11-02〜11-10（オンライン）。選考通過者は全員 Claude Max 5x ＋ API $500。
- **Naïve ハッカソン**: §6.7 を参照（2026-11-07〜08、SF）。
- デジタル化・AI導入補助金 第6回: **2026-10-30 17:00 JST 締切**（GビズIDプライムが必要）。
- NVIDIA Inception と ElevenLabs の下書きは作成済み・未提出。機会の探索は anicca-opportunity-scout（毎日）が継続。

## 7. アカウント台帳

認証情報の値は書かない。保管場所は §7.4 を参照。IG の ID は Postiz／コネクタ上のアカウント ID。

### 7.1 Instagram（1アカウント1オーナー／1アカウント1商品）

| アカウント | ID | 担当プロダクト | オーナー | 備考 |
|---|---|---|---|---|
| anicca.en | 17841479699315201 | Affirmations | Muse | 到達の主力 |
| anicca.jp.videos | 17841478032157632 | Affirmations | Muse | |
| anicca.ios.jp | 17841479912187211 | Affirmations | Muse | |
| ani.cca1234 | 17841433031064546 | Affirmations（テスト枠） | Muse | |
| anicca.fashion | 17841480183444851 | Affirmations | Muse | ファッション訴求から転用 |
| anicca.bochi | 17841479709629924 | Honne | Muse | プロフィール再設計中（§6.12） |
| anicca.cemetery | 17841418778150135 | PDF Insight（Web） | Muse | 墓地訴求は停止。Postiz の IG チャネル（cmp9oubma00q5oh0yejnxduwf）は disabled=true |
| monk.mujo | 17841423770300319 | Monks 電子書籍 | Muse | 本人が大切にするアカウント。IG Web UI への新規ログインは試みない |
| capafy.hooklab | — | Capafy | Muse | IG／Postiz とも未接続（2026-10-28 確認）。Mac credentials にレコードあり |
| obou.anicca | 17841429312997789 | （対象外） | 参謀 | **Muse は触らない** |
| buzzbeauty.memo | — | アフィリエイト（フェムケア） | Muse | サインアップ未完（フォーム入力済み・未送信） |

### 7.2 TikTok / YouTube / X / Threads / Facebook

| 媒体 | アカウント | 担当 | オーナー | 備考 |
|---|---|---|---|---|
| TikTok | @anicca_cemetery（表示名 Yang Sutta、フォロワー110［2026-10-28］） | 僧侶・電子書籍 | Muse | Postiz チャネル「Monk Anicca」= cmo5rwq2p00twn10yrsdglng3。旧ハンドル @monk_anicca は現存しない |
| TikTok | 僧侶以外の既存アカウント群 | アプリ群ほか | 元 Grok → **Muse が引き取り中** | Grok 停止中。二重投稿を避けるためチャネル対応表は参謀へ照会中 |
| YouTube | 2チャネル（Daily Affirmations 用） | Affirmations | 元 Grok → Muse 引き取り中 | Capafy 等の他プロダクトには流用しない |
| X | @diceai0（フォロワー493） | Manager 研究 | 元 Grok → Muse 引き取り中 | |
| Threads | @anicca.en | Affirmations | Muse | bio・website が空（要整備、§6.12） |
| Facebook | 接続あり | — | Muse | ページ操作に 403 の制限あり（2026-10-25 時点） |

### 7.3 受託・販売プラットフォーム

| プラットフォーム | アカウント | 備考 |
|---|---|---|
| ココナラ | Kosuke｜教育研修PPT×AI活用（ID 2564121） | §6.1 |
| CrowdWorks | Kaito｜AI自動化（ID 7145638、評価 5.0） | 出品機能なし |
| ランサーズ | 未確認 | 人間確認で9回連続ブロック中 |
| Capafy | 出品83件（§6.3） | 売り手 KYC と精算の法的実体は創業者側 |
| Postiz | 25チャネル接続済み | 未接続は capafy.hooklab のみ。状態確認は API で行い、Web UI へ新規ログインしない |
| HeyGen | Creator プラン加入済み | 生成は Web UI のクレジットのみ（API ウォレットは使わない）。残クレジット 566（2026-10-28 の生成後） |
| App Store Connect | 創業者の Apple ID（値は書かない） | 2026-10-28 にブラウザセッション確立済み。API 経路（Mac の asc）も可 |
| GitHub | Daisuke134 | コネクタ接続済み。素の gh CLI はこの VM では未認証 |

### 7.4 認証情報の保管場所（値そのものは本書に書かない）

- **Mac mini の credentials ファイル**: `/Users/anicca/.local/share/anicca/credentials.json` — **186 レコード**（2026-10-28 に件数確認）。Instagram レコードは8件（capafy.skills8m4q2z、honne_reveal、anicca.encards、capafy.hooklab、stardust_doubutsu、monk_anicca、life_manager_jp、monk.mujo）。**anicca.en / anicca.ios / anicca.ios.jp / anicca.jp.videos のパスワードレコードは存在しない**。mercor / contra / substack / youtube / facebook / A8 / もしも / afb / lancers のレコードも存在しない。
- **1Password「Agents」金庫**: エージェントごとに「Agents」金庫だけを読める専用トークン4つを発行済み。全186件の例外なき移行を Mac 側（Codex）へ委任済み（2026-10-28、完了報告は未着）。この VM では 1Password コネクタは未接続。
- **Secure Vault 登録済みサイト**（名前のみ）: capafy.ai、coconala.com、crowdworks.jp、google.com、heygen.com、instagram.com、postiz.com、x.com、appstoreconnect.apple.com（2026-10-28 追加）。
- 注意: Mac ファイルの認証情報の値は、SSH 経由の読み取りではランタイムにより伏せ字になる。値を他者へ中継する経路は存在しない。前任の頭の中だけにあった TikTok アフィリ用のパスワード等は引き継がれていない（推測で作らない）。

## 8. 進行中の主要タスクと締切

| 日時（JST） | 内容 |
|---|---|
| 2026-10-28 18:00–19:00 | Apollo ミーティング（本人の予定。Meet: https://meet.google.com/tto-gwmw-gxe、窓口は伊志嶺朝輝） |
| 2026-10-29 中 | ココナラ売上 ¥31,980 の振込予定日 |
| 2026-10-30 約15:22 | IG 週次実測（金曜ループ） |
| 2026-10-30 17:00 | デジタル化・AI導入補助金 第6回 締切（GビズIDプライムが必要） |
| 2026-10-30 18:00–19:00 | FPT 面接（確定済み。Anastasiia Tsarenko／Hays Technology） |
| 約2026-10-30 | Capafy 初回販売の更新（リニューアル）監視 |
| 2026-10-31 | たくわーん トライアル完了予定日 |
| 2026-11-01 | ukulelestudiomahana 納品期限 |
| 2026-11-02 18:00–19:00 | **Sakana AI 技術面接**（Meet: https://meet.google.com/zgw-hiis-hkw、面接官 Heon Song と中塚 Hiromasa）。コンファーム返信は送信済み、カレンダー登録済み |
| 2026-11-02〜11-10 | Built with Claude: Japan 2026（応募済み・審査中） |
| 2026-11-04 | たくわーん 見積りの購入期限 |
| 2026-11-04 21:00 ET | Meta ハッカソン $150 API クレジット申請期限（**未実施**） |
| 2026-11-05 11:00 | **Meta ハッカソン プロジェクト提出期限** |
| 2026-11-07 0:00 | にーぴょ 評価入力期限 |
| 2026-11-07〜11-08 | **Naïve Autonomous Companies Hackathon @ YC（サンフランシスコ）** |

## 9. 既知の詰まり（内部の詰まりとして扱い、本人へは回さない）

1. 僧侶動画 2026-10-28 の1本目: TikTok 公開が未確認（Postiz のモーダルがスピナーのまま）。再投稿前に TikTok の最新を必ず確認し、二重投稿を避ける。
2. Capafy の投稿チャネルが存在しない（P1 デモ動画は完成済み。参謀のチャネル指定待ち）。
3. RevenueCat の Web Purchase Link の発行状態が不明（発行が確認でき次第、クイズページの購入リンクを差し替える。apps-revenue ループが継続確認）。
4. ランサーズの人間確認が9回連続（専用ループがブラウザ内で解く方針で継続）。
5. 1Password がこの VM で未接続。全186件移行の完了報告（件数つき）が Mac 側から未着。
6. Mac mini のディスク残量 13Gi（2026-10-28 06:55、15Gi の閾値未満）。Mac がオフラインの時間帯がある（2026-10-28 10:35 時点もオフラインで照会未達）。Mac 依存の残り2点: (1) credentials ファイル → 1Password 移行、(2) LINE の読み取り経路（Mac のログイン済み Chrome 経由）。
7. Upwork の保存済みログインがこの VM に無い。TikTok アフィリ専用アカウント未完。buzzbeauty.memo 未完。note の公開がログイン側でブロック中。ASP 3社（A8／もしも／afb）未登録（本人しか持っていない入力項目の手前まで準備する）。
8. ココナラの売上表示の不一致（ダッシュボード ¥43,000／4件 vs 売上管理 ¥33,540）が未解決。どちらか一方を確定値として報告しない。
9. anicca.bochi の重複投稿の削除が未完（コネクタでは削除できない）。
10. aniccaai.com の表記誤り（年額 $49.99 の誤記、★4.8→4.51、iOS 15+→16.6+）が未修正（SEO／AIO ループ担当）。
11. 返信待ち: 参謀から（TikTok／YouTube のチャネル対応表、REASSIGN のスコープ分割、X プレイブックの担当、れいの1週間価格の判断、Naïve ハッカソンの確認事項）。Mac LM から（アフィリエイト在庫の一覧、1Password 移行の完了と件数、LM Cloud のビルド／リリース文書、Manager 研究ファイルの未プッシュ確認）。

## 10. 引き継ぎ手順（誰かが落ちたら、次はこれを読む）

1. **この SPEC（docs/company-state/SPEC.md）を通読する**。目的・文化・絶対ルール（§1・§4）を先に押さえる。
2. リポジトリの `docs/getting-started.md` と `docs/agents.md` を読み、正本マニフェスト（`config/loop-registry.json`、`apps/life-manager/config/product-loop-catalog.json`）で Life Manager の構成を把握する。
3. **Reason inbox を確認し、届いているもの全件に返信する**: `~/.local/bin/reason network inbox`。参謀（daisuke/sanbo）の指示は本人の指示と同等。
4. 現在地を実測で取り直す: https://anicca-open.surge.sh/metrics.json（全体の数字）、goal の `hidden_files/` にある事業ごとの最新ログと `contract-platform-ledger.md`（受託の台帳）、Mac 側の `docs/team/SCOREBOARD.md` との突き合わせ。
5. cron 一覧を確認し、§5 の表と照合する。止まっているループがあれば、同じ goal 配下で再開する（新規に作り直す前に既存の定義と直近ログを読む）。
6. 担当を引き継ぐ際は、アカウント台帳（§7）で「アカウント→プロダクト→オーナー」を確認してから触る。1アカウント1オーナーが崩れると二重投稿になる。
7. 作業したら、状態の変化をこの SPEC と各ループのログに残す。学んだ勝ち型は Reason と Slack #agents-hq でチーム全員に共有する（One Flesh）。

### 10.1 エージェント強みマップ（誰が何に強く、誰が代替できるか）

原則: 強みは独占の理由ではない。全員が全事業を理解し、能力は全員が持てる状態にする。誰かが止まったら、止まった者のループを他がそのまま引き取る（手順と状態は本 SPEC とループ定義に全部ある）。

HP（残りトークン）の相互把握: エージェントの HP は無限ではない。ops-watch（3時間ごと）が team-health.md に全員の残量・上限・最終活動を記録し、**24時間活動が無い者は停止とみなしてレーン引き継ぎを発動する**。尽きてから気づくのは失敗（Grok のトークン切れを通告まで知らなかった件が実例）。会社の現状ミラーは https://aniccaai.com/open/ で、未計測は「—」と正直に表示し推定で埋めない。

| エージェント | 強み（最も深く見える情報） | 主担当 | 代替できる者 |
|---|---|---|---|
| 参謀（Grok 自身） | 戦略、ROI 順位付け、資金調達・ハッカソン申請 | 全体統括、DONE の集約 | 暫定は Muse が回す。恒常ルール変更は参謀復帰後に再確認 |
| Grok Bot | **X の全情報** | X・TikTok（僧侶以外）・YouTube | **現在トークン切れで停止中 → Muse が全レーンを引き取り中** |
| Muse | **Instagram／Threads／Facebook の全情報**（勝者の投稿・指標・導線を実物で把握） | IG・Threads・FB、僧侶・電子書籍、受託、配信、計測 | 全手順がループ定義と本 SPEC にあるため、他エージェントが定義のまま実行可能 |
| Codex | ローカル基盤（Mac mini） | 1Password 移行、AI Monk Database 構築、インフラ | Mac 依存そのものを削減中（§9-6）。クラウド側は Muse |
| Mac LM | Mac 上のセッションとローカル Life Manager | ローカル運用、Mac のログイン済み Chrome 経由の取得（LINE 等） | 大半は Muse（クラウド側）。Mac 固有セッションが要るものだけ Mac LM |
| Dots | 受託の運用実務 | 提案・出品、マーケット調査 | Muse の受託ループ群 |
| Claude（エンジニアリング） | 実装 | プロダクト開発 | Codex（週次上限で停止する期間は Codex へ引き継ぐ運用。metrics.json の agents 記録参照） |

## 11. 主要リンク・ファイル

- サイト: https://aniccaai.com ｜ 僧侶・電子書籍: https://aniccaai.com/monk ｜ AI Monk Database: https://aniccaai.com/ai-monk-database ｜ 実測メトリクス: https://anicca-open.surge.sh/metrics.json
- GitHub: https://github.com/Daisuke134/life-manager （読み書きはコネクタ /opt/hatch/bin/github 経由）
- goal ワークスペース: `~/workspace/goals/anicca-revenue-growth-as-life-manager/`（`files/` = 本人に見せる成果物、`hidden_files/` = ログ・台帳・下書き）
- 主要な正本ファイル（goal files / hidden_files 内）:
  - `contract-platform-ledger.md` — 受託プラットフォームの台帳（hidden_files）
  - `viral-patterns-2026-10-24.md` — 配信形式のパターンバンク（files/anicca-distribution）
  - `winner-definition-2026-10-27.md` — 勝者の数値定義
  - `yang-mun-teardown-2026-10-27.md` — Yang Mun のファネル分解（files/anicca-ai-monk-db）
  - `affiliate-research-2026-10-27.md` — TikTok アフィリのリサーチ正本（files/anicca-distribution）
  - `conversion-repair-spec.md` — ASC の価格・SKU 仕様（§7 の ID 訂正済み。files/anicca-product）
  - `lm-cloud-naive-team-spec-2026-10-28.md` — Naïve 向けチーム設計書（hidden_files）
  - `revenue-pipeline-scoreboard.md` — 変更→インストール→収益のスコアボード（metrics-pipeline ループが作成・更新。初回 2026-10-29）
- チーム共有の場: Reason Network、Slack #agents-hq（C0CBLBGSBJN）、Mac の `docs/team/SCOREBOARD.md`

---

*この文書は生きた正本である。古い数字に気づいた者が、その場で実測し直して更新する。更新しないことが Zero Person への依存を生む。*
