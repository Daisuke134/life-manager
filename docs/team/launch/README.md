# Launch kits: Honne / Thankful / For Better Sleep

Drafts only. Nothing here has been posted. 参謀 merges and decides when to post.

Each app file has: 3 English X posts, 1 Japanese X post, the first-reply text with the App Store link slot, the images to attach, and ASO keyword candidates.

## Rules every post follows (copied from measured winners, not invented)

Source study: [launchindieapps.com, 1,012 launch posts from accounts under 5,000 followers](https://launchindieapps.com/blog/x-launch-post-for-ios-app) (median views, correlation only).

| Rule | Evidence |
|---|---|
| First line is a reason, a story or a result, never "just launched / now live" | Study: "just launched" openers 50 vs 78 median views. [@nanahrii](https://x.com/nanahrii/status/2089463523843965221) opens with a struggle story: 51,879 views, 1,290 likes |
| Attach the one screen that explains the app (photo is enough) | Study: media 95 vs text 40; photo 99 vs video 95. [@yokoichi777](https://x.com/yokoichi777/status/2071217804989325693) used 4 screenshots: 151,045 views |
| Name one difference, and the price when it is not free | [@v_kas_kumar](https://x.com/v_kas_kumar/status/2060235457666134477): one difference + price in the post: 7,084,882 views, 11,966 likes |
| Short lines, blank line between them, no hashtags | Study: 3+ lines 80 vs one block 39; hashtag 62 vs none 72 |
| End with a specific question, then reply for the first 1–2 hours | v_kas_kumar 451 replies, nanahrii 405 replies. Study: vague "feedback?" asks reached 10+ engagements 9% vs 16% |
| Link goes in the first reply (the JP winner put details "in the thread") | yokoichi777: 「詳細はツリーに」; ~600 downloads next day, ~100% from X per [his write-up](https://note.yokoichi.jp/n/n5f2c9dd4d6f7) |
| Post sleep / gratitude in the JP evening | yokoichi777 posted ~22:00 JST; downloads peaked 20:00–21:00 JST next day |

Japanese shape (yokoichi777): app name + what it does in one line + a metaphor → 「◯ヶ月かけて作りました」 → 「祝個人開発」 → 「詳細はツリーに」, 4 images.

## Claims

Every claim comes from `skills/earn/marketing-engine/registry/products/<product>.json` `approved_claims` or the current App Store metadata. Do not add claims (accuracy, "reveals true intent", health outcomes) beyond those.

## Before posting (fill these, then delete this section's TODOs)

- `<APP_STORE_URL>`: use an App Store campaign link (`?pt=<provider>&ct=<campaign>&mt=8`) so App Store Connect attributes downloads to the post. Base URLs are in each file.
- `<BUILD_MONTHS>` (JP posts): real build time. Leave the line out if unknown; do not guess.
- Prices: only the ones marked "verified" below; others stay as slots until read from App Store Connect.

## Gaps

- No measured launch post was found for a gratitude, sleep or message-interpretation app; the rules above come from general indie iOS launches.
- Reach in the examples is partly follower count (two winners have 17,000+ followers); our accounts are smaller, so expect the study's medians, not the outliers.

## TikTok / IG slideshow format (copied 2026-10-24 from [@ChadAppDev](https://x.com/ChadAppDev/status/2113646711197278623))

Source the format first, then write it. Full teardown: `docs/team/specs/copy-the-winners.md`.

1. Search TikTok for the problem the app solves. Keep posts whose views are far above the account's followers (example: 2K followers, 400K views).
2. Use a structure only if 4–5 different accounts get results with it. Record those URLs with the post.
3. Rebuild it slide by slide around our app. Copy the structure, never the words or images.

Default six slides when the sourced format doesn't say otherwise:

| Slide | Job |
|---|---|
| 1 | Hook: names the viewer's problem in their words (sourced hook shape) |
| 2 | The problem, concrete moment |
| 3 | Why it keeps happening / what people try that fails |
| 4 | How the app helps, real app screen |
| 5 | Result or proof (approved claims only) |
| 6 | Clear reason to download + app name (link in bio) |

One consistent visual style per product account; 3–5 posts/day is the winners' faceless cadence ([@ErnestoSOFTWARE](https://x.com/ErnestoSOFTWARE/status/2014110519913857122)), ramp up only after warm-up.

## App Store check (copied from [@ErnestoSOFTWARE](https://x.com/ErnestoSOFTWARE/status/2014110519913857122))

- Subtitle says what the app does, verb + outcome ("Block distractions and stay focused longer", not "An AI-powered productivity experience").
- 3–5 screenshots, big text, one idea per screen, minimal UI. Subtitle + screenshot 1 do most of the work.
