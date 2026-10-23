# Cursor — Forward Deployed Engineer, Japan 応募下書き

状態: 未提出。公式ATSから求人とフォーム8項目（必須3・任意5）を取得する。質問欄は原文の要旨を日本語で示し、順序は公式フォームに合わせる。

- 求人: https://jobs.ashbyhq.com/cursor/38bd03a3-3d65-4868-87df-cb248d0a45e3
- フォーム: https://jobs.ashbyhq.com/cursor/38bd03a3-3d65-4868-87df-cb248d0a45e3/application
- 確認経路: 公式 `ApiJobPosting` 読み取り。`isListed=true`、Japan、Remote、FullTime。通常HTMLの本文が空でも、求人終了とは判定しない。
- **提出前の確認点:** URLとフォームはCursor/Graphiteを示す一方、取得した求人本文はSpaceX・SpaceXSI・SpaceXAI・Grokに言及する。雇用主体と求人本文の整合は未確認。別求人へ差し替えず、参謀が公式画面で照合する。
- 求人要件の要旨: 顧客に入り込み、agent・開発workflowを本番まで構築し、評価・運用・成果測定を担う。ソフトウェア/ML/data scienceで5年以上を求めるが、既存経歴から5年以上の該当実務は裏付けない。

## フォーム回答案

| # | 質問の要旨 | 必須 | 回答案・扱い | 事実根拠 |
|---|---|---|---|---|
| 1 | 氏名 | 必須 | `Daisuke Narita`。提出担当が本人の正式表記と照合する。 | PROFILE |
| 2 | メール | 必須 | 私的正本 `candidate.application_email` から入力。値はrepoへ記載しない。 | PROFILE |
| 3 | Resume | 任意 | 既存の英語技術職用PDFを添付する案。新たな経歴・学位を足さない。 | RESUME |
| 4 | LinkedIn | 任意 | https://www.linkedin.com/in/daisuke-narita | PROFILE |
| 5 | GitHub | 任意 | https://github.com/Daisuke134 | PROFILE |
| 6 | 技術者に新しいsolution/toolを採用してもらった例。抵抗と対処は何か | 任意 | **現資料では空欄を推奨。** 下記の事実ベース素材は使えるが、具体的な抵抗・対処・採用結果が未確認なので完成したSTAR事例として送らない。 | TEACH |
| 7 | 現在または将来、日本で働くためのvisa sponsorshipが必要か | 必須 | `No`。日本国籍による日本国内の就労権を根拠とする。 | JP |
| 8 | Cursor/Graphiteの紹介者がいる場合、そのメール | 任意 | 空欄。紹介者の存在を示す資料はなく、メールを作らない。 | 未確認 |

### 質問6の素材（完成回答ではない）

> I founded a weekly community in my lab and graduate-school environment to teach Claude Code, Codex, Cursor, and AI-agent workflows for research and everyday work. This is a concrete example of helping a technical audience understand new tools. I can explain the community and the material I taught; the specific initial objection, my response, and the resulting adoption need to be supplied from an accurately recalled episode before using this as an answer to the full question.

抵抗・懸念・説得の方法・参加人数・導入率・時間短縮を補完しない。任意項目なので、未確認の物語を提出する必要はない。

## カバーレター案（補足原稿）

専用のカバーレター欄は確認できない。フォームに存在する欄として扱わない。雇用主体の照合後に使う応募動機の原稿である。

> Dear Hiring Team,
>
> I am applying for the Forward Deployed Engineer role in Japan because I want to help engineering teams turn AI tools into dependable working systems.
>
> At Mitsubishi UFJ Information Technology, I contribute to the deployment of Salesforce Agentforce agents in MUFG Bank's internal CRM for relationship managers. My documented contributions include building a Databricks workflow to inspect agent inputs, outputs, and response quality, and supporting prompt tuning and context engineering for company-information summaries. This experience gives me a practical perspective on the work between a model's response and a system that people use in an enterprise workflow.
>
> Alongside this work, I build Life Manager, an open-source local agent system with persistent scheduling and verified external actions. I also founded a weekly community teaching Claude Code, Codex, Cursor, and agent workflows in a research environment. These experiences are the basis for my interest in combining hands-on implementation with clear technical communication.
>
> I would bring this experience to customer discovery, implementation, evaluation, and operational handover, while being precise about my own contributions and the evidence for results. I am based in Tokyo, have unrestricted work authorization in Japan, and am available to start on December 1, 2026.
>
> Daisuke Narita

## 根拠・未確認事項

根拠ラベルの定義と私的資料の保存先は [タスクspec](../../specs/job-application-drafts.md#経歴根拠) を参照する。上記原稿の実績はMUIT・LOGS・PROMPT・LM・TEACH、所在地/就労権/開始日はTOKYO・JP・STARTに対応する。

5年以上の経験、Cursorでの勤務、顧客へのCursor導入実績、具体的な説得成功・採用指標は主張しない。公開フォームにはカバーレター欄・希望年収欄は確認できない。求人本文のブランド混在は未解消。応募の重複確認と提出は参謀の担当とする。
