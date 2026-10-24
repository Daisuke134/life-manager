# Agoda — Staff/Lead LLM Data Scientist (Singapore based) 応募下書き

状態: 未提出。台帳key: `job:agoda:7916603`（2026-10-24時点 `claude-3 / found`）。この原稿から応募・status更新を行わない。

**適合警告:** Staff/Lead職で「senior Data Scientists or ML practitioners」を対象とする。候補者の職務経験はMUITの2025年4月以降（約1年半）で、Data Scientistとしての職歴、本番での実験設計・統計modelingの職務実績は資料にない。経験年数・職位は大きく不足し、提出するかは参謀/本人が判断する。

- 求人: https://job-boards.greenhouse.io/agoda/jobs/7916603 （2026-10-24 HTTP 200、公開中。API `updated_at` 2026-10-16、初回公開 2026-05-13。締切記載なし）
- フォーム取得: `https://boards-api.greenhouse.io/v1/boards/agoda/jobs/7916603?questions=true` の公開read-only schema。`questions` 全20項目（必須19・任意1）＋ `location_questions`（Location入力1件は必須、緯度/経度2件は非表示の自動入力）。応募API・ファイル送信は使わない。
- 根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。追加の出典としてABOUT = https://aniccaai.com/about （2026-10-24取得）。

## 勤務地・ビザ

- 勤務地はSingapore。日本在住のため**Singaporeへの移住が前提**になる。候補者は日本国籍で日本国内の就労は無制限・sponsorship不要だが、Singaporeの就労資格はない（`legal_foreign_work_authorization_20260730`、ESTAは米国の渡航認証のみ）。
- 公式本文の記載: "We welcome both local and international applications for this role. Full visa sponsorship and relocation assistance available for eligible candidates." → sponsorshipと移住支援は明記されている（"eligible candidates" の条件付き）。
- フォームにBangkok勤務も検討するかの必須設問がある（本文側: "we have more openings for data science roles in Bangkok and would provide relocation assistance as well"）。
- **未確認:** 本人がSingapore（またはBangkok）へ移住する意思。PROFILEの `location_preferences` は "Anywhere" だが、具体的な国への移住意思の確認ではないため、Yesを補完しない。参謀/本人の確認事項とする。

## 求人要件と適合・不足

| 要件（公式） | 適合 | 不足・扱い |
|---|---|---|
| Strong hands-on Data Science (modeling, feature engineering, statistics, experimentation) | NAIST/ATRでEEGとMLによるmind-wandering研究（RESEARCH）、Toshiba research internでwearable sensorデータの環境識別にFFT・autoencoderで特徴抽出（ABOUT）、BERTによる感情分析（ABOUT） | 職務としてのA/B実験・統計modelingの実績は資料にない。研究期間を職歴年数に数えない |
| Production LLM systems (RAG, tool/agent orchestration, context/memory) with evaluation focus — "or the ability to ramp up quickly" | MUIT経由のAgentforce本番導入への寄与（MUIT）、Databricksでのagent入出力・応答品質分析（LOGS）、prompt tuning/context engineering（PROMPT）、Life Managerの評価gate・永続state（LM/RELIABILITY） | 単独主導・RAG構築・評価指標の改善率は書かない |
| Staff/Lead・senior | — | **最大の不足。** 約1.5年の職務経験。フォームの経験年数は "0-2 Years" |

## フォーム回答案

