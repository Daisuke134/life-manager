# Marketing Engine — the shared distribution OS

**One engine. Many loops. You never reinvent distribution.**

Every marketing loop (capafy, clip, and every future product) runs on this ONE shared engine.
The engine does all the hard, dangerous, already-solved work — creating IG accounts that survive,
warming them, posting durably, measuring reach, self-improving, reporting. A loop is just a
**manifest**: the 4 things that are actually different per product.

## To launch a new marketing loop, you decide ONLY 4 things

| You decide | Manifest key | Example (capafy) |
|---|---|---|
| **WHO** (persona) | `MKT_PERSONA` | devs who want ready-made Claude skills |
| **WHAT PROBLEM** | `MKT_PROBLEM` | building an AI skill from zero is slow |
| **WHAT you sell** (product) | `MKT_PRODUCT_SOURCE` / `MKT_LISTING_URL_FMT` / `MKT_BIO_LINK` | capafy `/agent/agents` listings |
| **HOW** (content) | `MKT_CONTENT_ADAPTER` | `faceless-video` (or slideshow / carousel / clip-cut) |

Everything else — account creation, warmup, posting, reach, self-improve, telegram — is the
shared engine. **Do not copy or re-implement it. Copy a manifest.**

## How to add a loop

1. Copy `manifests/capafy.manifest.sh` → `manifests/<yourproduct>.manifest.sh`, edit the values.
2. (soon: `new-marketing-loop <yourproduct>` registers the launchd job automatically.)
3. Done. The engine provisions an account, warms it, and posts your content on the shared,
   hardened distribution.

## The hard-won invariants baked into the engine (never re-learn these)

- **Account lifecycle**: day1 = signup + profile ONLY (no instagrapi login — a day-1 account is
  too young, private-API login is always rejected). Warm day1–2 via browser. **Day3**: establish
  the ONE golden instagrapi session (`Client().login` now accepted, aged) → `dump_settings`.
  **Never relogin after** — a relogin trips bloks `ChallengeRequired` = poison. Post from day3.
- **Status vocabulary (SSOT)**: `warming_day1` and `warming` mean the account is still warming;
  both are usable for the provision counter but are not eligible to post. `ready` and lifecycle
  `*_ready` states expose an active account to the owning loop. Any poisoned status or poison
  marker excludes the account. The resolver accepts non-poisoned `warming*`/`ready*`/`*_ready`.
