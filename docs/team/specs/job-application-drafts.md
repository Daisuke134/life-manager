# 求人応募文5件の下書き

目的: 参謀が公式フォームへ提出できる、求人別の回答案とカバーレターを5件作成する。

範囲: 公式求人本文とフォームを読み、既存の経歴・私的プロフィール・取得できたDots資料だけを事実根拠に使う。原稿は `docs/team/jobs/drafts/<company-role>.md` に保存する。公開repoへ連絡先・住所・生年月日・資格情報を複製せず、提出担当が私的正本から入力する。経歴や回答の不明点は明記する。応募送信・ledger・Thankful/build 10・他担当の作業領域は変更しない。

完了条件: 各求人の確認状態、実際の質問と必須/任意、回答案、根拠、未確認事項、カバーレターを5ファイルへ保存する。専用branch/PRをmainへ統合し、公式readback後にReasonで `daisuke/cursor` へPR URLを送る。閉鎖・取得不能の求人では、その状態と未取得の質問を明示し、架空のフォームを実在扱いしない。

## 対象と現在cursor

1. [Cursor FDE Japan](../jobs/drafts/cursor-forward-deployed-engineer-japan.md) — 原稿あり。公式フォーム8項目。求人本文のブランド混在と5年以上の経験要件、説得事例の不足を明記する。
2. [NICE Sr FDE Japan](../jobs/drafts/nice-senior-forward-deployed-engineer-japan.md) — 原稿あり。公式フォーム16項目。親族/子会社在籍など未確認回答を保留する。
3. [OpenAI Applied AI Engineer, Codex Tokyo](../jobs/drafts/openai-applied-ai-engineer-codex-tokyo.md) — 原稿あり。公式フォーム12項目。本人記入等の宣誓を代理で同意しない。
4. [OpenAI Applied AI Engineer Tokyo](../jobs/drafts/openai-applied-ai-engineer-tokyo.md) — 原稿あり。公式フォーム10項目。Codex職と異なる質問構成を保持する。
5. [BJAK Applied AI Engineer Tokyo](../jobs/drafts/bjak-applied-ai-engineer-tokyo.md) — 原稿あり。公式フォーム17項目。3年以上の職業経験を裏付けず、言語別の職務使用と採用マーケティング同意を未確認として扱う。

現在cursor: 下書き5件・全63項目の公式schema対応と事実根拠の照合を完了する。必須/任意の内訳と非公開連絡先の非掲載を確認する。ソース受入後の提出判断・未確認回答は各原稿を参照し、応募送信は参謀が所有する。PRのCI/統合状態はGitHubの当該branch/PRを正本とする。初回取得時に存在しない `docs/team/dots/` は、参謀のPR #8732で新設される。追加されたREADMEを読み、経歴・応募文メモはまだ未記入であることを確認する。参照先の既存応募履歴は読み取りのみ確認し、応募状況を職務経験の根拠へ転用しない。原稿の経歴根拠は私的プロフィールと既存英語技術職用resumeに限定する。具体的な回答を裏付けない包括的な経験attestationは、年数・言語・provider利用の根拠にしない。

## 経歴根拠

- **DOTS:** [共有メモREADME](../dots/README.md) と既存台帳のhistorical job application reconciliation節。READMEは今後のメモ置き場で、本文の経歴・応募文実例は未記入。過去のCursor AI Deployment Managerは今回のFDEとは別職であり、過去応募を今回の提出実績へ置換しない。台帳の編集・応募・個人メールの本文取得は行わない。原稿の正本pathは当初指定の `docs/team/jobs/drafts/` とし、別のdrafts directoryへ複製しない。

公開可能な職務・成果の要旨だけを原稿へ使う。メール・電話・住所・生年月日・私的属性の値はここへ複製しない。

