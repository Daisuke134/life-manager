# YC W27・シミュレーション企業への就職・イベント・公開連絡経路の調査

**確認日:** 2026-10-22 UTC。**用途:** Manager の仕様・実行計画へ取り込む読取調査。応募、メール送信、登録、面談予約、公開を実施していない。新しいSSOTではない。公式情報は同日 Firecrawl の **Manager 接続**（link_6ad9d35685e08191a01389178af3262c）で search → scrape、各本文は `maxAge:0` で取得した。検索スニペットと全文読取を区別し、以下の採用候補は公式求人本文に Apply または応募フォームがあるものに限定した。締切・採用状況は応募直前に再確認する。

## 1. 先に仕様へ反映すべき判断

1. **目標は明示的に YC Winter 2027。** 通常締切は **2026-11-02 20:00 America/Los_Angeles = 2026-11-03 04:00 UTC = 13:00 JST**。会期は2027年1–3月、SFで対面。原稿・書籍全体・人の便益実証の完了を待たず、現在の範囲を正確に説明する応募準備を進める。
2. **事業と就職の両方を選択肢として準備できる。** Simile、Andon Labs、Aaru、Artificial Societies、humans&、Anthropic の6社を下記の順位で調査対象にする。これは採用可能性の予測でも推薦内定でもない。本人の職歴、英語面談、移住意思、就労資格は未確認。YC採択時には会社へフルタイムで関与する要件があり、就職との実行上の整合は実際の条件が出た時に決める。
3. **Radiant は Artificial Societies の製品名。** 別会社として数えない。Ampersand/Persimmon は humans& の製品。検索で出た同名 RadiantGraph、Radiance、Persimmons半導体、Amperesand は対象から除外した。
4. **研究成果を用途別に見せる。** 動く小さなデモ、再実行可能な評価、失敗と限界を示す2ページの技術資料が中心。記事数・本の章数・slide数を人の便益や顧客tractionに置き換えない。
5. **外部の状態には受付証拠が必要。** 計画や草稿を `submitted`、返信を `interview`、口頭の好感触を `offer`、採用サイトの給与帯を個人の見込所得へ変換しない。

## 2. 既存資料を読んだ範囲と現在地

読取元: `AGENTS.md`、`products/manager/docs/MANAGER_PRODUCT_SPEC.md`、`products/manager/docs/plans/2026-10-22-manager-research-products-plan.md`、`products/manager/docs/founder/Y001_MANAGER_PITCH_EN_JA.md`、`products/manager/docs/research/manager-strategy-20261022/REPORT_JA.md`、E09/E16 verification、Ampersand ten-case receipt。Git root/branch/common-dir/origin を読み、canonical `Daisuke134/life-manager` の worktree と確認した。調査agentはscratchにのみ保存し、統合担当が本repoへ収録した。

現在の有限な製品は、所有する公開情報経路を観測・比較し、スコープを限定して変更し、独立に読み戻し、復元する Digital Autonomy v0.1。仕様上、E16 は **DEPLOYMENT_HOST_REQUIRED**、自律サイクルは本番未配備。既存の public support prototype の公開と、新サイクルの本番配備は別の証拠である。Y001 が引用する6 HTML・16 browser checksは2026-10-21の記録で、人16人の結果ではない。E16記録には2026-10-22 11:30 UTCの既存ページreadbackがあるが、今回の調査がそのデモを独立に再実行したわけではない。

E09はUCI日次集計の限定的・後ろ向き予測。subgroup risk が基準を超え **DENIED_SUBGROUP_RISK** を保持している。人の行動・福祉の較正へ転用しない。Ampersand ten-case receipt は実モデル呼出を含む架空scenarioの **P0_SYNTHETIC_ONLY / actual_people=0 / actual_effects=0 / settled_cost_usd=null**。CVや応募で「10人を改善」「収益」「検証済みAGI」と書けない。

## 3. YC W27 — 公式に確認した内容

