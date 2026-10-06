# リモート接続の復旧 — 2026-09-04

Mac mini (`AniccanoMac-mini.local`) とスマホの接続が3系統とも壊れた件の診断と TODO。

## 用語（この文書の前提）

- **daemon** — Mac 上で常駐しているプロセス。スマホからの指示を受け取る窓口
- **enrollment** — 「このマシンを、このアカウントのリモート先として登録した」というサーバー側の記録
- **pairing** — スマホのアプリに「この Mac を使う」と教える操作。daemon の接続とは**別物**
- **session** — 1本の会話。daemon が抱えるプロセス。daemon が死ぬと session も死ぬ

## 3系統の状態（2026-09-04 00:30 時点、実測）

| 系統 | アカウント | 状態（01:05 更新） |
|---|---|---|
| Codex acct2 | daisukenarita53 (`9aac4cc6…`) | ✅ 接続済み・自己修復あり |
| Codex acct1 | keiodaisuke (`59f9ff19…`) | ✅ 接続済み・自己修復あり |
| Claude RC | keiodaisuke | ✅ 接続・trust flag 自動修復・err ログ復旧 |
| **Mac 本体** | — | ❌ **1〜2日おきに kernel panic** |

両 Codex は別 environment で**同時接続**を実測（`…8ff8c53e` / `…9bced6d2`）。

---

## 判明した原因

### 原因A2 — plist のキー名が誤っていて、エラーが5年分どこにも残っていなかった

`com.anicca.claude-remote-control.plist` に `StandardErrPath` と書かれていた。
launchd の正しいキーは **`StandardErrorPath`**。launchd は未知のキーを黙って無視するため、
**stderr がどこにも記録されていなかった**。今夜、原因特定が遅れた直接の理由。

**対処済み**: キー名を修正。修正後に初めて err ログファイルが生成された。

### 原因A — Claude の trust flag が false に戻っていた

`~/.claude.json` の
`projects["/Users/anicca/Projects/life-manager-main"].hasTrustDialogAccepted` が `false`。

`claude remote-control` は起動直後に

```
Error: Workspace not trusted.
```

で exit 1。`KeepAlive=true` なので15秒ごとに同じ失敗を無限リトライ。stderr ログファイルすら作られず、外からは無音死に見えた。

**対処済み**: flag を `true` に戻して kickstart。さらに恒久対策として
`~/.local/bin/claude-remote-control-preflight.sh` を launchd の起動ラッパーにし、
起動のたびに flag を検査・修復するようにした（plist の ProgramArguments を差し替え）。

**実証**: launchd 環境で flag を `false` にして再起動 → err ログに
`preflight: restored hasTrustDialogAccepted for /Users/anicca/Projects/life-manager-main`
が記録され、flag は `True` に復帰、`exit 0`。障害を再現した上で自動修復を確認した。

同ラッパーで `out.log` のローテーションも行う（10MB 超で `.1` へ退避。56MB まで
無制限に育っていた）。

### 原因B — `codex login --device-auth` は起動時点で auth.json を消す

ソースで確認。`codex-rs/cli/src/login.rs` の `run_login_with_device_code` は、
デバイスコードを表示する**前**に `clear_existing_auth_before_login()` を呼ぶ。
失敗してもキャンセルしても、古い認証は戻らない。

`~/.codex-remote-keepalive.sh` には
「acct2 が未ログインなら `com.anicca.codex-acct2-setup` を kickstart」という分岐があり、
それが device-auth を呼ぶ。

**つまり、復旧役が認証を消しにいく構造。** 2026-09-04 に acct2 が死んだのはこれ。

**対処済み**: 有効な認証を `~/.local/share/anicca/codex-acct2-auth.json`（600）に退避。
分岐そのものはまだ生きている（TODO 1-a / 1-b）。

### 原因C — session guard が毎回例外を投げ、自動復旧が一度も走っていなかった

`~/.local/bin/codex-session-rollover.py` が

```
UnsafeProcess: pid 83294: executable is not owned by /Users/anicca/.codex-acct2
```

で raise → keepalive が `exit 75` → `ensure()` に到達せず。
**5分ごとの自動復旧が機能していなかった。**

理由は2つ:
1. 所有判定を「バイナリのパスが `$home/packages/standalone/` 配下か」で行っていた。
   `~/.local/bin/codex` は CODEX_HOME に関係なく単一 release に解決するので、この前提は成立しない
