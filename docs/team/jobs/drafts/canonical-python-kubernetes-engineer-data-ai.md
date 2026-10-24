# Canonical — Python and Kubernetes Software Engineer - Data, Workflows, AI/ML & Analytics

応募ドラフト。送信は参謀が所有する。台帳key: `job:canonical:5703396`（2026-10-24 `found`）。

> **最重要: AI生成文の使用禁止。** 公式フォームの必須設問 `question_45893742` は「During this application process I agree to use only my own words. I understand that plagiarism, the use of AI or other generated content will disqualify my application.」。この原稿はAIが作成したため、**下の文章をそのまま貼ってYesを選ぶと宣誓が虚偽になり失格事由になる。** 記述回答は本人が自分の言葉で書くための事実アウトラインとして扱い、貼付用の完成文は用意しない。カバーレター案も提出物ではなく、本人が書く際の論点整理に限る。

公式求人: https://job-boards.greenhouse.io/canonical/jobs/5703396 。Greenhouse公開API（`boards-api.greenhouse.io/v1/boards/canonical/jobs/5703396?questions=true`）で本文と応募フォームを取得する。状態: **募集中**（API応答に本文・設問あり、`updated_at` 2026-08-05）。勤務地 `Home based - Worldwide`。応募mutation・ファイルアップロード・送信は行わない。

フォーム: 全22項目（必須19・任意3）＋任意のEEOC障害自己申告1項目（`disability_status`）。GDPRの追加同意は `requires_consent=false`。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`。ABOUTは https://aniccaai.com/about （2026-10-24取得）。連絡先の値は公開原稿へ転記しない。

## 就労資格

勤務地はHome based - Worldwide。本文は時差の近いチームへ配属すると記し、特定国の居住を要求しない。本人は日本国籍・東京在住で日本での就労制限なし（JP）。**日本から勤務する場合、sponsorshipは不要。** フォームにsponsorship設問はない。日本での雇用形態（現地法人・EOR・契約）は本文になく未確認。米国勤務になる場合はESTAのみのためsponsorshipが必要（PROFILE `travel_authorizations`）。

## 適合と不足

- DIRECT: Databricksでagentの入出力・応答品質を分析するworkflow（LOGS）、EEGとmachine learningの研究（RESEARCH）、Toshiba研究インターンでのwearable sensorデータへのML適用（ABOUT）。
- TRANSFERABLE: Life Managerのopen-source運用、永続state・自動check・評価gate（LM/RELIABILITY）、週次AIツール勉強会の設立（TEACH）、ICLR 2026での社内報告（ABOUT/PROFILE `iclr`）。
- **GAP（重大）: Kubernetesの職務・個人利用の根拠が許可ソースに一切ない。** 職名に含まれる中核要件で、必須の記述設問がある。経験を補完しない。
- **GAP: Pythonでのsoftware deliveryの根拠がない。** RESUME/PROFILE/ABOUTにPythonの記載はない。Life Managerの実装言語・本人の担当範囲は許可ソース外で、ABOUTは「development uses AI assistance」と記す。本人がPython経験を自分で説明できる場合だけ記入する。
- GAP: 学士はKeio法学部政治学科（技術系ではない）。授与と成績（GPA等）は未確認。高校成績の根拠資料もない。
- GAP: Linux（Debian/Ubuntu）、container、public cloud、Kubeflow/MLflow/Airflow等の経験は許可ソースにない。
- 雇用先除外リスト（PROFILE `employer_exclusions`）にCanonicalは含まれない。

## フォーム回答案

| # | 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|
| 1 | First Name / `first_name` | 必須 | Daisuke | PROFILE |
| 2 | Last Name / `last_name` | 必須 | Narita | PROFILE |
| 3 | Email / `email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| 4 | Phone / `phone` | 任意 | 入力する場合はPROFILE `candidate.phone`。国番号を提出担当が確認 | PROFILE |
| 5 | Resume/CV / `resume`（file）or `resume_text` | 必須 | 既存英語resume PDF。PythonやKubernetesの記載がないことを前提に提出判断する | RESUME |
| 6 | Own-words / no-AI attestation / `question_45893742` | 必須・Yes/No | **本人判断。** 記述回答をすべて本人が自分の言葉で書いた場合だけYes。この原稿の文を流用した場合はYesを選べない | 公式設問 |
| 7 | Describe your experience with Kubernetes / `question_45893748` | 必須・textarea | **本人記入。** 許可ソースに経験の根拠なし。経験がない場合はその事実と学習意欲を本人の言葉で書く。下記アウトラインA | なし（GAP） |
| 8 | Python software engineer experience, data/mlops/workflow/analytics / `question_45893749` | 必須・textarea | **本人記入。** 下記アウトラインB | LOGS/RESEARCH/ABOUT |
| 9 | High school mathematics performance / `question_45893743` | 必須・選択 | **未選択。** 根拠資料なし。本人が実績に基づき選ぶ。「Cannot recall」も自動選択しない | 未確認 |
| 10 | High school native-language performance / `question_45893744` | 必須・選択 | **未選択。** 同上 | 未確認 |
| 11 | Rationale for high-school selections / `question_45893745` | 必須・textarea | **本人記入。** 確認済みはKeio Shiki Senior High School在籍（2017-04〜2020-03）とKeio大学への進学のみ。順位・試験成績・受賞は資料にない | PROFILE `education_high_school`/`education` |
| 12 | Bachelor's degree result with grading system / `question_45893746` | 必須・textarea | **本人記入。** Keio University, Faculty of Law, Department of Political Science（2020-04〜2024-04）。授与・GPA・評価方式は未確認 | PROFILE `education` |
| 13 | Companies worked for since first undergraduate degree / `question_46909085` | 必須・選択 | 候補「1」（MUIT）。NAIST/ATRの研究が雇用だったかで「2」になり得るため本人確認 | MUIT/RESEARCH |
| 14 | Website / `question_45893750` | 任意 | https://aniccaai.com/about または https://github.com/Daisuke134 | ABOUT/PROFILE |
| 15 | LinkedIn Profile / `question_45893751` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 16 | In-person events 2-4 times a year, international travel / `question_45893747` | 必須・Yes/No | **本人判断。** 年2〜4回・1〜2週間の海外出張の可否は許可ソースにない | 未確認 |
| 17 | Country you currently work in / `question_45893752` | 必須・選択 | Japan | JP/TOKYO |
| 18 | Recruitment Privacy Notice and Privacy Policy / `question_45893753` | 必須・Acknowledge | 下書きでは未選択。提出担当が本文を確認して選ぶ | 公式設問 |
| 19 | Time zone / `question_51726141` | 必須・選択 | Asia Pacific Time Zones | TOKYO |
| 20 | Gender / `question_55370434` | 必須・選択（任意回答の旨の注記あり） | PROFILE `candidate.gender`。開示しない場合は「Prefer not to say」を本人が選ぶ | PROFILE |
| 21 | Nationality / `question_65008223[]` | 必須・複数選択（任意回答の旨の注記あり） | Japanese | PROFILE `nationality` |
| 22 | Race or ethnicity / `question_65008235` | 必須・選択（任意回答の旨の注記あり） | **未選択。** 許可ソースに記載なし。本人が選ぶ（「Prefer not to say」可） | 未確認 |
| — | EEOC Disability status / `disability_status` | 任意 | 空欄。本人が選ぶ | 未確認 |

