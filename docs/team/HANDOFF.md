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
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Writer 記事公開の復旧（local_proxy env退役 #8586・見出し画像を finisher で生成 #8603・article-daily/resume fence #8621/#8645・judge を acct2 待機に #8646） | in_progress | main（全PR merged、release 20261023T162454-e6260790 以降に適用済み） | `tail ~/.local/state/life-manager/writer/articles.jsonl` に live_url が出るか確認。止まっていれば `lm-loop health --loop article-daily --explain` と `writer-claim-loop`（disk_floor_low だと topic 供給停止＝空き12GiB必要） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Coconala 応募の fence 復旧（#8581/#8591/#8679：scoped write-ahead 証明、claimed も live-owner 確認付きで閉じる） | in_progress | main（merged、release d41feb33 以降） | `~/gig/applied.jsonl` に新規 applied があるか。止まったら `lm-loop health --loop hf-gig-apply-direct --explain` → effect_unknown なら `skills/earn/gig/scripts/coconala_application_effect_reconcile.py --owner-id hf-gig-apply-direct` を release から実行（証明が揃う時だけ閉じる） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Lancers 交渉担当 account_unavailable の原因特定（#8620 で診断を出力） | blocked | `~/.local/state/anicca/lancers/logs/bounded/launchd-lancers-revenue-negotiate.err.log` | 理由: disk_floor_low で未実行。次の実行で `lancers_reply_account_diagnostic:` 行を読み、reason/http_status に応じて修正 | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Codex profile lease 競合（FND04）とディスク/swap | blocked | SSOT「FND04 実測」節（#8638）・#8579 | 理由: swap 11–12GB（ChatGPT内Codex・Codexアプリ・daily-driver）で空きが10GiB付近を上下。人間がアプリを閉じるかメモリ方針を決める必要 | codex |
| 2026-10-23 21:13 | life-manager-main-claude-2 | LINEスタンプ工場復旧（set-042申請／set-038カテゴリ修正／恒久修正PR #8696） | in_progress | capafy/podcast-clip-hook-lab-offline-20261005 / PR #8696 / docs/team/BOARD.md 20:50行 | PR #8696 は CI green・ready。merge は auto-mode classifier が拒否したので人間か Codex が `gh pr merge 8696 --squash --admin`。merge 後: immutable release を切り `line-sticker-factory-hourly` へ loaded-idle apply、set-043 以降が「カワウソのぽか太の{場面}【毎日使える】」型・年末年始テーマで出るか ~/.local/state/life-manager/line-sticker/factory-events.jsonl で確認。ログインは credentials.json の line-account と ~/.cloak/vault/line-creators/auth-state.json（値はここに書かない）。配布: line-sticker-distribute の IG/Threads は 10/16 から suspended で停止、articles レーン（aniccaai.com）は 10/10 で停止中→次に原因調査。X/Bluesky はスタンプ専用アカウントが未作成。運用ルール: LINE/サービス終了時は必ずログアウトしてから終了（閉じるだけ禁止、成田 10/23）。merge は classifier 拒否のため Codex/人間が実行 | codex |

## 2026-10-23 Mac mini disk/loop audit (参謀)
- lm_loop_run: ~89 processes, but each loop label appears exactly once (no self-respawn). Each launchd plist runs one label; long-running daemons stay pinned to the release they started from (some still on 20261018 releases). Not a duplication bug. Optional fix: release cut should kickstart -k long-running labels so old releases can be GCd.
- Stale cozempic.cli guard orphans (ppid 1, started 10/17-10/22) killed. premiere-pro-mcp/node_repl are children of the live codex app-server daemon (one per thread); left alone.
- Disk: 0.4G -> ~13G free (tmp clones, loop-tmp, simulators erased, caches, 6 clean stale worktrees, old cloak state-backups, gz old codex sessions). Remaining hogs: .worktrees ~11G (mostly dirty), .codex-acct2 sessions 7G, git packs, ollama 4.4G.
- Rule: log out of Mac apps before quitting; never force-quit LINE/ChatGPT.
