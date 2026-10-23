# LayerX — 【バクラク】AI Builder 応募下書き

状態: 未提出。公式応募フォームの表示設定12グループと同意欄を取得する。SNS内の4入力は1グループとして数え、必須8・任意5グループに対応する。応募状態は台帳を正本とし、この原稿から応募・status更新を行わない。

- 求人: https://open.talentio.com/r/1/c/layerx/pages/122552
- フォーム: https://open.talentio.com/r/1/c/layerx/pages/122552/apply
- key: `job:open.talentio.com/r/1/c/layerx/pages/122552`
- 確認範囲: 公式募集一覧・求人本文・応募ページの `CandidateForm/index` の公開 `data-react-props`。`form` の表示・必須設定、選択肢、`showAgreement=true`、添付UIを取得する。求人に応募導線があり、終了表示はない。

## 求人要件と適合・不足

AIエージェントを日常的に活用して業務・生産性を大きく変えた経験、コードを読み書き・レビューできる基礎、経済合理性や成果を基準とした判断、不確実な状況での実行と学習、主体性を求める。固定の実務年数・言語・学位指定はない。東京勤務またはリモートが対象で、給与は会社規定による。

MUITでのAgentforce導入支援、Databricksによる応答品質分析、prompt/context支援、Life Managerのagent運用、週次のAIツール指導が接点になる。業務の大部分をAIへ置換した割合、生産性の改善率、顧客企業の成果数値は資料にないため補わない。「劇的な変化」の具体的な前後比較は未確認であり、応募文では確認できる開発・運用内容を説明する。

## フォーム回答案

source keyは公開 `form` のキー。同意欄は別の公開設定pathを記す。

| # | source key | 質問・入力 | 必須 | 回答案・扱い | 根拠 |
|---|---|---|---|---|---|
| 1 | `candidateName` | 氏名。ビジネスネームと本名が異なる場合の注記あり | 必須 | 日本語の値は私的正本 `candidate.name_ja` を参照する。依頼内表記との差を解消せず転記しない。 | PROFILE |
| 2 | `nameEn` | 名前（ローマ字）。ヘボン式、名姓順 | 必須 | `Daisuke Narita`。分割入力では `candidate.name_romaji_parts` と照合する。 | PROFILE |
| 3 | `email` | メールアドレス | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 4 | `phone` | 電話番号 | 必須 | 私的正本 `candidate.phone` と到達性・国番号を提出担当が照合する。 | PROFILE |
| 5 | `resume` | 添付資料 | 必須 | 既存の私的英語技術職用 `Daisuke_Narita_AI_Resume.pdf` が添付候補。和文履歴書・職務経歴書は今回未作成で、英語PDFの受理可否は未確認。 | RESUME |
| 6 | `media` | Facebook、X、Wantedly、LinkedIn | 任意 | LinkedInは https://www.linkedin.com/in/daisuke-narita 。他3件は確認済みURLがないため空欄。 | PROFILE |
| 7 | `site` | その他リンク。形式不問、複数歓迎 | 任意 | https://github.com/Daisuke134 と https://github.com/Daisuke134/life-manager 。 | PROFILE・LM |
| 8 | `etc` | 応募の背景。LayerXを知ったきっかけ・エントリー背景 | 必須 | 下記「応募背景兼カバーレター案」。今回の公式求人調査と、確認済みの経験・応募動機を記す。以前からの認知を作らない。 | 公式求人・MUIT・LOGS・PROMPT・LM・TEACH |
| 9 | `etc2` | 気になること・質問 | 任意 | `AI Builderが現場実装から継続運用へ移る際、成果・品質・費用をどのように評価し、事業側と開発側で責任を分担しているかを伺いたいです。` 質問の提案であり、未確認の社内事情を断定しない。 | 求人の業務内容 |
| 10 | `additional` | 選考上の確認事項。開始希望時期、面接時間の配慮、稼働・働き方等 | 任意 | `入社可能日は2026年12月1日です。東京在住で、職務に応じたオフィス勤務に対応できます。` 面接配慮・時短希望等は資料にないため追加しない。 | START・TOKYO |
| 11 | `additional2` | 応募を後押しした情報・メディア（複数回答可） | 必須 | **選択未確定。** 下記11択から実際の接点に対応するものを提出担当が選ぶ。今回の求人調査だけを根拠に、本人がSNS・note・動画を見たことにせず、「該当なし」も自動選択しない。 | 公式選択肢・本人接点未確認 |
| 12 | `additional3` | 特に参考になったコンテンツ・イベントのタイトル・URL | 任意 | 現資料では空欄。本人にとって参考になったと確認できるものだけ記入する。 | 未確認 |
| 13 | `showAgreement` / `agreement` | 同意事項 | 必須 | 下書きでは未チェック。提出担当が下記の採用プライバシーポリシーを確認し、同意する場合に選択する。 | 公式同意欄 |