取得schemaにcover letter専用欄はない。

### アウトラインA（Kubernetes、本人が自分の言葉で書く）

- 許可ソースにKubernetes経験はない。経験がないなら、ないと書く。
- 書ける接点: Databricks上でのデータworkflow構築（LOGS）、Life Managerの永続schedule・状態管理・自動check（LM/RELIABILITY）。これらをKubernetes経験として言い換えない。
- 本人が実際に触ったcontainer/cluster経験があれば、具体的な対象・規模・期間を本人が書く。

### アウトラインB（Python / data / MLOps / analytics、本人が自分の言葉で書く）

- Since April 2025 at MUIT: built a Databricks workflow to analyze Salesforce Agentforce agent inputs, outputs and response quality for relationship managers, using Genie Code (LOGS)。使用言語は資料にないため、Pythonだったかは本人が書く。
- Prompt tuning and context engineering for company-information summaries (PROMPT)。
- NAIST/ATR: EEG and machine learning for mind-wandering detection (RESEARCH)。Toshiba research intern: wearable-sensor data, FFT features and an autoencoder to identify walking environments (ABOUT)。Earlier BERT-based analysis of emotional tone in soccer commentary (ABOUT)。実装言語は本人確認。
- Open source: Life Manager, https://github.com/Daisuke134/life-manager (LM)。担当はdirection・release・go-to-marketで、開発はAI支援（ABOUT）。
- 改善率・データ量・利用者数は資料にないため書かない。

### カバーレター論点（提出物ではない。本人が書く場合の材料）

Dear Canonical Hiring Team,

I am interested in the Python and Kubernetes Software Engineer role on the data, workflows and AI/ML team because it sits where my experience is strongest: making ML and agent systems measurable and usable.

Since April 2025 I have worked on applied AI at Mitsubishi UFJ Information Technology. I contributed to MUFG Bank's production deployment of Salesforce Agentforce in its internal relationship-manager CRM, and built a Databricks workflow to analyze agent inputs, outputs and response quality. Before that, my graduate research at NAIST and ATR applied EEG and machine learning to mind-wandering detection, and a Toshiba research internship applied machine learning to wearable-sensor data.

Outside work I run Life Manager, an open-source agent system with persistent scheduling, durable state and automated checks, and I founded a weekly study group on AI coding tools and agent workflows.

I want to be direct about the gap: I have not yet worked professionally with Kubernetes, and my undergraduate degree is in political science. I would bring hands-on data and ML experience, a habit of verifying outcomes rather than processes, and the drive to learn the Linux and Kubernetes stack quickly.

I am based in Tokyo and can work from Japan without sponsorship.

Sincerely,
Daisuke Narita

## 未確認・提出前の残項目

- AI生成文禁止の宣誓（#6）。本人が全記述を自分で書くことが提出の前提。
- Kubernetes経験・Pythonでの開発経験・Linux経験の有無と具体例（#7, #8）。
- 高校の数学・国語の成績と根拠（#9〜#11）、学士の授与と成績（#12）、雇用社数（#13）。
- 年2〜4回の海外出張の可否（#16）、人種/民族の回答（#22）、プライバシー同意（#18）。
- 日本での雇用形態（法人/EOR/契約）と報酬帯（本文に金額なし。目標約1,000万円はSALARY）。
- ABOUTとRESUME/PROFILEでA10 Labの在籍期間が異なる（ABOUT: 2020-11〜2022-01、RESUME: 2020-01〜2021-01）。この求人の回答には使わないが、resume提出前に本人が統一する。