| # | source field | 公式設問（要約） | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|---|
| 1 | `first_name` | First Name | 必須 | Daisuke | PROFILE |
| 2 | `last_name` | Last Name | 必須 | Narita | PROFILE |
| 3 | `email` | Email | 必須 | PROFILE `candidate.application_email` から入力（値は非掲載） | PROFILE |
| 4 | `phone` | Phone | 必須 | PROFILE `candidate.phone` から国番号付きで入力（値は非掲載） | PROFILE |
| 5 | `resume` / `resume_text` | Resume/CV | 必須 | 既存英語resume PDF。送信直前に最新性を確認する | RESUME |
| 6 | `cover_letter` / `cover_letter_text` | Cover Letter | 任意 | 下の「カバーレター案」をtextで貼る | 下記 |
| 7 | `question_66774382` | Bangkokも勤務地として検討するか（Yes/No） | 必須 | **未確定。** 本人の移住意思が未確認のため選択しない | 本人確認 |
| 8 | `question_66774383` | 選考時のCodeSignal testを7日以内に受けられるか（Yes/No） | 必須 | **未確定。** 受験意思・日程は本人確認。代理でYesにしない | 本人確認 |
| 9 | `question_66774384` | 数学/物理Olympiad参加歴（Yes/No） | 必須 | **未確定。** 資料に記載なし。参加歴がなければNo、を本人が確認して選ぶ | 資料なし |
| 10 | `question_66774385` | 過去6か月にAgodaのDS職で技術test/面接を受けたか（Yes/No） | 必須 | No（台帳 `ledger/APPLICATIONS.md` にAgodaの過去応募行なし。台帳外の応募有無は本人確認） | 台帳 |
| 11 | `question_66774386` | How did you hear about this job? | 必須 | 案: External job board（`application_source_job_board_20260807`）。ただし発見元はAgoda自身のGreenhouse boardなので、"Direct to Careers at Agoda" とどちらが実態に合うかを提出担当が判断する | PROFILE fact |
| 12 | `question_66774387` | 個人データ利用・第三者共有への同意（Yes/No） | 必須 | 下書きでは未選択。提出担当がprivacy policyを確認して選ぶ | 同意欄 |
| 13 | `question_66774388` | Gender（任意回答の旨あり、選択肢に "Prefer not to disclose"） | 必須 | 未選択。PROFILEに値はあるが、開示するかは本人の判断 | PROFILE |
| 14 | `question_66774389` | Deloitte（子会社含む）との現在/過去の関係 | 必須 | "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"。PROFILE記載の職歴（A10 Lab、NAIST/ATR、MUIT）とABOUTの経歴にDeloitte関連なし。設問は契約・株主・internも含むため送信前に本人確認 | PROFILE/ABOUT |
| 15 | `question_66774390` | Overall years of relevant experience（0-2 / 3-5 / 6-8 / 8+） | 必須 | 0-2 Years（MUIT 2025年4月〜）。包括的な経験attestationで年数を上げない | MUIT |
| 16 | `question_66774391` | Booking Holdings傘下に現在在籍しているか | 必須 | No（現職はMUIT） | MUIT |
| 17 | `question_66774392` | 現在の居住国 | 必須 | Japan | TOKYO |
| 18 | `question_66774393` | 選考のSMS通知を許可するか | 必須 | 未選択。本人の連絡希望を確認 | 本人確認 |
| 19 | `question_66774394` | Booking Holdings各社の求人・newsletterメール | 必須 | 未選択。本人の希望を確認 | 本人確認 |
| 20 | `question_69638429` | Singapore work passのsponsorshipが今後必要か | 必須 | "Yes - I do not currently hold a Singapore work pass" | JP/`legal_foreign_work_authorization_20260730` |
| L | `location`（＋非表示 `latitude`/`longitude`） | Location | 必須 | Tokyo, Japan（緯度経度は画面の自動補完に任せる） | TOKYO |

## カバーレター案（`cover_letter_text` 用、約220語）

Dear Agoda Hiring Team,

I am applying for the Staff/Lead LLM Data Scientist role. I want to be direct that my professional experience is shorter than this level usually requires; I am applying because the work, evaluating and improving LLM systems in real user flows, is the work I do now.

Since April 2025 I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contributed to MUFG Bank's production deployment of Salesforce Agentforce in its internal relationship-manager CRM. I built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering for company-information summaries.

My data science foundation comes from research: graduate research at NAIST and ATR applying EEG and machine learning to mind-wandering detection, and a Toshiba research internship where I extracted features from wearable-sensor data with fast Fourier transforms and an autoencoder. I also build Life Manager, an open-source agent system, where I rely on evaluation gates, durable state and independent checks before trusting an external action.

I am based in Tokyo, hold Japanese citizenship, and would need Singapore work-pass sponsorship. I would welcome a conversation about whether my profile fits this team or a different level.

Sincerely,
Daisuke Narita

## 経歴根拠・未確認事項

根拠: MUIT=`muit_role_2025`・`muit_agent_crm`・`mufg`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、RESEARCH=`naist`・`atr_research`、LM/RELIABILITY=`life_manager`・`agent_reliability_engineering_20260805`、JP=`legal_japan_work_authorization_20260730`、TOKYO=`candidate.base`。Toshiba internとBERT研究はABOUTのみに記載（RESUMEにはない）。

未確認/不足（参謀・本人）:

1. **経験年数・職位:** Staff/Lead・senior対象に対し職務経験約1.5年。DS職歴なし。レベル違いで書類不通過となる可能性が高い。
2. **移住意思:** Singapore／Bangkokへの移住意思（設問7、本文の勤務地）。
3. CodeSignal受験意思、Olympiad参加歴、SMS・newsletter希望、gender開示、個人データ同意。
4. Deloitte関連の契約・株主関係を含む最終確認。
5. 学位: NAIST修士号の授与は未確認。カバーレターでは「graduate research」と書き、取得済み学位としない。
6. 本番実験（A/B test）・統計modelingの職務経験は資料になく、主張しない。
