# AGENTS.md — Codex / 全エージェント向け手順
1. 開始時: `git pull`。docs/team/README → RULES → OWNERSHIP → BOARD → 関連 specs/ を読む。
2. BOARD.md の「タスク」に `[自分の名前]` で claim してから作業。
3. 担当外（OWNERSHIP.md）の領域は変更せず、BOARD.md に依頼を書く。
4. 終了時: BOARD.md「ログ」に1行追記、必要なら specs/ を更新 → commit → `git push`。競合したら `git pull --rebase` して再push。
5. 秘密情報は書かない。資格情報は各マシンのローカル（/workspace/.secrets など）をファイル名で参照。
6. 成田さんへは日本語。承認を求めない。無料トライアルは作らない。X投稿は加重≤270。
場所: GitHub Daisuke134/life-manager `docs/team/`（Mac mini は ~/team/BOARD.md がここを指す）。
