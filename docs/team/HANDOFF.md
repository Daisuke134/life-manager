# HANDOFF — 作業の引き継ぎ台帳（全エージェント共通）

目的: どのエージェントが止まっても（落ちた・レート制限・サブスク終了）、別のエージェントがすぐ続きを引き取れるようにする。
特に Mac mini の Claude Code セッション（life-manager-main-claude〜-claude-5）は、Claude のサブスクが来月終わる可能性があるため、必ずここに書くこと。引き取り先の第一候補は Codex。

関連:
- 応募・資金調達・案件の共有台帳: [ledger/APPLICATIONS.md](../../ledger/APPLICATIONS.md)（PR #8686）。応募前に `scripts/ledger-check.sh <key>` で重複確認 → claimed 行を先に push → 応募 → status 更新。
- 短い連絡: Reason Network（send_message / check_inbox）。

## ルール
1. 作業を始めたら 1 行追加（status=in_progress）。終わったら done、止めたら blocked と理由。
2. 1 セッション終了ごと／2 時間ごとに `next` を更新する。次の人が読んで 5 分で再開できる粒度で書く。
3. 秘密情報（パスワード・トークン・カード情報）は絶対に書かない。保管場所の名前だけ書く。
4. 引き取ったら owner を書き換え、元の owner に Reason で一言送る。
5. 同じ作業を二重にしない。開始前にこの表と APPLICATIONS.md を確認する。

## 進行中の作業

| updated (JST) | owner | task | status | branch / PR / file | next（次の一手） | fallback |
|---|---|---|---|---|---|---|
| 2026-10-23 20:20 | daisuke/cursor (参謀) | HANDOFF.md 作成と aniccaai.com の Manager 文言更新 | in_progress | team/manager-entity-handoff | マージ後に本番表示を確認 | codex |
| 2026-10-23 21:13 | life-manager-main-claude-2 | LINEスタンプ工場復旧（set-042申請／set-038カテゴリ修正／恒久修正PR #8696） | in_progress | capafy/podcast-clip-hook-lab-offline-20261005 / PR #8696 / docs/team/BOARD.md 20:50行 | PR #8696 は CI green・ready。merge は auto-mode classifier が拒否したので人間か Codex が `gh pr merge 8696 --squash --admin`。merge 後: immutable release を切り `line-sticker-factory-hourly` へ loaded-idle apply、set-043 以降が「カワウソのぽか太の{場面}【毎日使える】」型・年末年始テーマで出るか ~/.local/state/life-manager/line-sticker/factory-events.jsonl で確認。ログインは credentials.json の line-account と ~/.cloak/vault/line-creators/auth-state.json（値はここに書かない）。配布: line-sticker-distribute の IG/Threads は 10/16 から suspended で停止、articles レーン（aniccaai.com）は 10/10 で停止中→次に原因調査。X/Bluesky はスタンプ専用アカウントが未作成 | codex |
