# OpenAI — Applied AI Engineer, Codex / Tokyo 応募下書き

状態: 未提出。公式ATSから求人とフォーム12項目（必須10・任意2）を取得する。質問の要旨は掲載順。

- 求人: https://jobs.ashbyhq.com/openai/6668417f-6878-4244-940f-9a99ae4ebcb0
- フォーム: https://jobs.ashbyhq.com/openai/6668417f-6878-4244-940f-9a99ae4ebcb0/application
- 確認経路: 公式HTMLの求人データと `ApiJobPosting` 読み取り。`isListed=true`、Tokyo、FullTime。本文は週3日出社を示す。
- 求人要件の要旨: 顧客のソフトウェア開発でCodexを実装・評価・本番展開し、継続利用と開発成果につなぐ。Python・評価・企業環境での実装・日英のコミュニケーションを重視する。

## フォーム回答案

| # | 質問の要旨 | 必須 | 回答案・扱い | 事実根拠 |
|---|---|---|---|---|
| 1 | 政府発行IDと完全一致するLegal Name | 必須 | 候補 `Daisuke Narita`。IDの現物は確認していないため、提出担当が本人の正式表記と照合する。 | PROFILE |
| 2 | Preferred Name | 任意 | 空欄、または私的正本の希望名を本人が使う場合のみ入力する。 | PROFILE |
| 3 | メール | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 4 | Resume | 必須 | 既存の英語技術職用PDF。卒業学位・実務年数・役職を求人に合わせて増やさない。 | RESUME |
| 5 | 電話 | 必須 | 私的正本 `candidate.phone` から入力し、国番号と到達性を提出担当が確認する。 | PROFILE |
| 6 | 現在地 | 必須 | `Tokyo, Japan` | TOKYO |
| 7 | 入社可能日 | 必須 | `2026-12-01` | START |
| 8 | 求人の所在国で就労可能か | 必須 | `Yes`。日本国籍に基づく日本での就労権。 | JP |
| 9 | 現在/将来、日本で就労visa sponsorshipが必要か | 必須 | `No` | JP |
| 10 | 東京officeへ週3日出社できるか | 必須 | `Yes`。正本では週5日の出社も可能。 | TOKYO |
| 11 | Additional Information（志望動機など） | 任意 | 下記カバーレターの本文を使用する案。別の職務経歴や性能数値は足さない。 | MUIT・LOGS・PROMPT・LM・TEACH |
| 12 | 正確性・重要事項の不隠蔽・応募者本人による記入等の宣誓 | 必須 | **本人の確認事項。** 選択肢は `I confirm I have read the above.`。本人が宣誓本文と全回答を確認し、本人記入に関する文言を満たす場合だけ選択する。代理作成済みのため自動同意しない。 | 公式フォーム |

宣誓欄の説明は、現職など第三者に対して秘密保持義務のある情報を開示しないよう求める。社内データ・顧客情報・内部性能数値は本文へ持ち込まない。専用のカバーレター添付欄やGitHub欄は確認できないため、補足欄へ必要な公開リンクだけを入れる。

## カバーレター案（Additional Information用）

> Dear OpenAI Applied AI Engineering Team,
>
> I am applying for the Codex-focused role in Tokyo because I want to help engineering organizations turn AI coding tools into workflows they can evaluate, operate, and continue using.
>
> At Mitsubishi UFJ Information Technology, I contribute to Salesforce Agentforce deployments in MUFG Bank's internal CRM for relationship managers. My contributions include a Databricks workflow for inspecting agent inputs, outputs, and response quality, as well as prompt tuning and context engineering for company-information summaries. This is the enterprise deployment experience I would bring to discussions of workflow fit, observability, and the gap between a successful demonstration and useful operation.
>
> I also build Life Manager, an open-source local agent system with persistent scheduling and verified external actions. In my own agent workflows, I use scoped changes, automated checks, durable state, explicit handoffs, and independent confirmation before retrying ambiguous external actions. I founded a weekly community teaching Claude Code, Codex, Cursor, and agent workflows for research and daily work. These experiences connect my interest in reliable implementation with hands-on technical enablement.
>
> I would welcome a technical discussion of these systems and how their lessons could inform customer adoption of Codex. My public work is available at https://github.com/Daisuke134/life-manager. I am based in Tokyo, can work onsite three days per week, and am available to start on December 1, 2026 without Japanese visa sponsorship.
>
> Daisuke Narita

## 根拠・未確認事項

ラベルの定義と資料は [タスクspec](../../specs/job-application-drafts.md#経歴根拠) を参照する。実績はMUIT・LOGS・PROMPT・LM・RELIABILITY・TEACH、所在地/就労権/開始日はTOKYO・JP・START。

企業でのCodex全社導入、開発生産性の改善率、Pythonの職業経験年数、OpenAIとの勤務歴は未確認で、主張しない。日英fluencyを試験点数から自動認定せず、英語実績はLANGの記録にとどめる。NAISTの学位授与は未確認のため修士号取得済みとは書かない。本人の宣誓とID表記の照合は提出担当が扱う。
