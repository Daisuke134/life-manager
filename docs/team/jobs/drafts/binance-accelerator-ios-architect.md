# Binance — Accelerator Program - iOS Architect

応募ドラフト。送信は参謀が所有する。台帳key: `job:binance:5002685101`（`ledger/APPLICATIONS.md` は `found`）。この原稿から応募・status更新を行わない。

公式求人: https://job-boards.eu.greenhouse.io/binance/jobs/5002685101 。公開Greenhouse Job Board API `boards-api.greenhouse.io/v1/boards/binance/jobs/5002685101?questions=true` で求人本文とフォームを取得する（EU host `boards-api.eu.greenhouse.io` はこの環境から応答なし、global hostは同じ `absolute_url` を返す）。`first_published` 2026-10-13、`updated_at` 2026-10-15で掲載中。締切記載なし。応募フォーム全20項目（必須15・任意5）。GDPR同意欄・demographic設問はschemaにない。応募mutation・ファイルアップロード・送信は行わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`、ABOUTは https://aniccaai.com/about （2026-10-24取得）。

## 応募資格と勤務地（最重要）

- **職位の実態:** 職名は「Architect」だが、Accelerator Programの6か月full-time契約で、要件は「Current student or recent graduate」。多年のiOS architecture経験を求める職ではない。本人を「iOS architect」として経験年数を誇張しない。
- **在学/新卒要件（GAP・提出判断要）:** 必須設問「active student or have graduated less than 2 year ago with a Bachelors, Masters or PhD?」がある。Keio法学部は2024年4月までの在籍で、2026年10月時点で卒業から2年を超える可能性が高い。NAIST修士課程の研究期間は2024年4月〜2026年4月だが学位授与は未確認。授与済みならYes、未授与ならNoになり得る。資料から自動でYesにしない。
- **勤務地・visa:** location表記は「Hong Kong; Japan; Singapore; Taiwan」、office欄はHong Kong、本文は「Remote-first, work-from-home arrangement (may vary depending on the nature of the role and team)」。Japanが勤務地に含まれるため、日本から勤務する限りsponsorshipは不要（JP）。チームがHong Kong・Singapore・Taiwanへの転居を求める場合は、本人に日本以外の就労資格がないため **visa/sponsorshipと転居が必要**。US就労資格はない（ESTAのみ）。
- **報酬:** 非開示。希望下限800万円（SALARY）を満たす根拠はない。

## 適合と不足

- DIRECT:「Hands-on experience in iOS development」— 6本のiOS app（Anicca、Honne、STUDIO CHERIE、Sleep Reset、Thankful、Daily Dhamma）を公開し、product decisions・AI-assisted development・App Store release・marketingを担う（ABOUT/ANICCA）。
- TRANSFERABLE:「internal tooling, automation, and developer experience」— Life Managerのagent・自動check・永続state（LM/RELIABILITY）、AI coding toolsの指導（TEACH）。
- GAP: ABOUTは開発を「AI-assisted development」と記す。Swift/Objective-Cの習熟、UIKit/SwiftUI、app lifecycle、networking、multithreading、memory managementの理解、再利用module・frameworkの設計経験は資料が裏付けない。CS/Software Engineering系の学位でもない（Keio法学部政治学科、NAISTはEEG/ML研究）。data structures/algorithmsの学習歴も未記載。
- GAP: crypto/blockchainの経験は資料に一切ない（必須設問あり、下記）。

## フォーム回答案