| 項目 | 2026-10-22 の公式本文 | Managerの準備に必要なこと |
|---|---|---|
| batch・場所 | Winter 2027、January–March、San Francisco、in-person | SF滞在・フルタイム稼働の現実的条件を本人情報で確認 |
| 通常締切 | November 2 at 8pm PT | 年はW27 cycleから2026と判断。実日付のPST UTC−8をPython zoneinfoで変換済み |
| 結果 | on-timeならDecember 11まで | 2026年とcycleから判断。合格や個別面談の約束ではない |
| late | 締切後も検討するが応答時期を保証しない | late応募を通常締切の代替計画にしない |
| interview | 主にNovember/December、video conference、通常面接当日に判断 | 本番画面・実装説明・顧客仮説・限界に短く答える練習 |
| founder video | 1分、創業者が話すだけ、全創業者、台本朗読を避けbullet points | founder video と product demo を別ファイルにする |
| demo | founder videoとは別のapplication欄 | 動く範囲とsandbox／本番の区別を実画面で示す |
| eligibility | 世界中から応募可、solo founder可、応募前の米国法人化不要 | 国籍・visaを推測しない。採択後の法人・移住は具体条件で確認 |
| 現職との関係 | 現職・学生でも応募可、採択したらbatch中・後も会社にfull-time commitmentを期待 | 就職活動の存在を隠して時間的commitmentを架空にしない |
| 提出の証拠 | confirmation email with a copy of application | Y003は実際の提出控え／受付時刻を確認するまで進めない |

短い原文:
- Apply: “The deadline to apply on-time is November 2 at 8pm PT”
- Video: “The video should be 1 minute long and should contain nothing except the founders talking.”
- FAQ: “We send you a confirmation email with a copy of your application when you submit.”

公式URL:
- https://www.ycombinator.com/apply
- https://apply.ycombinator.com/home （公式Applyの遷移先。ログイン／フォーム記入／送信はしていない）
- https://www.ycombinator.com/video
- https://www.ycombinator.com/faq
- https://www.ycombinator.com/howtoapply

How to Apply全文は、曖昧な大義より具体的な製品、創業者の実績、独自の洞察、弱点の開示、簡潔な表現を勧める。これは公開された一般助言であり、**W27ログイン後の現在の全設問や文字数を検証したものではない**。応募欄は実際に開いた時に読み直す。FAQにはPaxel reportがoptionalとある。必須のために私的coding sessionを新たに共有する必要がある、と解釈しない。

用意する最小パッケージは、(a)買い手と利用者を分けた1文、(b)現在動くデモ、(c)創業者自身が作ったもの・判断したことの具体例、(d)観測事実と未検証仮説、(e)原価と次の反証可能な実験、(f)founder video。認証・送信・公開は本報告の範囲外。

**正直な英語説明案（founder videoの朗読台本ではなく、口頭練習の材料）:**

> I’m building Manager, software that maintains public-service information and records evidence of what changed. An owned support-navigation prototype is public. Our autonomous cycle has been verified in a sandbox; production deployment is still blocked on its host and adapter. We haven’t measured whether anyone obtained support or experienced better wellbeing. The next steps are a bounded production canary and conversations with operators about whether maintaining these journeys is a problem they would pay to solve.

公開デモ: https://daisuke134.github.io/life-manager/manager-support/ 。既存Y001の表現と歴史的検証日時を保持し、応募当日の実状態で更新する。

## 4. 応募先6社 — 公式求人本文を確認した短縮リスト

順位はManager成果物との接続しやすさによる。適合を断定しない。給与は広告値であり、本人の現在所得・予想内定額・手取り・実売上ではない。全6社とも読んだ求人にclosing dateは見当たらず、**締切未記載**。日本在住からの完全remote可と確認できた職種はこのリストにはない。

### 1) Simile — Evaluations - Member of Technical Staff