- **PROFILE:** `/Users/anicca/.config/anicca/job-search/profile.json` の `candidate`。英字名、公開GitHub/LinkedIn、非公開連絡先の参照元。日本語氏名は依頼と私的正本に表記差があるため、原稿は共通する英字名を用い、正式氏名欄は本人IDとの照合を残す。
- **RESUME:** `/Users/anicca/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.html` と対応PDF。review用コピーとも職務記述を照合する。提出にはこの既存PDFを使う案を示し、PDF自体や連絡先をGitへ追加しない。
- **MUIT:** `facts[id=muit_role_2025]`、`muit_agent_crm` とRESUME。MUITのApplied AI/AI-agent業務は2025年4月開始。MUFG Bankのrelationship manager向け内部CRMへのSalesforce Agentforce導入へ寄与する。単独主導や5年以上の実務とは書かない。
- **LOGS:** `muit_genie_logs` とRESUME。Databricksでagentの入出力・応答品質を分析するworkflowを構築する。改善率や使用言語を補完しない。
- **PROMPT:** `muit_rm_summary` とRESUME。会社情報summary等へのprompt tuning/context engineeringを支援する。
- **TEACH:** `agent_club` とRESUME。研究室/大学院でClaude Code・Codex・Cursor・agent workflowを教える週次communityを設立する。参加人数・抵抗の具体例・採用結果は未記載。
- **LM:** `life_manager`、`life_manager_open_source_operations_20260805`。Life Managerはlocal agent、永続schedule、calendar/commute/phone/Telegram等の検証付き外部操作を扱うopen-source project。公開コード: https://github.com/Daisuke134/life-manager 。
- **RELIABILITY:** `async_operating_practices_20260805`、`agent_reliability_engineering_20260805`。限定変更、自動check、永続state、評価gate、明示handoff、曖昧な外部作用の独立確認を実践する。企業顧客への成果数値へ置換しない。
- **ANICCA:** `anicca_consumer` とRESUME。mobile affirmation appの構築・出荷。過去のrating件数を現在値として転記しない。
- **RESEARCH:** `naist`、`atr_research`、`education_naist` とRESUME。NAIST/ATRでEEGとmachine learningによるmind-wandering研究を行う。研究期間とMUITの在籍期間は一部重なる。修士号授与は未確認なので取得済み学位としない。
- **LANG:** `languages` とRESUME。日本語native、TOEFL iBT 96、TOEIC 910、Duolingo English Test 140。試験実績を勤務上のfluency認定へ置換しない。
- **JP:** `legal_japan_work_authorization_20260730`、`legal_no_japan_sponsorship_required_20260806`。日本国籍、日本国内の就労制限なし、国内就労sponsorship不要。
- **TOKYO:** `candidate.base`、`availability_tokyo_office_three_days_20260806`。Tokyo在住、週5日office勤務も可能。
- **START:** `candidate.start_date`、`availability_start_date_20261201`。入社可能日は2026年12月1日。契約上のnotice periodそのものは未確認。
- **SALARY:** `candidate.desired_compensation_jpy` とcompensation target。目標約1,000万円。現在年収・希望基本給の厳格な下限・上限とは混同しない。

公式フォームはAshbyの公開 `ApiJobPosting` queryとNICE/Greenhouseの埋め込み定義から読み取る。mutationや応募APIは使わない。求人URLと現行フォームの状態は各原稿に記録する。入力方式・必須/任意は取得したschemaに基づき、同意や個人情報の未確認を任意・falseへ置換しない。

検証: 質問一覧との対応、事実の出典、未確認事項の明示、連絡先/secret非掲載、変更path、diffチェック、公式CI、main上の5ファイルを確認する。アプリのビルド・追加テスト・応募提出は行わない。

## 追加5件のclaimと応募素材

目的: 前回5件と既存応募を除外し、未claim求人から適合度の高い新規5件を確保して参謀へ渡す。

