# Supabase — AI Platform Engineer

応募ドラフト。送信は参謀が所有する。台帳key: `job:supabase:3b5d54ca-741b-45ac-bd3f-31605a0d3541`（2026-10-24 `found`）。

公式求人: https://jobs.ashbyhq.com/supabase/3b5d54ca-741b-45ac-bd3f-31605a0d3541 。公開job board API（`api.ashbyhq.com/posting-api/job-board/supabase`）で本文・`isListed=true`・`publishedAt` 2026-07-31を確認する。状態: **募集中**。報酬は非公開（`shouldDisplayCompensationOnJobPostings=false`）。公開Ashby `ApiJobPosting` queryで応募フォーム全12項目（必須9・任意3）、追加survey（`surveyForms`）なしを取得する。応募mutation・ファイルアップロード・送信は行わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`、ABOUTは https://aniccaai.com/about （2026-10-24取得）。連絡先の値は公開原稿へ転記しない。

## 就労資格

勤務地 `Remote, Global`。本文: 「Fully Remote — We hire globally. We believe you can do your best work from anywhere.」「~400 team members, 60+ countries」。日本居住を排除する記載はない。本人は日本国籍・東京在住で日本での就労制限なし（JP）。**日本から勤務する場合、sponsorshipは不要。** フォームにsponsorship設問はなく、Passport CountryとCountry of Residenceを問う。日本での雇用形態（EOR・契約）は本文になく未確認。

## 適合と不足

本職は単独のengineerとして、event queue・model非依存runtime・永続state・human review gate・rollback・全run logging・評価層・governanceを本番構築する。

- DIRECT: Life Managerは永続schedule、検証付き外部操作、評価gate、曖昧な外部作用の再試行前の独立確認を扱うopen-source agent system（LM/RELIABILITY）。本文の「durable state」「human gate」「the dangerous action is impossible」と同じ問題を扱う。ABOUTはLife Managerが2026年9月に人手介入なしで20万円の売上を出した（founder-reported historical result）と記す。
- DIRECT: Databricksでagentの入出力・応答品質を分析するworkflow（LOGS）は本文のLLM observabilityに近い。
- TRANSFERABLE: MUFG BankのAgentforce本番導入への寄与（MUIT/PROFILE `mufg`）、週次AIツール勉強会（TEACH）。
- **GAP（重大）: MCP serverの作成経験の根拠がない（must have）。**
- **GAP（重大）: Python on GCP・cloud warehouse・IaCでのend-to-end運用の根拠がない（must have）。** 実装言語の根拠も許可ソースにない。ABOUTはLife Managerの開発を「AI assistance」と記し、本人の役割をdirection・release・go-to-marketとする。
- GAP: 評価はLife Managerの「evaluation gates」までが根拠。golden set・judge rubric・pass threshold・CI gateを本人が設計した具体例は資料にない。
- GAP: 「他者が依存する本番LLM agent systemと、語れるincident」— MUIT導入は寄与の立場で、本人がownerだったincidentは資料にない。Life Managerの利用者規模・incident事例も資料にない。本人が具体例を語れることが面接の前提。
- GAP: async/remote勤務の雇用経験は資料にない（MUITの勤務形態は未記載）。
- 雇用先除外リストにSupabaseは含まれない。

## フォーム回答案