- 正式求人: https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662
- 応募: https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662/application
- 採用一覧: https://simile.ai/careers （確認時10 positions）
- 場所／雇用: San Francisco または New York、full time、**on-site**。
- 報酬: **$200,000–$400,000 USD** base salary range、equity/benefits。本文はSalary Rangeで、年額等の期間は明記していない。
- Must Haves: meaningfulなevalの判断、LLM/model fluency、統計的判断、Python/SQL/R等での実装、hands-on ownership。PhDや固定年数は列挙されていない。
- Nice to Haves: sampling/calibration、causal inference、LLM-as-judge、実験、行動データ、multi-agent/group behavior等。self-directed builder／recent graduateにも言及。
- Visa／就労資格: 読取本文にsponsorshipの明記なし。米国就労可能とも不可とも推測しない。same role再応募は90日待機policy。
- 合う成果物: E09のcoverage/riskとsubgroup failure、holdout境界、vendor指標を万能accuracyへしない比較表、再実行コード。最大のgapは**新しい人のground truthでの外部評価や顧客利用の証拠がまだない**こと。
- 短い原文: “How do we know when a simulation of human behavior is good enough to trust?”

### 2) Andon Labs — Research/Engineering: AI Safety and Evals

- 公式: https://andonlabs.com/join
- 公式からリンクされた現行応募フォーム: https://andonlabs.notion.site/32851e560a9581ea910ff74837b37806?pvs=105
- 場所: **San Francisco, in-person only**。フォームはFull time／Internshipを選ぶ方式。internship条件や同じ給与の適用は未確認。
- 報酬表記: **$120k–$180k salary + $300k–$900k equity**。通貨コード、給与期間、equityの評価・vesting条件は本文未明記。
- 仕事: 実配備agentのbehaviorを測るevalを設計・実行し、結果の解釈、次の実験、SAO control protocolsを実装する。固定学位／必要年数は明示なし。
- 応募フォームは「誇れるproject」とGitHub等のlink、公開Vending-Bench記事を読んだ上でeval setup改善案を求める。
- Visa: 明記なし。
- 合う成果物: no-per-run-approvalを前提にした権限境界、UNKNOWNの隔離、独立readback、rollback、replay-zeroとその失敗テスト。**Manager本番常時運用済みと書かない**。
- 短い原文: “We’re based in San Francisco (in-person only).”

### 3) Aaru — Research Engineer

- 公式求人／応募入口: https://aaru.com/careers/f04cd7a3-b53c-4797-bb8f-ebfe0467e9fe
- 現行一覧: https://aaru.com/careers （Research Engineerを含むResearch6 rolesを確認）
- 場所: **New York City、週5日office**。NY metropolitan areaに居住またはrelocationを想定。
- 報酬: 読んだ公式求人本文には数値の掲載なし。検索snippetの数値を採用しない。
- 本文のfit条件: deep ML/AI、production LLMのmeaningful prior work、仮説→評価→配備、**3+ years hands-on ML/AI systems**、data collection/training/evaluation/production lifecycle。
- Strong candidates may also: top venue publication、多agent、probabilistic/Bayesian/causal、hybrid architectures。これらを全て必須とは読まない。
- **Visa sponsorship と relocation support を明記**。個人のvisa承認保証ではない。
- 合う成果物: simulation contracts、evaluation harness、同一入力のbaseline比較、低費用化、raw outputから説明可能な成果物への変換。本人の3年以上の経験と大規模production実績は未確認のgap。
- 公開組織窓口: **jobs@aaru.com**。公式careers末尾 “Don’t see your role?” に掲載。特定社員の私的／推定addressは収集していない。
- 短い原文: “Research Engineers own the path from research idea to production system.”

### 4) Artificial Societies（Radiant）— Forward Deployed Engineer / ML Engineer

