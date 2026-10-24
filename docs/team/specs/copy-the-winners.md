# Copy-the-winners teardowns

Owner: 参謀 (routine "Copy-the-winners teardown", daily ~09:00 JST). One section per run, newest first.
Rule: copy the structure of profitable devs to the detail, never invent. No free trials, free tools only, reuse existing assets.
Watched: @ErnestoSOFTWARE, @maubaron, @blakeandersonw, @ChadAppDev, @jackfriks, @oliverhenry.

## 2026-10-24

### 1. Six-slide TikTok slideshow, structure copied from niche winners (@ChadAppDev)

- Source: [@ChadAppDev, "How to scale your app to $1M w/ TikTok Slideshows" (2026-10-23)](https://x.com/ChadAppDev/status/2113646711197278623), quoted as "everything I know after 100x'ing my revenue in the last 5 months" ([post](https://x.com/ChadAppDev/status/2113647937288904728)); also [@ErnestoSOFTWARE guide](https://x.com/ErnestoSOFTWARE/status/2014110519913857122) (faceless = free channel, 3–5 posts/day, consistent style or character).
- What they do:
  1. Search TikTok for the problem the app solves (e.g. "can't sleep", "overthinking texts", "gratitude journal").
  2. Keep only posts with views far above the account size (their example: 2,000 followers, 400K views).
  3. Copy a structure only when the same structure works on 4–5 different accounts (one viral post can be luck).
  4. Break it down slide by slide: what the hook promises, how middle slides deliver, where the product appears, what the last slide asks. Rebuild that sequence around our app. Copy the structure, never the content.
  5. Six slides: hook, problem, problem deepened, how the app helps (real screen), proof or result, clear reason to download.
  6. A small generator (topic + saved structure in, slides out) makes volume; review text readability and product details before posting.
- What we change: our TikTok slideshow lane (`tiktok.anicca_slideshow`, `apps/life-manager/scripts/anicca-en-slideshow-tiktok-canary.js`) and the launch kits had no format-sourcing rule and no fixed slide structure. Added the six-slide template and the 4–5 account rule to `docs/team/launch/README.md`. Every format we post must cite the 4–5 source TikTok URLs in the post record.
- Apps/accounts: For Better Sleep, Thankful, Honne (本音翻訳), Anicca; TikTok `anicca_slideshow`, Muse's Instagram, Postiz channels.
- Skipped: Content Rewards paid CPM campaigns (paid tool, against the free-tools rule). Revisit only once a format is proven and there is revenue.
- Cadence: Ernesto posts 3–5 faceless posts/day per account; we keep one consistent visual style (and optionally one character) per product account.

### 2. App Store subtitle and screenshots (@ErnestoSOFTWARE)

- Source: [@ErnestoSOFTWARE, "I built 10 apps in 10 months and make $800,000/yr"](https://x.com/ErnestoSOFTWARE/status/2014110519913857122), re-promoted [2026-10-23](https://x.com/ErnestoSOFTWARE/status/2113658382787678711) (says 7.2M views).
- What they do: subtitle says plainly what the app does (good: "Block distractions and stay focused longer"; bad: "An AI-powered productivity experience"). 3–5 screenshots, big text, one idea per screen, minimal UI (Cal AI as the example). "Your subtitle + first screenshot do all the work."
- What we change: added this as an ASO check to `docs/team/launch/README.md`; next ASC metadata edit for each app rewrites the subtitle as "verb + outcome" and screenshot 1 as one big-text benefit. No ASC change made in this run.
- Apps: all six public apps (see `docs/team/specs/apps.md`).
- Note: Ernesto's guide says "hard unskippable paywall, pay upfront or start a free trial". Team rule is no free trials, but some paywall specs (Daily Dhamma, For Better Sleep, STUDIO CHERIE) mention a 3-day annual trial; flagged for the owner to reconcile.
