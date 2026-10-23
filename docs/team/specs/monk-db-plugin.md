# Monk DB plugin — ChatGPT app, Muse connector, Claude connector (and every other store)

Owner: 参謀 · Status: both MCP endpoints live on aniccaai.com (Netlify); store listings pending · Updated 2026-10-23 23:55 JST

## 0. What exists today (read this first)

| Asset | Where | What it is |
|---|---|---|
| **AI Monk Database** (aniccaai.com/ai-monk-database) | `anicca-products` → `apps/landing/public/data/ai-monk-avatar-database-2026.json` (~200 KB, 75 records, 57 sources) | A directory of **AI monk video avatar accounts** (Yang Mun etc.): audience, views, revenue claims. Not teachings. |
| AI Monk Index CLI + MCP v0.4.2 | `anicca-products/packages/ai-monk-index` | Already has a **live remote MCP**: `https://aniccaai.com/.netlify/functions/ai-monk-mcp` (tools `search_ai_monks`, `get_ai_monk`, `ai_monk_index_stats`; verified `tools/list` 200 on 2026-10-23). Not listed in any store. |
| aniccaai.com/monk | `anicca-products/apps/landing/app/monk` | Sales page for *The Anicca Reset* ebook (49 chapters, $10.99). Paid content: **not** put in the free DB. |
| `/dais` card | `life-manager` branch `dais-ai-monk-db-pin` (2 commits ahead, 412 behind main) | Marketing card only, no data. |
| **Monk teachings DB (new)** | `life-manager/apps/monk-mcp` | This spec. Teachings by topic/teacher with sources. Seed: full Dhammapada (423 verses, CC0). |

**Decision (成田さん, 2026-10-23): the product is the AI Monk accounts database.** The plugin centres on the 75 AI monk avatar accounts and how they win: followers, formats, hooks, scripts, monetization and sources. The Dhammapada teachings server is a minor extra.

