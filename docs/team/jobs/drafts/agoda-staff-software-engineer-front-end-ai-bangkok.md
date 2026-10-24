# Agoda — Staff Software Engineer - Front End AI (Bangkok based, Relocation provided) 応募下書き

状態: 未提出。台帳key: `job:agoda:7543795`（2026-10-24時点 `claude-3 / found`）。この原稿から応募・status更新を行わない。

**適合警告:** 公式要件は "8+ years' experience building and leading rich web applications at scale"、"Deep mastery of JavaScript/TypeScript and modern frameworks (React, Next, Vue)"、SPA/SSRとCore Web Vitalsのportfolio、team leadership。候補者の職務経験はMUITの2025年4月以降（約1年半）で、職業としてのfront-end開発・React/Next.js・BFF・team leadershipの経験は資料にない。**必須要件の大半を満たさない。** 3件中で最も適合度が低い。提出するかは参謀/本人が判断する。

- 求人: https://job-boards.greenhouse.io/agoda/jobs/7543795 （2026-10-24 HTTP 200、公開中。API `updated_at` 2026-10-16、初回公開 2026-01-15。締切記載なし）
- フォーム取得: `https://boards-api.greenhouse.io/v1/boards/agoda/jobs/7543795?questions=true` の公開read-only schema。`questions` 全31項目（必須27・任意4）＋ `location_questions`（Location入力1件は必須、緯度/経度2件は非表示の自動入力）。"What is your current notice period?" が別field（`question_62830901` と `question_62853854`）で2回出る。応募API・ファイル送信は使わない。
- 根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。追加の出典としてABOUT = https://aniccaai.com/about （2026-10-24取得）。

## 勤務地・ビザ

- 勤務地はBangkok（"Hybrid remote/Bangkok HQ model"）。日本在住のため**Bangkokへの移住が前提**になる（"***This position is based in Bangkok, Thailand (Relocation Provided)***"）。
- 公式本文の記載: "Premium Relocation & Expat Support: Visa, flight & moving package for you and family" → visa支援は明記されている（"sponsorship" という語ではなく "Visa ... package" の表現）。
- 候補者は日本国籍で日本国内の就労は無制限だが、Thailandの就労資格はない（`legal_foreign_work_authorization_20260730`）。
- **未確認:** 本人がBangkokへ移住する意思。必須設問17は本人確認まで選択しない。

## 求人要件と適合・不足

| 要件（公式） | 適合 | 不足・扱い |
|---|---|---|
| 8+ years rich web apps at scale | — | **不足。** 職務経験約1.5年。フォームは "0-2 Years" |
| JS/TS、React/Next/Vue のdeep mastery | 6本のiOS appをAI-assisted developmentで構築・公開（ABOUT）、Life Managerのopen-source開発（LM） | 職務としてのweb front-end経験・使用frameworkは資料にない |
| SPA/SSR、Core Web Vitals のportfolio | — | 資料にない |
| team leadership、system design、stakeholder influence | 週次のAIツール指導community設立（TEACH） | 職務上のleadershipはない |
| Bonus: A/B experimentation、international exposure、travel/e-commerce | ICLR 2026（Rio de Janeiro）でMUITを代表（ABOUT/RESUME）、Santa Monicaでの1か月の研究internship（ABOUT）、client SaaS LPの改善（`saas_lp_cvr_3_to_10_20260819`） | LPの改善はA/B testとしては記録されていないため、A/B実験経験とは書かない |
| AI-driven chat experiences | Agentforce本番導入への寄与、応答品質分析、prompt/context支援（MUIT/LOGS/PROMPT） | 最も直接的な接点。単独主導とは書かない |

## フォーム回答案

