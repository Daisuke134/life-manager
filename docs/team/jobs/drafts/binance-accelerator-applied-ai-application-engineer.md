# Binance — Accelerator Program - Applied AI Application Engineer

応募ドラフト。送信は参謀が所有する。台帳key: `job:binance:5002569101`（`ledger/APPLICATIONS.md` は `found`）。この原稿から応募・status更新を行わない。

公式求人: https://job-boards.eu.greenhouse.io/binance/jobs/5002569101 。公開Greenhouse Job Board API `boards-api.greenhouse.io/v1/boards/binance/jobs/5002569101?questions=true` で求人本文とフォームを取得する（EU host `boards-api.eu.greenhouse.io` はこの環境から応答なし、global hostは同じ `absolute_url` を返す）。`first_published` 2026-10-13、`updated_at` 2026-10-21で掲載中。締切記載なし。応募フォーム全15項目（必須10・任意5）。GDPR同意欄・demographic設問はschemaにない。応募mutation・ファイルアップロード・送信は行わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`、ABOUTは https://aniccaai.com/about （2026-10-24取得）。

## 応募資格と勤務地（最重要）

- **在学要件（GAP・提出判断要）:** 本職はTech Seeds 2026のinternship。「Currently pursuing a Bachelor's or Master's degree」「Expected graduation in 2026 or 2027」を要求する。資料上の学歴はKeio法学部（2020年4月〜2024年4月）とNAIST修士課程の研究期間（2024年4月〜2026年4月）で、現在の在籍は確認できず、NAIST修士号の授与も未確認。現役学生とは書かない。
- **6か月のfull-time:** 「Available for a 6-month full-time commitment」。資料はMUITでのApplied AI業務（2025年4月〜現在）と新しい職務の開始可能日2026年12月1日（START）を示す。MUITを離れて6か月の有期internshipへ就く意思は未確認。
- **勤務地・visa:** location表記は「Hong Kong; Japan; Singapore; Taiwan」、office欄はHong Kong、本文は「Remote-first, work-from-home arrangement (may vary depending on the nature of the role and team)」。Japanが勤務地に含まれるため、日本から勤務する限りsponsorshipは不要（JP）。チームがHong Kong・Singapore・Taiwanへの転居を求める場合は、本人に日本以外の就労資格がないため **visa/sponsorshipと転居が必要**。US就労資格はない（ESTAのみ）。
- **報酬:** internshipの報酬は非開示。希望下限800万円（SALARY）を満たす根拠はない。

## 適合と不足

- DIRECT: agent応答の入出力・品質をDatabricksで分析するworkflow（LOGS）は「evaluation metrics / failure cases」に対応。Agentforce導入への寄与（MUIT）、prompt tuning/context engineering（PROMPT）は「prompt strategies」「production AI systems」に対応。
- DIRECT: AI coding toolsの日常利用と指導（TEACH）、Life Managerのagent・永続schedule・検証付き外部作用（LM/RELIABILITY）は「agent workflows」「tool-use logic」「reliability」に対応。
- GAP: 必須の「Solid programming skills in Python or Java」を資料が裏付けない。Python/Javaの職務・個人利用を補完しない。backend services、retrieval/vector DB、LangChain、OpenAI/Anthropic APIの個別利用経験も未記載。ABOUTはLife Manager・iOS appの開発を「AI-assisted development」と記す。
- GAP: crypto/blockchainの経験は資料に一切ない（必須設問あり、下記）。

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
| LinkedIn Profile / `question_9808968101` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| Website / `question_9808969101` | 任意 | https://aniccaai.com/about | ABOUT |
| Where do you currently live? / `question_9808970101` | 必須・単一選択 | Japan | TOKYO |
| Will you require employer sponsorship for a work visa or work permit in the country where you currently reside or are currently based? / `question_9808971101` | 必須・Yes/No | No（日本居住・日本国籍。日本以外への転居時は別途必要） | JP |
| What language(s) can you speak at a native or business level? / `question_9808972101[]` | 必須・複数選択 | Japanese。**Englishは本人判断待ち**（資料はTOEFL iBT 96・TOEIC 910・DET 140の試験実績のみで、business levelの自己評価は未確認）。Spanish（DELE B1）は選ばない | LANG |
| How did you hear about our job opening? / `question_9808973101` | 必須・単一選択 | 案: Company Career page（Binance公式のGreenhouse求人boardから確認）。PROFILEの経路回答「Job board」は選択肢にない。提出担当が実際の発見経路と照合する | PROFILE `application_source_job_board_20260807` |
| Please briefly describe your professional or personal experience with cryptocurrency / blockchain. / `question_9808974101` | 必須・1行text | **本人確認必須。** 下の条件付き案 | 資料に該当factなし |
| Have you ever been employed at Binance before? / `question_9808975101` | 必須・Yes/No | No（RESUME/ABOUTの職歴にBinanceなし。提出前に本人確認） | RESUME/ABOUT |

### crypto/blockchain設問の条件付き案

資料にcrypto/blockchainの職務・個人経験は記載がない。本人が「経験なし」と確認した場合だけ次を使う。個人での保有・取引・開発経験がある場合は本人の事実へ差し替える。

> I have no professional cryptocurrency or blockchain experience yet; my current applied-AI work is in banking (AI agents in MUFG Bank's internal relationship-manager CRM), and I want to apply agent and evaluation skills to digital-asset products.

### カバーレター案

Dear Binance Tech Seeds Team,

I am applying for the Applied AI Application Engineer role in the Accelerator Program. My work sits where this role does: building agent workflows and checking whether they actually behave well in production.

Since April 2025, I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contribute to MUFG Bank's production deployment of Salesforce Agentforce in its internal CRM for relationship managers. I built a Databricks workflow to analyze agent inputs, outputs, and response quality, and supported prompt tuning and context engineering for company-information summaries. That work taught me to treat failure cases as the main source of improvement.

Outside work, I build Life Manager, an open-source agent system with persistent scheduling and verified external actions, using AI coding tools as part of my normal workflow. I also founded a weekly lab and graduate-school community teaching Claude Code, Codex, Cursor, and agent workflows. My master's research at the Nara Institute of Science and Technology (April 2024–April 2026) applied EEG and machine learning to mind-wandering detection.

I am based in Tokyo, authorized to work in Japan without sponsorship, and available from December 1, 2026. I would welcome a conversation about how I could contribute to your agent and evaluation work.

Sincerely,
Daisuke Narita

（約210語）

## 経歴根拠・未確認事項

MUIT=`muit_role_2025`・`muit_agent_crm`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、TEACH=`agent_club`、LM=`life_manager`・`life_manager_open_source_operations_20260805`、RESEARCH=`naist`・`education_naist`、LANG=`languages`、JP=`legal_japan_work_authorization_20260730`・`legal_no_japan_sponsorship_required_20260806`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`。

提出前の残項目: (1) 在学要件を満たすか（現在の在籍・2026/2027卒業見込み・NAIST学位授与）。満たさない場合は応募可否そのものを参謀が判断する。(2) 6か月full-time internshipへ就く意思とMUITとの関係。(3) Python/Javaの実力の扱い。(4) crypto/blockchain経験の有無。(5) English選択。(6) 日本からのremote勤務が当該チームで可能か（不可なら転居・visaが必要）。(7) internship報酬が希望下限を下回る可能性。原稿の存在を資格充足・応募済みの証明として扱わない。
