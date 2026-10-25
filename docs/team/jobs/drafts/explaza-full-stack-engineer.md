# エクスプラザ — 【正社員】フルスタックエンジニア 応募下書き

状態: 未提出。公式HERP応募ページの `__NEXT_DATA__` にある13入力と個人情報同意欄、計14項目（必須9・任意5）に対応する。給与条件とcloud・職務でのfull-stack経験に未確認部分がある候補として扱う。

- 求人: https://herp.careers/v1/explaza/4GzgM8DDKYId
- フォーム: https://herp.careers/v1/explaza/4GzgM8DDKYId/apply
- key: `job:herp.careers/v1/explaza/4gzgm8ddkyid`
- 確認範囲: 公式求人一覧・求人本文、応募HTMLの `company.careerPage.form.fields` の全項目・必須設定・入力制限・添付MIME型、同意欄と公式frontendの必須validation。終了表示はない。フォーム入力・応募API送信はしない。

## 求人要件と適合・不足

必須はcloud基盤（AWS/GCP/Azure等）の設計・構築、アプリケーションの実務full-stack開発、個人レベルでのLLM活用、運用監視・アラート対応、日本語native相当。固定年数・個別言語の職務経験は明記されていない。東京を拠点とするhybrid勤務で、募集年収は500〜800万円。

金融CRMでのAgentforce導入支援、品質分析・prompt/context支援、Life ManagerとAniccaの開発・運用が接点になる。ただし、cloud基盤を設計・構築した職務経験、職務としてのfull-stack開発、商用監視・アラート対応の担当範囲は現資料では未確認。個人開発をそのまま職務経験へ置換しない。募集上限800万円と私的正本の希望下限が一致する場合に限って給与面が重なり、希望額を引き下げたものとは扱わない。

## フォーム回答案

source keyは `form.fields[].id` の末尾 `-4GzgM8DDKYId` を省いた値。紹介欄は元のUUID、同意欄はHTMLの `name` を示す。

| # | source key | 質問・入力 | 必須 | 回答案・扱い | 根拠 |
|---|---|---|---|---|---|
| 1 | `name` | 名前（上限200文字） | 必須 | 私的正本 `candidate.name_ja` を参照する。依頼内表記との差を推測で埋めない。 | PROFILE |
| 2 | `email` | メールアドレス | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 3 | `currentCompany` | 現所属（上限255文字） | 必須 | `Mitsubishi UFJ Information Technology, Ltd.（MUIT）` | MUIT |
| 4 | `age` | 年齢 | 必須 | 私的正本 `candidate.date_of_birth` から提出時点の年齢を算出する。年齢値・生年月日はrepoへ載せない。 | PROFILE |
| 5 | `education` | 最終学歴（上限200文字） | 必須 | **表記確認が残る。** `education`・`education_naist` と既存resumeを参照し、最終在籍先と取得済み学位を分ける。NAIST修士研究は確認できるが、学位授与を確認せず「修士号取得」としない。 | RESEARCH・RESUME |
| 6 | `telephoneNumber` | 電話番号（上限20文字） | 任意 | 記入する場合は私的正本 `candidate.phone` と到達性・国番号を照合する。 | PROFILE |
| 7 | `career` | 経歴（上限10,000文字） | 任意 | 下記「経歴回答案」。個人開発・研究・職務を分けて記す。 | MUIT・LOGS・PROMPT・LM・ANICCA・RESEARCH |
| 8 | `links` | リンク（上限25,500文字） | 任意 | https://github.com/Daisuke134 、https://github.com/Daisuke134/life-manager 、https://www.linkedin.com/in/daisuke-narita 。 | PROFILE・LM |
| 9 | `messageToCompany` | 応募先へのメッセージ（上限1,000文字） | 必須 | 下記「応募メッセージ兼カバーレター案」。 | MUIT・LOGS・PROMPT・LM・TEACH |
| 10 | `resume` | 履歴書のアップロード | 必須 | **書類準備が残る。** 既存は私的な英語技術職用 `Daisuke_Narita_AI_Resume.pdf`。和文履歴書は今回未作成で、この欄を充足するとは断定しない。 | RESUME |
| 11 | `careerSummaries` | 職務経歴書のアップロード | 必須 | **別の必須欄。** 和文職務経歴書は今回未作成。英語PDFの兼用可否は未確認で、履歴書と同一の書類で満たせると断定しない。 | RESUME |
| 12 | `otherFile` | その他のファイル | 任意 | 現資料では添付なし。公開成果は質問8のリンクに記す。 | PROFILE・LM |
| 13 | `8a99895b-ebf5-4a61-9425-afb8052d1143` | 社員紹介がある場合、その社員の氏名（上限1,000文字） | 任意 | 空欄。紹介者を示す確認済みの資料がないため氏名を作らない。 | 未確認 |
| 14 | `privacyPolicy` | 応募にあたり個人情報の取り扱いに同意 | 必須 | 下書きでは未チェック。提出担当が下記ポリシーを確認し、同意する場合に選択する。 | 公式同意欄・必須validation |

