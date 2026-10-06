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

| Legacy `MKT_CONTENT_ADAPTER` | Instagram media | `poster.py` route |
|---|---|---|
| `faceless-video` | Reel | instagrapi `clip_upload` |
| `clip-cut` | Reel | instagrapi `clip_upload` |
| `slideshow` | Carousel | instagrapi `album_upload` |
| `carousel` | Carousel | instagrapi `album_upload` |

Monetization assets are a separate check: a loop may only go live with revenue links the
agent owns (an affiliate tag owned by a human must be replaced before live).

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