- FDE: https://societies.ai/careers/forward-deployed-engineer
- FDE応募: https://societies.ai/careers/forward-deployed-engineer/apply
- ML: https://societies.ai/careers/ml-engineer
- ML応募: https://societies.ai/careers/ml-engineer/apply
- 場所／雇用: 両方 **London、full-time、in-office**。
- 報酬表記: FDE **£100k–£180k + 0.05%–0.20% equity**、ML **£100k–£180k + up to 0.20% equity**。£はGBP、給与の期間は本文未明記。
- FDE条件: computational social science等のbackground、agentic AI、production Python/Git/code review。client-facingはpreferred。client brief→persona/network→experiment→interpretation→product化。
- ML条件: **startupで2年以上MLをship**、language-model pre/post-training（RL/finetuning/distillation等）、Python、統計・確率。classical MLのみでは不足と明記。論文・simulation/calibration OSSはnice-to-have。
- Visa: 読取本文にsponsorshipの明記なし。
- 合う成果物: Radiant field guide／AS benchmarkの用途別検証、集団分布と個人予測を区別した評価、既存Concordia adapterの隔離、再利用可能なdata/eval contract。FDEには顧客との実作業、MLには本番学習経験という別のgapがある。
- 短い原文（FDE）: “Location: London, in-office.”

### 5) humans& — Member of Technical Staff（Research）

- 公式企業: https://humansand.ai/ （公式footerがAmpersand／Persimmonをリンク）
- 現行採用一覧: https://jobs.ashbyhq.com/humans-and （確認時2 positions）
- 正式求人: https://jobs.ashbyhq.com/humans-and/3daf12ad-471f-43ba-b940-8552e9ad61aa
- 応募: https://jobs.ashbyhq.com/humans-and/3daf12ad-471f-43ba-b940-8552e9ad61aa/application
- 場所／雇用: **San Francisco、full time、on-site**。
- 報酬表記: **$450K base salary excluding equity、Offers Equity**。通貨ISOコード・期間は本文未明記。
- 要件: modern AIのfrontierでexceptionalなresearch/engineering work。詳細な技術別必須要件や固定学位／年数はこの短い求人に記載なし。
- Visa: 明記なし。
- 合う成果物: Ampersand公開aggregateの再計算、score-weight感度、原データと自分の推論を分けた再現性、10架空caseの負の結果。**モデル内部をreverse-engineerした、Ampersandと共同研究した、human outcomeを検証したとは書かない**。frontier研究実績が求められるstretch candidate。
- 短い原文: “researchers and engineers who have done exceptional work at the frontier of modern AI.”

### 6) Anthropic — Research Engineer, Post-Training Model Evaluations

- 公式ATS: https://job-boards.greenhouse.io/anthropic/jobs/5198255008
- 公式採用一覧（同じATSをリンク）: https://www.anthropic.com/careers/jobs
- 場所: **San Francisco, CA / Seattle, WA**。company hybrid policyは少なくともoffice25%、roleによって増える。日本からの完全remoteを意味しない。
- 報酬: **Annual Salary $500,000–$850,000 USD** と明記。
- fit条件: scaleでのML evalのdesign/run/analyze、measurement品質、強いPythonとproduction、曖昧な結果から判断、急なlive training問題への対応。post-training経験・統計／実験設計等はstrong candidates may also。
- minimum education: bachelorまたは同等のeducation/training/experience。必要経験年数はinternal levelに依存し固定値なし。
- **Visa sponsorshipあり。ただし全role／全candidateへ成功できるとは限らない**と明記。
- 合う成果物: evalの意味・限界、regression、quality gates、再現性と観測の信頼性。frontier production trainingを担当した証拠は未確認で、6社中でもstretchが大きい。
- Project Vend／agent evalsは既存研究資料で関連を確認できるが、この求人自体は**post-training eval fleet**。Managerに近い題材だけを根拠に職務を取り違えない。
- 応募にはcandidate AI guidanceを読んで本人の経歴・回答で提出する。今回フォーム記入はしていない。

## 5. イベント3件 — 開催日と応募／参加状態は別に記録

