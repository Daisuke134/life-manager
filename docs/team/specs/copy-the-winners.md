# Copy-the-winners teardowns

Owner: 参謀 (routine "Copy-the-winners teardown", daily ~09:00 JST). One section per run, newest first.
Rule: copy the structure of profitable devs to the detail, never invent. No free trials, free tools only, reuse existing assets.
Watched: @ErnestoSOFTWARE, @maubaron, @blakeandersonw, @ChadAppDev, @jackfriks, @oliverhenry.

## 2026-10-26

### 3. Anicca iOS: store description line 2 as a question (winner: I am - Daily Affirmations)

- Winner: I am - Daily Affirmations (the category's top affirmations app). Source: Anicca Marketer's 2026-10-26 09:50 JST teardown as relayed by 参謀; not re-verified here. Their pattern: line 1 = a concrete benefit, line 2 = a question, weekly theme updates, and a recurring complaint about too many notifications.
- What we already do (read from the live ASC en-US/ja localizations of version 1.9.6, 2026-10-26): line 1 is a concrete moment ("When the same negative thought keeps looping, read one kinder line." / ja: 「頭の中で同じ否定的な言葉がくり返す日に。」); line 2 is empty; features start at line 3.
- What we copy (one change only): fill line 2 with a one-sentence question that names the reader's moment, in the same voice as line 1. Draft en-US: "What would you say to a friend who thought this way?" Draft ja: 「同じ言葉に疲れた日、友だちにならどんな言葉をかけますか？」. Both are placeholders for Narita to confirm; public copy stays first person and does not mention AI.
- Why this one: it is store-metadata only (no app code, no RevenueCat or price change), so it can ship without a new build. Paywall and onboarding changes need code and a new review, and 1.9.6 itself is still blocked (see below).
- Ship plan: version 1.9.7 metadata, after 1.9.6 is accepted into review. Not shipped yet.
- Not copied: weekly theme updates (needs content cadence and code) and the notification-volume fix (we send fewer notifications than the winner's reviews complain about, unmeasured; revisit with real data).
- Measure: store page conversion (impressions to downloads) before and after in App Store Connect, same 14-day window.
- Blocker for 1.9.6: ASC rejects the new submission with STATE_ERROR.ITEM_PART_OF_ANOTHER_SUBMISSION. Version 1.9.6 sits in the 2026-07-04 review submission (UNRESOLVED_ISSUES), whose items this API key cannot read (403). It needs someone to read Apple's review message and resolve or withdraw that submission.

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