2. zombie プロセス（`<defunct>`）を unsafe と判定していた

**対処済み**: pid record + processStartTime を正とする形に修正。`exit 0` を実測確認。

### 原因D — acct1 の enrollment 行が汚染

`state_5.sqlite` の `remote_control_enrollments`:

```
~/.codex        AniccanoMac-mini.local | env_e_6a5e30ef…  ← 古い
                AniccanoMac-mini.local | env_e_6a5e30ef…  ← 重複
                AniccanoMac-mini.local | env_e_6a6df772…
                AniccanoMac-mini.local | env_e_6a6df772…  ← 重複
~/.codex-acct2  AniccanoMac-mini.local | env_e_6a6ca7b7…  ← 1行だけ、綺麗
```

openai/codex#25241 が同じ症状:

> "The CLI reuses this persisted enrollment regardless of whether server_name
> matches the current machine. The OpenAI relay server detects the mismatch and
> silently closes the WebSocket."

「enabled だが errored」の正体はこれ。**未対処。**

### 原因E — daemon の接続と pairing は別物

CLI が `status: connected` でも、スマホ側の pairing が無ければ電話には出てこない。
acct2 が繋がったのは `codex remote-control pair` のコードを入力した時点。
**この手順が抜けていたのが「CLI は connected なのに電話に出ない」の正体。**

### 原因F — Claude の session は daemon 再起動で全滅する

RC を再起動した際、ログに

```
[22:43:07] Shutting down 4 active session(s)…
```

現在 `Capacity: 1/32` = ホストが抱える session は1本のみ。
スマホに見えている「Mercor Money Printer hackathon」「Life manager loops status」は
Mac 側に対応するプロセスが無い。だから送っても永久に `Thinking…`。

### 原因G — Mac 本体が kernel panic で落ちている（最上位の原因）

`last reboot` と `/Library/Logs/DiagnosticReports/*.panic` の時刻が完全一致:

| panic ログ | 再起動 |
|---|---|
| 09-03 06:45:51 | Sep 3 06:45 |
| 09-01 11:26:54 | Sep 1 11:26 |
| 08-30 16:40:18 | Aug 30 16:40 |
| 08-30 01:49:04 | Aug 30 01:48 |
| 08-29 04:46:59 | Aug 29 04:46 |

```
panic(cpu 2): userspace watchdog timeout: no successful checkins from
              WindowServer (2 induced crashes) in 120 seconds
```

**再起動を仕込んだ job は存在しない**（`~/Library/LaunchAgents`・`/Library/LaunchDaemons`
を全検索、該当ゼロ。予約電源は `wakepoweron at 6:00AM` のみ）。
つまり「誰かが再起動している」のではなく、**過負荷で落ちている**。

**真因はメモリ枯渇。CPU ではない。** panic ログの `memoryStatus`:

```
free:            927 pages = 約 15 MB   ← 16GB のマシンで
wired:       270,175 pages = 約 4.2 GB
compressions:   2,497,067,244           ← 25億回
decompressions: 2,348,545,942
```

WindowServer が checkin できなかったのは CPU 不足ではなく、
**描画に必要なメモリすら確保できなかったから**。

計測時点の実機も同じ状態:

```
搭載 RAM  16 GB / 空き 61 MB / swap 8.4 GB 使用（10GB 中 82%）
```

内訳（巨大プロセスは無く、数の問題。最大でも 314MB）:

| 種別 | プロセス数 | 合計メモリ |
|---|---|---|
| **Chromium (CloakBrowser)** | **111** | **4,845 MB** |
| claude | 26 | 1,745 MB |
| node | 54 | 1,104 MB |
| Python | 74 | 859 MB |
| codex | 28 | 689 MB |
| openclaw | 13 | 669 MB |
| mds (Spotlight) | 2 | **70 MB** |

全プロセス数 724。

**Spotlight 犯人説は棄却。** 70MB しか使っていない。CPU の瞬間値だけを見た早計だった。
**loop を減らす案も棄却** — 稼働中の loop 全部（claude+codex+python+node = 4.4GB）より
**Chromium 単独（4.8GB）のほうが多い**。稼ぎを削る必要はない。

ChatGPT デスクトップアプリは起動しておらず無関係。

**これが全ての切断の親玉。** Claude も Codex も Mac ごと落ちれば切れる。

---

## 棄却した仮説

