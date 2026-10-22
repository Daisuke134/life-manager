# Manager：実証を核にした出版・専門性・収益の調査提案

調査日：2026-10-22 UTC。作業範囲は読取調査と本レポート・出典JSONの保存のみ。外部公開、投稿、連絡、インタビュー、申込、価格設定、請求、決済操作、リポジトリ編集を行っていない。本稿の項目は検討用であり、Managerの新しいタスク台帳ではない。実行状態は既存 `products/manager/docs/roadmap/tasks.json` のみを正本とする。

## 判断

**Managerの実際の動作と顧客支払を一つずつ証明し、その同じ証拠を記事・章・発表・カルーセルへ展開する。書籍の冊数や発信量を先に増やさない。** 再利用するのは成功者の「作動する成果物→失敗も含む具体的説明→読者の問題→明確な次の行動」という構造であり、文面、商標、数字、肩書、価格は移植しない。

最初の市場仮説は現行仕様に合わせ、公共的情報の重要な案内経路を管理する小規模運営者向けの「範囲を限定した保守・改善と検証レポート」。支払者は運営者、受益者は案内を必要とする人という区別を保つ。需要・支払意思・収益は未実証。無料の自社ページは技術試験面であり顧客ではない。

## 1. 現在の証拠と不足

全体を読んだ資料は `AGENTS.md`、`MANAGER_PRODUCT_SPEC.md`、`plans/2026-10-22-manager-research-products-plan.md`。さらに研究出版3文書、既存founder pitch、newsletter/book体系、FIRST_WEDGE、U002–U008、経済scorecard進捗、独立金融outcome検証手順を確認した。canonical originは `https://github.com/Daisuke134/life-manager.git`、checkoutは `/workspace/manager-execution` で一致。read-onlyなのでworktree・production・SSOTを変更していない。

| 区分 | この調査で読めたこと | 正確な扱い |
|---|---|---|
| 公開ナビゲーション | founder文書には2026-10-21 14:36 UTCの6 HTML内容一致・16ブラウザ検査という履歴がある | 日付付きP2成果物。今回live URL/receiptを再取得していないため現時点の稼働保証ではない |
| 自律製品 | 現行仕様はE16を `DEPLOYMENT_HOST_REQUIRED`、Digital Autonomy v0.1未配備とする | 旧prototype公開と継続自律運用を分ける |
| 研究教材 | EBAは公開研究提案・実行可能な架空v0として明示され、記事・書籍・講義の原稿や一部出力が存在 | proposal、manuscript、rendered、publishedを別判定する |
| 既存公開記事数 | 研究出版planに過去の65 articles/33 mediaというbaselineがある | 今回未再確認の履歴。現在の公開数や需要の証拠として再引用しない |
| 顧客/人の成果 | U002の異なる立場の同意ある実面談5件以上は未証明。下流の人の便益は未測定 | 架空persona・クリック・ソフト検査を人数や生活改善に置き換えない |
| 金銭 | 既存経済scorecard文書は外部決済未接続、hashだけではreceipt真正性を認めないと明記 | 今回Manager実売上を示す真正な請求・決済・返金・費用資料は得ていない。金額は `NOT_VERIFIED / UNKNOWN` |

