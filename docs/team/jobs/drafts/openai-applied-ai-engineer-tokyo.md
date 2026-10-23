# OpenAI — Applied AI Engineer / Tokyo 応募下書き

状態: 未提出。公式ATSから求人とフォーム10項目（必須9・任意1）を取得する。Codex職のフォームと混同せず、質問の要旨を掲載順に示す。

- 求人: https://jobs.ashbyhq.com/Openai/4762783e-61e1-4d36-af1d-8dee3c5f70e2
- フォーム: https://jobs.ashbyhq.com/Openai/4762783e-61e1-4d36-af1d-8dee3c5f70e2/application
- 確認経路: 公式HTMLと `ApiJobPosting` 読み取り。`isListed=true`、Tokyo、Hybrid、FullTime。本文は週3日出社を示す。
- 求人要件の要旨: 企業のユースケース選定から実装・評価・本番展開までを担当する。顧客の既存システム、運用、セキュリティ等の要求に向き合う職務である。

## フォーム回答案

| # | 質問の要旨 | 必須 | 回答案・扱い | 事実根拠 |
|---|---|---|---|---|
| 1 | 氏名 | 必須 | `Daisuke Narita`。正式表記は提出担当が本人と照合する。 | PROFILE |
| 2 | メール | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 3 | Resume | 必須 | 既存の英語技術職用PDFを使う。 | RESUME |
| 4 | 電話 | 必須 | 私的正本 `candidate.phone` から入力する。国番号・現在の到達性は提出担当が確認する。 | PROFILE |
| 5 | 現在地 | 必須 | `Tokyo, Japan` | TOKYO |
| 6 | 入社可能日 | 必須 | `2026-12-01` | START |
| 7 | 現在/将来、日本で就労visa sponsorshipが必要か | 必須 | `No`。日本国籍による日本国内の就労権を根拠とする。 | JP |
| 8 | 東京officeへ週3日出社できるか | 必須 | `Yes`。週5日出社も可能という記録がある。 | TOKYO |
| 9 | Additional Information（応募動機など） | 任意 | 下記カバーレター本文を使用する案。 | MUIT・LOGS・PROMPT・LM・ANICCA・RESEARCH |
| 10 | 正確性・重要事項の不隠蔽・応募者本人による記入等の宣誓 | 必須 | **本人の確認事項。** 選択肢は `I confirm I have read the above.`。宣誓本文と全回答を本人が確認し、本人記入の文言を満たす場合だけ選択する。代理作成を本人記入済みと扱わない。 | 公式フォーム |

取得したフォームには、独立した就労可能可否の設問、preferred name、カバーレター専用添付欄はない。Codex職の追加設問を作らない。宣誓欄の説明に従い、現職など第三者の秘密情報は記載しない。

## カバーレター案（Additional Information用）

> Dear OpenAI Applied AI Engineering Team,
>
> I am applying for the Applied AI Engineer role in Tokyo because I want to help organizations move from AI prototypes to systems that fit real workflows and can be operated reliably.
>
> At Mitsubishi UFJ Information Technology, I contribute to the deployment of Salesforce Agentforce agents in MUFG Bank's internal CRM for relationship managers. I built a Databricks workflow to analyze agent inputs, outputs, and response quality, and supported prompt tuning and context engineering for company-information summaries. This work gives me a concrete foundation for discussing enterprise integration, observing model behavior, and improving responses in the context of an existing business process.
>
> I also build Life Manager, an open-source local agent system with persistent scheduling and verified external actions, and built and shipped Anicca, a mobile affirmation app. My graduate research at NAIST and concurrent work at ATR applied EEG and machine learning to mind-wandering detection. These are distinct experiences in enterprise agents, products, and research; I would be glad to explain my specific contribution to each.
>
> I am particularly interested in bringing this background to hands-on implementation and evaluation with customer engineering teams, and in turning deployment lessons into reusable technical guidance. My public work is available at https://github.com/Daisuke134/life-manager. I am based in Tokyo, can meet the three-day onsite requirement, and am available from December 1, 2026 with unrestricted work authorization in Japan.
>
> Daisuke Narita

## 根拠・未確認事項

資料とラベルは [タスクspec](../../specs/job-application-drafts.md#経歴根拠) を参照する。実績はMUIT・LOGS・PROMPT・LM・ANICCA・RESEARCH、所在地/就労権/開始日はTOKYO・JP・START。

全社AI導入を単独で主導した実績、RAG/セキュリティ設計の責任者経験、性能改善率、修士号授与、特定言語の職業経験年数は資料から追加しない。英語はLANGの既存試験実績として扱い、fluencyを自動認定しない。宣誓への本人同意と応募重複確認は提出担当の作業である。
