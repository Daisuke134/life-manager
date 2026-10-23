# BJAK — Applied AI Engineer, AI Finance Agent 応募下書き

状態: 未提出。指定URLの正式な求人名はApplied AI Engineer - AI Finance Agent。公式フォーム17項目（必須14・任意3）を取得し、要旨を掲載順に示す。

- 求人: https://jobs.ashbyhq.com/bjakcareer/bdaca888-9ed5-402f-bd73-48ae269da06e
- フォーム: https://jobs.ashbyhq.com/bjakcareer/bdaca888-9ed5-402f-bd73-48ae269da06e/application
- 確認経路: 公式HTMLと `ApiJobPosting` 読み取り。`isListed=true`、Tokyo、Hybrid、FullTime。日本officeへ週3日以上の出社、強い英語コミュニケーションを求める。
- 求人要件の要旨: 金融サービスの業務でagent・自動化を実装し、評価・監視・fallbackを含めて本番化する。フォームでは職業ソフトウェアエンジニア経験3年以上と、職務での言語・LLM利用を個別に問う。

## フォーム回答案

| # | 質問の要旨 | 必須 | 回答案・扱い | 事実根拠 |
|---|---|---|---|---|
| 1 | 氏名 | 必須 | `Daisuke Narita`。正式表記は提出担当が照合する。 | PROFILE |
| 2 | メール | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 3 | 電話 | 必須 | 私的正本 `candidate.phone` から入力し、国番号・到達性を提出担当が確認する。 | PROFILE |
| 4 | 国籍 | 必須 | `Japanese` | JP |
| 5 | 現在の国・都市 | 必須 | `Tokyo, Japan` | TOKYO |
| 6 | LinkedIn | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 7 | Resume | 必須 | 既存の英語技術職用PDF。許容拡張子・容量は今回のフィールド定義では未確認なので、画面の制限に従う。 | RESUME |
| 8 | 就労visaが必要か | 任意 | `No`。日本での勤務を前提とする。 | JP |
| 9 | 採用マーケティング目的での個人情報処理とbusiness updates等の連絡への同意（表示タイトル空欄） | 必須 | **入力保留。** 既存資料にはこのBJAK固有のマーケティング同意がない。必須だからという理由で本人の意思を作らず、提出担当が同意内容と意思を確認する。 | 公式フォーム・未確認 |
| 10 | 職業ソフトウェアエンジニア経験が3年以上あるか | 必須 | **`Yes`の根拠なし。** 資料で確認できるMUITの開始は2025年4月。大学研究・個人開発・marketing internを足して3年以上としない。現資料に基づく選択案は `No`。未記載の該当実務がある場合だけ本人の具体的履歴で更新する。 | MUIT・RESUME |
| 11 | 実ユーザーが本番で使うAI機能を1つ以上構築・出荷したか | 必須 | `Yes`。Agentforceの銀行CRMへの導入への寄与と、Aniccaの出荷が根拠。単独で銀行システム全体を構築したとは主張しない。 | MUIT・ANICCA |
| 12 | LLMを職務で扱ったことがあるか | 必須 | `Yes`案。AgentforceのAI-agent導入・prompt tuning/context engineeringが根拠。特定の基盤モデルproviderへ直接接続した経験までは含めない。 | MUIT・PROMPT |
| 13 | Node.jsを職務で使ったことがあるか | 必須 | **入力保留。** 個人repoの使用と職務での使用は別。既存resumeに職務上の利用は明示されない。 | 未確認 |
| 14 | Pythonを職務で使ったことがあるか | 必須 | **入力保留。** Databricksや機械学習研究という記述だけでは、職務で使った言語と責任範囲を確定しない。 | 未確認 |
| 15 | 職務で利用したLLM providerを選択 | 必須 | **入力保留。** 選択肢はOpenAI/Anthropic/Llama/Gemini/Mistral/DeepSeek/Other/None。Agentforce利用だけで下位providerを特定せず、個人でのcoding tool利用も職業利用へ置換しない。未確認を `None` にもしない。 | 未確認 |
| 16 | AI評価・A/Bテスト・prompt評価frameworkの経験があるか | 必須 | `Yes`案。正本のagent workflowの評価gateとprompt品質分析を根拠とする。A/Bテストの実施や特定frameworkの利用までは主張しない。 | RELIABILITY・LOGS・PROMPT |
| 17 | GitHub・portfolio・demo・AI projectのリンク | 任意 | 下記のリンク回答案。 | PROFILE・LM |

### 質問17の回答案

> GitHub: https://github.com/Daisuke134
>
> Life Manager: https://github.com/Daisuke134/life-manager
>
> Life Manager is my open-source local agent system for persistent scheduling and verified actions across everyday workflows.

## カバーレター案（補足原稿）

カバーレター専用欄はない。質問17を長い志望動機欄として扱わず、下記は別途求められた場合の原稿とする。

> Dear BJAK Hiring Team,
>
> I am interested in the Applied AI Engineer role for the AI Finance Agent because it connects applied AI with the financial workflows that users and operators need to rely on.
>
> At Mitsubishi UFJ Information Technology, I contribute to the deployment of Salesforce Agentforce agents in MUFG Bank's internal CRM for relationship managers. My contributions include a Databricks workflow for analyzing agent inputs, outputs, and response quality, and prompt tuning and context engineering for company-information summaries. This gives me relevant experience with AI inside an existing financial-services workflow.
>
> I also build Life Manager, an open-source local agent system with persistent scheduling and verified external actions, and built and shipped Anicca, a mobile affirmation app. In my agent workflows, I use durable state, automated checks, evaluation gates, and independent confirmation before retrying uncertain external actions. This is the background I would bring to discussions of useful automation, evaluation, and reliable operation at BJAK.
>
> My documented MUIT role begins in April 2025, and I do not represent my research or personal projects as three years of professional software engineering employment. If my experience is relevant to your team's needs, I would welcome a practical technical discussion. I am based in Tokyo, can work onsite at least three days per week, and am available from December 1, 2026 without Japanese work-visa sponsorship.
>
> Daisuke Narita

## 根拠・未確認事項

ラベルと資料は [タスクspec](../../specs/job-application-drafts.md#経歴根拠) を参照する。実績はMUIT・LOGS・PROMPT・LM・ANICCA・RELIABILITY、所在地/就労権/開始日はTOKYO・JP・START。

3年以上の職業経験というscreeningには現資料で適合を示せない。Node.js/Pythonの職業利用、職業利用したLLM provider、BJAK固有のマーケティング同意が未確認。LANGの英語試験実績を勤務言語の採用判断と同一視しない。曖昧な「すべての必須経験へYes」という過去の包括的な記録より、今回の各質問に対応する具体的経歴を優先する。