一次資料：既存founder pitchが示す[公開prototype](https://daisuke134.github.io/life-manager/manager-support/)、[履歴run](https://github.com/Daisuke134/life-manager/actions/runs/39617848783)、[deployment run](https://github.com/Daisuke134/life-manager/actions/runs/39618047098)。これらは文書で読んだ参照先であり、本調査のlive再検証済みURL一覧には含めない。

## 2. 参考にする4例と、証明していないこと

指定のFirecrawl **Manager** 接続で検索し、以下の公式本人/自社ページを `maxAge:0` で取得した。取得時HTTP 200、scrape ID、読取範囲は隣接JSONに保存。本人が執筆した記事・公開repo・販売案内の存在と、実際の入金や発信が成功の原因だったことは異なる。成功例だけを選んだ比較から一般的な成功率は推定できない。

| 人物 | 観測できる公開成果・経路 | Managerへ再利用する構造 | 検証上の限界 |
|---|---|---|---|
| Hamel Husain / Parlance Labs | [eval FAQ](https://hamel.dev/blog/posts/evals-faq/)は実務の問いを体系化し講座へつながる。[decision-model比較](https://hamel.dev/blog/posts/decision-model-evals/)は100 traces、ラベル、閾値、性能/費用、採点promptを説明。[Parlance](https://parlance-labs.com/)はeval教育を明確な仕事にする | 狭い実務問題を、実データの失敗分析・比較・再現手順・深い教材にする。無料記事の後に、評価設計/運用を必要とする読者の次の一歩を置く | 比較は著者側実験で、今回独立再現していない。講座参加者数やレビューは運営側/プラットフォーム表示。価格×人数で売上計算しない |
| Chip Huyen | [本人books](https://huyenchip.com/books/)に技術書の刊行・販売先。[AI Engineering repo](https://github.com/chiphuyen/aie-book)に目次、章要約、study notes、case studies、prompt examples、補助script。本人homeは講義がML Systems本の基礎になったと説明 | 一つの教材体系を、原稿・章要約・補助コード・参照集・複数形式へ育てる。全章を新たな別企画として作らない | repo自体に「tutorial bookではなくcode snippetsは多くない」とある。repo=完全な再現benchmarkとはしない。best-seller/閲覧順位/会社売却は本人記載であり、印税や売却益を今回検証していない |
| Simon Willison | [plugin更新記事](https://simonwillison.net/2025/Nov/6/upgrading-datasette-plugins/)は同じ実装を動画、notes、TIL、tests、release、fresh環境確認へ接続。[about/disclosures](https://simonwillison.net/about/)にはDatasette、OSS活動、相談/研修、スポンサー向け短い月刊briefingがある | 小さな実動変更一件を深く説明し、既存素材を再利用する。費用・利害関係を開示し、無料記事を信頼の入口にする | 公開物と本人の収入源説明を確認しただけ。スポンサー数、実売上、顧客獲得率、雇用条件は未検証。公表$10/月は提供条件であり入金証拠ではない |
| Jason Liu | [Instructor repo](https://github.com/567-labs/instructor)と[本人home](https://jxnl.co/)から公開実装・記事・教育素材への連続性を確認。[content記事](https://jxnl.co/writing/2025/04/04/creating-content-that-converts-my-guide-for-ai-consultants/)は顧客会話から記事を作り同じ問題説明を再利用した過去の本人説明 | 実会話で繰り返す困り事を教材の問いにし、サービス説明を「誰のどの問題を何で確かめるか」にする。公開repoを第三者が確認できる職業ポートフォリオにする | content記事は明確にarchival。[現services](https://jxnl.co/services/)はconsulting/expert calls/cohort募集を終了したと明示。homeのOpenAI Codex DX職は本人記載で企業側照合未実施。過去views・時給・顧客一覧を独立検証済み成果/現在販売としない |

この4例は、記事だけで専門家になれることや、同じ発信をすれば同じ仕事/売上になることの証拠ではない。Managerは「公開実装と根拠を読者が検査できる」「何が未知かを説明できる」「相手の具体的な問題に応えられる」という検証可能な能力を示す。

## 3. 一つの証拠から作る最初の成果物

canonicalな証拠パッケージは既存repoのrun、固定source SHA、比較条件、失敗、費用、公開readbackに集約する。新しい広報DBや本プロジェクトを増やさず、既存P01 claim index、記事、book outline、P06 storyboard、publication receiptsを使う。

初回case-study案：

**「Managerが実際に変えたこと、まだ確かめていないこと——公開情報ナビゲーションの検証記録」**  
英語案：**“What Manager Changed—and What We Have Not Measured”**

これは現在未執筆の提案タイトル。初版は既存の2026-10-21 P2成果物を日付付きで説明し、再確認できた事実だけを採用する。継続自律cycleや有料顧客がまだなければ、その欄を未知として残す。E16運用証拠が得られた時に同じcase-studyを改版する。無変更、rollback、UNKNOWN、失敗、費用超過も同じ様式で掲載する。

必須項目は「対象/権限→変更前の問題→比較したNO_ACTION/静的checker/人手→実行差分→独立readback→費用/人手→失敗/回復→結果の限界→再現コマンド」。単にサイトを配置したことと、役立つ修正を自律的に行ったことを分ける。経済結果と人の便益も別欄にする。

| 派生成果物 | 具体的な初回形 | 完了の証拠 |
|---|---|---|
| 技術記事 EN/JA | 上記case-study、原理図1枚、before/after、再現手順、出典、現状/限界 | 対訳のclaim一致、再現、レビュー。公開済み判定は別 |
| 書籍の最初の章 | 既存計画の **“Prediction, intervention, and what counts as an improvement”**。同じcase-studyを実装例として参照 | 一章の原稿、参考文献、演習実行、読者レビュー。HTML/EPUBを作った時だけその形式をdoneにする |
| 12-slide発表 | 問題/対象/仕組み/比較/差分/証拠/費用/失敗/人の結果未測定/収益状態/再現/次の問い | 実PPTX/PDF、checksum、文字・図の目視検査。スライド原稿だけは未完成 |
| 8-panelカルーセル | 「agentがSUCCESSと言った後、何を確認するか」。1問、1具体例、receiptとreadback、費用、未知、再現、CTA | 各PNG等、出典/claim ID、alt text、可読性、リンク、目視検査 |
| 60–90秒slideshow | 同じ8 panelsから音声/字幕付きの実demo抜粋 | 実動画bytes、再生確認。concept映像と実画面を明示して区別 |

すべての派生物で共通のclaim IDを参照し、原出典の訂正が翻訳・図・章・投稿へ伝播するようにする。既存published packageの固定SHAや旧記事は黙って上書きしない。複数巻は同じ章の包装であり、顧客確認前に30章を完成させる義務ではない。

公開状態は `DRAFT → EVIDENCE_CHECKED → EDITOR_REVIEWED → RENDERED_QA → RELEASE_READY → PUBLISHED_VERIFIED`。訂正/撤回/到達不能は別状態で履歴を残す。GitHub commit、deckのMarkdown、投稿文draft、review passだけでは `PUBLISHED_VERIFIED` にならない。実公開先のpermalink、取得時刻、期待source/package SHA、独立GET、asset bytesが必要。

## 4. 5件の会話から、最初の有料仮説へ

U002の既存要件は「異なる立場の5件以上の同意ある面談と、実際に必要とする結果」。例として運営者2・支援者1・対象となり得る利用者2の配分を提案するが、これは募集済み人数ではなく調整可能な計画値。架空会話、persona、SNS反応は代替にならない。

聞くのは直近の実例、失敗した段階、頻度、現行代替、担当時間、予算/承認者、誤案内の損失、成果をどう確認するか。「このAIを買いますか」だけでは需要を証明できない。本人同意の下で必要最小限の匿名メモを残し、支払者と受益者の異なる要求を見えるようにする。

有料design-partner仮説（未販売・未契約）：

- **対象**：一つの重要な公開案内経路を保有し、定期的なリンク/鮮度/アクセス性問題を実際に負担している運営者。
- **範囲**：1 journey、期間2–4週、運営者が明示した範囲と予算で観測・許可済み訂正・独立readback・復元・週次証拠レポート。現行の自社owned範囲を他者サイトへ勝手に拡張しない。
- **提供価値の仮説**：誤情報/到達失敗の早期発見と保守負担の軽減。人の時間削減・便益は実測前に約束しない。
- **比較**：既存link checker/監視ツール、定期人手確認、無変更。安価なcheckerで十分ならそれを選び、Managerの必要性を捏造しない。
- **料金**：5会話とscope/実原価から見積もる。高額eval講座や無関係なLife Manager listingの価格をそのまま移植しない。このレポートは価格や課金を決定しない。
- **受入**：一件以上の有用な納品を先方が確認し、scope/請求/支払い条件を明示し、外部顧客の真正な決済が得られること。自動で売れた、黒字、継続利用、PMFとは別判定。
- **停止/修正**：5会話で重要な反復課題が出ない、権限が取れない、既存代替で十分、納品原価が支払意思を上回るなら、次の本を書く前に問題/対象を修正する。

運営者有償pilotが成立しても、既存U004–U008の実利用・人の結果・比較に関する依存を満たしたとはしない。売買契約上の受入と研究上の因果的便益は別の受入である。

## 5. 「真の収益」の最小証拠契約

新しい決済システムを作らず、既存経済scorecardの未知/重複/未決済区別と、適切な提供者の照合を使う。まず一件の実顧客支払を説明できるようにする。以下は契約案であり、真正な取引データではない。

**売上レーンを分ける**

| レーン | 含めるもの | Managerの製品収益に数えないもの |
|---|---|---|
| Manager product | Managerソフトウェア/継続保守機能に対する外部顧客の支払。契約で製品分を識別 | 自分の送金、資金調達、補助金/寄付、未決済注文、架空残高 |
| Manager-enabled service | 実際にManagerを使って納品した運用/評価サービス。人手の作業を明示 | SaaS ARR、完全自律収益という表示。混合契約は製品/人手分を分解 |
| Founder consulting | 創業者個人の相談・受託報酬 | Manager製品売上への付け替え |
| Founder employment | 給与、採用契約、雇用上の所得 | Manager売上、製品による所得因果効果 |
| Content | 本、記事、教材、研修、スポンサー等。種類も区分 | Manager product売上との合算。無料購読/予約数を入金扱いしない |
| Life Manager / その他 | 別製品・別運営であることを表示 | 既存Capafy/Writer/アプリ等の売上やbeneficiary支援金をManagerへ輸入 |

**一取引に必要な項目**

`product_id / lane / contract_or_order_id / external_customer_ref / related_party_flag / invoice_id / invoice_amount / payment_id / provider_account_ref / paid_amount / tax / fee / refund / chargeback / currency / status / invoiced_at / paid_at / available_at / payout_at / service_window / cutoff / evidence_source / authentication_method / independent_readback_at / cost_items / human_minutes / completeness`。

個人/取引詳細・認証情報はGitに入れずowner管理の既存保管場所に置く。公開版は集計、証跡の所在/検証方法、匿名化ID、観測期間、必要なら秘匿理由だけ。hash一致だけでは送金の真正性、支払者の外部性、最終状態は認めない。

- 見積、口約束、発注、請求、カード承認、決済完了、残高利用可能、口座へのpayoutを区別する。請求額は実入金ではない。processor決済と同じ銀行payoutを二重売上にしない。
- 売上の観測期間、収益認識/現金basis、サービス提供期間、返金cutoff、時間帯を明示する。単発pilotをMRR/ARRへ年率換算しない。
- 金額は元通貨とminor unitで保存。JPYとUSDを直接合算しない。換算値にはrate/source/dateを添え、元通貨を残す。
- 税を除く決済済み顧客対価、返金/chargeback、決済手数料、API/hosting/納品等の帰属可能な現金費用を別項目にする。
- **期間内の現金貢献 = 決済済み税抜対価 − 返金/chargeback − 手数料 − 帰属可能な実支出**。原価または返金範囲が未確認ならnetは `UNKNOWN` とし、確認済みgrossだけを別掲する。cash contributionと会計利益を混同しない。
- 創業者の無給時間は0コストとせず分/時で記録。経済的採算を示す場合は事前の時給仮定と現金採算を別掲し、必要な有給人件費は実費へ含める。赤字は符号を保つ。
- 顧客入金は提供者の正式記録と権限ある別経路照合で確認。銀行着金を主張する場合はその実照合も必要。未決済、返金中、曖昧な結果、coverage不足は成功へ昇格しない。
- `0` は特定期間/商品/提供者accountのcoverageが完全で、対象取引が0と照合できた場合だけ。未確認、未取得、未接続は `UNKNOWN / NOT_VERIFIED`。今回の実売上額を0とは断定しない。

調査開始時の `tasks.json` **U008.verify** に「収益は未獲得なら0とする」があった。今回の統合改稿で、対象期間/決済経路を照合した確定ゼロと未確認 `UNKNOWN` を区別する文面へ修正した。自律実行の金銭操作権限や新しい外部支払scopeはこの設計から発行されない。

## 6. 配信・専門家としての信用・キャリアを測る

初回の基本CTAは「証拠とコードを再現する」。運営者向けは「この保守問題が自社にもあるか、現在の運用を教えてほしい」、技術職/研究者向けは「再現結果や失敗例をissueへ」のように一つの主目的を選ぶ。架空の相談実績・推薦・企業ロゴは載せない。将来の商談/採用入口は連絡先やproviderを実際に確認してから接続する。本調査で送信はしない。

配信は既存ownedサイトをcanonicalにし、接続済みと確認された無料channelだけで短い切り口を出す。X、LinkedIn等は接続を仮定しない。既存ルール通り広告/boost/有料配信を購入しない。各リンクに既存の `ct` 等のcontent/channel識別を使い、記事→コード/証拠→任意signup/実会話→提案→納品→決済を追う。個人の公的支援ニーズを広告profileへ変換しない。

| 見たいもの | 測定/分母 | 誤認を避ける |
|---|---|---|
| 内容の有用性 | 外部の再現成功、具体的な訂正issue、独立した引用、出典クリック / 観測できた読者または試行 | 自社bot/著者自身を除外。訪問者coverage不明なら不明 |
| 関与の質 | 課題が具体的な返信、運営責任者/実務者との会話、コード利用、継続読書 | impressions/like数だけで顧客価値を認定しない |
| 商業需要 | 実施済み会話、scope付き提案、納品受入、正式order、settled paymentを段階別記録 | scheduled≠実施、proposal≠契約、入金≠黒字 |
| 継続 | 次期間の実利用、更新/再購入、実支払、支援負担 | 「また使いたい」だけをretentionにしない |
| キャリア | 公開実装の著者/貢献範囲、発表の実receipt、具体的な技術相談、実面接/offer | 採用返信や給与をManager revenueにしない |

創業者ポートフォリオは、短い問題定義、実demo、固定commit、失敗/比較、再現手順、費用、本人が実装した範囲、未達項目を一ページで示す。研究職では新規性/方法/再現、founderでは顧客課題/利用/入金、engineeringでは品質/運用/復旧を同じ証拠から見せる。肩書「専門家」自称を目標にせず、読者が検査できる能力を蓄積する。

## 7. 小さな週次運用案と判定

以下は**提案する作業目標**で、実績・予測・契約ではない。

- 毎週：新しい実証一件または未解決点を閉じる一件を先に置く。証拠/費用/失敗を更新してから、記事一件、または既存case-studyの改版一件を作る。deckとcarouselは同じ週に全部必須とせず交互に派生させる。新しい証拠がなければ何が未確認かを記す。
- 週の前半：技術実証と実会話。後半：同じ証拠の編集・配信・反応確認。出版作業は製品/顧客検証を遅らせない上限をチームで決める。
- 最初の4週間の目標案：5件以上のqualifying interviews、繰り返す痛みのある一つの運営者segment、scope付き有料提案2件、外部顧客の真正なsettled payment1件。いずれも未達ならそのまま未達とする。適切な顧客を見つけるまでの期間を保証しない。
- 4週で検証するのは需要と小さな納品/支払経路。因果的な人の便益、PMF、ARR、労働なしの自律黒字はこの目標から主張しない。
- 一件の入金が確認できた次に、全費用、納品品質、30日後の実利用/更新を確認する。自律性は通常運用の人手介入・例外対応時間も含めて測る。

## 8. rootが既存計画へ組み込める9件の具体的TODO

下表は既存P/U/Y/Eへの提案対応表であり、独立した進捗正本を作らない。

| 順 | 作業 | 依存 | 完了に必要な証拠 |
|---|---|---|---|
| 1 | P01で歴史的P2/runと現在E16状態、実売上UNKNOWNをclaim indexへ区別して固定 | 既存spec、run/receipt、source SHA | 出典/日付/読取深度/権利/限界。過去記事数を再検証なしに現在値へしない |
| 2 | 既存founder pitch/デモに「真の製品成果/顧客/金銭/人の便益」4欄を接続 | 1、Y001/Y002 | 実画面とproof level、未達明示、本人の実装範囲 |
| 3 | U002の同意ある異なる立場5件の面談を実施・匿名メモ化 | 既存U001、連絡の実際の権限/相手承諾 | 直近実例、代替、頻度、必要結果、支払/承認主体。今回は未実施 |
| 4 | U003で一つの運営者journeyと小さな有料pilot案を選ぶ | 3 | 問題/代替比較、scope、費用上限、権限、受入、続行/断念理由 |
| 5 | 原因/費用/失敗を含むcanonical case-study一件を完成 | 1、現物のlive再確認。自律成果版はE16実運用receipt | 固定証拠、比較、実際の差分/readback、原価、不明/負結果 |
| 6 | P02/P05のEN/JA記事・最初の一章へ同じcase-studyを組み込む | 1、5。source-only説明はE16を待たず進行可能 | 対訳claim整合、参考文献、演習再現、原稿/実exportの区別 |
| 7 | P06で同じclaim IDsの12 slides/8 panelsを実出力・検査 | 6 | PPTX/PDF/画像bytes、可読性、alt text、出典、hash、目視。公開は別 |
| 8 | 有料pilotの正式scope/納品/請求/決済/費用/返金を照合しレーン別report | 4、実契約/納品/提供者権限。人の便益研究とは別 | 真正な外部顧客取引、重複防止、cash contribution、未知のcoverage。単発をMRRにしない |
| 9 | P07/既存U/Y計画で公開receiptと週次conversion・質・継続を確認 | 5–8、実際のchannel/公開権限 | live permalinks/readback、実会話/受入/決済の段階、反証と次の判断。投稿/応募は各別操作 |

**今回のDONE条件**：read-only一次調査、4例の限定付き比較、canonical出版経路、真正な収益契約、5会話→有料仮説、測定/週次運用、依存つき9 TODOを本稿に保存した。Managerの売上・顧客・公開・実利用・因果的便益の達成を宣言していない。

出典監査用JSON：[出典台帳](FOUNDER_EXECUTION_SOURCES_20261022.json)。各first-party pageは取得済み本文の関連箇所を読んだが、書籍全本文、企業内部の会計、雇用契約、第三者再現を読んだとは主張しない。


---
統合注記: このlaneは読取調査として実施し、報告を製品repoへ収録した。現行状態・改稿結果は [統合更新](FOUNDER_EXECUTION_UPDATE_JA.md) と既存task台帳を参照。