| # | source field | 公式設問（要約） | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|---|
| 1 | `first_name` | First Name | 必須 | Daisuke | PROFILE |
| 2 | `last_name` | Last Name | 必須 | Narita | PROFILE |
| 3 | `email` | Email | 必須 | PROFILE `candidate.application_email` から入力（値は非掲載） | PROFILE |
| 4 | `phone` | Phone | 必須 | PROFILE `candidate.phone` から国番号付きで入力（値は非掲載） | PROFILE |
| 5 | `resume` / `resume_text` | Resume/CV | 必須 | 既存英語resume PDF。送信直前に最新性を確認する | RESUME |
| 6 | `cover_letter` / `cover_letter_text` | Cover Letter | 任意 | 下の「カバーレター案」をtextで貼る | 下記 |
| 7 | `question_62830901` | Current notice period | 必須 | 案: 1 Month（入社可能日2026年12月1日から逆算。契約上のnotice periodは未確認）。#18と同じ値にする | START |
| 8 | `question_62828943` | LinkedIn Profile?（link or 'No'） | 必須 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 9 | `question_62828944` | Github Profile?（link or 'No'） | 必須 | https://github.com/Daisuke134 | PROFILE |
| 10 | `question_62828945` | Website / blog / other | 任意 | https://aniccaai.com/about | ABOUT |
| 11 | `question_62828946` | Overall years of relevant experience（0-2 / 2-5 / 5-8 / 8+） | 必須 | 0-2 Years（MUIT 2025年4月〜）。包括的な経験attestationで年数を上げない | MUIT |
| 12 | `question_62828947` | Highest academic level | 必須 | 案: Bachelor's Degree（慶應義塾大学法学部政治学科 2020年4月〜2024年4月）。学士号授与の明記はPROFILEにないため本人確認。NAIST修士号は授与未確認のため "Master's Degree" を選ばない | `education`・`education_naist` |
| 13 | `question_62828948[]` | 職務で使った技術stack（上位3つ選択） | 必須 | **未確定。** 職務での使用言語は資料にない（specの禁止事項：個別言語を補完しない）。本人確認 | 資料なし |
| 14 | `question_62828949` | Preferred field of interest | 必須 | 案: Machine Learning（希望の選択で事実主張ではない。本人の希望を優先） | 希望 |
| 15 | `question_62828950` | BFF layerを設計・構築・保守したことがあるか（Yes/No） | 必須 | No（職務でのBFF経験は資料にない。本人が具体的な経験を示した場合のみ見直す） | 資料なし |
| 16 | `question_62828951` | BFF architectureの経験と使用技術を簡潔に記述 | 必須・textarea | 下の「BFF設問の回答案」 | MUIT/LM |
| 17 | `question_62828952` | Bangkok在住または移住可か（Yes/No） | 必須 | **未確定。** 移住意思の本人確認まで選択しない | 本人確認 |
| 18 | `question_62853854` | Current notice period（重複設問） | 必須 | #7と同じ値 | START |
| 19 | `question_62828953` | Agoda社員との個人的関係（Yes/No） | 必須 | **未確定。** 資料に記載なし。本人確認 | 本人確認 |
| 20 | `question_62828954` | （19がYesの場合）関係の種類 | 任意 | 19がNoなら空欄 | — |
| 21 | `question_62828955` | （19がYesの場合）社員名 | 任意 | 19がNoなら空欄 | — |
| 22 | `question_62828956` | 個人データ利用・第三者共有への同意（Yes/No） | 必須 | 下書きでは未選択。提出担当がprivacy policyを確認して選ぶ | 同意欄 |
| 23 | `question_62828957` | Gender（任意回答の旨あり） | 必須 | 未選択。PROFILEに値はあるが、開示するかは本人の判断 | PROFILE |
| 24 | `question_62828958` | Deloitte（子会社含む）との現在/過去の関係 | 必須 | "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"。PROFILEの職歴とABOUTにDeloitte関連なし。契約・株主等を含むため送信前に本人確認 | PROFILE/ABOUT |
| 25 | `question_62828959` | Booking Holdings傘下に現在在籍しているか | 必須 | No（現職はMUIT） | MUIT |
| 26 | `question_62828960` | How did you hear about this job? | 必須 | 案: External job board（`application_source_job_board_20260807`）。発見元はAgoda自身のGreenhouse boardのため "Direct to Careers at Agoda" とどちらが実態に合うかを提出担当が判断 | PROFILE fact |
| 27 | `question_62828961` | Engineering blogを読んだか（Yes/No） | 必須 | **未確定。** 閲覧の事実は資料にない。本人確認 | 本人確認 |
| 28 | `question_62828962` | 現在の居住国 | 必須 | Japan | TOKYO |
| 29 | `question_62828963` | 過去6か月にAgodaへ応募したか（Yes/No） | 必須 | No（台帳にAgodaの過去応募行なし。Agoda 7916603/7543802を先に送信した場合は送信順に応じて見直す。台帳外の応募は本人確認） | 台帳 |
| 30 | `question_62828964` | 選考のSMS通知を許可するか | 必須 | 未選択。本人の連絡希望を確認 | 本人確認 |
| 31 | `question_62828965` | Booking Holdings各社の求人・newsletterメール | 必須 | 未選択。本人の希望を確認 | 本人確認 |
| L | `location`（＋非表示 `latitude`/`longitude`） | Location | 必須 | Tokyo, Japan | TOKYO |

