# Agoda — Staff Software Engineer - Full Stack AI (Bangkok based, Relocation provided) 応募下書き

状態: 未提出。台帳key: `job:agoda:7543802`（2026-10-24時点 `claude-3 / found`）。この原稿から応募・status更新を行わない。

**適合警告:** 公式要件は "8+ years of experience in software engineering (web, backend, or full stack)"、Java/Kotlin/.NETのbackend expertise、Node.js/TypeScript BFFの所有、"Proven experience leading end-to-end architecture on high-traffic platforms"、team mentoring。候補者の職務経験はMUITの2025年4月以降（約1年半）で、職業としてのfull-stack・backend開発、React/Next.js、BFF、high-traffic architectureの経験は資料にない。**必須要件の大半を満たさない。** 提出するかは参謀/本人が判断する。

- 求人: https://job-boards.greenhouse.io/agoda/jobs/7543802 （2026-10-24 HTTP 200、公開中。API `updated_at` 2026-10-16、初回公開 2026-01-15。締切記載なし）
- フォーム取得: `https://boards-api.greenhouse.io/v1/boards/agoda/jobs/7543802?questions=true` の公開read-only schema。`questions` 全28項目（必須24・任意4）＋ `location_questions`（Location入力1件は必須、緯度/経度2件は非表示の自動入力）。応募API・ファイル送信は使わない。
- 根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。追加の出典としてABOUT = https://aniccaai.com/about （2026-10-24取得）。

## 勤務地・ビザ

- 勤務地はBangkok（hybrid、Bangkok HQ）。日本在住のため**Bangkokへの移住が前提**になる（"*** This position is based in Bangkok, Thailand (Relocation Provided) ***"）。
- 公式本文の記載: "Full Relocation and Onboarding Support: Visa sponsorship for you and your family" → sponsorshipは明記されている。英語業務（"English-First: Work and collaborate in English—no Thai required!"）。
- 候補者は日本国籍で日本国内の就労は無制限だが、Thailandの就労資格はない（`legal_foreign_work_authorization_20260730`）。
- **未確認:** 本人がBangkokへ移住する意思。必須設問14（Bangkok在住または移住可か）は本人確認まで選択しない。

## 求人要件と適合・不足

| 要件（公式） | 適合 | 不足・扱い |
|---|---|---|
| 8+ years software engineering | — | **不足。** 職務経験約1.5年。フォームは "0-2 Years" |
| React/Next.js/TypeScript、state管理、build tooling | 6本のiOS appをAI-assisted developmentで構築・公開（ABOUT）、Life Managerのopen-source開発（LM） | 職務としてのReact/Next.js経験は資料にない。iOS appの使用技術も未確認 |
| Java/Kotlin/.NET backend、microservices、REST/gRPC | — | 資料にない |
| Node.js/TypeScript BFF | — | 資料にない |
| Core Web Vitals、testing（Jest/Cypress/Playwright） | Life Managerの自動checkと評価gate（RELIABILITY） | 具体的なtest frameworkは未確認 |
| high-traffic architecture、mentoring、cross-team | 週次のAIツール指導community設立（TEACH）、MUIT経由の企業本番導入への寄与（MUIT） | 技術leadership・mentoringの職務実績はない |
| AI-driven chat experiences | Agentforce本番導入への寄与、Databricksでの応答品質分析、prompt/context支援（MUIT/LOGS/PROMPT） | 最も直接的な接点。単独主導とは書かない |

## フォーム回答案

