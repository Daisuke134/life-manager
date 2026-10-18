# Anicca website: story, products, and Life Manager design draft

2026-10-18. **Reviewable design prototype only. Not deployed.**

Start with `en.html`, the primary English review entry for YC and international readers. `index.html` is the Japanese counterpart. Three page types are available in both languages, with reciprocal EN/JA links. These static pages share navigation, typography and a product footer; no build, dependencies, credentials or analytics are required. A local HTTP server can be used for browser preview.

## Pages and intended routes

| Preview | Existing public route | Purpose |
| --- | --- | --- |
| `en.html` / `index.html` | `/en` / `/ja` | Anicca's mission, Manager, product entrances, founder story, measured work |
| `life-manager-en.html` / `life-manager.html` | `/lm` (language routing to preserve during integration) | Proactive general agent; body, mind, money; earning loops; local/cloud options |
| `products-en.html` / `products.html` | `/dais` (language routing to preserve during integration) | Unified directory for all products; no separate Life Manager/app categories |

Retain `/dais`; a `/products` alias can be considered later. Preserve existing localized routes, payment/onboarding callbacks, policies and metadata when implementing production. The prototype intentionally does not change production source. `apps/landing` contains only part of the marketing source and lacks the shared layout and strings needed to build the full public website.

## Design decisions

- Extend `../manager-universe-preview`'s warm paper, ink, orange accent and editorial typography. Keep the universe/all-living-beings ambition alongside concrete products.
- Keep **Manager** (world/population/behavior/intervention research) distinct from **Life Manager** (personal proactive agent). Anicca remains the company/umbrella.
- Explain the founder's motivation before asking readers to understand the research. Story: Vipassana around age 16; graduate research on personalized decoding; IACS auditory neurofeedback with 64-channel EEG; current work on shared conditions and environments. Do not invent dates, formal job titles, effectiveness results, or exact chronology between graduate work and IACS.
- Use ニューロフィードバック / neurofeedback. The story describes work and intention, not proof of reduced suffering.
- Broaden Life Manager beyond travel-time management using the current repository README. Local and cloud use the same core. The visual action log is explicitly illustrative, without invented activity, earnings or receipts.
- Explain continuous earning workflows without promising profit or claiming every platform's identity/interview/approval steps are autonomous. No unverified price/trial carried over from the stale live page.
- Following the user’s review, the home has one “My products” entrance. Life Manager and other apps are not presented as separate top-level product groups. Product footer appears on all six language pages. Catalogue links use the existing public `/dais` inventory; product pages are introductions, not evidence that every service is fully operational. Lookmax is marked in preparation, without a live CTA. No separate 'Flash Dice' product was inferred from the transcript.
- No product ratings, customers, testimonials, medical benefits or revenue figures are invented.

## Evidence and sources read

Live pages read on 2026-10-18: `https://aniccaai.com/en`, `https://aniccaai.com/lm`, `https://aniccaai.com/dais`, `https://aniccaai.com/honne/ja`, `https://aniccaai.com/affirmation-app/ja` and sitemap. Raw snapshots are outside Git at `/workspace/artifacts/manager-website-redesign-20261018/`.

The live home already presents Manager, but lacks the requested product directory/footer and founder context; its population evidence is outdated. The live `/lm` still describes the Calendar travel-time assistant. Public copy can therefore differ from the current canonical README and partial `/lm` source.

Repository sources:

- `README.md`: proactive general agent, delegated actions, body/mind/money, local/cloud and evidence requirements.
- `docs/research/manager/2026-10-18-founder-story-and-mission.md`
- `docs/research/manager/2026-10-18-iacs-resume-addendum.md`
- `docs/research/manager/articles/2026-10-18-household-v0-results-ja.md`
- `docs/research/manager/evidence/2026-10-18/household-v0-summary.json`
- `docs/superpowers/specs/2026-10-08-manager-website-copy.md`
- `apps/landing/README.md`, `apps/landing/app/lm/page.tsx`, `apps/landing/app/lm/LmBody.tsx`

The home evidence card uses measured 8B counts: 441,570 households, 1,042,763 persons. Behavior/intervention effects remain unmeasured. Research links point to the saved branch, not to an unpublished blog route.

## Visuals and checks

`*-desktop.png` and `*-mobile.png` are full-page screenshots of the actual HTML rendered by system Chromium through Playwright. `*-first-screen.png` is the desktop viewport. These are faithful implementation previews, not AI-generated mockups or production screenshots.

`verification.json` records checks of internal file/anchor targets, common footer, 390px overflow, JavaScript errors and EN/JA switching. English pages are checked for untranslated Japanese visible text. Product filters were removed to keep one unified listing. External URLs are drawn from the observed pages; this is not a full audit of the destination apps, hosted availability, checkout flows or localized pages.

No site publishing, app deployment, marketing posting or outreach was performed. Current work/order remain exclusively in the unified SSOT.

## English-first revision, following user review

The user approved the visual direction and asked to combine product entrances and show English first. `en.html`, `products-en.html` and `life-manager-en.html` provide full English copy, including the founder story and shared footer. English product links use existing English landing routes where known. Linked research articles remain Japanese and are labeled accordingly; an English marketing page does not imply every linked destination has been translated.

`*-mobile-first-screen.png` shows a 390×844 viewport; `*-first-screen.png` a 1440×1000 viewport. Full-page desktop and mobile screenshots are also retained. These images are actual browser renders of the HTML.

The user requested production deployment **after reviewing and accepting the English preview**. That acceptance is pending. Read-only preflight reconfirmed that the canonical `apps/landing` is a scoped subset, and the full shared site's source and Netlify configuration remain in `anicca-products`. No second site was registered, no production source was changed, and no deploy was triggered. Production integration must preserve onboarding, other products, policies, locale routes and the existing hosting identity.