| 優先・用途 | 実日付・場所 | 公式確認した状態／deadline | 次の行動候補 |
|---|---|---|---|
| 1. AI Engineer Code Summit — agent実装者・採用担当との技術会話 | **2026-11-10–12、SF Hilton Union Square**。workshop10日、本会議11–12日 | **Applications now open、参加はapplication-only**。申請無料だが座席は確保されない。approvedならRegular $1,299+fees、workshop+$299+fees。**CFP closed**、speaker結果late October予定。参加申請締切は未記載 | 無料livestream/YouTubeを優先可能。現地参加は費用・移動条件と既存予算方針に照らして別判断。参加や登壇を獲得したとは書かない |
| 2. NeurIPS 2026 — 行動simulation/eval/agent研究者、career site | **Sydney12/6–12、Atlanta/Paris12/9–13** | Homeおよびpricing上部: early registration **10/30 AoE**。refund **11/4 AoE**。ticket waitlistから追加開放との告知。virtual-only passあり、金額は取得本文の動的表から確定不可 | 既存の論文投稿期限は通過。今からmain-track論文を出せるとは書かない。career siteと公開programで3テーマを絞り、具体的質問を準備 |
| 3. AAMAS 2027 — autonomous agents／multiagentの研究方向 | **2027-05-03–07、Hanoi JW Marriott** | Main abstract10/1・paper10/8は過去。Blue Sky **abstract11/5、paper11/12、全てAoE UTC−12**。ただし **OpenReview author registration10/20** と記載があり既に過去。new authorが今から提出できるか未確認。workshop proposal10/29、workshop paper推奨1/24、early registration3/17はtentative | まず既存OpenReview資格とCFPを読む。満たせなければ聴講／将来workshop候補。Blue Skyも4頁、original、double-blind、expertise、rationaleとtrack-record回答が必要。仕様書を論文として提出しない |

公式URL:
- https://ai.engineer/code/2026 （日程・参加費・申請・CFP全文）
- https://neurips.cc/ （日程・waitlist・careerリンク・早期登録）
- https://neurips.cc/Conferences/2026/Pricing （pricing/virtual/refund）
- https://neurips.cc/careers/ （公式homeからリンク。**今回は本文未読**）
- https://warwick.ac.uk/fac/sci/dcs/aamas2027/
- https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/call-for-blue-sky-ideas/

NeurIPSのpricing頁は上部の10/30 23:59 UTC−12と、末尾の “2026-10-31 22:59 pacific time” に時刻表示の不一致がある。ここで勝手に一方へ訂正しない。登録が必要な段階で公式フォームの時刻を再確認する。AAMASのauthor-registration期限が過去である点も、abstract deadlineだけ抜き出すと誤る重要な制約である。

追加探索したSusHi Tech Tokyo 2027は検索snippetに日付があったが、公式 https://sushitech-startup.metro.tokyo.lg.jp/en/ のlive fetchは **503 maintenance**。今回の「日付・受付状態を公式本文確認した候補」には数えない。AGNTCon/MCPCon North America10/22–23は調査日当日開始の検索結果が出たが、事前準備可能な将来3件を優先し採用しなかった。

## 6. 成果物 → 職務 → 追加する証拠

| 既存成果物 | 見せる先 | 1つのreview packetにする時の内容 | 埋めるgap |
|---|---|---|---|
| E09 scoped calibration + code + CI | Simile / Aaru eval | scope固定、split/hash、coverage-risk、subgroup failure、非昇格理由 | 新しいtask-matched reference。人のprediction calibrationへ外挿しない |
| E16 kernel・outbox・独立readback・rollbackテスト | Andon / Aaru engineering | 失敗1例→再現テスト→guard→readback→replay-zero | persistent host／production adapter／実本番canaryは未完 |
| Ampersand aggregate再計算・感度・ten-case raw receipt | humans& / Simile | providerの公開値と自分の計算、baseline同点／不利な結果、actual_people0 | 未公開内部や独立human validationを知っていると装わない |
| AS/Radiant field guide、Concordia隔離adapter | Artificial Societies / Aaru | population／question／time、分布と個人、rights、data provenance | 実際のclient briefing、CSS/background、production ML経験は本人確認 |
| live support prototype + Y001 + rendered presentation | YC / deployment/product職 | 30秒の実画面、technical proof、顧客仮説、次の反証実験 | customer interview、利用、支払意思、売上、便益は未確立 |
| bilingual文章／図／book chapter | 技術コミュニケーションの補助 | 相手のroleに必要な2頁だけ抜き出す | 長さや記事量をskillsや売上の代理指標にしない |