| # | source field | 公式設問（要約） | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|---|
| 1 | `first_name` | First Name | 必須 | Daisuke | PROFILE |
| 2 | `last_name` | Last Name | 必須 | Narita | PROFILE |
| 3 | `email` | Email | 必須 | PROFILE `candidate.application_email` から入力（値は非掲載） | PROFILE |
| 4 | `phone` | Phone | 必須 | PROFILE `candidate.phone` から国番号付きで入力（値は非掲載） | PROFILE |
| 5 | `resume` / `resume_text` | Resume/CV | 必須 | 既存英語resume PDF。送信直前に最新性を確認する | RESUME |
| 6 | `cover_letter` / `cover_letter_text` | Cover Letter | 任意 | 下の「カバーレター案」をtextで貼る | 下記 |
| 7 | `question_62829012` | LinkedIn Profile?（link or 'No'） | 必須 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 8 | `question_62829013` | Github Profile?（link or 'No'） | 必須 | https://github.com/Daisuke134 | PROFILE |
| 9 | `question_62829014` | Website / blog / other | 任意 | https://aniccaai.com/about | ABOUT |
| 10 | `question_62829015` | Overall years of relevant experience（0-2 / 2-5 / 5-8 / 8+） | 必須 | 0-2 Years（MUIT 2025年4月〜）。包括的な経験attestationで年数を上げない | MUIT |
| 11 | `question_62829016` | Highest academic level | 必須 | 案: Bachelor's Degree（慶應義塾大学法学部政治学科 2020年4月〜2024年4月）。学士号授与の明記はPROFILEにないため送信前に本人確認。NAIST修士号は授与未確認のため "Master's Degree" を選ばない | `education`・`education_naist` |
| 12 | `question_62829017[]` | 職務で使った技術stack（上位3つ選択：JS/TS/React/Angular/.NET/.NET Core/Java/Scala/NodeJS/Go/Python/Kotlin） | 必須 | **未確定。** 職務での使用言語は資料にない（specの禁止事項：個別言語を補完しない）。本人が職務で使った言語を確認して選ぶ | 資料なし |
| 13 | `question_62829018` | Preferred field of interest | 必須 | 案: Machine Learning（希望の選択で事実主張ではない。本人の希望を優先） | 希望 |
| 14 | `question_62829019` | Bangkok在住または移住可か（Yes/No） | 必須 | **未確定。** 移住意思の本人確認まで選択しない | 本人確認 |
| 15 | `question_62853846` | Current notice period | 必須 | 案: 1 Month（入社可能日2026年12月1日から逆算。契約上のnotice periodは未確認） | START |
| 16 | `question_62829020` | Agoda社員との個人的関係（Yes/No） | 必須 | **未確定。** 資料に記載なし。本人確認 | 本人確認 |
| 17 | `question_62829021` | （16がYesの場合）関係の種類 | 任意 | 16がNoなら空欄 | — |
| 18 | `question_62829022` | （16がYesの場合）社員名 | 任意 | 16がNoなら空欄 | — |
| 19 | `question_62829023` | 個人データ利用・第三者共有への同意（Yes/No） | 必須 | 下書きでは未選択。提出担当がprivacy policyを確認して選ぶ | 同意欄 |
| 20 | `question_62829024` | Gender（任意回答の旨あり） | 必須 | 未選択。PROFILEに値はあるが、開示するかは本人の判断 | PROFILE |
| 21 | `question_62829025` | Deloitte（子会社含む）との現在/過去の関係 | 必須 | "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"。PROFILEの職歴とABOUTにDeloitte関連なし。契約・株主等を含むため送信前に本人確認 | PROFILE/ABOUT |
| 22 | `question_62829026` | Booking Holdings傘下に現在在籍しているか | 必須 | No（現職はMUIT） | MUIT |
| 23 | `question_62829027` | How did you hear about this job? | 必須 | 案: External job board（`application_source_job_board_20260807`）。発見元はAgoda自身のGreenhouse boardのため "Direct to Careers at Agoda" とどちらが実態に合うかを提出担当が判断 | PROFILE fact |
| 24 | `question_62829028` | Engineering blogを読んだか（Yes/No） | 必須 | **未確定。** 閲覧の事実は資料にない。本人が読んでからYes、読んでいなければNo | 本人確認 |
| 25 | `question_62829029` | 現在の居住国 | 必須 | Japan | TOKYO |
| 26 | `question_62829030` | 過去6か月にAgodaへ応募したか（Yes/No） | 必須 | No（台帳にAgodaの過去応募行なし。同時に検討中のAgoda 7916603/7543795を先に送信した場合は、送信順に応じてこの回答を見直す。台帳外の応募は本人確認） | 台帳 |
| 27 | `question_62829031` | 選考のSMS通知を許可するか | 必須 | 未選択。本人の連絡希望を確認 | 本人確認 |
| 28 | `question_62829032` | Booking Holdings各社の求人・newsletterメール | 必須 | 未選択。本人の希望を確認 | 本人確認 |
| L | `location`（＋非表示 `latitude`/`longitude`） | Location | 必須 | Tokyo, Japan | TOKYO |

## カバーレター案（`cover_letter_text` 用、約210語）

Dear Agoda Hiring Team,

I am applying for the Staff Software Engineer - Full Stack AI role in Bangkok. I want to be upfront: I do not have the eight years of full-stack and backend experience this level asks for. I am applying because of the role's focus on AI-driven chat experiences, which is where my recent work sits.

Since April 2025 I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contributed to MUFG Bank's production deployment of Salesforce Agentforce in its internal relationship-manager CRM. I built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering for company-information summaries.

Outside that work, I build Life Manager, an open-source AI agent system, using small scoped changes, automated checks and durable state, and I have published six iOS apps with AI-assisted development. I also founded a weekly community teaching Claude Code, Codex, Cursor and agent workflows.

I am based in Tokyo, hold Japanese citizenship, and would need Thai visa sponsorship. If this level is not the right fit, I would welcome being considered for a more suitable AI engineering role in the same team.

Sincerely,
Daisuke Narita

## 経歴根拠・未確認事項

根拠: MUIT=`muit_role_2025`・`muit_agent_crm`・`mufg`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、TEACH=`agent_club`、LM/RELIABILITY=`life_manager`・`async_operating_practices_20260805`・`agent_reliability_engineering_20260805`、JP=`legal_japan_work_authorization_20260730`、TOKYO=`candidate.base`、START=`availability_start_date_20261201`。6本のiOS appはABOUTに記載。

未確認/不足（参謀・本人）:

1. **経験年数・職位:** 8年以上の必須要件に対し職務経験約1.5年。Java/Kotlin/.NET、Node.js BFF、React/Next.js、high-traffic architecture、mentoringの職務経験は資料になく、主張しない。書類不通過の可能性が高い。
2. **移住意思:** Bangkok移住の意思（設問14）。
3. 職務で使った技術stack上位3つ（設問12）。
4. Agoda社員との関係、Engineering blog閲覧、SMS・newsletter希望、gender開示、個人データ同意、notice periodの契約値、学士号授与。
5. Deloitte関連の契約・株主関係を含む最終確認。
6. Agoda 3件を同時に出す場合の「過去6か月の応募」回答の整合。
