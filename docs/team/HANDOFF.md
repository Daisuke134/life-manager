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
| 2026-10-24 02:25 | daisuke/life-manager-main-claude-3 | Mac mini disk 回復（参謀依頼） | done | worktree 16本返却（統合済み・clean・lease期限切れ） | 空き 9.4→11GiB。release は全30本が LaunchAgent/実行中から参照され正規GCで削除0。15GiB 未達の主因は swap 13–15GB（Codex/ChatGPT/daily-driver 常駐）。SSH は sshd 正常、接続先は tailscale aniccanomac-mini-1。アプリ終了はログアウト後に | codex |
| 2026-10-23 20:20 | daisuke/cursor (参謀) | HANDOFF.md 作成と aniccaai.com の Manager 文言更新 | in_progress | team/manager-entity-handoff | マージ後に本番表示を確認 | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Writer 記事公開の復旧（local_proxy env退役 #8586・見出し画像を finisher で生成 #8603・article-daily/resume fence #8621/#8645・judge を acct2 待機に #8646） | in_progress | main（全PR merged、release 20261023T162454-e6260790 以降に適用済み） | `tail ~/.local/state/life-manager/writer/articles.jsonl` に live_url が出るか確認。止まっていれば `lm-loop health --loop article-daily --explain` と `writer-claim-loop`（disk_floor_low だと topic 供給停止＝空き12GiB必要） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Coconala 応募の fence 復旧（#8581/#8591/#8679：scoped write-ahead 証明、claimed も live-owner 確認付きで閉じる） | in_progress | main（merged、release d41feb33 以降） | `~/gig/applied.jsonl` に新規 applied があるか。止まったら `lm-loop health --loop hf-gig-apply-direct --explain` → effect_unknown なら `skills/earn/gig/scripts/coconala_application_effect_reconcile.py --owner-id hf-gig-apply-direct` を release から実行（証明が揃う時だけ閉じる） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Lancers 交渉担当 account_unavailable の原因特定（#8620 で診断を出力） | blocked | `~/.local/state/anicca/lancers/logs/bounded/launchd-lancers-revenue-negotiate.err.log` | 理由: disk_floor_low で未実行。次の実行で `lancers_reply_account_diagnostic:` 行を読み、reason/http_status に応じて修正 | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Codex profile lease 競合（FND04）とディスク/swap | blocked | SSOT「FND04 実測」節（#8638）・#8579 | 理由: swap 11–12GB（ChatGPT内Codex・Codexアプリ・daily-driver）で空きが10GiB付近を上下。人間がアプリを閉じるかメモリ方針を決める必要 | codex |
| 2026-10-24 11:00 | life-manager-main-claude-2 | LINEスタンプ工場復旧（set-042/038 審査待ち、set-043 retitle 済み）＋ swap 逼迫 wake deferral ゲート | in_progress | PR #8696 merged（main 3e121984）/ docs/team/BOARD.md 20:50行 | ①release-reconciler の自動 apply で line-sticker-factory-hourly 等の label が #8696 入り release（20261023T230037 以降）を指すのを plist で確認。②readback-hourly の creators-item.json state_observed で set-042(48552798)/038(48283042)/043(48554244) の審査結果を監視し、承認/リジェクトを BOARD に1行。③リジェクトなら line_sticker_resubmit の cannot_fix 理由を読み、カテゴリ/タグなら console で直す（set-038 と同じ手順、scratch の fix038.py を写す）。ログインは credentials.json の line-account と ~/.cloak/vault/line-creators/auth-state.json（値は書かない）。終了時は必ずログアウトしてから閉じる。X/Bluesky 配布は専用口座なし→参謀の方針待ち | codex |
| 2026-10-23 22:39 | daisuke/anicca-project-codex | Dots の Reason Network 参加確認 | done | docs/dots-reason-participation-20261023 / docs/team/HANDOFF.md | `daisuke/chatgpt` を公式 `list_team` で確認済み。追加join・代理session作成は不要。詳細は下記「Dots の Reason Network 参加」 | daisuke/cursor |
| 2026-10-23 23:28 | daisuke/anicca-project-codex | 求人応募文5件の下書き（提出は参謀） | done | docs/job-application-drafts-five-20261023 / docs/team/specs/job-application-drafts.md | 原稿5件・公式質問63件・根拠照合を完了。PRのCI/統合状態を確認後、参謀が各原稿の未確認回答と提出可否を扱う。応募・ledger・Thankfulは未操作 | daisuke/cursor |

## Dots の Reason Network 参加

目的・範囲・完了条件: アカウント2の既存Dots本人をReason Networkで確認し、公式 `list_team` に本人セッションが表示されることを完了条件とする。既存接続が成立している場合は再登録しない。結果をこの台帳とReasonの `daisuke/cursor` へ共有する。

- 確認結果: Reason MCP `list_team` の「Daisukeのネットワーク」に `daisuke/chatgpt`、agent `chatgpt`、`personal agent (chatgpt), through Reason` が表示される。接続手順の正本 [Dots の RevenueCat 利用と音声通話](https://github.com/Daisuke134/ai-config/blob/main/specs/dots-revenuecat-voice.md) も、このセッションをDots本人の成功経路として示す。本人参加の完了条件を満たす。
- 今回の操作: 公式一覧と手順の読み取り、チーム文書の更新のみ。新規join、MCP設定変更、認証変更、Mac側の代理Dots、追加監視loopは作らない。idle表示は稼働中タスクや自動起動の証明にしない。
- 別件の未完: 正本に残る応募履歴の共有・応募台帳への反映は、この参加確認の完了と分ける。未着の分割や応募情報を補完せず、既送信分も再送しない。
- 所有境界: Thankful と build 10 は `life-manager-main-claude-5` の単独担当。Codexは変更・ビルドを行わない。保護されたmainへ直接pushせず、専用branch/PRで反映する。
- 次の一手: 参謀は既存の `daisuke/chatgpt` を連絡先として使う。追加のDots参加作業は不要。

## 2026-10-23 Mac mini disk/loop audit (参謀)
- lm_loop_run: ~89 processes, but each loop label appears exactly once (no self-respawn). Each launchd plist runs one label; long-running daemons stay pinned to the release they started from (some still on 20261018 releases). Not a duplication bug. Optional fix: release cut should kickstart -k long-running labels so old releases can be GCd.
- Stale cozempic.cli guard orphans (ppid 1, started 10/17-10/22) killed. premiere-pro-mcp/node_repl are children of the live codex app-server daemon (one per thread); left alone.
- Disk: 0.4G -> ~13G free (tmp clones, loop-tmp, simulators erased, caches, 6 clean stale worktrees, old cloak state-backups, gz old codex sessions). Remaining hogs: .worktrees ~11G (mostly dirty), .codex-acct2 sessions 7G, git packs, ollama 4.4G.
- Rule: log out of Mac apps before quitting; never force-quit LINE/ChatGPT.