範囲: `origin/main:ledger/APPLICATIONS.md` を唯一の共通台帳として読む。未claim行の既成リストは存在しないため、公式求人から新しい候補を調べ、勤務地、AI導入・実装との関連、既存経歴との一致、経験年数の不足を比較する。過去の応募・不明な送信結果・同一職種の再掲は新規候補にしない。候補ごとに `scripts/ledger-check.sh <key>` を実行し、`owner=codex`、`status=claimed` の5行をPRでmainへ統合してから原稿を作る。台帳の旧main直push手順より、最新のPR指示を優先する。

成果物: 求人別の実際のフォーム項目への回答案とカバーレターを既存 `docs/team/jobs/drafts/` に追加する。経歴の出典は上記PROFILE/RESUME等を再利用し、回答不能・本人意思・経験要件の不足は明示する。提出用メールは参謀指定の値と私的正本の一致を確認し、公開原稿には連絡先の値を複製しない。

完了条件: claim PRと追加5件のドラフトPRがmainへ統合され、main上の5キーと5ファイルを公式readbackで確認する。Reasonで `daisuke/cursor` へ両PR URLと5キーを返信する。応募送信、応募済みへのstatus更新、Thankful/build 10、他のCodex作業、runtimeやcronは範囲外。

選定基準: 調査した公式求人の中で、東京勤務、既存のAI導入・実装・指導との接点、固定年数の制約、報酬帯を比較する。下表はその候補内の優先順であり、全市場の網羅順位や採用可能性の予測ではない。5年以上を要求するNotion FDE/Architect、4年以上のCognition Support、3〜5年のGenspark CSMを下げる。Algomatic AI Builder（組織変革本部）は既存履歴でchecker exit 1となるため除外する。雇用先除外リストも確認する。

| 順位 | 求人・公式情報 | key | 根拠と不足 |
|---|---|---|---|
| 1 | [LayerX — 【バクラク】AI Builder](https://open.talentio.com/r/1/c/layerx/pages/122552) | `job:open.talentio.com/r/1/c/layerx/pages/122552` | Agent活用・実装・業務変革が直接関連。固定経験年数なし。生産性改善の数値、特定言語の職務使用は未確認。 |
| 2 | [Algomatic — AIエンジニア](https://herp.careers/v1/algomatic/3b_GpdNQjy8N) | `job:herp.careers/v1/algomatic/3b_gpdnqjy8n` | 実務・研究・個人開発を評価。LLM実装/研究と接点。個別言語・RAG等の経験は補完しない。 |
| 3 | [Cognition — Forward Deployed Engineer - Japan](https://jobs.ashbyhq.com/cognition/9ebb0dff-2cbf-42ba-bb4a-0256812a06e0) | `job:cognition:9ebb0dff-2cbf-42ba-bb4a-0256812a06e0` | 企業AI導入支援・ツール指導と接点。STEM学位授与は未確認。過去のPartner Deployed Engineerとは別職種。 |
| 4 | [Databricks — Scale Solution Engineer (Japanese-speaking; English required)](https://databricks.com/company/careers/open-positions/job?gh_jid=8779016002) | `job:databricks:8779016002` | Databricks応答品質分析とML研究が直接関連。technical role 2年以上を要求、MUIT職務は2025年4月開始。cloud/言語/ETLの要件充足は未確認。過去FDEとは別職種。 |
| 5 | [エクスプラザ — 【正社員】フルスタックエンジニア](https://herp.careers/v1/explaza/4GzgM8DDKYId) | `job:herp.careers/v1/explaza/4gzgm8ddkyid` | AI活用・agent運用設計と接点、固定年数なし。cloud設計構築と職務上のfull-stack経験は未確認。年収500〜800万円は希望下限800万円と上限のみ重なる。 |

5キーはすべて `scripts/ledger-check.sh` がexit 0（FREE）であることを最終確認してから台帳へ追加する。既存のCognition Partner Deployed Engineer、Databricks FDEのstatusは変更しない。

現在cursor: 5件のclaimを専用PRでmainへ統合する。その後、フォームの取得範囲・回答案・カバーレターを5原稿へ保存し、別のドラフトPRを統合する。前回の5原稿はPR #8730で完了済みとして保持する。
