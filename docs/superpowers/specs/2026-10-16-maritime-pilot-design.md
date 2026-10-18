# Keiki × Maritime採択後のLife Manager実運用設計

**目的:** 採択済みのKeiki × Maritime competitionで、Life Managerを一人ずつが自分用に使えるサービスとして公開し、12月1日までに実利用者1,000人へ届ける。3人pilotは技術・安全性・体験の確認であり、勝利条件ではない。実行順と進捗カーソルは [`2026-09-25-life-manager-unified-ssot.md`](2026-09-25-life-manager-unified-ssot.md) に置く。

## 参加者1,000人は必要だが、VMは1,000台いらない

2026年10月15日更新の公式Program Termsは、競技終了までにagentを実際に使うdistinct user 1,000人を目標とし、最初に到達して検証された3プロジェクトをwinnerとしている。数えるのは人であり、agent・VM・subagent数ではない。TermsはKeikiまたはMaritimeのproject-level usageを実利用の確認に使うと書いているが、利用者の具体的な本人確認・計数方法や同着処理は未公表である。[Program Terms](https://competition.maritime.sh/terms)

したがって、推奨構成は、既存のLife Manager CloudとTelegram導線を使った共通サービスに、本人ごとのLife Manager ID、会話ID、保存領域を割り当てる形である。**人の単位で体験とデータを分け、VMは利用者数に合わせて増やさない。**主催者が「一人一agent」または「一人一VM」を求めると書面で確認した場合だけ、単価とアクセス上限を再計算する。

## 受諾メールと公式規約で開始日が食い違う

2026年10月16日、Darshan Golchhaから件名「You're in! Keiki x Maritime」の受諾メールを受け取った。採択済みであり、単なる問い合わせ受付ではない。メールは、各参加者のLife Managerを動かすこと、初週にアイデアと製品を磨くこと、上位30チームだけが第2週へ進むことを案内している。チームメンバーは返信で追加できるが、受諾メールには追加対象者の名簿はない。

開始日はメールが10月19日、現行Program Termsが10月20日と食い違う。Termsは終了を12月1日午後11時59分Pacific Timeと定める。週1の終了時刻、上位30チームの選考基準、提出物、審査者が見る利用実績、チーム登録の状態は公表されていない。10月16日にDarshanへ日付・週1締切・選考・プラットフォーム要件・請求条件を尋ねる返信を送っており、10月18日までに追加回答は見つかっていない。**10月27日などを確定締切として扱わない。**

受諾メールはMaritimeとKeikiへの登録、Maritime Scaleの2か月プロモーション（メール記載の価値は参加者一人あたり1,000ドル相当）、初週に利用者へ提供するKeiki LLMクレジット（メールには利用者一人あたり25ドル相当とある）を案内する。プロモーションの対象者・適用手順・利用制限はTermsに記載されていない。規約は大会期間中の両サービスへのfull accessを約束するが、恒久利用やすべての第三者費用を負担するとは約束していない。プロモーションコード、招待コード、token付きURLは元メールだけに置き、この設計書やコードへ転記しない。Scale適用前にカード要否、2か月後の自動課金、追加VM・モデル利用料、参加者ごとの適用範囲を確認する。

賞はwinner projectあたり最大20,000ドル相当のAI creditsで、全winnerが同額とは限らない。最初の3 winning projectsには3日間のSan Francisco体験があるが、スポンサーflightは米国内の人に限られる。日本からの渡航費、同行人数、宿泊・食費、日程は未公表である。非返金の旅程は予約しない。[Program Terms](https://competition.maritime.sh/terms)

## Cloud基盤はあるが、大会向けMaritime経路は停止中

「ほぼローカルだけ」という認識は一部だけ当たっている。ローカルrunnerや個人用BYOK stateは存在する一方、リポジトリにはRailway向けの常時稼働server設定、Supabaseを使うCloud経路、Telegram webhookと既存tenant分離の設計もある。したがって、Cloudへ移すための基盤がゼロではない。ただし、今の時点で公開ユーザーが登録して自然利用できることや、本番Cloudが大会用構成で稼働していることはこのソース確認では証明していない。

PR #8168はmainへmerge済みで、`maritime-sdk@0.9.0`、Telegram `/pilot`、Maritime側の冪等provision、UID由来のHMAC ID、会話ID、重複updateのreceipt fenceを追加した。SDKはCommonJS serverから遅延importされる。`MARITIME_PILOT_ENABLED`、data approval、tool-policy verification、API key、`LM_UID_SECRET`、最大3 UID allowlistが揃わなければprovider callをしない。現在のrouteは3人pilot用であり、一般signup、1,000人のオンボーディング、取得経路計測、winner readbackは実装・稼働確認されていない。

`/pilot`は現在、UIDごとにMaritime agentをprovisionし、そのUIDに結び付くconversation IDで応答する。MaritimeのSDKは同じagent IDにconversation IDを渡して会話を分けられる。現在の「UIDごとにagentを作る」設計をそのまま1,000人へ拡大すると、利用者数とは無関係にVM費用と管理負荷を増やす。OpenClaw templateはbrowser/code/file toolを持つため、promptで禁止しただけでは安全境界にならない。実行可能なtool policyを確認するまでpilot gateは解除しない。

Maritimeの料金表ではScaleは月500ドルで500 agent、追加agentは月1ドル、同時起動60台である。1人1VMを1,000人に単純適用するとhostだけで約1,000ドル/月となり、モデル利用料は別になる。しかし公式勝利条件は1,000人であって1,000VMではないため、この構成を前提にしない。[Maritime pricing](https://maritime.sh/pricing) [SDK agents](https://maritime.sh/docs/sdk/agents.md)

Maritime AI creditsを使う場合、MaritimeのPrivacy Policyはrequest本文・会話・tool結果とmodel responseを保存し、model-call contentをアカウント削除後も無期限保持すると説明する。自分のmodel API keyを使う呼び出しはMaritimeを経由せず、この保存対象ではないが、各agentへ秘密情報を預ける条件が増える。初期版では実カレンダー、連絡先、メール、住所を送らず、利用者へ保持条件を説明して明示的に同意を得る。[Maritime Privacy Policy](https://maritime.sh/privacy)

## 個人ごとの体験を分け、VM台数とは切り離す

| 領域 | AS-IS | TO-BE |
|---|---|---|
| 利用面 | 主な製品説明はTelegramのcommute agent。個人端末で動く機能も残る。 | Telegramの既存共有リンクからCloud版を開始し、Macや開発者のログイン状態なしで使える。 |
| 個人化 | Maritime `/pilot`は最大3 UIDで、ユーザーごとにagentを作る。 | 1人につき1つの安定したLife Manager identity、会話ID、task stateを使う。会話・保存データはユーザー間で分離する。agent/VMを1人ずつ増やす要件は主催者確認後にだけ採用する。 |
| 最初の価値 | `/pilot`は依頼文へのテキスト応答が中心で、一般利用者向け登録・使い方・継続価値は未確認。 | まず日常で繰り返し使う一つの仕事に絞る。推奨する仮説は、Telegramの一言から今日の次の行動を短い計画にし、本人が完了・変更を返せること。カレンダー連携は最初の利用価値に必須としない。 |
| 安全・データ | tool-policyとdata approval gateはoff。Maritime AI creditsの会話保持条件あり。 | tool capabilityを実際に制限して確認し、本人別データ・開示・同意・削除案内を整えてから実利用を有効化する。プロンプト本文はLife Managerのログ・計測へ保存しない。 |
| 勝敗計測 | 3人pilotは技術・費用確認。正式なsignup funnelや1,000人の重複除外集計はない。 | 実在する別人の利用者数と、初回に役立つ応答を受け取った人を別々に計測する。Keiki/Maritime project-level usageを照合し、signupだけを利用実績として数えない。 |
| 運用 | Cloud source/configはあるが、大会向け公開導線の自然利用とprovider readbackは未確認。 | 既存Cloud/Telegram/Supabase経路を再利用し、公開導線、user isolation、error/cost、公式usage readbackを確認してから利用者獲得を増やす。 |

## 短い導入と毎日の利用者獲得に集中する

**推奨:** すべてのLife Manager機能を見せず、一つの反復タスクを最初の価値にする。新しい利用者は共有リンクから短いTelegram会話で開始し、最初の数分で自分の情報だけを使った結果を受け取る。利用者の個人データを使わずに価値が出るところから始め、予定・メール・購入など外部サービスを変える操作は提供しない。継続利用と紹介が実測できたチャネルを一つずつ増やす。

同じ利用者・媒体・目的で、1,000人までの成長と再現できる勝ち方を一次情報で確認できる公開事例は、今回の限定調査では見つからなかった。一般的な「first 1,000 users」記事はこのcompetitionと同一用途・計測条件を満たさず、勝ち筋としてコピーしない。代わりに、最初の実験で共有リンク→開始→最初の有用な完了→7日以内の再利用を計測する。最初の25人は実在する対象利用者に直接案内し、どの導入文・開始手順・仕事が完了を生むかを記録する。良い反応が出た仕組みだけを次のcohortへ広げる。

大会全体は10月20日から12月1日までの42日間である。1,000人を締切までに均等に増やすと平均約24人/日となる。これは大会の週1選考基準ではなく、必要な配信規模を把握する計算である。第1週の上位30選考はメールにだけ記載され、rubric・締切・提出形式が不明なので、独自の目標人数を公式条件と誤認しない。週1は「動くCloud体験」「初期利用者の実利用」「本物の利用記録」「何を学んで直したか」を提示できる状態にする。

## 1,000人へ広げる前に分離・安全・計測を確認する

1. 利用者が開発者のMacやlocal credentialなしでTelegramの公開導線から開始できる。
2. 既存の署名済みTelegram actorから本人別のtenantを決め、同じ本人の再開で別アカウントやagentを重複作成しない。
3. 1,000人へ開く前に、最低3人の同意済みpilotで他人の設定・会話・送信先を読めないことを確認する。3人は大会の利用者目標ではない。
4. agent/VMを共用する場合、conversation IDと保存stateの分離を確認する。主催者が専用agent/VMを求める場合は、その回答と実費上限を先に記録する。
5. Maritime tool policyは機能ごとに許可を絞り、browser/code/file/外部送信を使わない構成を実際に確認する。promptだけでoffと見なさない。
6. user-facing data noticeに、Maritime AI creditsの入力・出力が無期限に保持されること、外部連携をまだしていないこと、利用者が送らない方がよい情報を明記する。同意前は実データをMaritimeへ送らない。
7. internal metricはHMAC化した利用者identity、初回利用時刻、初回の有用な完了、再利用、エラー、モデル/host費用だけを記録する。自由文・予定・応答・秘密情報は記録しない。大会の公式人数とは分けて表示する。
8. scale段階（3人→25人→100人→1,000人）ごとに、実際の利用・tenant分離・公式dashboard usage・billingを読み戻す。25/100は進め方を評価する内部cohortで、公式閾値ではない。
9. 公式の1,000 distinct usersに関する重複・team/test userの扱いは主催者確認後に固定し、fake account、bot、複数identityでの水増しは行わない。

## 今回のdistribution-first source実装

**AS-IS:** 公開Life Manager pageはGoogle Calendar接続とカード登録必須の7日trialへ誘導する。Telegramの通常`/start`はCalendar OAuthを始める。大会用のTelegram入口、Maritime保持条件の同意記録、紹介元から初回成功・再利用までの計測はない。既存Maritime `/pilot`はdefault-offで、最大3 UIDのallowlist、data/tool-policy/API-key gatesを維持している。

**TO-BE:** `NEXT_PUBLIC_MARITIME_PILOT_CTA=1`の時だけ既存Life Manager pageに大会向けTelegram CTAを表示する。CTAはLife Manager serverの`/maritime` pageから`/maritime/start?source=<allowlisted-source>`へ進み、`MARITIME_PILOT_PUBLIC_ENTRY_ENABLED=1`と設定済みbot usernameがある場合だけ`/start maritime_<source>`へredirectする。Telegram開始は既存private actor/tenant claimを使い、Calendar OAuthは呼ばない。入力・応答の保持条件を表示し、`/maritime_accept`による明示同意を保存する。同一Telegram updateの再配信では同意・撤回を再処理せず、撤回後に古いacceptを再送しても同意を復活させない。成功利用RPCはparticipant rowをlockし、その時点のDB状態で初回応答か7日以内再利用かを選び、状態更新とfunnel eventを同一DB transactionで記録する。同時に成功した別updateも順番に分類し、初回／再利用を取りこぼさない。7日以内再利用は初回成功より後、初回から7日以内の別の成功利用だけを数える。同意と既存pilot gatesの両方がpassした場合だけ`/pilot`でMaritimeを呼ぶ。

紹介元は小文字英数字と`-`/`_`だけの短いtagに制限し、未許可値は`other`へ正規化する。既存`lm_web_funnel_events`へ記録するのはcampaign source、HMAC化UID、start/consent/first-success/repeatのeventと時刻だけとし、Telegram本文・Maritime response・氏名・Telegram IDを記録しない。初回成功・再利用eventは利用者ごとに各1回だけ。competition dashboardのdistinct-user数と自社funnel数は別の指標として扱う。

**Feature gates:** Web CTAとredirectはdefault-off。既存`MARITIME_PILOT_ENABLED`、data approval、tool-policy verification、API key、UID allowlistのgateを緩めない。source buildでは本番環境変数の変更、規約同意、Maritime/Keiki signup、VM provisioning、実ユーザーへの招待・送信をしない。Maritimeの実行可能tool policyとdata approvalを確認するまで、CTAをproductionへ出さない。

**受入条件:**

1. CTA flag未設定時の既存Calendar CTAと既存`/start`の挙動が変わらない。
2. CTA/redirect feature gateがoffなら大会用redirectやprovider callが起きない。
3. 有効なcampaign sourceだけがdeep linkへ渡り、invalid/arbitrary inputでURL injectionできない。
4. 大会用`/start`はtenantを一度だけclaimし、Calendar OAuthもMaritime callも開始せず保持条件を表示する。
5. 同意記録なし、撤回済み、既存global gate offのいずれかで`/pilot`を拒否する。
6. 同一Telegram updateの`/maritime_accept`再配信は同意を成立させず、撤回後に古いacceptを再配信しても撤回状態を維持する。
7. 初回・7日以内再利用のmilestone時刻とfunnel eventは同一DB transactionで確定し、7日後の利用や同じ初回処理の重複呼び出しを再利用に数えない。
8. consent setupの案内で示す`/start maritime_direct`が実装済みdeep-link parserに一致する。
9. 同時に成功した2件の異なる`/pilot` updateはDB状態で直列分類され、初回応答と7日以内再利用をそれぞれ最大一件記録する。
10. consented userの成功利用と最初の再利用だけが各一件記録され、eventにprompt/response/Telegram IDが含まれない。
11. DB migrationはappend-only/RLS/service-role boundaryを維持し、本番へは適用しない。

**Source実装状態:** distribution page `/maritime`、allowlist source tag付きTelegram redirect、`/start maritime_<source>`、保持条件の同意/撤回、同意前provider拒否、初回応答と7日再利用の計測をLife Manager sourceに追加した。anonymous landing/click telemetryはbest-effortで、遅い書込みがTelegram redirectを止めない。公開CTAは`NEXT_PUBLIC_MARITIME_PILOT_CTA=1`、server入口は`MARITIME_PILOT_PUBLIC_ENTRY_ENABLED=1`と既存data/tool/API-key gatesが揃った場合だけ開く。人数上限は25人を既定、1,000人まで設定可能。Supabase migrationは作成したが未適用で、production flagは変更していない。招待、実ユーザー入力、Maritime/Keiki account・VMも作成していない。

`apps/landing`には`package.json`、`tsconfig.json`、および`@/lib/launchStrings`のsourceがtrackedされていないため、CTAのfrontend build/typecheckはこのrepo内で実行できない。CTA copyは`LmBody.tsx`に英語/日本語で閉じ、未設定時は既存Calendar CTAだけを表示する。

## Top 30の審査基準と渡航条件は主催者へ確認する

| 未確定 | 現在わかること | 決め方 |
|---|---|---|
| 開始日 | 受諾メールは10/19、Termsは10/20。 | Darshanからの書面回答を正本へ記録する。回答前は公式Termsの日付を基準にするが、週1締切は推定しない。 |
| 第1週のtop 30 | メールに記載、Termsには審査方法・rubricがない。 | 週1締切、提出物、ランキング基準、利用実績の最低要件を確認する。 |
| Keiki/Maritime利用 | TermsはKeikiまたはMaritime上のproject usageで実利用を確認すると記載。受諾メールは両方の登録を案内。 | 競技参加に両方の実装が必要か、片方のusageで十分かを確認し、必要条件だけ実装する。 |
| 1人用agent構成 | Termsの計数は利用者。受諾メールは一人ずつのLife Managerを求める。 | 個人別体験・会話分離は必須として実装し、一人一VMは要求が明文化された場合のみ行う。 |
| Scale promo | Emailは2か月Scaleと価値1,000ドル/参加者を案内。 | カード要否・自動更新・overage・対象者を確認。確認前に有料planへ変更しない。コードはメールに限定。 |
| SF travel | 3日体験。スポンサー便は米国内の人に限定。 | 日本からの便、宿泊、人数、日程が書面確定してから旅程を判断する。 |
| 事業登録 | 公開Termsは競技参加に法人を必須としていない。個別サービス要件は別途適用。 | 法人登記を競技の前提にしない。支払・税務・契約で必要になる場合だけ別途判断する。 |
| YC紹介 | 競技TermsはYC紹介や採択を約束していない。 | YC応募は別手続きとして直接行う。勝利やSF招待をYC入学の確約として扱わない。 |

## 採択・公開可能・大会勝利を別の状態として扱う

この設計の実装完了と大会勝利は別の状態にする。技術上は、利用者別導線・分離・安全・公式usage readbackが確認できたら「公開可能」。競技結果は、Keiki/Maritimeの記録と主催者の確認により1,000 distinct users到達が認められた場合だけ「winner」とする。採択メールやローカルtestだけでは勝利と報告しない。