### BFF設問の回答案（`question_62828951`）

I have not designed or owned a Backend-for-Frontend layer in a professional role. My closest experience is on the AI side of the stack: through Mitsubishi UFJ Information Technology, I contributed to MUFG Bank's production Salesforce Agentforce deployment in an internal CRM, built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering. In my open-source project Life Manager, I work on an agent system that coordinates external services with durable state and automated checks. I would need to ramp up on BFF design for this role.

## カバーレター案（`cover_letter_text` 用、約200語）

Dear Agoda Hiring Team,

I am applying for the Staff Software Engineer - Front End AI role in Bangkok. I want to be clear that I do not have the eight years of web front-end experience or the team leadership this level asks for. What draws me to the role is the AI-driven chat experience it builds, which is where my recent work is.

Since April 2025 I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contributed to MUFG Bank's production deployment of Salesforce Agentforce in its internal relationship-manager CRM. I built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering for company-information summaries.

Independently, I have published six iOS apps with AI-assisted development and build Life Manager, an open-source AI agent system. I also founded a weekly community teaching Claude Code, Codex, Cursor and agent workflows.

I am based in Tokyo, hold Japanese citizenship, and would need Thai visa support. If a different level or AI-focused role on the team is a better match, I would welcome that conversation.

Sincerely,
Daisuke Narita

## 経歴根拠・未確認事項

根拠: MUIT=`muit_role_2025`・`muit_agent_crm`・`mufg`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、TEACH=`agent_club`、LM=`life_manager`・`async_operating_practices_20260805`、JP=`legal_japan_work_authorization_20260730`、TOKYO=`candidate.base`、START=`availability_start_date_20261201`。6本のiOS app・ICLR・Santa Monica internshipはABOUTに記載。

未確認/不足（参謀・本人）:

1. **経験年数・職位:** 8年以上の必須要件に対し職務経験約1.5年。web front-end、React/Next/Vue、SPA/SSR、Core Web Vitals、BFF、team leadershipの職務経験は資料になく、主張しない。BFF設問はNoと正直な記述で回答する。書類不通過の可能性が最も高い。
2. **移住意思:** Bangkok移住の意思（設問17）。
3. 職務で使った技術stack上位3つ（設問13）。
4. Agoda社員との関係、Engineering blog閲覧、SMS・newsletter希望、gender開示、個人データ同意、notice periodの契約値、学士号授与。
5. Deloitte関連の契約・株主関係を含む最終確認。
6. Agoda 3件を同時に出す場合の「過去6か月の応募」回答の整合。
