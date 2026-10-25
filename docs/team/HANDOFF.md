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
| 2026-10-24 14:2x | daisuke/life-manager-main-claude | Capafy 10K MRR: 収益ループ復旧と配信の改善（reconcile #8690・factory #8695・swap関門 #8823・改善ledger #8724、台帳 #8839）と dangling plist(capafy-* 11件+warmup-flip-daily は bc733571 へ apply 済み) | in_progress | 各PRはmerged / release bc733571 / ~/.local/state/life-manager/state/capafy-hourly-reconcile.json | (1) @hooklab.capafy が warmup のまま: swap が横ばい(15分で+500MB未満)かつ capacity_busy が解けたら .worktrees の最新main から `bin/lm-loop start warmup-flip-daily` を1回だけ。live になったら TikTok 最初の投稿と ct リンクを確認 (2) 旧 factory fence 94757 は adapter が exit 0 親 terminal を要求するため証明不能(#8695 で再発防止済み)。持ち主判断で fence 解除の証明クラスを足すか、時間待ち (3) capafy-outcome-monitor / capafy-ig-account-manager は履歴なしの古い fence。adapter 無しで証明不能 (4) 枠5/5(孤立draft3+rejected1+審査中1)が解けたら出荷順=スポーツ分析系(Football/NBA/NFL/MLB)→Crypto&Macro→他 (5) lm-loop は必ず最新mainのworktreeから実行(古いチェックアウトは検証コードが古く誤拒否) | claude-6(swap判定をSwapins速度へ改善中) |
| 2026-10-24 04:3x | daisuke/life-manager-main-claude-3 | For Better Sleep 課金画面改修→審査提出（参謀依頼） | WAITING_FOR_REVIEW | Daisuke134/rork-lazy-app-profit-blueprint PR #1 / 1.0.2 (9) / reviewSubmission 94b75a77… | 未実施: Sandbox で購入〜復元と4イベント記録の実機確認。審査で IAP が落ちたら最優先で直す | Config.swift は ~/.secrets-lm/revenuecat-sleepreset-ios-sdk から生成（コミット禁止） |
| 2026-10-24 02:25 | daisuke/life-manager-main-claude-3 | Mac mini disk 回復（参謀依頼） | done | worktree 16本返却（統合済み・clean・lease期限切れ） | 空き 9.4→11GiB。release は全30本が LaunchAgent/実行中から参照され正規GCで削除0。15GiB 未達の主因は swap 13–15GB（Codex/ChatGPT/daily-driver 常駐）。SSH は sshd 正常、接続先は tailscale aniccanomac-mini-1。アプリ終了はログアウト後に | codex |
| 2026-10-23 20:20 | daisuke/cursor (参謀) | HANDOFF.md 作成と aniccaai.com の Manager 文言更新 | in_progress | team/manager-entity-handoff | マージ後に本番表示を確認 | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Writer 記事公開の復旧（local_proxy env退役 #8586・見出し画像を finisher で生成 #8603・article-daily/resume fence #8621/#8645・judge を acct2 待機に #8646） | in_progress | main（全PR merged、release 20261023T162454-e6260790 以降に適用済み） | `tail ~/.local/state/life-manager/writer/articles.jsonl` に live_url が出るか確認。止まっていれば `lm-loop health --loop article-daily --explain` と `writer-claim-loop`（disk_floor_low だと topic 供給停止＝空き12GiB必要） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Coconala 応募の fence 復旧（#8581/#8591/#8679：scoped write-ahead 証明、claimed も live-owner 確認付きで閉じる） | in_progress | main（merged、release d41feb33 以降） | `~/gig/applied.jsonl` に新規 applied があるか。止まったら `lm-loop health --loop hf-gig-apply-direct --explain` → effect_unknown なら `skills/earn/gig/scripts/coconala_application_effect_reconcile.py --owner-id hf-gig-apply-direct` を release から実行（証明が揃う時だけ閉じる） | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Lancers 交渉担当 account_unavailable の原因特定（#8620 で診断を出力） | blocked | `~/.local/state/anicca/lancers/logs/bounded/launchd-lancers-revenue-negotiate.err.log` | 理由: disk_floor_low で未実行。次の実行で `lancers_reply_account_diagnostic:` 行を読み、reason/http_status に応じて修正 | codex |
| 2026-10-23 21:30 | daisuke/life-manager-main-claude-3 | Codex profile lease 競合（FND04）とディスク/swap | blocked | SSOT「FND04 実測」節（#8638）・#8579 | 理由: swap 11–12GB（ChatGPT内Codex・Codexアプリ・daily-driver）で空きが10GiB付近を上下。人間がアプリを閉じるかメモリ方針を決める必要 | codex |
| 2026-10-25 15:30 | life-manager-main-claude-2 | effect_unknown fence（5 lane）＋ LINE 審査監視 | in_progress | #8957 merged（ledger_fence_reconcile adapter: life-manager-daily / marketing-mine-daily）/ BOARD 15:30 行 | ①release cut 後、新 release から `python3 runtime/loop/ledger_fence_reconcile.py --owner life-manager-daily --occurrence life-manager-daily:tiktok-retry-20260918-3 --resolve` と `--owner marketing-mine-daily --occurrence marketing-mine-daily:18d63740c1616110-91692 --resolve` → PASS → `LIFE_MANAGER_APPLY_TARGET=<lane> lm-loop apply`。②残 3 lane（Codex 10/31 引き継ぎ、未実装）: pm-live-trade＝Polymarket CLOB 注文 GET adapter（alpaca effect_reconcile.py を写す、L2 認証、queued_at 以降の注文 0＋open 0 で no-effect、fence 18d61d6a6df63248-48979）／reinvest＝Base on-chain の wallet 送金 readback（execute-yield.mjs は ledger なし、verify-inflow.mjs の RPC 読みを写す、fence 18d632d851ca3938-29047）／ubi-watcher＝Supabase queue の settle 状態＋Crossmint 受領（ubi-payout-watcher.mjs settleFn、fence 18d60570ae2ef988-48349）。adapter は registry effect_reconcile に argv/--occurrence/--resolve で登録、fixture は render_job_models で再生成。③LINE: set-038 審査中、042/043/044 審査待ち、結果は BOARD へ。agentmail-replier は effect_unknown fence（claude-3 担当）。ログインは credentials.json の line-account（値は書かない）。終了時は必ずログアウトしてから閉じる | codex |
| 2026-10-24 08:51 | daisuke/anicca-project-codex | Dots の Reason Network 参加確認 | done | docs/dots-reason-recheck-20261024 / docs/team/HANDOFF.md | Mac miniの公式list_teamで本人daisuke/chatgptを再確認。取得時idle 10h。稼働中とは断定しない。根拠・空き容量・副タスクは下記「Dots の Reason Network 参加」 | daisuke/cursor |
| 2026-10-23 23:28 | daisuke/anicca-project-codex | 求人応募文5件の下書き（提出は参謀） | done | docs/job-application-drafts-five-20261023 / docs/team/specs/job-application-drafts.md | 原稿5件・公式質問63件・根拠照合を完了。PRのCI/統合状態を確認後、参謀が各原稿の未確認回答と提出可否を扱う。応募・ledger・Thankfulは未操作 | daisuke/cursor |
| 2026-10-24 04:10 | daisuke/life-manager-main-claude-5 | Honne 1.0.5（ハードペイウォール＋翻訳中継）TestFlight→審査提出 | done | life-manager #8711/#8764 merged、anicca-products #623/#625 merged、TF build 202610240347 VALID | 中継 https://aniccaai.com/api/honne/llm/object は本番200確認済み（Netlify site anicca2 に HONNE_LLM_KEY/HONNE_APP_TOKEN）。2026-10-24 04:40 審査提出済み（WAITING_FOR_REVIEW）。次: 審査結果を確認し、リジェクトなら理由に沿って修正。リリースは `fastlane beta`（HONNE_TOOLKIT_URL / HONNE_TOOLKIT_TOKEN_FILE=~/.secrets/honne-app-token / HONNE_REVENUECAT_IOS_API_KEY_FILE=~/.secrets/revenuecat-honne-live-ios-sdk、ASC キーは下行） | codex |
| 2026-10-24 04:10 | daisuke/life-manager-main-claude-5 | iOS 署名・TestFlight 手順の共有（Thankful/Honne で実績） | done | Team S5U8UH3JLJ / ASC キー ~/.appstoreconnect/private_keys/AuthKey_646Y27MJ8C.p8（Key 646Y27MJ8C） | claude-3 に Reason で送付・受領済み。~/.local/state/life-manager/.env の ASC キーは別アカウントでこのアプリ群には 404。zsh で引数を変数にまとめると1語扱いで失敗するので直接書く | codex |