ローカル参照先:
- `products/manager/docs/verification/E09_SCOPED_CALIBRATION_20261022.md`
- `products/manager/docs/verification/E16_CYCLE_AND_DEPLOYMENT_GATE_20261022.md`
- `products/manager/docs/research/ampersand-20261022/README.md`
- `products/manager/docs/verification/ampersand-20261022/ten_case_receipt.json`
- `products/manager/docs/articles/manager-radiant-societies-field-guide-en.md`
- `products/manager/docs/founder/Y001_MANAGER_PITCH_EN_JA.md`
- `products/manager/docs/presentations/artifacts/Manager_Completion_YC_20261022.pdf`

## 7. 的を絞ったcadence案 — 実施前の準備として

**2026-10-22〜10-25:** W27応募用の最新事実・founderの職歴・commitment・demoを揃える。同時に共通CVと2頁のevidence packetを作り、Simile/Andon/Aaruの各JDに1つずつ対応させる。応募文を大量生成する前に、本人の職歴・学位・就労／移住・英語・望む雇用形態を空欄のまま保持し確認する。

**10-26〜10-30:** 1日1社以内、まず3社まで。公式job applicationにrole-specificな成果物1つと短いcover noteを用意する。Aaruのように公開組織窓口があれば、role不明時の問い合わせ案を用意できる。冷たいメールを自動で多数の人へ送らず、最初は**1社1窓口・1目的**。提出／送信はこの報告で行っていない。

**11-01までを内部準備目安:** YCのフォーム、創業者動画、別demoをレビュー可能な形にする。これは公式の新締切ではない。通常締切は11/02 20:00 PT。全研究／本の完成を待たない。

**送信を別途実施した場合:** 5–7営業日後、成果物の具体的な更新がある時に1回だけfollow-up。これは返信保証のない運用提案で、今回は送っていない。明示的拒否・停止要請なら終了。週1回30分、verified/open/closed/返信証拠を見直し、改善するのは見せる実績と職務の対応。

**イベント:** 週1回、次の2週間の公式programから1件を選び、公開論文／デモについて具体的質問を3つ準備する。非公開社員連絡先の推測収集は不要。無料streamと公開研究を利用し、まだ得ていない紹介・登壇・参加実績を書かない。

## 8. 公開窓口に送る場合の正直な英語案（未送信）

**Subject:** Research engineering — reproducible evals and bounded autonomous execution

> Hello Aaru team,
>
> I’m building Manager, a prototype for maintaining public-service information with bounded autonomous execution and independent readback. I’m interested in your Research Engineer role, particularly simulation contracts and evaluation infrastructure.
>
> I have an owned public demo and reproducible evaluation artifacts that preserve negative results. Our reference calibration is scoped to one retrospective aggregate task; our autonomous cycle is verified in a sandbox and is not yet deployed in production. We have not measured human benefit.
>
> I’d like to share a short evidence packet showing the evaluation harness, failure cases, and engineering decisions, and discuss whether that work is relevant to your team.
>
> Public prototype: https://daisuke134.github.io/life-manager/manager-support/
>
> Thank you,  
> Daisuke

氏名・経歴・英語・稼働条件は本人が最終確認する。実際に本人が説明できる貢献だけ残す。3年以上ML、frontier training、顧客実績、資金調達、収入等を補って作らない。Simile宛てならcalibration/measurement、Andon宛てならunknown/rollbackに主題を変え、相手の役割について読んだ具体的箇所を1つ示す。公開組織窓口として確認したのはAaruの **jobs@aaru.com**。他社は直接job formを使う候補とし、個人のemail patternを作らない。YCの **apply@ycombinator.com** は公式応募質問窓口で、就職営業の宛先ではない。

## 9. 既存台帳へ追加するpipeline契約案

状態は既存のManager SSOTに組み込む設計であり、本報告自体に新しい進捗authorityを作らない。career、YC、eventの種類を持たせ、同じ「応募」を混同しない。