質問11の全選択肢: LayerX社員の発信（SNS、noteなど）／公式YouTube／公式note／公式SNS（X、LinkedInなど）／公式PodCast（LayerX NOW!）／LayerXエンジニアブログ／LayerX主催イベント（勉強会/Meetup、Casual Nightなど）／LayerX社員が登壇・協賛しているイベント・カンファレンス／外部メディアの記事・動画など／プレスリリース／該当なし。

同意事項は「LayerXが定める採用プライバシーポリシー」: https://layerx.notion.site/e664016aaa4a46fabff2c231e875cd03 。添付UIは最大100MBを示す。添付の注記に「資料がある場合」とある一方、公開schemaの `resume.required=true` を優先して必須と記録する。許容拡張子の厳密な一覧は今回のschemaにはない。

非表示の `nameKana`、`gender`、`birthday`、`address`、`experience`、`education`、`language`、`license`、`additional4`〜`additional20` を応募項目として追加しない。

## 応募背景兼カバーレター案（`etc` 用）

> 今回の求人調査で公式採用ページのAI Builder募集を確認し、課題の発見からプロトタイプ、現場実装、継続改善までを担う仕事内容に、私の企業内AI導入と個人開発の経験がつながると考え、応募します。
>
> MUITでは2025年4月からApplied AI・AIエージェントの業務に携わり、MUFG Bankのrelationship manager向け内部CRMへのSalesforce Agentforce導入を支援しています。具体的には、Databricksでagentの入出力や応答品質を分析するworkflowを構築し、会社情報の要約などに対するprompt tuningとcontext engineeringを支援してきました。
>
> 個人では、永続的なスケジュールと外部操作の結果確認を備えるopen-source agent system「Life Manager」を開発しています。小さく範囲を定めた変更、自動check、永続state、曖昧な外部作用を再試行する前の独立確認を重視しています。また、研究室・大学院の環境でClaude Code、Codex、Cursorやagent workflowを教える週次communityを設立しました。
>
> これらの経験をもとに、業務の目的と制約を理解し、品質・費用・運用の観点から確かめながら、現場が継続して利用できるAIの実装に取り組みたいと考えています。公開成果は https://github.com/Daisuke134/life-manager でご覧いただけます。
>
> Daisuke Narita

## 経歴根拠・未確認事項

共通ラベルは [既存タスクspecの経歴根拠](../../specs/job-application-drafts.md#経歴根拠) を参照する。MUIT=`muit_role_2025`・`muit_agent_crm`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、TEACH=`agent_club`、LM=`life_manager`・`life_manager_open_source_operations_20260805`、RELIABILITY=`async_operating_practices_20260805`・`agent_reliability_engineering_20260805`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`・`availability_tokyo_office_three_days_20260806`。連絡先・氏名の私的値はPROFILEを参照する。

未確認はAI活用による生産性変化の具体例、本人の認知メディア、添付書類の日本語要件。和文書類の作成・応募送信・同意の選択は本原稿の作成範囲に含まない。提出担当は台帳の重複防止手順に従う。