同意先: https://explaza.jp/privacypolicy 。添付は複数可能、全ファイル合計50MBまで。schemaで許容する21 MIME型はPDF、DOCX、DOC、XLSX、JPEG、PNG、XLS、TXT、PPTX、GIF、XLSM、HEIC、ODS、PPT、Markdown、XLTX、XLSB、PPSX、TIFF、PPTM、XPS。zip・mp4は含まれない。

取得した13入力は全て表へ対応する。氏名よみがな、生年月日、年収、visa可否、就業開始日の独立設問はないので、別のHERP求人の項目を追加しない。

## 経歴回答案（`career` 用）

> 2025年4月からMUITでApplied AI・AIエージェント業務に従事し、MUFG Bankのrelationship manager向け内部CRMへのSalesforce Agentforce導入を支援しています。Databricksでagentの入出力・応答品質を分析するworkflowを構築し、会社情報summary等へのprompt tuning・context engineeringを支援しています。
>
> 個人開発では、永続スケジュールと検証付き外部操作を備えるopen-source agent system「Life Manager」を開発し、mobile affirmation app「Anicca」を構築・出荷しました。
>
> 研究では、2024年4月から2026年4月にNAISTでEEGとmachine learningを用いたmind-wandering研究に取り組み、同時期にATRでも研究・発表を行いました。学位授与は応募資料上未確認のため、取得済み学位として記載していません。

## 応募メッセージ兼カバーレター案（`messageToCompany` 用、1,000文字以内）

> 生成AIを活用したプロダクトのPoCから実装・運用へ取り組む仕事内容に関心を持ち、応募します。
>
> MUITでは2025年4月からApplied AI・AIエージェント業務に携わり、MUFG Bankのrelationship manager向け内部CRMへのSalesforce Agentforce導入を支援しています。Databricksでagentの入出力・応答品質を分析するworkflowを構築し、会社情報summaryなどへのprompt tuningとcontext engineeringを支援しています。
>
> 個人では、永続スケジュールと外部操作の結果確認を備えるopen-source agent system「Life Manager」を開発し、mobile affirmation app「Anicca」を構築・出荷しました。agentの運用では、永続state、自動check、評価gate、曖昧な外部作用を再試行する前の独立確認を重視しています。また、研究室・大学院でAI coding toolやagent workflowを教える週次communityを設立しました。
>
> 業務の目的・制約と利用者の反応を踏まえ、実装と評価を重ねる仕事に貢献したいと考えています。担当した範囲を具体的にご説明します。公開成果は https://github.com/Daisuke134/life-manager です。東京在住で、入社可能日は2026年12月1日です。
>
> Daisuke Narita

本文はMarkdownの引用記号を除き、段落間の改行を含め657文字。1,000文字の上限内である。

## 経歴根拠・未確認事項

共通ラベルは [既存タスクspecの経歴根拠](../../specs/job-application-drafts.md#経歴根拠) を参照する。MUIT=`muit_role_2025`・`muit_agent_crm`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、LM=`life_manager`・`life_manager_open_source_operations_20260805`、ANICCA=`anicca_consumer`、TEACH=`agent_club`、RELIABILITY=`async_operating_practices_20260805`・`agent_reliability_engineering_20260805`、RESEARCH=`naist`・`atr_research`・`education_naist`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`。SALARYは私的正本の `candidate.compensation_floor_jpy`・`candidate.desired_compensation_jpy`。連絡先・年齢等の私的値はPROFILEを参照する。

cloud設計・構築、職務でのfull-stack開発、商用監視・アラート対応の具体的な担当範囲、最終学歴の確定表記、2種類の必須添付書類が未確認・未準備。給与は募集上限と希望下限の接点しかなく、希望条件に合う採用条件があるとは断定しない。和文書類の生成・応募送信・同意選択は本原稿の作成範囲に含めない。
