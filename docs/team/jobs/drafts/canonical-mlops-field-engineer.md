# Canonical — MLOps Field Engineer

応募ドラフト。送信は参謀が所有する。台帳key: `job:canonical:6783943`（2026-10-24 `found`）。

> **最重要: AI生成文の使用禁止。** 公式フォームの必須設問 `question_55709257` は「During this application process I agree to use only my own words. I understand that plagiarism, the use of AI or other generated content will disqualify my application.」。この原稿はAIが作成したため、**下の文章をそのまま貼ってYesを選ぶと宣誓が虚偽になり失格事由になる。** 記述回答は本人が自分の言葉で書くための事実アウトラインとして扱い、貼付用の完成文は用意しない。カバーレター案も提出物ではなく論点整理に限る。

公式求人: https://job-boards.greenhouse.io/canonical/jobs/6783943 。Greenhouse公開API（`?questions=true`）で本文と応募フォームを取得する。状態: **募集中**（API応答に本文・設問あり、`updated_at` 2026-08-05）。勤務地 `Home based - Worldwide`。応募mutation・ファイルアップロード・送信は行わない。

フォーム: 全22項目（必須18・任意4）＋任意のEEOC障害自己申告1項目。GDPRの追加同意は `requires_consent=false`。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILE/RESUME/ABOUTの所在は[Canonical Python/K8s原稿](canonical-python-kubernetes-engineer-data-ai.md)と同じ。連絡先の値は公開原稿へ転記しない。

## 就労資格

本文: 「Most of our colleagues work from home. We are growing teams in EMEA, Americas and APAC time zones, so can accommodate candidates from almost any country.」。本人は日本国籍・東京在住で日本での就労制限なし（JP）。**日本から勤務する場合、sponsorshipは不要。** フォームにsponsorship設問はない。日本での雇用形態は未確認。業務で最大30%の国際出張があり、米国の顧客訪問は短期商用渡航の範囲で行う前提。米国勤務になる場合はESTAのみのためsponsorshipが必要。

## 適合と不足

本職は「not a software development role」で、presalesでの顧客対話、ML architecture設計、presentation・trainingが中心。Pythonは中級を要求し、KubernetesのOperator開発も業務に含む。

- DIRECT: Databricksでagentの入出力・応答品質を分析するworkflow（LOGS）、EEG×ML研究（RESEARCH）、ICLR 2026の社内経営層向け報告と公式会議レポートでの発表（PROFILE `iclr`/ABOUT）。
- TRANSFERABLE: MUITを通じたMUFG BankのAgentforce本番導入への寄与（MUIT/PROFILE `mufg`）。利用者は銀行内のrelationship managerで、社外顧客へのpresales経験ではない。週次AIツール勉強会の設立（TEACH）は研修・説明の経験として使う。顧客SaaSのLP改善（PROFILE `saas_lp_cvr_3_to_10_20260819`、CVR約3%→約10%）は顧客案件だが技術presalesではない。
- **GAP（重大）: Kubernetesの経験根拠がない。** 必須の記述設問がある。
- **GAP（重大）: 社外顧客向けの技術職（presales・solutions architect・consulting）の職歴がない。** 必須の記述設問がある。
- GAP: Python中級・Linux・virtualization・networking・AWS/Azure/GCP・Kubeflow/MLflow/Spark/OpenStackの根拠なし。
- GAP: 学士は法学部政治学科。授与・成績・高校成績の根拠なし。
- 雇用先除外リストにCanonicalは含まれない。

## フォーム回答案

