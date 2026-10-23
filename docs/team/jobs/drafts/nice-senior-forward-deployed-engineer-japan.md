# NICE — Senior Forward Deployed Engineer 応募下書き

状態: 未提出。公式求人とフォーム16項目（必須10・任意6）を取得する。質問の要旨と回答案を掲載順に示す。

- 求人・フォーム: https://boards.eu.greenhouse.io/nice/jobs/4981245101
- 確認経路: 公式Greenhouseページの本文・埋め込みフォーム定義。Japan - Remote、求人番号11747。終了表示はない。
- 求人要件の要旨: 企業向け会話agentの構築・評価・運用と顧客との実装を担当する。日本国籍または永住資格が必須。Seniorの職名を本人の現職・経験年数として転用しない。

## フォーム回答案

| # | 質問の要旨 | 必須 | 回答案・扱い | 事実根拠 |
|---|---|---|---|---|
| 1 | First Name | 必須 | `Daisuke` | PROFILE |
| 2 | Last Name | 必須 | `Narita` | PROFILE |
| 3 | Preferred First Name | 任意 | 空欄。別のpreferred nameを推測しない。 | PROFILE |
| 4 | メール | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 5 | 電話 | 任意 | 私的正本 `candidate.phone` と登録状態を提出担当が確認して入力する。値は記載しない。 | PROFILE |
| 6 | Resume/CV | 任意 | 既存の英語技術職用PDFを添付する案。PDF/DOC/DOCX/TXT/RTFまたはテキスト入力に対応する。 | RESUME |
| 7 | Cover Letter | 任意 | 下記の英文。手入力または対応形式の添付。 | MUIT・LOGS・PROMPT・LM・TEACH |
| 8 | LinkedIn | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 9 | Website | 任意 | https://github.com/Daisuke134/life-manager | LM |
| 10 | 配偶者・親・子・きょうだいがNICE/子会社に在籍しているか | 必須 | **入力保留。** 家族の勤務先は既存資料で確認できず、`No`と推測しない。 | 未確認 |
| 11 | NICE/子会社で働いたことがあるか | 必須 | **入力保留。** 既存履歴にはNICE在籍の記載がないが、子会社を含む生涯の在籍否定までは裏付けない。 | RESUME |
| 12 | 日本国籍または永住資格があるか | 必須 | `Yes`。日本国籍。 | JP |
| 13 | 希望する年間基本給（JPY） | 必須 | `JPY 10,000,000 annually, negotiable depending on the role and overall package.` 総報酬と基本給は別なので、基本給としての希望額は提出前に確認する。 | SALARY |
| 14 | Notice period | 必須 | `I am available to start on December 1, 2026. My contractual notice period needs to be confirmed.` 退職予告期間を1か月などと作らない。 | START |
| 15 | 応募前からNiCEを知っていたか。知った経路・当時の知識 | 必須 | **応募前の認知は未確認。** 現時点で使える素材: `I learned about this opportunity through NICE's official careers posting. I am interested in the role's focus on building and operating enterprise AI agents.` 過去の認知については本人の事実で補う。 | 公式求人・未確認 |
| 16 | 転職先選びで重視する要素を3つ選ぶ | 必須 | **提案:** `Meaningful professional challenges`、`Hands-on work with AI and AI skill development`、`Career growth and development`。職務との適合に基づく提案であり、本人の上位3項目を確認済みとは扱わない。 | 志向の回答案 |

希望額の私的正本は約1,000万円の目標を持つが、「基本給が1,000万円必須」「現在年収が1,000万円」とは主張しない。フォーム定義には独立したEEOC設問・マーケティング同意欄はない。提出画面で追加項目が出た場合は未確認として扱う。

## カバーレター案

> Dear NICE Hiring Team,
>
> I am interested in the Senior Forward Deployed Engineer role because its focus on operating enterprise AI agents connects closely with my work in banking and my own agent projects.
>
> At Mitsubishi UFJ Information Technology, I contribute to deploying Salesforce Agentforce agents into MUFG Bank's internal CRM for relationship managers. I built a Databricks workflow to analyze agent inputs, outputs, and responses, and supported prompt tuning and context engineering for company-information summaries. These contributions have made me interested in the practical questions of response quality, workflow fit, and dependable operation in a regulated enterprise environment.
>
> I also build Life Manager, an open-source local agent system with persistent scheduling and verified external actions. Outside enterprise work, I built and shipped Anicca, a mobile affirmation app. Together, these projects give me experience connecting agent behavior with the needs of operators and users. I have also founded a weekly community teaching AI coding tools and agent workflows in a research setting.
>
> I would welcome the opportunity to bring this background to NICE's customer deployments and to discuss the specific systems I have built and the boundaries of my contributions. I am based in Tokyo, am authorized to work in Japan without sponsorship, and am available from December 1, 2026.
>
> Daisuke Narita

## 根拠・未確認事項

根拠ラベルと資料の保存先は [タスクspec](../../specs/job-application-drafts.md#経歴根拠) を参照する。実績はMUIT・LOGS・PROMPT・LM・ANICCA・TEACH、所在地/就労権/開始日はTOKYO・JP・START。

親族の在籍、NICE子会社を含む勤務歴、契約上のnotice period、応募前のNiCE認知、希望基本給と上位3要素の確定が残る。RAG・Go・Reactの職務経験やNICE製品の利用歴は追加しない。応募の重複確認と提出は参謀の担当とする。
