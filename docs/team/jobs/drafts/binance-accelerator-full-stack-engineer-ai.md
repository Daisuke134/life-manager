# Binance — Accelerator Program - Full Stack Engineer (AI)

応募ドラフト。送信は参謀が所有する。台帳key: `job:binance:5002443101`（`ledger/APPLICATIONS.md` は `found`）。この原稿から応募・status更新を行わない。

公式求人: https://job-boards.eu.greenhouse.io/binance/jobs/5002443101 。公開Greenhouse Job Board API `boards-api.greenhouse.io/v1/boards/binance/jobs/5002443101?questions=true` で求人本文とフォームを取得する（EU host `boards-api.eu.greenhouse.io` はこの環境から応答なし、global hostは同じ `absolute_url` を返す）。`first_published` 2026-10-13、`updated_at` 2026-10-21で掲載中。締切記載なし。応募フォーム全15項目（必須10・任意5）。GDPR同意欄・demographic設問はschemaにない。応募mutation・ファイルアップロード・送信は行わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`、ABOUTは https://aniccaai.com/about （2026-10-24取得）。

## 応募資格と勤務地（最重要）

- **在学要件（GAP・提出判断要）:** 「Currently pursuing a Bachelor's degree or above」を要求し、職務を「seed learner」と位置づけるAccelerator Programの職。資料上の学歴はKeio法学部（2020年4月〜2024年4月）とNAIST修士課程の研究期間（2024年4月〜2026年4月）で、現在の在籍は確認できず、NAIST修士号の授与も未確認。現役学生とは書かない。期間・雇用形態（internshipか）の明記はない。
- **勤務地・visa:** location表記は「Hong Kong; Japan; Singapore; Taiwan」、office欄はHong Kong、本文は「Remote-first, work-from-home arrangement (may vary depending on the nature of the role and team)」。Japanが勤務地に含まれるため、日本から勤務する限りsponsorshipは不要（JP）。チームがHong Kong・Singapore・Taiwanへの転居を求める場合は、本人に日本以外の就労資格がないため **visa/sponsorshipと転居が必要**。US就労資格はない（ESTAのみ）。
- **報酬:** 非開示。希望下限800万円（SALARY）を満たす根拠はない。

## 適合と不足

- DIRECT: 「Integrate AI coding tools (Cursor, Copilot, Claude Code)」「articulate requirements and constraints to AI tools」— Claude Code・Codex・Cursorを教える週次community（TEACH）と、AI-assisted developmentで6本のiOS appを公開しLife Managerを開発する実績（ABOUT/LM）。
- DIRECT（Nice to Have）: open-sourceのGitHub project（Life Manager, https://github.com/Daisuke134/life-manager ）、個人side projectの継続的な構築（LM/ANICCA）。iOSでのapp公開はcross-platform項目の一部に当たるが、Android/Webの経験は資料にない。
- GAP: 必須の「Foundation in at least one backend language (Java, Go, Rust, C++)」を資料が裏付けない。「Familiarity with Node.js and modern frontend frameworks」「database design」も未記載。ABOUTは開発を「AI-assisted development」と記し、本人の担当をproduct direction・release・marketing等とする。手書きのfull-stack実装経験を補完しない。
- GAP: crypto/blockchainの経験は資料に一切ない（必須設問あり、下記）。
- A10 Labのmarketing internshipを「startupでのengineering経験」とは書かない。

## フォーム回答案