| # | 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|---|
| 1 | Name / `_systemfield_name` | 必須 | Daisuke Narita | PROFILE |
| 2 | Email / `_systemfield_email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| 3 | Resume / `_systemfield_resume` | 必須・file | 既存英語resume PDF。送信直前に内容を確認する | RESUME |
| 4 | Passport Country / `5c60106e-bfac-4204-8e04-f490aceae780` | 必須 | Japan | PROFILE `citizenships` |
| 5 | Country of Residence / `15c66e51-3f59-4684-997e-86fd80103c7a` | 必須 | Japan | PROFILE `base` |
| 6 | Are you over the age of 18? / `27cb2e41-18c5-45f9-a60e-bfe732273692` | 必須・Boolean | Yes | PROFILE `legal_age_over_18_20260805` |
| 7 | Twitter / X profile / `238da55a-7c7e-4f7a-9cae-53fb3ac9badb` | 任意 | 空欄。確認済みの個人X URLが許可ソースにない | 未確認 |
| 8 | Github Profile / `f4337c35-1043-450b-b4f0-1eb10defc88f` | 必須 | https://github.com/Daisuke134 | PROFILE |
| 9 | Linkedin / `d9415c3c-22be-43c9-9616-c64bd942004f` | 必須 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 10 | Async/remote experience: practices and challenges / `33653c13-8823-4187-a806-079124784eeb` | 必須・LongText | 下記「Async/remote」案 | RELIABILITY/LM/TEACH |
| 11 | Open source contributions / `c3c51ba4-c1aa-4708-9755-053793af43ed` | 任意・LongText | 下記「Open source」案 | LM/ABOUT |
| 12 | Where did you hear about this vacancy? / `a6c582e1-3e7c-4bfb-b9f7-f070c7ba1479` | 任意 | Job board（公式Ashby job boardから発見） | PROFILE `application_source_job_board_20260807` |

取得schemaにcover letter専用欄はない。下のletterは補助原稿で、実フォームにない欄への入力が可能とは断定しない。

### Async/remote の回答案（#10）

Most of my agent work is asynchronous by nature: I build Life Manager, an open-source agent system that runs on a schedule and acts without human intervention, and I develop it with AI coding assistance. What works for me is the same discipline I would want from a teammate. I keep changes small and scoped, write concise progress notes where the next person will look, keep state durable so work can resume after a failure, run automated checks before anything is merged, and make handoffs explicit about what is done, what is not, and what to check next.

The hardest challenge has been ambiguous outcomes. When an external action times out, the tempting move is to retry. I learned not to retry blindly, and to confirm from an independent source whether the action actually happened before releasing or repeating it.

A second challenge is that written context has to carry what a hallway conversation would. I learned that while running a weekly study group on Claude Code, Codex and Cursor in my lab and graduate school: a short written example works better than a long explanation.

I have not yet worked for a fully remote company, so I would expect to adapt to Supabase's specific async norms quickly.

### Open source の回答案（#11）

Life Manager — https://github.com/Daisuke134/life-manager . It is an open-source AI manager that runs locally with persistent scheduling and verified external actions; it finds work, sends proposals, handles client replies, creates deliverables and tracks payments. I own its direction, releases and go-to-market, and development uses AI assistance. The design problems are close to the ones in this role: durable state that survives a failed run, evaluation gates before changes ship, and conservative handling of external side effects whose outcome is uncertain.

### カバーレター案

Dear Supabase Hiring Team,

I am applying for the AI Platform Engineer role because the problem you describe, making the dangerous action impossible rather than discouraged, is the problem I keep running into in my own agent work.

I build Life Manager, an open-source agent system that runs on a schedule and takes real external actions. Its hard parts are the ones in your posting: state that survives a failed run, evaluation gates before changes ship, and not retrying an external action until an independent source confirms what happened. I own its direction and releases, with AI-assisted development.

Since April 2025 at Mitsubishi UFJ Information Technology, I have contributed to MUFG Bank's production deployment of Salesforce Agentforce in an internal CRM used by relationship managers across Japan, a regulated setting where governance is not optional. I built a Databricks workflow to analyze agent inputs, outputs and response quality, and supported prompt tuning and context engineering.

To be clear about gaps against your must-haves: I have not authored an MCP server in a professional setting, and I have not owned Python infrastructure on GCP with infrastructure as code. I would bring a working instinct for agent governance and observability, and I would close those gaps quickly.

I live in Tokyo and can work from Japan without sponsorship.

Sincerely,
Daisuke Narita

## 未確認・提出前の残項目

- must haveのMCP server作成、Python/GCP/IaC運用、評価設計（golden set・rubric・CI gate）の実例。本人が具体例を持たない場合、カバーレターの不足記述を維持する。
- 本人がownerとして語れる本番incidentの具体例。
- Life Managerの20万円売上はABOUTのfounder-reported値で、PROFILEの記録は2026年8月のUSD 1,000。回答・letterでは数値を使っていない。
- 日本での雇用形態（EOR・契約）と報酬（非公開。目標約1,000万円はSALARY）。
- Async回答の「fully remote companyでの勤務経験なし」の記述は、MUITの勤務形態を本人が確認して調整する。
