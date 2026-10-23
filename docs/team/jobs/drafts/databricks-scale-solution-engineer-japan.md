# Databricks — Scale Solution Engineer (Japanese-speaking; English required)

応募ドラフト。送信は参謀が所有する。台帳key: `job:databricks:8779016002`。claim PR: [#8780](https://github.com/Daisuke134/life-manager/pull/8780)。

公式求人: https://databricks.com/company/careers/open-positions/job?gh_jid=8779016002 。公式Greenhouse公開API `https://boards-api.greenhouse.io/v1/boards/databricks/jobs/8779016002?questions=true` でTokyoの現行求人本文とフォーム全12項目（必須9・任意3）を取得する。location questions・demographic questionsの追加はなく、data complianceのprocessing/retention consentは必須false。応募API・アップロード・送信は使わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`。メールはPROFILE `candidate.application_email`と参謀指定の応募用アドレスが一致することを確認済み。連絡先の値は公開原稿へ複製しない。

## 適合と不足

- DIRECT: Databricks/Genie Codeでagentの入出力と応答品質を分析するworkflowを構築する（LOGS）。AI導入支援とprompt/context調整（MUIT/PROMPT）、EEG・machine learning研究（RESEARCH）も接点がある。
- TRANSFERABLE: 週次AIツールcommunityの指導（TEACH）、永続stateと外部作用を扱うagent開発（LM/RELIABILITY）。
- GAP: 求人はtechnical roleで2年以上、public cloudの知識、Python/Scala/SQLのいずれか、データ分析の全工程とETL等またはdata warehousingの実務/学術経験を求める。既存資料はMUITの職務開始を2025年4月とする。NAIST/ATR研究と職務の重複期間を加算して「職務2年以上」としない。cloud製品別・言語別・ETL/warehouseの具体的経験、Databricks資格は未確認。学位の授与も未確認で、研究・関連実務を説明する。
- 日本語nativeと英語試験実績（LANG）は根拠がある。試験点数から勤務上の英語fluency認定を作らない。年収帯は取得求人に明示がなく、希望年収を市場給与として記載しない。
- 既存台帳のDatabricks Forward Deployed Engineerは別職種の未解決履歴。このScale Solution Engineerのreq IDとは区別し、既存FDEのstatusは変えない。

## フォーム回答案

| 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|
| First Name / `first_name` | 必須 | Daisuke | PROFILE |
| Last Name / `last_name` | 必須 | Narita | PROFILE |
| Preferred First Name / `preferred_name` | 必須 | Daisuke（英字名に合わせる案） | PROFILE |
| Email / `email` | 必須 | PROFILE `candidate.application_email` | PROFILE |
| Phone / `phone` | 必須 | PROFILE `candidate.phone` | PROFILE |
| Resume/CV / `resume`・`resume_text` | 必須 | 上記英語resume PDFを添付する案。fileまたはtextという1設問であり、2件に数えない | RESUME |
| Cover Letter / `cover_letter`・`cover_letter_text` | 任意 | 下記letterをtext欄へ入力する案。専用PDFを作成済みとは扱わない | 下記 |
| LinkedIn Profile / `question_38157861002` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| How did you hear about this job? / `question_38157863002` | 任意 | Your careers website.（今回の求人発見経路の案） | 公式採用一覧から取得 |
| Are you legally authorized to work in the country in which you are applying? / `question_38157864002` | 必須・Yes/No | Yes | JP |
| Do you now or will you in the future need sponsorship for employment visa status in the country in which you are applying? / `question_38157865002` | 必須・Yes/No | No | JP |
| Do you possess business fluency in Japanese? / `question_38210576002` | 必須・Yes/No | Yes（日本語native） | LANG |

取得schemaでは経験年数・cloud・言語をYes/Noで申告する追加欄はない。書類の内容から、それらの必須要件を充足済みと推測しない。実フォームに別の同意・追加質問が表示された場合は、その文面を確認して扱う。

## カバーレター案

Dear Databricks Hiring Team,

I am applying for the Scale Solution Engineer role in Tokyo. I am interested in helping customers turn questions about data and AI into working systems and understandable technical decisions.

Since April 2025, I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contribute to Salesforce Agentforce deployment in MUFG Bank's internal CRM for relationship managers. I built an observability workflow in Databricks to analyze agent inputs, outputs, and responses, using Genie Code to investigate behavior and response quality. I have also supported prompt tuning and context engineering for company-information summaries. This is the experience I would bring to conversations about how customers investigate and improve AI applications.

My research at the Nara Institute of Science and Technology, conducted concurrently with work at ATR, applied EEG and machine learning to mind-wandering detection. Outside enterprise work, I build Life Manager, an open-source agent system, and founded a weekly community teaching Claude Code, Codex, Cursor, and agent workflows. These projects have reinforced the importance of clear explanations, reproducible investigation, and practical implementation.

I am a native Japanese speaker based in Tokyo, with unrestricted authorization to work in Japan. My English test results include TOEFL iBT 96, TOEIC 910, and Duolingo English Test 140. I would welcome the opportunity to discuss how my Databricks investigation work and AI implementation experience could contribute to your team.

Sincerely,
Daisuke Narita

提出前の残項目: 求人のtechnical role年数、cloud・言語・data engineering/warehousing要件との具体的対応、resumeの最新性を確認する。未確認を「経験あり」へ補完しない。候補者の希望入社日はSTARTの2026年12月1日だが、フォームにない設問を追加しない。
