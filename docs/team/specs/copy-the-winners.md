# Copy-the-winners teardowns

Owner: 参謀 (routine "Copy-the-winners teardown", daily ~09:00 JST). One section per run, newest first.
Rule: copy the structure of profitable devs to the detail, never invent. No free trials, free tools only, reuse existing assets.
Watched: @ErnestoSOFTWARE, @maubaron, @blakeandersonw, @ChadAppDev, @jackfriks, @oliverhenry.

## 2026-10-26 (17:00 JST run): monk e-book, AI Monk Factory, Life Manager Cloud

### 4. Monk e-book: comment keyword → automatic DM with the checkout link (winner: Yang Mun)

- Source: [Yang Mun site](https://yang-mun.com/) (3-ebook bundle $19.99, anchor $38.97, "includes free Inner Circle", "20,000+ readers ★4.9") and the funnel teardown [InstantDM, "Yang Mun Sold a $24 Ebook"](https://instantdm.com/blog/yang-mun-ai-influencer-digital-product-funnel).
- What they do: Reels say "comment GUIDE". An official Instagram API tool DMs the checkout link within seconds, asks for an email in the same thread, and the account replies "sent" publicly under the comment. Three keywords only: GUIDE (first touch, ebook), HEAL (ebook plus a one-line course mention), COURSE (program). One follow-up after 24h, upsell 3–5 days after purchase. Link in bio leaks buyers.
- What we do now: every monk caption ends "The Anicca Reset, link in bio" (`marketing/monk-factory/monk_daily.py`); no DM automation (gap first noted 2026-10-23 in MONK-BUSINESS.md, still not done).
- What we change: (1) connect the monk Instagram account to a free comment-to-DM tool (ManyChat free tier or InstantDM free plan, 500 automations/month, official Meta API, no password sharing) with keyword RESET → DM "Here's the link you asked for" + https://aniccaai.com/monk?utm_source=ig&utm_medium=dm&utm_campaign=monk_daily&ct=dm_reset, and public reply "sent 🙏". (2) Only after a test comment from a second account receives the DM, switch the IG caption CTA in `monk_daily.py` to "Comment RESET and I'll send you the book." TikTok keeps "link in bio". (3) Product: when the second e-book exists, copy the bundle shape (bundle price with the crossed-out sum as the anchor).
- Owner: 参謀 (Monk daily video routine) for the caption switch; browser step queued in BROWSER-QUEUE (needs the IG login, interactive session).

### 5. AI Monk Factory: a hidden "how is this made" lane (winner: Yang Mun's operator lane)

- Source: same [InstantDM teardown](https://instantdm.com/blog/yang-mun-ai-influencer-digital-product-funnel): a separate keyword (BUILD) for people asking how the AI character is made, routed to a waitlist or paid call, never mixed into the e-book DM.
- What we change: add keyword BUILD in the same DM tool → https://aniccaai.com/ai-monk-factory?ct=dm_build (3 free videos, then $199/mo). Do not mention it in captions; reply only when a commenter asks how the monk is made.
- Owner: 参謀 (same browser step as #4).

### 6. Life Manager Cloud: copy the hosted-agent winners' offer and the "easy button" (winners: SimpleClaw, Claws.host, Rapid Claw)

- Sources: [SimpleClaw case](https://aidevcases.com/en/cases/simpleclaw) ($30K MRR in 2 weeks: sign in with Google, pick a model, own agent live in under a minute, used from Telegram; revenue-milestone threads on X amplified by @levelsio/@marclou), [Claws.host on TrustMRR](https://trustmrr.com/startup/claws-host) ($1,606 MRR, 35 subs; $29/$69/$129 per month; "Run OpenClaw in 5 minutes, not 5 hours"), [Rapid Claw on Indie Hackers](https://www.indiehackers.com/post/we-hit-2k-mrr-letting-people-deploy-ai-agents-without-touching-a-terminal-45cfa83e06) ($2K MRR, 68 customers, $29/mo including $10 of AI tokens, one practical "10 automations you can set up today" blog post drives ~30% of signups; best users are small agency owners).
- What we change: (1) Distribution: publish one practical use-case post for Life Manager Cloud ("10 things the manager does for you by email, set up today"), on Telegraph and dev.to via the Distribution loop, linking aniccaai.com/lm with ct=usecase10; every revenue milestone of LM Cloud gets an X post on @diceai0 in 成田さん's first person. (2) Product: hero line in the winners' shape ("Your own manager running in 1 minute, not 1 weekend"), three tiers starting at $29/mo with model usage included, Google sign-in, no terminal. Owner: life-manager-main-claude-2 (Maritime build) for the onboarding/pricing; 参謀 Distribution loop for the post.

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