| 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|
| First Name / `first_name` | 必須 | Daisuke | PROFILE |
| Last Name / `last_name` | 必須 | Narita | PROFILE |
| Preferred First Name / `preferred_name` | 任意 | Daisuke | PROFILE `candidate.preferred_name` |
| Email / `email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| Phone / `phone` | 任意 | PROFILE `candidate.phone`から国番号付きで入力 | PROFILE |
| Resume/CV / `resume` (file) or `resume_text` | 必須 | 既存英語resume PDFを添付。送信直前に最新性を確認する | RESUME |
| Cover Letter / `cover_letter` (file) or `cover_letter_text` | 任意 | 下の「カバーレター案」を `cover_letter_text` へ貼る | 下記 |
| LinkedIn Profile / `question_9808352101` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| Website / `question_9808353101` | 任意 | https://github.com/Daisuke134 （GitHub projectを重視する求人のため） | PROFILE |
| Where do you currently live? / `question_9808354101` | 必須・単一選択 | Japan | TOKYO |
| Will you require employer sponsorship for a work visa or work permit in the country where you currently reside or are currently based? / `question_9808355101` | 必須・Yes/No | No（日本居住・日本国籍。日本以外への転居時は別途必要） | JP |
| What language(s) can you speak at a native or business level? / `question_9808356101[]` | 必須・複数選択 | Japanese。**Englishは本人判断待ち**（資料はTOEFL iBT 96・TOEIC 910・DET 140の試験実績のみ）。Spanish（DELE B1）は選ばない | LANG |
| How did you hear about our job opening? / `question_9808357101` | 必須・単一選択 | 案: Company Career page（Binance公式のGreenhouse求人boardから確認）。PROFILEの経路回答「Job board」は選択肢にない。提出担当が実際の発見経路と照合する | PROFILE `application_source_job_board_20260807` |
| Please briefly describe your professional or personal experience with cryptocurrency / blockchain. / `question_9808358101` | 必須・1行text | **本人確認必須。** 下の条件付き案 | 資料に該当factなし |
| Have you ever been employed at Binance before? / `question_9808359101` | 必須・Yes/No | No（RESUME/ABOUTの職歴にBinanceなし。提出前に本人確認） | RESUME/ABOUT |

### crypto/blockchain設問の条件付き案

資料にcrypto/blockchainの職務・個人経験は記載がない。本人が「経験なし」と確認した場合だけ次を使う。経験がある場合は本人の事実へ差し替える。

> I have no professional cryptocurrency or blockchain experience yet; I build AI-assisted products and currently work on AI agents in a banking context (MUFG Bank's internal CRM), and I want to learn digital-asset product engineering at Binance.

### カバーレター案

Dear Binance Accelerator Program Team,

I am applying for the Full Stack Engineer (AI) role. The program's emphasis on AI coding tools, product thinking, and learning fast matches how I already build.

I have built and published six iOS apps, including Anicca, a daily-affirmation app, and Honne, which interprets pasted conversations and suggests replies. I own product decisions, AI-assisted development, App Store releases, and marketing for them. I also build Life Manager, an open-source agent system with persistent scheduling and verified external actions: https://github.com/Daisuke134/life-manager. Turning a product idea into clear requirements and constraints for AI coding tools is a daily part of my work, and I founded a weekly lab and graduate-school community teaching Claude Code, Codex, Cursor, and agent workflows.

Since April 2025, I have worked on applied AI at Mitsubishi UFJ Information Technology, contributing to MUFG Bank's production Salesforce Agentforce deployment, including a Databricks workflow for analyzing agent response quality.

I want to strengthen my backend and frontend engineering foundations under senior engineers, and this program is designed for that kind of growth. I am based in Tokyo, authorized to work in Japan without sponsorship, and available from December 1, 2026.

Sincerely,
Daisuke Narita

（約195語）

## 経歴根拠・未確認事項

ANICCA=`anicca_consumer`・ABOUT「Six published iOS apps」、LM=`life_manager`・`life_manager_open_source_operations_20260805`、TEACH=`agent_club`、MUIT=`muit_role_2025`・`muit_agent_crm`、LOGS=`muit_genie_logs`、RESEARCH=`education`・`education_naist`、LANG=`languages`、JP=`legal_japan_work_authorization_20260730`・`legal_no_japan_sponsorship_required_20260806`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`。Anicca評価件数は日付付きの過去値なので転記しない。

提出前の残項目: (1) 在学要件（現在の在籍・NAIST学位授与）。満たさない場合は応募可否を参謀が判断する。(2) Java/Go/Rust/C++・Node.js・frontend framework・DB設計の実力の扱い。(3) 雇用形態・期間（本文に記載なし）とMUITとの関係。(4) crypto/blockchain経験の有無。(5) English選択。(6) 日本からのremote勤務が当該チームで可能か（不可なら転居・visaが必要）。(7) 報酬が希望下限を下回る可能性。