- **Browser isolation**: every loop leases its OWN isolated context on the shared `:9222`
  daily-driver via `cdp_context_lease.py` (never the raw default context — that churns other
  loops' tabs and poisons accounts). Each account gets a dedicated port (never 9222/9223).
- **Poster**: `poster.py` (tier1 saved session). One poster for every loop. The web
  composer (`post_reel.py`) is a dead end — IG silently drops automated web-composer posts.
- **Reach is the real shadowban test**; near-zero views across posts = cooked → provision fresh.
- **Poison detection only on day3+ accounts** (a young account failing instagrapi is expected,
  not poison — don't false-cook it).

## Owner-scoped publishing routes

The manifest and warmup instructions in this README describe the legacy
agent-owned Instagram route: the loop owns its account and posts through
`poster.py`'s saved instagrapi session. Life Manager Product Loop publishers may
explicitly use the shared Postiz publication adapter when their registry owner
declares a Postiz integration. Keep each owner on its declared route; never mix
or silently switch providers.

英語eBookの完成済みHeyGen動画は、同じrequest/video IDの公式completed確認と
保存済み出力hashの照合後に再利用する。当時の費用が欠ける場合はrender receiptの
`wallet_cost=null`・`cost_reconciliation_required=true`を保持し、費用0とは扱わない。
sidecarも`cost_reconciliation_required`を維持し、別slotの新規生成は保留する。
既存素材のmanual投稿も、同じprovider receipt ID・出力hash・未照合状態の一致が必要。
英語TikTokの単発回復は、main由来immutableの正規runnerを使う。

```sh
env -u LIFE_MANAGER_RUN_ID /absolute/immutable/release/bin/lm-loop-run ebook-en-tiktok-daily /absolute/immutable/release --slot-at '<configured past UTC slot, including .000Z>'
```

runnerはfreshな`manual-*` IDを発行し、durable admission・owner lockを通す。
`--slot-at`と環境の非空`LIFE_MANAGER_RUN_ID`の併用はadmission前に拒否する。
自分のactual claimと一致する時だけ指定slotを子へ渡し、Nodeは既存render receiptを必須とする。
別FIFO/容量待ち/unknownで実行できなければ新規生成・投稿は行わない。
後の通常wakeが保留manualをclaimした場合は`manual_slot_request_expired`として未実行で終端し、
次の通常FIFOへ進む。手動指定の自動復元や、実行済みという扱いはしない。

| Legacy `MKT_CONTENT_ADAPTER` | Instagram media | `poster.py` route |
|---|---|---|
| `faceless-video` | Reel | instagrapi `clip_upload` |
| `clip-cut` | Reel | instagrapi `clip_upload` |
| `slideshow` | Carousel | instagrapi `album_upload` |
| `carousel` | Carousel | instagrapi `album_upload` |

Monetization assets are a separate check: a loop may only go live with revenue links the
agent owns (an affiliate tag owned by a human must be replaced before live).

## AI Monk Factory：利用者設定から配信予定を確認する

既存Marketing Engineの環境で、自分のavatar・voice・商品・Postiz連携を設定する。
設定例をコピーし、placeholderを自分の値へ置き換える。API keyやpasswordは設定JSONへ入れない。

```sh
cp examples/ai-monk-factory.config.example.json my-monk.config.json
printf '%s\n' 'ここに自分の僧侶avatarが話す台本を書く。' > my-script.txt
python3 bin/lm factory plan --config my-monk.config.json --script my-script.txt
```

`language`は`en`または`ja`、Postizの`platform`は`tiktok`または`instagram`。
`state_root`には自分専用の絶対pathを指定する。`~`も使える。
このcommandは設定と台本を読み、生成要求・要求SHA・投稿先と商品をJSONで返す。
出力の`status`は`planned`、`provider_calls`は`0`、`external_effects`は空配列になる。

この段階ではstate directoryの作成、認証、voiceや連携のprovider照合、動画生成、投稿を行わない。
有効な計画の出力は公開や収益の証明ではない。実生成は次のcommandから行う。
投稿の実行入口、費用上限と照合、他ユーザー向け導入、Factory MCPと
hosted subscriptionは残る作業である。
Databaseを検索するAI Monk Index CLI/MCPとは別の機能として扱う。

### 利用者設定から1回生成する

同じ設定と台本を使い、新しい動画に自分で決めたrun IDを付ける。
同じ要求を再実行するときは同じrun IDを使う。
このcommandは認証済みHeyGen CLIで有料の生成要求を送る。

```sh
python3 bin/lm factory render --config my-monk.config.json --script my-script.txt --run-id first-video
```

HeyGen CLIを事前に認証しておく。configのavatar/voiceだけを選択に使い、
configから別の認証profileへ切り替えない。API key/passwordをJSONへ保存しない。

生成物は`state_root/renders/<project_id>.<run_id>.mp4`へ保存する。
HeyGenのlockと費用sidecarは、host共通の`LM_DATA_DIR/marketing/ebook`に保存する。
`LM_DATA_DIR`未設定時は`~/.local/state/life-manager/marketing/ebook`を使う。
このhost設定をprojectごとに変更しない。同じUnix userの既存ebook/全Factory projectが
同じ`locks/heygen-avatar-iv-account.lock`と`runs/*.heygen-effect.json`を共有する。
他の未確定要求があれば新しい生成へ進まない。同じproject/run IDの再実行は
保存済み要求と出力を照合し、既存rendererの再送防止を使う。

既存host disk gateが止まる場合はproviderを呼ばない。
結果の`schema_version`は`ai-monk-factory.render.v1`。
`setup_required`や`reconciliation_required`は未完で、`rendered`でも
`wallet_cost`がnullまたは`cost_reconciliation_required`がある場合は費用未確定である。
この入口には生成前のUSD費用上限保証がない。既存wallet/auto-reload閾値の確認と
費用差分/unknownガードの範囲を超えて、上限内に収まるとは説明しない。

このcommandは投稿しない。利用者の投稿先・disclosure・caption・商品URL・asset承認を
既存publisherへ渡す接続、実課金/実投稿/日次自動運転/実売上、Factory MCPと
hosted subscriptionは残る作業である。

## Files

| File | Role |
|---|---|
| `provision_prompt.sh` | shared account-creation prompt (parameterized by manifest) |
| `account_state.sh` | resolve active handle/port from a loop's account state file |
| `load_manifest.sh` | `me_load_manifest <name>` → export `MKT_*`, validate required keys |
| `manifests/*.manifest.sh` | per-loop config (the ONLY thing that changes) |
| `poster.py` | shared instagrapi poster (tier1 saved session), one poster for every loop |
| `warmer.py` | deterministic WARM step; establishes the golden instagrapi session on day3 |

## Where a loop's own code lives

A loop keeps only what is genuinely unique: its selector (what to promote), its copy/voiceover
judgment, and its content adapter (how the video/slideshow is built). Everything else is here.

**Future**: this engine migrates to `profitable-claude` as OSS so anyone — human or AI — can stand
up a self-improving marketing loop by writing a manifest. A meta-loop ("advertise product X") will
generate the manifest itself → loops that build loops.