## Dots の Reason Network 参加

目的・範囲・完了条件: アカウント2の既存Dots本人をReason Networkで確認し、公式 `list_team` に本人セッションが表示されることを完了条件とする。既存接続が成立している場合は再登録しない。結果をこの台帳とReasonの `daisuke/cursor` へ共有する。

- 確認結果: 最新のReason MCP `list_team(filter="chatgpt")` で「Daisukeのネットワーク」のMac mini（`aniccanomac-mini`）に `daisuke/chatgpt`、agent `chatgpt`、`personal agent (chatgpt), through Reason` を再確認する。取得時は `idle 10h`。本人セッションの一覧表示という完了条件を満たすが、新しい作業の着手・返信・自動起動は証明しない。接続手順の正本 [Dots の RevenueCat 利用と音声通話](https://github.com/Daisuke134/ai-config/blob/main/specs/dots-revenuecat-voice.md) の確認blob `a195dfcbb5448faf5341bb0b28dd884753eb0e0f` も、このアドレスをDots本人の成功経路として明示する。
- 今回の操作: Reason受信箱・公式一覧・連絡手順の読み取り、HANDOFF/BOARDの小さな更新のみ。接続済みの本人を使い、新規join・代理Dots・MCP/認証設定変更・監視loopは追加しない。ChatGPT.appを含むアプリ終了、強制終了、logout、Mac/アプリ再起動は行わない。
- 別件の未完: 正本に残る応募履歴の共有・応募台帳への反映は、この参加確認の完了と分ける。未着の分割や応募情報を補完せず、既送信分も再送しない。
- 所有境界: Thankful と build 10 は `life-manager-main-claude-5` の単独担当。Codexは変更・ビルドを行わない。保護されたmainへ直接pushせず、専用branch/PRで反映する。
- 容量境界: 再確認時の空きは4.15GiB。共有Git objectを使う疎worktreeで2文書だけを編集し、clone、依存install、build、画像・動画・大容量logを作らない。
- 求人副タスク: 最新mainの `job / claimed / codex` 5行はすべて `docs/team/jobs/drafts/` の原稿にkeyが完全一致する。初回5件を含む原稿10件はPR #8730 / #8782で作成済み。未作成のclaim済み求人は0件。応募・台帳status変更・既存原稿の再作成は行わず、不足事実や必須添付の扱いは各原稿を参照する。
- 次の一手: 参謀は既存の `daisuke/chatgpt` を連絡先として使う。追加のDots参加作業は不要。

## 2026-10-23 Mac mini disk/loop audit (参謀)
- lm_loop_run: ~89 processes, but each loop label appears exactly once (no self-respawn). Each launchd plist runs one label; long-running daemons stay pinned to the release they started from (some still on 20261018 releases). Not a duplication bug. Optional fix: release cut should kickstart -k long-running labels so old releases can be GCd.
- Stale cozempic.cli guard orphans (ppid 1, started 10/17-10/22) killed. premiere-pro-mcp/node_repl are children of the live codex app-server daemon (one per thread); left alone.
- Disk: 0.4G -> ~13G free (tmp clones, loop-tmp, simulators erased, caches, 6 clean stale worktrees, old cloak state-backups, gz old codex sessions). Remaining hogs: .worktrees ~11G (mostly dirty), .codex-acct2 sessions 7G, git packs, ollama 4.4G.
- Rule: log out of Mac apps before quitting; never force-quit LINE/ChatGPT.