| 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|
| First Name / `first_name` | 必須 | Daisuke | PROFILE |
| Last Name / `last_name` | 必須 | Narita | PROFILE |
| Preferred First Name / `preferred_name` | 任意 | Daisuke | PROFILE `candidate.preferred_name` |
| Email / `email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| Phone / `phone` | 任意 | PROFILE `candidate.phone`から国番号付きで入力 | PROFILE |
| Resume/CV / `resume` (file) or `resume_text` | 必須 | 既存英語resume PDFを添付。このPDFはiOS app 6本を個別に列挙しないため、App Store portfolio URLをcover letterで補う | RESUME |
| Cover Letter / `cover_letter` (file) or `cover_letter_text` | 任意 | 下の「カバーレター案」を `cover_letter_text` へ貼る | 下記 |
| LinkedIn Profile / `question_9809507101` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| Where do you currently live? / `question_9809508101` | 必須・単一選択 | Japan | TOKYO |
| Are you legally authorized to work in the country where you are located? / `question_9809509101` | 必須・Yes/No | Yes | JP |
| What language(s) can you speak at a native or business level? / `question_9809510101[]` | 必須・複数選択 | Japanese。**Englishは本人判断待ち**（資料はTOEFL iBT 96・TOEIC 910・DET 140の試験実績のみ）。Spanish（DELE B1）は選ばない | LANG |
| What is the earliest possible date that you could join? (d/m/year) / `question_9809511101` | 必須・text | 1/12/2026 | START |
| Can you work full-time? (This is a full-time position.) / `question_9809512101` | 必須・Yes/No | Yes（2026年12月1日からの新しい職務として） | START・TOKYO |
| Please briefly describe your professional or personal experience with cryptocurrency / blockchain. / `question_9809513101` | 必須・1行text | **本人確認必須。** 下の条件付き案 | 資料に該当factなし |
| Are you an active student or have graduated less than 2 year ago with a Bachelors, Masters or PhD? / `question_9809514101` | 必須・Yes/No | **未確定。** NAIST修士号が授与済みならYes。未授与なら資料上Yesの根拠なし | `education`・`education_naist`（degree_conferral_unverified） |
| Would you be able to complete the 6 months contract? / `question_9809515101` | 必須・Yes/No | **本人確認必須。** 開始可能日はあるが、6か月有期契約を完遂する意思・MUITとの関係は未確認 | START（意思は未確認） |
| How many weekdays per week would you be able to commit to working? / `question_9809516101` | 必須・textarea | 案: `5 weekdays per week, starting December 1, 2026.`（6か月契約の意思確認と同時に確定する） | START・`availability_tokyo_office_three_days_20260806` |
| Which university's AMA session did you attend? / `question_9809517101` | 任意 | 空欄（AMA参加の記録なし） | 該当factなし |
| Have you ever been employed at Binance before? / `question_9809518101` | 必須・Yes/No | No（RESUME/ABOUTの職歴にBinanceなし。提出前に本人確認） | RESUME/ABOUT |
| How did you hear about our job opening? / `question_9809519101` | 必須・単一選択 | 案: Company Career page（Binance公式のGreenhouse求人boardから確認）。PROFILEの経路回答「Job board」は選択肢にない。提出担当が実際の発見経路と照合する | PROFILE `application_source_job_board_20260807` |

本フォームにはWebsite欄がない。App Store portfolioはcover letter本文で示す。

### crypto/blockchain設問の条件付き案

資料にcrypto/blockchainの職務・個人経験は記載がない。本人が「経験なし」と確認した場合だけ次を使う。経験がある場合は本人の事実へ差し替える。

> I have no professional cryptocurrency or blockchain experience yet; I build and publish consumer iOS apps and work on AI agents in banking (MUFG Bank's internal CRM), and I want to learn how a large-scale crypto app is engineered.

### カバーレター案

Dear Binance Experience & Connectivity Team,

I am applying for the iOS Architect role in the Accelerator Program. I have hands-on experience taking iOS apps from idea to the App Store, and I want to deepen the architecture and engineering fundamentals behind them.

I have built and published six iOS apps: Anicca, Honne, STUDIO CHERIE, Sleep Reset, Thankful, and Daily Dhamma (https://apps.apple.com/us/developer/daisuke-narita/id1852117244). I own product decisions, AI-assisted development, App Store releases, and marketing for each, so I have handled the full cycle of shipping and maintaining apps for real users. I also build Life Manager, an open-source agent system with automated checks and persistent state, and founded a weekly community teaching Claude Code, Codex, Cursor, and agent workflows. That background connects with the team's work on internal tooling, automation, and developer experience.

Since April 2025, I have worked on applied AI at Mitsubishi UFJ Information Technology, contributing to MUFG Bank's production Salesforce Agentforce deployment.

I would value learning reusable module design, performance, and stability practices from your engineers at Binance's scale. I am based in Tokyo, authorized to work in Japan, and available full-time from December 1, 2026.

Sincerely,
Daisuke Narita

（約190語）

## 経歴根拠・未確認事項

ANICCA=`anicca_consumer`・ABOUT「Six published iOS apps」とApp Store portfolio URL、LM=`life_manager`・`life_manager_open_source_operations_20260805`、RELIABILITY=`agent_reliability_engineering_20260805`、TEACH=`agent_club`、MUIT=`muit_role_2025`・`muit_agent_crm`、RESEARCH=`education`・`education_naist`、LANG=`languages`、JP=`legal_japan_work_authorization_20260730`・`legal_no_japan_sponsorship_required_20260806`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`。Anicca評価件数は日付付きの過去値なので転記しない。

提出前の残項目: (1) 在学/2年以内卒業の必須設問（NAIST学位授与の有無）。Noなら応募可否を参謀が判断する。(2) 6か月契約の完遂意思とMUITとの関係。(3) Swift/Objective-C・UIKit/SwiftUI・lifecycle・networking・multithreading・memory managementの実力の扱い（面接で問われる前提）。(4) crypto/blockchain経験の有無。(5) English選択。(6) 日本からのremote勤務が当該チームで可能か（不可なら転居・visaが必要）。(7) 報酬が希望下限を下回る可能性。