- **ディスク満杯** — `df` で31Gi空き。過去の事例とは別物
- **トークン期限切れ** — acct2 は exp 2026-09-12 で有効だった
- **2アカウントが同一ホストで衝突** — `installation_id` は CODEX_HOME ごとに独立
  （`~/.codex`=`7b05d812…` / `~/.codex-acct2`=`fa67d2bd…`）。併存は構造上可能
- **アカウント停止・課金** — 両方 ChatGPT ログイン有効、plan は pro / plus

---

## TODO

### 優先1 — Codex acct2 を forever にする

- [x] **1-a** `~/.codex-remote-keepalive.sh` の device-auth kickstart 分岐を削除し、
      保護コピー `~/.local/share/anicca/codex-acct2-auth.json` からの復元に置き換える
- [x] **1-b** `com.anicca.codex-acct2-setup` を無効化（1-a の保険）
- [x] **1-c** keepalive が接続成功時に保護コピーを更新する
      （トークンは自動 refresh で中身が変わるため）
- [x] **1-d** 保護コピーを作成（`shasum -a 256` で live と一致を確認）
- [ ] **1-e** Mac 再起動を跨いで pairing が残るか実測（**未検証**）

### 優先2 — Claude セッション

- [x] **2-a** 既存 session は復活不可。新規で開き直す（要ユーザー操作）
- [x] **2-b** 既存 session は **約4時間以内なら復帰可能**（公式 docs）。
      `claude remote-control`（全 session 復帰）/ `--continue`（起動時 session のみ）/
      `--session-id <id>`。
      > "These commands work for about four hours after the server stopped.
      > After that, run `claude remote-control` to start a new session."
      > — docs.claude.com/en/docs/claude-code/remote-control
      **停止時刻 22:43 と 00:05 → 期限は 02:43 / 04:05。**
      ただし復帰の結果は3分岐で、旧メッセージが引き継がれない場合がある:
      「Claude Code starts a replacement session with an auto-generated name and
      leaves the conversation's earlier messages out of it.」
- [x] **2-c** trust flag の自動修復 preflight を RC の plist に追加
      （`hasTrustDialogAccepted` が false なら true に戻してから起動）
- [x] **2-d** stderr ログが作られていない件の調査。今回これが発見を遅らせた
- [ ] **2-e** 既知バグの確認: anthropics/claude-code#34255
      「Remote Control silently drops the connection... the built-in reconnection
      doesn't work... Connection typically drops after 15-60 minutes of use.」
      自動再接続が効かない報告あり。今回の無音死と症状が近い
- [ ] **2-f** 参考: 非公式の常時起動構成
      github.com/zuluparry/claude-remote-control-always-on
      「the moment you close the terminal the session dies」を launchd で解決する例。
      公式 docs に launchd 手順の記載は無い

### 優先3 — Codex acct1 (keiodaisuke)

- [x] **3-a** `~/.codex/state_5.sqlite` の古い enrollment 行を削除（バックアップ後）
- [x] **3-b** device-auth で keiodaisuke ログイン（2026-09-04 00:2x に OpenAI 側が
      `503 Service Unavailable` を返した。時間を置いて再試行）
- [x] **3-c** `remote-control start` → `remote-control pair` でコード入力

**3-a を 3-b より先に。** enrollment が汚染されたままではログインしても errored が続く可能性。

---

### 優先4（★最上位） — kernel panic を止める

原因G。ここを直さないと、他の全ての修正が1〜2日で無効になる。

- [x] **E1** panic ログを読み、真因を特定 → **メモリ枯渇**（CPU ではない）
- [ ] **E2** ~~Spotlight のインデックス除外~~ **棄却**。実測 70MB、効果なし
- [ ] **E3** ~~loop の同時実行数に上限~~ **棄却**。稼ぎを削る割に Chromium より小さい
- [ ] **E4** **CloakBrowser の Chromium が 111 プロセス・4.8GB ある理由を特定し、
      不要なものを閉じる。搭載メモリの 30% を単独消費** ← E群の本体
- [ ] **E5** ~~1週間 panic を追跡~~ **棄却**。監視は成果物ではない。
      対策は「見張らなくても壊れない仕組み」であるべき

### 優先5 — 監視（気づかない時間をゼロに）

- [ ] **D1** 3系統（Codex×2, Claude RC）を1つのヘルスチェックで監視し、
      落ちたら Telegram へ通知