| state | 進めるための証拠 |
|---|---|
| DISCOVERED | 公式URL・対象会社／role・source timestamp |
| VERIFIED_OPEN | 同日全文、title/location/eligibility、Apply route、closed noticeなし。期限が不明ならnull |
| FIT_REVIEWED | 本人の実経歴との比較。must/preferred、移住／visa／働き方、gapを記録 |
| DRAFT_READY | CV/回答/video/demoのhashまたはversion。ここまで外部提出なし |
| SUBMITTED | official acknowledgement、submission ID/receipt、時刻、role、提出version。タイムアウト時はEFFECT_UNKNOWN |
| EFFECT_UNKNOWN | 受付が不明。既存提出状況を読戻すまで再送しない。失敗や未提出へ勝手に変換しない |
| RESPONSE_RECEIVED | 実返信の証拠。自動受付と人の返信を区別 |
| INTERVIEW_SCHEDULED / COMPLETED | 実招待＋日時／実施の記録。単なる希望や会話を数えない |
| OFFER_RECEIVED | 正式な書面、雇用条件、報酬・通貨・期間・期限。広告のsalaryはofferではない |
| ACCEPTED / DECLINED / REJECTED / CLOSED | 本人の意思決定または相手の正式結果と日付 |
| YC_ACCEPTED / EVENT_ADMITTED / ATTENDED | 各providerの正式結果／参加実態。job offerや人の便益とは別 |

最低fields: `kind, organization, role_or_batch, official_url, apply_url, checked_at, read_depth, open_status_evidence, deadline_local, timezone, deadline_utc, location, remote_restrictions, visa_text, compensation_text, fit_gaps, artifact_refs, draft_version, last_action_at, next_action_at, receipt_ref, outcome`。未確認の値はnull/UNKNOWN。private receipts/CVはownerの既存private storeに置き、repoに個人のemailや応募書類全文を追加しない。

## 10. 検証済み・未検証を分けたsource ledger

下記「全文読取」に列挙した求人本文・イベント主頁・YC公開ページは**公式本文を全文取得・読取、live fetch maxAge0、2026-10-22確認**。直接application URLのうち、AndonのNotionフォーム以外は求人本文にリンクがあることを確認しただけで、フォームを開いていない。公開デモも今回独立取得していない。更新日がページにない場合、確認日は記事や求人の公開日を意味しない。HTTP200だけを受付の証拠にはせず、求人のApply・現行一覧・応募フォームを合わせて採用した。job formの送信ボタンは押していない。

- **全文読取:** YC apply/video/faq/howtoapply、Simile careers＋Eval求人、Aaru careers＋Research Engineer求人、Artificial Societies ML/FDE求人、Andon join＋AI Safety/Evals応募フォーム、humans&企業＋採用board＋Research MTS、Anthropic当該ATS求人、AI Engineer Code、NeurIPS home/pricing、AAMAS home/calls/Blue Sky CFP。
- **検索のみ／本文未読:** Anthropic careers一覧は検索の長い公式excerptでATSとの関連を確認し、採用本文の根拠は当該ATSを使用。DeepMind careersは候補探索だけで、特定role未検証のため6社へ追加しない。NeurIPS career boardは公式homeリンクのみ確認し、個別求人を見たとは主張しない。
- **取得失敗:** SusHi Tech公式503 maintenance。確定日程／受付候補から除外。
- **未確認:** W27ログイン後の現在の全設問、本人のアカウント／提出状態、全roleの応募締切、Aaru以外・Anthropic以外のvisa、本人の適合／移住、AAMAS late author registration、イベントticket残数、今後の採否。
- 検索は網羅調査ではない。給与は会社の公開募集条件であり、現在の成果・収入を表さない。

**実施結果:** 調査agentによる調査と報告のみ。統合担当による文書収録とは別に、申請、contact、登録、支出、income、interview、offer、admissionは本調査では発生していない。


---
統合注記: このlaneは読取調査として実施し、報告を製品repoへ収録した。現行状態・改稿結果は [統合更新](FOUNDER_EXECUTION_UPDATE_JA.md) と既存task台帳を参照。
