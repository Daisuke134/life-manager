# Cognition — Forward Deployed Engineer - Japan

応募ドラフト。送信は参謀が所有する。台帳key: `job:cognition:9ebb0dff-2cbf-42ba-bb4a-0256812a06e0`。claim PR: [#8780](https://github.com/Daisuke134/life-manager/pull/8780)。

公式求人: https://jobs.ashbyhq.com/cognition/9ebb0dff-2cbf-42ba-bb4a-0256812a06e0 。Tokyoの求人本文・公開一覧と`isListed=true`を確認する。公開Ashby `ApiJobPosting` queryで応募フォーム全5項目（必須4・任意1）、追加surveyなしを取得する。応募mutation・ファイルアップロード・送信は行わない。

根拠記号は[共通spec](../../specs/job-application-drafts.md#経歴根拠)を参照する。PROFILEは私的正本 `~/.config/anicca/job-search/profile.json`、RESUMEは `~/.local/share/anicca/job-search/materials/master/Daisuke_Narita_AI_Resume.pdf`。メールはPROFILEの`candidate.application_email`を使う。参謀指定の応募用アドレスとの一致を確認済みで、値は公開原稿へ転記しない。

## 適合と不足

- DIRECT: MUIT経由の企業AI導入支援（MUIT）、agent応答のDatabricks分析（LOGS）、prompt/context支援（PROMPT）。
- TRANSFERABLE: Claude Code・Codex・Cursorを教える週次community（TEACH）、Life Managerのagent運用・外部作用の検証（LM/RELIABILITY）。Devinの導入経験とは書かない。
- GAP: 必須のSTEM学位は授与を確認できない。NAISTの修士研究期間は確認できるが、取得済み修士号へ置換しない。過去GTM/FDE職での企業導入実績を求める求人に対し、MUITの導入への寄与を説明する。単独責任者、営業quota、数千名への展開実績は主張しない。
- 台帳の過去「Partner Deployed Engineer, Japan」は別職名の履歴で、このFDEの新規key・URLとは区別する。過去応募を削除・再送しない。

## フォーム回答案

| 公式設問 / source field | 区分 | 回答案・入力元 | 根拠 |
|---|---|---|---|
| Name / `_systemfield_name` | 必須 | Daisuke Narita | PROFILE/RESUME |
| Email / `_systemfield_email` | 必須 | PROFILE `candidate.application_email`から入力 | PROFILE |
| Resume / `_systemfield_resume` | 必須・file | 上記の既存英語resume PDF。送信直前に内容と添付対象を確認する | RESUME |
| Linkedin profile / `156f18c6-3a0f-449c-873f-87000e7faf5a` | 必須 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| Share an experience or achievement that you take particular pride in. / `62e7eb49-8446-411f-9ef4-3007effc0f54` | 任意 | 下の「成果・経験」案 | LM/RELIABILITY/TEACH |

取得schemaにcover letter専用欄はない。下のletterは補助原稿として用意し、実フォームにない欄への入力・添付が可能とは断定しない。任意の成果欄に両文章を重複して貼らない。学位やDevin経験を問う追加欄は取得schemaにはなく、表示が変わった場合にこの原稿からYesを補完しない。

### 成果・経験の回答案

One project I take particular pride in is Life Manager, an open-source system I build to coordinate everyday workflows through local agents, persistent scheduling, and verified external actions. It has taught me to distinguish a successful process from a successful real-world outcome. I build and test workflows with durable state, recovery paths, evaluation gates, and conservative handling of ambiguous side effects.

I also founded a weekly community in my lab and graduate-school environment to teach Claude Code, Codex, Cursor, and agent workflows. Building systems and helping others understand how to use them are complementary parts of my work. These experiences are why the combination of customer deployment, hands-on building, and ongoing enablement in this role interests me.

### カバーレター案

Dear Cognition Hiring Team,

I am applying for the Forward Deployed Engineer role in Japan. My experience combines enterprise AI implementation support, hands-on agent development, and teaching people how to work with AI development tools.

Since April 2025, I have worked on applied AI and AI agents at Mitsubishi UFJ Information Technology. Through MUIT, I contribute to deploying Salesforce Agentforce into MUFG Bank's internal CRM for relationship managers. I built a Databricks workflow to investigate agent inputs, outputs, and response quality using Genie Code, and have supported prompt tuning and context engineering, including company-information summaries. This work connects implementation details with the needs of the people using an agent.

Outside that work, I build Life Manager, an open-source local-agent system with persistent scheduling and verified external actions, and founded a weekly community teaching Claude Code, Codex, Cursor, and agent workflows. I would bring that combination of building, investigation, and practical enablement to helping customers adopt Devin.

I am based in Tokyo and have unrestricted authorization to work in Japan. I would welcome the opportunity to discuss the deployment work and learning approach I can contribute to Cognition.

Sincerely,
Daisuke Narita

提出前の残項目: 必須資格にあるSTEM学位の扱い、実フォームの変更、resumeの最新性を確認する。現時点の原稿を学位要件充足・応募済みの証明として扱わない。