- [ ] **D2** ディスク空き容量のガード。
      `claude-remote-control.out.log` が **56MB** まで無制限に育っていた（ローテーション無し）
- [ ] **D3** Mac 再起動を跨いで3系統が自力で戻るか実測（**未検証**）

---

## 完了したもの（2026-09-04 01:05 時点）

| 項目 | 実測した証拠 |
|---|---|
| acct2 の自己修復 | auth.json を意図的に削除 → `restored auth.json from vault` → 次パスで `connected`、`shasum` 一致 |
| acct1 のログイン | `Successfully logged in`、`account_id` `59f9ff19…`（acct2 と別であることを確認） |
| 両アカウント同時接続 | `.codex` `connected` env…8ff8c53e / `.codex-acct2` `connected` env…9bced6d2 |
| 自動復旧の復活 | keepalive `exit 0`（従来 `exit 75` で一度も動いていなかった） |
| vault 自動更新 | `acct1 vault updated` をログで確認、両 home 分のファイル生成 |
| 自爆経路の除去 | `com.anicca.codex-acct2-setup` を launchd から除去、plist を `.DISABLED-20260904` へ |
| preflight（未適用） | flag を false にして実行 → `restored hasTrustDialogAccepted` → True、他132プロジェクト無傷 |

---

## 復旧レシピ（また壊れた時）

### Codex acct2 が落ちた

```bash
pkill -f 'codex login'                                    # 自爆プロセスを止める
cp ~/.local/share/anicca/codex-acct2-auth.json ~/.codex-acct2/auth.json
chmod 600 ~/.codex-acct2/auth.json
CODEX_HOME=~/.codex-acct2 codex remote-control start
CODEX_HOME=~/.codex-acct2 codex remote-control pair      # コードをスマホに入力
```

**`codex login --device-auth` を安易に叩かない。** 既存の認証が消える。

### Claude RC が落ちた

```bash
tail ~/Library/Logs/claude-remote-control.out.log         # まず原因を見る
python3 -c "import json;d=json.load(open('/Users/anicca/.claude.json'));print(d['projects']['/Users/anicca/Projects/life-manager-main']['hasTrustDialogAccepted'])"
# false なら true に直してから
launchctl kickstart -k gui/501/com.anicca.claude-remote-control
```

#### ログアウトで落ちた（2026-10-06 の事故 → 自動化済み）

症状: スマホの Code 画面「デバイス」欄に Mac mini が出ない。`~/Library/Logs/claude-remote-control.err.log` に
`Error: You must be logged in to use Remote Control.` が15秒ごとに並ぶ。`claude auth status` が `"loggedIn": false`。
原因: データボリューム100%で keychain の OAuth トークン更新が書けず失効した（`credentials.json` の
`CLAUDE_CODE_OAUTH_TOKEN` 注入では RC は通らなかった）。Dais は帰宅してログインし直すしかなかった。

**今は自動**: `bin/claude-remote-control-preflight.sh`（インストール先 `~/.local/bin/`）が起動のたびに
`claude auth status` を確認し、未ログインなら `claude auth login --claudeai` を裏で起動して承認URLを Telegram に送る
（30分に1回まで、ログイン処理は同時に1つ）。**スマホでURLを開いて承認を押すだけで復旧**し、コード貼り付けは不要。
状態とログ: `~/.local/state/life-manager/claude-remote-control/`。

手動で同じことをする場合:

```bash
df -h /System/Volumes/Data                    # 100% ならまず空ける（再発の根本原因）
~/.local/bin/claude auth status               # loggedIn を確認
sleep 1200 | ~/.local/bin/claude auth login --claudeai   # 出たURLをスマホで承認 → "Login successful."
```

承認後は launchd の KeepAlive が自動で再起動し、out.log に `Connected · life-manager` が出れば完了。

## バックアップの場所

| 中身 | パス |
|---|---|
| acct2 の有効な認証（exp 2026-09-12） | `~/.local/share/anicca/codex-acct2-auth.json` |
| 同上（元） | `~/.codex/auth.json.bak-was53-20260904002002` |
| keio の失効した認証（refresh 不可） | `~/.codex/auth.json.bak.keio-20260604-232413` |
| keepalive スクリプト | `~/.codex-remote-keepalive.sh.bak-*` |
| session guard | `~/.local/bin/codex-session-rollover.py.bak-*` |
| Claude 設定 | `~/.claude.json.bak-rcfix` |
