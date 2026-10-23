# Algomatic — AIエンジニア 応募下書き

状態: 未提出。公式HERP応募ページの公開 `herp-react-props` から表示設定・必須設定・ラベルを取得する。表示11入力と個人情報同意欄の計12項目（必須7・任意5）を扱う。既存履歴のAI Builder（組織変革本部）とは別の求人であり、その応募実績を本求人へ移さない。

- 求人: https://herp.careers/v1/algomatic/3b_GpdNQjy8N
- フォーム: https://herp.careers/v1/algomatic/3b_GpdNQjy8N/apply
- key: `job:herp.careers/v1/algomatic/3b_gpdnqjy8n`
- 確認範囲: 公式求人一覧・求人本文と `applyForm`、公開i18n、`showYomiganaAndDOBFields=true`。求人データは `published=true`・`status=published`。応募API・認証・送信は使わない。

## 求人要件と適合・不足

プログラミングによる実装経験に加え、LLM・生成AI機能の開発、LLMの研究・モデル選定・精度評価、深層学習モデルの開発・研究のいずれかを求める。実務・研究・個人開発のいずれも対象で、固定の年数・学位要件はない。東京勤務またはリモート、正社員、年収目安600〜1200万円。

Agentforce導入支援と応答品質分析、prompt/context支援、Life Managerのagent開発が、LLMを業務へ接続して評価・改善する仕事との接点になる。NAIST/ATRのEEG・machine learning研究も背景として使えるが、資料にない深層学習手法、RAG実装、職務でのPython/TypeScript利用、AWS/GCP運用を経験済みと補わない。求人の開発環境一覧を本人の経験へ転載しない。

## フォーム回答案

source keyは `applyForm` の設定名。固定入力と同意は公開i18nの参照pathを添える。`mandatory` は必須、`visible` は任意、`invisible` は除外として扱う。

| # | source key / 設定path | 質問・入力 | 必須 | 回答案・扱い | 根拠 |
|---|---|---|---|---|---|
| 1 | `i18n.name` / `validations.nameIsRequired` | 名前 | 必須 | 私的正本 `candidate.name_ja` から入力する。依頼内表記との差を推測で埋めない。 | PROFILE |
| 2 | `namePronunciation` | 名前よみがな | 必須 | 私的正本 `candidate.name_kana` を参照する。値はrepoへ載せない。 | PROFILE |
| 3 | `i18n.email` / `validations.emailIsRequired` | メールアドレス | 必須 | 私的正本 `candidate.application_email` から入力する。 | PROFILE |
| 4 | `currentCompany` | 現所属 | 任意 | `Mitsubishi UFJ Information Technology, Ltd.（MUIT）` | MUIT |
| 5 | `dateOfBirth` | 生年月日 | 任意 | 私的正本 `candidate.date_of_birth` 参照。値は非掲載とし、この任意欄への記入は提出担当が判断する。 | PROFILE |
| 6 | `telephoneNumber` | 電話番号 | 必須 | 私的正本 `candidate.phone` と到達性・国番号を提出担当が照合する。 | PROFILE |
| 7 | `links` | リンク | 任意 | https://github.com/Daisuke134 、https://github.com/Daisuke134/life-manager 、https://www.linkedin.com/in/daisuke-narita 。 | PROFILE・LM |
| 8 | `messageToCompany` | 応募先へのメッセージ | 任意 | 下記カバーレター案を使用する。 | MUIT・LOGS・PROMPT・LM・RESEARCH・TEACH |
| 9 | `resume` | 履歴書のアップロード | 必須 | **書類準備が残る。** 既存は私的な英語技術職用 `Daisuke_Narita_AI_Resume.pdf`。和文履歴書は今回未作成で、この欄を充足するとは断定しない。 | RESUME |
| 10 | `careerSummaries` | 職務経歴書のアップロード | 必須 | **別の必須欄。** 和文職務経歴書は今回未作成。英語PDFと履歴書の兼用可否は未確認で、同じPDFを自動的に両欄へ割り当てない。 | RESUME |
| 11 | `otherFile` | その他のファイル | 任意 | 現資料では添付なし。公開成果のリンクは質問7に記載する。 | PROFILE・LM |
| 12 | `i18n.privacyPolicyLabel` / `validations.agreeToPrivacyPolicyIsRequired` | 応募にあたり個人情報の取り扱いに同意 | 必須 | 下書きでは未チェック。提出担当が下記ポリシーを確認し、同意する場合に選択する。 | 公式同意欄 |

同意先: https://algomatic.jp/policy 。ファイルは全添付合計50MBまで。zip・mp4等はアップロード不可で、詳細な形式一覧は公式フォームのHERPヘルプリンクを参照する。追加の選択式screening質問は取得した設定にない。

`age`、`education`、`career`、`currentAnnualSalary`、`minDesiredSalary`、`desiredSalary`、`additionalRequirements` は非表示なので、年齢・最終学歴・経歴テキスト・年収等の設問を追加しない。HERPアカウントのログイン導線は応募質問として数えない。

## カバーレター案（`messageToCompany` 用）

> AIを顧客の業務へ接続し、実装から評価・継続改善まで担う仕事内容に関心を持ち、AIエンジニア職へ応募します。実務・研究・個人開発を対象にしている募集方針を拝見し、私の複数の経験を具体的にお伝えしたいと考えました。
>
> MUITでは2025年4月からApplied AI・AIエージェントの業務に携わり、MUFG Bankのrelationship manager向け内部CRMへのSalesforce Agentforce導入を支援しています。Databricksでagentの入出力や応答品質を分析するworkflowを構築し、会社情報summaryなどへのprompt tuningとcontext engineeringを支援しています。
>
> 個人では、永続スケジュールと外部操作の検証を備えるopen-source agent system「Life Manager」を開発し、mobile affirmation app「Anicca」を構築・出荷しました。また、NAISTとATRではEEGとmachine learningを用いるmind-wandering研究を行い、研究室・大学院の環境でAI coding toolやagent workflowを教える週次communityを設立しています。
>
> 業務の目的と制約、AIに任せる範囲、品質を確認する方法を整理し、利用者にとって役立つ仕組みへつなぐ仕事に取り組みたいと考えています。個々の経験で担当した範囲と、どのように結果を確かめたかを具体的にご説明します。公開成果は https://github.com/Daisuke134/life-manager です。東京在住で、入社可能日は2026年12月1日です。
>
> Daisuke Narita

## 経歴根拠・未確認事項

共通ラベルは [既存タスクspecの経歴根拠](../../specs/job-application-drafts.md#経歴根拠) を参照する。MUIT=`muit_role_2025`・`muit_agent_crm`、LOGS=`muit_genie_logs`、PROMPT=`muit_rm_summary`、LM=`life_manager`・`life_manager_open_source_operations_20260805`、ANICCA=`anicca_consumer`、RESEARCH=`naist`・`atr_research`・`education_naist`、TEACH=`agent_club`、START=`availability_start_date_20261201`、TOKYO=`candidate.base`。連絡先・氏名等の私的値はPROFILEを参照する。

NAISTの学位授与、職務で使用した個別言語、RAGやcloudの担当範囲は未確認。英語PDFは存在するが、和文の履歴書・職務経歴書は今回生成しない。2つの必須添付欄の書類準備と受理形式の確認は提出担当が扱う。既存AI Builderへの応募を再送しない。
