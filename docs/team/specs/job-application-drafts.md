# 求人応募文5件の下書き

目的: 参謀が公式フォームへ提出できる、求人別の回答案とカバーレターを5件作成する。

範囲: 公式求人本文とフォームを読み、既存の経歴・私的プロフィール・取得できたDots資料だけを事実根拠に使う。原稿は `docs/team/jobs/drafts/<company-role>.md` に保存する。公開repoへ連絡先・住所・生年月日・資格情報を複製せず、提出担当が私的正本から入力する。経歴や回答の不明点は明記する。応募送信・ledger・Thankful/build 10・他担当の作業領域は変更しない。

完了条件: 各求人の確認状態、実際の質問と必須/任意、回答案、根拠、未確認事項、カバーレターを5ファイルへ保存する。専用branch/PRをmainへ統合し、公式readback後にReasonで `daisuke/cursor` へPR URLを送る。閉鎖・取得不能の求人では、その状態と未取得の質問を明示し、架空のフォームを実在扱いしない。

## 対象と現在cursor

1. Cursor FDE Japan — 公式求人・質問を調査中: https://jobs.ashbyhq.com/cursor/38bd03a3-3d65-4868-87df-cb248d0a45e3
2. NICE Sr FDE Japan — 公式求人・質問を調査中: https://boards.eu.greenhouse.io/nice/jobs/4981245101
3. OpenAI Applied AI Engineer, Codex Tokyo — 公式求人・質問を調査中: https://jobs.ashbyhq.com/openai/6668417f-6878-4244-940f-9a99ae4ebcb0
4. OpenAI Applied AI Engineer Tokyo — 公式求人・質問を調査中: https://jobs.ashbyhq.com/Openai/4762783e-61e1-4d36-af1d-8dee3c5f70e2
5. BJAK Applied AI Engineer Tokyo — 公式求人・質問を調査中: https://jobs.ashbyhq.com/bjakcareer/bdaca888-9ed5-402f-bd73-48ae269da06e

現在cursor: 公式質問の抽出と経歴根拠の照合。`docs/team/dots/` は取得したmainに存在せず、参謀へ所在を照会する。既存の私的プロフィールと英語技術職用resumeを確認する。

検証: 質問一覧との対応、事実の出典、未確認事項の明示、連絡先/secret非掲載、変更path、diffチェック、公式CI、main上の5ファイルを確認する。アプリのビルド・追加テスト・応募提出は行わない。