| # | 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|
| 1 | First Name / `first_name` | 必須 | Daisuke | PROFILE |
| 2 | Last Name / `last_name` | 必須 | Narita | PROFILE |
| 3 | Email / `email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| 4 | Phone / `phone` | 任意 | 入力する場合はPROFILE `candidate.phone` | PROFILE |
| 5 | Resume/CV / `resume` or `resume_text` | 必須 | 既存英語resume PDF | RESUME |
| 6 | Outline your experience with MLOps and Analytics / `question_55709246` | 任意・textarea | **本人記入。** 下記アウトラインA | LOGS/RESEARCH/ABOUT |
| 7 | Outline your experience with Kubernetes / `question_55709247` | 必須・textarea | **本人記入。** 許可ソースに経験なし。経験がない場合は事実として書く。下記アウトラインB | なし（GAP） |
| 8 | Professional experience in customer-facing technical roles / `question_55709248` | 必須・textarea | **本人記入。** 下記アウトラインC | MUIT/TEACH/ABOUT |
| 9 | High school mathematics performance / `question_55709249` | 必須・選択 | **未選択。** 根拠資料なし。本人が選ぶ | 未確認 |
| 10 | High school native-language performance / `question_55709250` | 必須・選択 | **未選択。** 同上 | 未確認 |
| 11 | Rationale for high-school selections / `question_55709251` | 必須・textarea | **本人記入。** 確認済みはKeio Shiki Senior High School在籍（2017-04〜2020-03）のみ | PROFILE `education_high_school` |
| 12 | Bachelor's degree result with grading system / `question_55709252` | 必須・input_text（1行） | **本人記入。** Keio University, Faculty of Law, Political Science。授与・GPAは未確認 | PROFILE `education` |
| 13 | In-person events 2-4 times a year plus customer/external travel / `question_55709253` | 必須・Yes/No | **本人判断。** 年2〜4回の社内イベントと顧客訪問の出張可否は許可ソースにない | 未確認 |
| 14 | Website / `question_55709254` | 任意 | https://aniccaai.com/about | ABOUT |
| 15 | LinkedIn Profile / `question_55709255` | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 16 | Country you currently work in / `question_55709256` | 必須・選択 | Japan | JP/TOKYO |
| 17 | Own-words / no-AI attestation / `question_55709257` | 必須・Yes/No | **本人判断。** 全記述を本人が自分の言葉で書いた場合だけYes | 公式設問 |
| 18 | Recruitment Privacy Notice and Privacy Policy / `question_55709258` | 必須・Acknowledge | 下書きでは未選択。提出担当が本文を確認して選ぶ | 公式設問 |
| 19 | Companies worked for since first undergraduate degree / `question_55709259` | 必須・選択 | 候補「1」（MUIT）。NAIST/ATRが雇用なら「2」。本人確認 | MUIT/RESEARCH |
| 20 | Gender / `question_55709260` | 必須・選択（任意回答の旨の注記あり） | PROFILE `candidate.gender`。開示しない場合は「Prefer not to say」 | PROFILE |
| 21 | Nationality / `question_65084282[]` | 必須・複数選択（同上） | Japanese | PROFILE |
| 22 | Race or ethnicity / `question_65084300` | 必須・選択（同上） | **未選択。** 本人が選ぶ | 未確認 |
| — | EEOC Disability status / `disability_status` | 任意 | 空欄。本人が選ぶ | 未確認 |

取得schemaにcover letter専用欄と時間帯設問はない（Python/K8s職とは構成が異なる）。

### アウトラインA（MLOps / Analytics）

- MUIT（2025-04〜）: Databricks workflow to analyze Agentforce agent inputs, outputs and response quality, using Genie Code (LOGS)。Prompt tuning / context engineering (PROMPT)。
- NAIST/ATR: EEG + machine learning for mind-wandering detection (RESEARCH)。Toshiba research intern: FFT features and an autoencoder on wearable-sensor data (ABOUT)。
- 本番MLモデルの学習・配備・監視pipelineの経験は資料にない。書かない。

### アウトラインB（Kubernetes）

- 許可ソースに経験なし。経験がないなら、ないと書く。他の経験をKubernetesと言い換えない。

### アウトラインC（customer-facing technical）

- 社外顧客向けの技術職歴は資料にない。この事実を曲げない。
- 近い経験: MUFG Bankのrelationship manager向け社内CRMへのAgentforce導入への寄与（社内利用者向け、単独主導ではない）（MUIT）。ICLR 2026で研究を経営層向けに要約し、公式会議レポートで発表（PROFILE `iclr`）。研究室・大学院でClaude Code/Codex/Cursorを教える週次community（TEACH）。顧客SaaSのLP改善でCVR約3%→約10%（PROFILE、技術presalesではない）。

### カバーレター論点（提出物ではない）

Dear Canonical Field Engineering Team,

I am interested in the MLOps Field Engineer role because I enjoy the part of AI work where a technical system meets the people who must trust it.

Since April 2025 at Mitsubishi UFJ Information Technology, I have contributed to MUFG Bank's production deployment of Salesforce Agentforce in an internal CRM used by relationship managers across Japan. I built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering. I also represented the company at ICLR 2026 and turned the research into an executive briefing and a public conference report. My graduate research at NAIST and ATR applied machine learning to EEG data.

I founded and run a weekly study group teaching Claude Code, Codex, Cursor and agent workflows, which is where I learned to explain a system by showing it working.

The gaps are real: I have not held an external presales or consulting role, and I have not worked professionally with Kubernetes. I would bring a regulated-enterprise deployment perspective, clear explanation, and a commitment to learning Canonical's MLOps stack in depth.

I am based in Tokyo and can work from Japan without sponsorship.

Sincerely,
Daisuke Narita

## 未確認・提出前の残項目

- AI生成文禁止の宣誓（#17）。本人が全記述を自分で書くことが提出の前提。
- Kubernetes・社外顧客向け技術職・Python中級・Linux/cloudの実経験（#7, #8）。
- 高校成績と根拠、学士の授与と成績、雇用社数（#9〜#12, #19）。
- 最大30%の国際出張と年2〜4回の社内イベントの可否（#13）、人種/民族（#22）、プライバシー同意（#18）。
- 日本での雇用形態と報酬（本文に金額なし。業績連動bonus/commissionあり）。
- A10 Labの在籍期間がABOUTとRESUMEで異なる。resume提出前に本人が統一する。