Live endpoints (no auth, free on the existing Netlify site):
- **AI Monk DB (main):** `https://aniccaai.com/.netlify/functions/ai-monk-mcp`. Tools: `search_ai_monks`, `get_ai_monk`, `ai_monk_index_stats`, plus `top_formats` (sampled videos ranked by dated views, with format/hook/script structure; PR anicca-products#605), `how_they_monetize` (offers, prices, seller counters, unaudited revenue claims; #605) and `winning_playbooks` (creator-published playbooks; #606).
- **Teachings (extra):** `https://aniccaai.com/.netlify/functions/monk-teachings-mcp`, with pages at aniccaai.com/monk-teachings/{privacy,terms,support} (#604).

Next DB enrichment: transcripts and scripts of the top sampled videos (fair-use excerpts plus our structure notes, never full re-uploads), posting-time patterns per account, and more creator playbooks found on X. The daily `ai-monk-database` Codex automation (Mac mini, 09:00 JST) owns the metric refreshes, so don't edit the same records in parallel.

## 1. Server (phase 1)

- One remote MCP server, stateless Streamable HTTP, `POST /mcp`, JSON responses, no auth, CORS open, 64 KiB request cap, no logging of queries (privacy).
- Tools (all `readOnlyHint: true, openWorldHint: false, destructiveHint: false`):
  - `search_teachings {query?, tag?, teacher?, collection?, limit≤25}`
  - `get_teaching {id}`
  - `daily_dhamma {date?}`: the same verse for everyone on a given day, which also feeds the monk avatar video.
- Every record: `id, title, collection, chapter, teacher, translator, text, tags, source_url, license`.
- Hosting (free): **Cloudflare Workers free plan** (100k req/day) at `anicca-monk-db.<acct>.workers.dev`, then custom domain `mcp.aniccaai.com`. Fallback: Netlify function on the existing aniccaai.com site (same pattern as `ai-monk-mcp`).
- Required public pages (all stores ask for them): privacy policy, terms, support contact, and a landing page at aniccaai.com/monk-db. Reuse the `/ai-monk-database/privacy` page pattern.

Copying the winners: the top ChatGPT/Claude directory apps of this type (reference/knowledge apps) are a few narrow read-only tools with good descriptions, citations in every result and no login. We do the same: no OAuth, so there is nothing for review to break.

## 2. Phase 2: the biggest, most detailed monk/dhamma database

Target: every teaching, with full text, talks and transcripts where the license allows, tagged by **topic, teacher, tradition, collection, language**, with a source and license on each record.

| Source | License | Use |
|---|---|---|
| SuttaCentral bilara-data (Sujato, Brahmali: DN, MN, SN, AN, KN, Vinaya), plus multilingual translations incl. JA | **CC0** | Full ingest; the core corpus (~tens of thousands of segments). |
| Access to Insight (Thanissaro, Bodhi excerpts, Nyanaponika, Wheel publications) | Mostly **CC BY-NC 4.0**; some items "free distribution" only | Ingest **only** items with an explicit CC BY-NC license; keep attribution. Keep NC items out of any paid tier. |
| dhammatalks.org (Thanissaro talks and transcripts) | Free distribution, **no** blanket license | Metadata plus links only, unless written permission is obtained. |
| Ajahn Chah / Forest Sangha free books | Mostly free distribution, CC BY-NC-ND on some | Metadata, link, short quote. Full text only where CC. |
| Wikisource / Pali Text Society pre-1929 translations (Rhys Davids, Müller Dhammapada 1881) | **Public domain** | Full ingest, labelled as historical translations. |
| YouTube talks (Ajahn Brahm, Thich Nhat Hanh, etc.) | Copyrighted | Index title, teacher, URL and topic only. **No** transcripts unless CC-licensed. |

Rules: store `license` per record; never mix NC content into anything paid; ND content is never modified (no summaries presented as the text); refresh with a weekly `scripts/build-data.py` run; publish the compiled DB as CC BY 4.0 (our tags) + the per-record source license. Add a `list_topics` / `list_teachers` tool when the corpus is larger than 5k records, plus server-side BM25 (still free on Workers with a prebuilt index in KV/R2 free tier).

## 3. Store submission: what each one needs

| Store | How | Needs from 成田さん | Review |
|---|---|---|---|
| **ChatGPT app directory** (Apps SDK = MCP) | platform.openai.com → plugin submission portal → MCP URL → Scan Tools → listing form | OpenAI Platform sign-in plus **individual identity verification** (ID check), `api.apps.write` role | Yes, timeline varies. Needs: name, logo, short/long description, category, website, support, privacy and terms URLs, tool annotations, **5 positive + 3 negative test cases**, starter prompts, countries, release notes, domain challenge at `/.well-known/openai-apps-challenge` (the Worker can serve it). After approval: click Publish. |
| **Claude connectors directory** | Anthropic remote MCP directory submission form (claude.ai → Connectors → "Submit") | Anthropic account sign-in, contact email | Yes. Needs: remote HTTPS MCP URL, tool annotations, privacy policy, support contact, usage examples, logo. Before listing, anyone can add it as a **custom connector** with the URL. |
| **Muse (Meta) connector platform** | platform.muse.ai → describe → submit for review | Meta developer account sign-in; accept Muse Connector Terms (effective 2026-09-18) | Yes: functional, security and legal review plus end-to-end testing. Needs: endpoint, auth = none, tool docs (inputs/outputs, read/write classification, rate limits, errors). Before approval, users can add it as a **custom connector**. Muse Code takes MCP directly. |
| Other free MCP directories | Official MCP Registry (`mcp-publisher`, GitHub sign-in), Smithery, mcp.so, Glama, PulseMCP, MuseDirectory.dev, Cursor directory, LobeHub | GitHub OAuth (mostly) | Light or none |
| Grok / xAI | Remote MCP is usable via the xAI API `mcp` tool; no public directory yet | none | none |

Contact email for all forms: use the private service configuration in the local credentials store.

## 4. Distribution plan

1. Launch day: X thread from @diceai0 (build in public: "I turned the Dhammapada into an MCP server, free, in ChatGPT/Claude/Muse"), plus a short demo GIF. Reply to MCP/ChatGPT-apps threads from the X growth playbook targets.
2. Directories: all the free MCP registries above on day 1; Product Hunt and Hacker News (Show HN) once the ChatGPT listing is live.
3. Existing loop: add the product to `skills/earn/marketing-engine/registry/products/` so the Postiz/TikTok/Instagram slots (`monk_anicca`, `monk.mujo`, 08:00/21:00 JST) rotate it in; link from /dais, /monk, the Daily Dhamma app and the Anicca Reset email.
4. SEO: one static page per teaching (`aniccaai.com/dhamma/dhp1`), generated from the same JSON, with a "use in ChatGPT/Claude" CTA.
5. **The AI Monk avatar promotes it.** After launch, the daily HeyGen monk video routine runs these scripts (≤20 s each, one per day, same voice/persona):

   - **Script A — "I live in ChatGPT now"**
     "Friends… I have news. I moved. I now live inside ChatGPT. Ask me about anger, grief, or why your phone is louder than your mind — I answer with the Buddha's own words, and I always show where they come from. Search 'Anicca Monk' in ChatGPT apps. No robes required."
   - **Script B — "Daily verse, any app"**
     "Every morning I pick one verse for the whole world. Today's is: *[daily_dhamma text]*. Want tomorrow's before I even wake up? Ask me in ChatGPT, Claude, or Muse: 'daily dhamma'. Yes, even monks have plugins now."
   - **Script C — "Ask me anything (seriously)"**
     "People ask me, 'Monk, are you real?' I am 2,500 years of teachings in one database. Real enough. Type any problem into ChatGPT or Claude with Anicca Monk connected, and I will find the verse for it. Try 'my boss'. I dare you."

## 4b. Shalev playbook (Yang Mun creator) and how it feeds our factory

Source: Shalev (@shalevhvs), *I Built a Fake AI Monk, Made $500K in 6 Months (Full Guide)*, X article, 2026-04-09 (https://x.com/shalevhvs/status/2042242260784537736), plus his 2026-09-08 "stages" thread and posts from 2026-09/10. All figures are his own claims and unaudited. It's stored in the DB as `playbooks[shalev-yang-mun-playbook]`.

- **Character:** looks different from the feed and carries authority. A monk in orange robes in a temple, photoreal ("unexpected + real"). Pick a niche where trust matters.
- **Script formula:** (1) 0–2 s: show you understand their pain, no judgment; (2) 2–5 s: flip it positive or promise a specific fix; (3) 20–40 s: teach ONE thing usable tonight; (4) last 3 s: an identity line ("The calm ones aren't lucky. They just learned this first.").
- **Winning hooks:** "If you're going to overthink… then overthink the positive." (24M views) and "How to fall asleep fast in two minutes even when your mind doesn't want you to." (6.5M views). Empathy reframe and solution hook.
- **Voice:** the exact same AI voice, speed and tone on every video.
- **Cadence:** 3 videos a day per character, native-uploaded to TikTok, IG Reels, YT Shorts and FB Reels at the same time through a scheduler.
- **Funnel and money:** content builds trust, then link in bio, then **digital products only** (no affiliates, sponsorships or ads). He claims $300K in 3 months and $500K in 6 months, sold one character for $170K, and now sells AI Growth Lab. Once a character works, he spins up 5 more in the same lane the same day.
- His thesis: "the script IS the business"; the tool doesn't matter.

**Applied to our monk factory** (`/workspace/marketing/monk-factory/monk_daily.py`; versioned copy in `apps/monk-mcp/factory/`):
- The default daily script now follows his 4-part formula. There are 7 weekday scripts: overthink-positive, 2-minute sleep, feelings-are-weather, approval, morning, anger, loneliness.
- Every video ends with a soft ebook CTA ("…it is in The Anicca Reset. Link in my bio.") and every caption carries the ebook line plus "Not medical advice". Before, the CTA ran on 2 of 7 days.
- The voice stays fixed (Simon, Calm & Gentle). The old banks are still reachable with `--topic db|art|truth|breath|letgo|night`. Hooks live in `sources/winning-hooks.json`.
- **Not changed yet:** cadence stays at 1 video a day (HeyGen budget guardrail, about $0.5/video). Moving to his 3/day across TikTok, IG, YT Shorts and FB costs about $45/month and needs the budget raised and YT/FB channels added in Postiz.
- **Ebook agent:** use `winning_playbooks` and `how_they_monetize` to write chapter hooks and the sales page. The winners sell $50–60 guided programs and bundles next to the $10.99 entry book (Yang Mun's 30-Day Healing Journey at $49.99 and Complete Collection at $59.99), so plan a $49 program as the upsell.

## 5. Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026)

Fit: yes, as a **Theme 1 ("bring Meta's models into your domain")** project, but only if Meta models are core. The hackathon requires building with Muse Spark / Muse Image / SAM 3.1 / Meta open weights / Muse Code. Entry idea: "AI Monk on Muse". Package this MCP server as a Muse connector, plus a Muse Spark–powered monk that answers only from cited teachings (RAG over this DB), plus Muse Image for daily verse cards. Track 2 (startup) fits Anicca. **Application deadline: Oct 25, 11:59 PM ET (= Oct 26, 12:59 JST)**, rolling cap of 20k. Apply now if not already done.

## 6. Blockers (human-only)

- Cloudflare (or Vercel) account sign-in for a free deploy. No hosting credentials are in the vault.
- OpenAI Platform identity verification (ID) for the ChatGPT directory.
- Anthropic and Meta developer sign-ins for the Claude and Muse submissions.
- Logo, privacy and terms pages for the new endpoint (agent can draft them in anicca-products/landing).
