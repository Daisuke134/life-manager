# Capafy BEST PRACTICES — the "brain" (proven across 13 live listings, 2026-06-25→27)

This is the knowledge that makes a listing **profitable AND rejection-proof**. Every rule here is
backed by real winner data (read via `vendor/capafy-user`) or a real publish/rejection we lived through.
`lint_listing.py` enforces the hard ones deterministically.

## 0. The ONE rule above all — WE COPY A WINNER VERBATIM
Originality = lost sales + rejection risk. For each new listing: search a proven seller, read its live
data (`GET /agent/agent/agents/<id>`), and **copy its pricing / trial / category / structure verbatim**.
Write original *words* (avoid plagiarism), copy the *facts/structure*. NEVER invent a price, cap, or
trial number "to be safe" — the winner already proved the numbers convert and the cap keeps cost < revenue.

## 1. SELLABLE TEST (decide before building)
- **run_online** (what we sell): buyer chats in a sandbox = model + pasted input only. No web/tool/
  account/browser/file/cron. Sellable iff full value lands from chat alone (humanizer, copy, slides,
  data-analyst, strategist). ❌ NOT: anything that acts on the world (publish/post/send/fetch) or claims
  live data — it does nothing in a sandbox and gets rejected.
- **download** (buyout): buyer runs the package in their own env; tools/browser OK. (Sell the
  auto-publisher itself this way, never as run_online.)

## 2. PRICING — copy the winner's ladder (observed real numbers)
Common shapes that sell (pick the one your winner uses; don't blend two):
| shape | example (real winner) | when |
|---|---|---|
| 2-tier week+month | Copyvert $2.99/wk · $6.99/mo · Unbot $5.99/wk·$19.99/mo | most writing skills |
| 3-tier day+week+month | Unscore (humanizer) $2.99/d·$5.99/wk·$19.99/mo · Viralpost $2.99/$5.99/$12.99 | high-frequency use |
| high-value 2-tier | Slides $9.99/wk·$24.99/mo · Best Data analysis $7.99/wk·$27.99/mo | deep/pro output |
- **cap (cycleMaxMessageCount)** is what keeps you profitable: cap × per-call cost << cycle price.
  Copy the winner's cap; don't raise it.
- Cheap impulse niches (cold email) run low (week $1.99 / month $5.99). Pro/analyst niches run high
  (month $24.99–27.99). Match the niche's proven band.

## 3. TRIAL config — copy the winner per-plan (this was a real CP1 blocker)
Each plan needs a trial CHOICE or the price tab stays invalid (red ✗) and submit no-ops.
Typical winning pattern (copy your winner's exactly):
- **day** plan → No Free Trial
- **week** plan → Enable Free Trial 24h or 72h
- **month** plan → Enable Free Trial 72h or 168h
(Unbot: day No / wk 72h / mo 168h. Unscore: day No / wk 24h / mo 72h. Copyvert: wk 24h / mo 168h.)

## 4. CATEGORY (use the winner's; JP labels in the CP1 dropdown)
writing→ライティング · research→リサーチ · marketing→マーケティング · social→ソーシャルメディア ·
productivity/slides→生産性 · data/analysis→分析 · image→画像 · commerce→コマース.
Copy the winner's `categoryId` intent; pick the matching JP label.

## 5. MODEL + LLM HOST (CP2)
- Display + host **Claude Sonnet 4.6** via **OpenRouter** (`anthropic/claude-sonnet-4.6`, format
  `openai-responses`, key `CAPAFY_HOST_OPENROUTER_KEY`). gpt-4o-mini display = nobody buys.
- Image skills: OpenAI `gpt-5` image_generation (displays "GPT Image 2"), key `CAPAFY_HOST_OPENAI_KEY`.
- Delete any blockrun/localhost card in CP2 (verification fails otherwise).

## 6. HONESTY = REJECTION-PROOF (the C4 lesson, enforced by lint_listing.py)
C4 "Deep Research" was REJECTED for advertising **live multi-source web retrieval** a pure-LLM sandbox
can't do. The fix (now a hard rule): describe ONLY what the model can do from its knowledge + the user's
pasted input. **Banned in buyer-facing copy** (the linter blocks these unless negated):
- live / real-time / up-to-date / browse / scrape / crawl / fetch / retrieval / "searches the web"
- "pulls from sources" / competitor data / posts to / schedules / sends email / uploads to
- .pptx / downloadable file (we output HTML/text, not binary files)
- guaranteed / undetectable / "bypass detector" / "X% increase"
Honest reframes that PASS: "from your input + model knowledge", "outputs self-contained HTML",
"reasons over the data you paste", "self-critiques its own draft", mark unknowns `[ADD: …]`/`[UNVERIFIED]`.

## 7. FIELD LIMITS (hard, linter-enforced)
- title ≤ 50 chars · shortDescription ≤ 500 chars (≤495 safe; em-dash counts as 1 codepoint, but Capafy's
  counter is the arbiter — the CP1 form shows red at >500).
- detailedDescription: emoji-headed sections (✨/⚙️/📦/💡/👤), a clear "how it works" numbered list,
  "what makes it different" (3 points incl. an Honesty point), "who it's for".
- welcomeMessage: 👋 + one-line "I do X" + an "Example:" line (build_config extracts the test input from it).

## 8. LISTING FILE SHAPE (so build_config.py can parse it)
`$LIFE_MANAGER_STATE_HOME/features/capafy-<name>/LISTING.md`:
- header line: `Primary Model: Claude Sonnet 4.6 · category: <JP> ... tags: a, b, c`
- a pricing table: `| cycle | price | cap | trial |` rows (trial = "No Free Trial" or "<N>h")
- `## Title` / `## shortDescription` / `## welcomeMessage` / `## detailedDescription`
(internal notes above `## Title` are NOT submitted — only the labeled sections are.)

## 9. REFERENCE — winners we cloned (verified live)
| ours | winner cloned | proof |
|---|---|---|
| O1 JP Humanizer | Unscore 4097802482 (19 sales) | day No / wk24 / mo72 trial |
| O2 Academic Humanizer | Unbot 2098780796 (9) | wk72 / mo168 |
| O3 Conversion Copywriter | Copyvert 4497373524 (5) | wk$2.99 / mo$6.99 |
| O4 Slide Maker | Slides maker 9991086787 (22) | wk$9.99 / mo$24.99 |
| O5 Data Analyst | Best Data analysis 8356434477 (18) | wk$7.99 / mo$27.99 |
| O6 Cold Email | Cold Email 8367499727 | wk$1.99 / mo$5.99 |
| O7 Social Post | Viralpost 7006047590 (14) | 3-tier |
| O8 Marketing Strategist | Marketing Strategy 9435156959 (9) | ★stripped its live-research overclaim★ |
| O12 Decision Debate | (gap-fill, no direct clone — see §10) | cloned O8's own pricing ladder |

## 10. MARKET SWEEP (2026-07-12, firecrawl `capafy.ai` homepage — trending tab)
Real trending listings observed (sold counts from the public homepage, not invented):
"Ocup Analysis" (football match analytics) 2,175 sold @ $3.99/day · "Serenity Stock Tracker"
(X-post stock-mention tracker) 431 sold @ $5.99/day · "Commerce Video" (photo→ad video) 84 sold ·
"AI Brainstorm: Ideas from Claude, ChatGPT & Gemini" (multi-model comparison) 11 sold. Takeaways:
(a) sports/finance "analysis" niches sell very high volume, but they lean on live-data framing we
cannot honestly claim in a pure-LLM `run_online` sandbox (§6) — do not clone the live-data claim,
only the STRUCTURE (structured report from a named subject). (b) The "AI Brainstorm" multi-model
niche shows real demand for multi-perspective output but is itself likely overclaiming literal
access to 3 separate frontier models from inside one sandbox call — our honest version (O12) is
ONE model performing distinct personas, which we must never describe as "multiple AI models" or
"queries Claude, GPT, and Gemini" (that would be the same overclaim, just relabeled). (c) None of
our 20 online listings do multi-perspective decision support — this was a genuine catalog gap,
now filled by O12.

## 11. MARKET SWEEP (2026-07-20, WebSearch — press/review coverage, not homepage scrape)
Press-cited flagship/most-promoted categories beyond what §10 covers (source: aixploria.com,
testingcatalog.com capafy launch coverage): compliance/ESG (a skill encoding 2026 CSRD/ESRS —
scoping, double materiality assessment, disclosure mapping, gap analysis, draft sustainability
statements, flags where auditor assurance needed) and video-hook optimization (rebuilds the first
3s of a video with an AI-crafted intro for TikTok/Reels/Shorts/paid social). Neither is in our 26
online listings — genuine gaps. Caveat before cloning either: compliance/ESG is a `run_online`-safe
structured-analysis task (matches §1) but video-hook optimization implies editing/outputting an
actual video file, which a pure-LLM sandbox cannot do (§6 download-file ban) — if built, frame it as
a *text* hook-script + shot-list generator from a pasted video description/transcript, never as
"we edit your video." No real sold-count data found for either (press coverage only, not a live
leaderboard) — do not invent sales numbers for these two.

## 12. MARKET SWEEP (2026-07-28, firecrawl search "capafy.ai top selling AI agent skills marketplace")
Homepage/search snippets (sold counts as shown, not invented): "Serenity Stock Tracker" 2,776 sold
4.6★ (X-post stock-mention tracker, same niche as §10's earlier 431-sold instance — confirms
sustained high volume). Video-generation skills built on "Seedance 2.0" cluster densely near the
top: "Viral Clone — Swap In Your Own" 96 sold 4.8★, "Drama Ads — Absurd Product Skits" 16 sold,
"Viralume — Viral Videos on Seedance" 36 sold 4.8★ — these output actual video via an underlying
video-gen model call, not a pure-LLM sandbox, so cloning the STRUCTURE (prompt template + shot
list) is honest but claiming literal video rendering is not (same §6 constraint as video-hook
optimization). Sports "analysis" niche keeps recurring: "Match Scout — World Cup, Premier League &
UCL" 12 sold, "Football Match Analyst" 9 sold — smaller than §10's Ocup Analysis but confirms the
niche is still active into World Cup 2026 season; same live-data honesty caveat as §10(a) applies.
New-to-us niche: HR/talent deck writer ("built more decks than I can count — talent reviews, hiring
cases, board updates") — text/structured-output only, `run_online`-safe, not yet in our 28 listings.
Takeaway: no fabricated "winner" this pass (sales_selector signal=none across our 28), so this sweep
is enrichment only per the loop contract — did not change which listing gets published this pass.

## 13. MARKET SWEEP (2026-09-28, WebSearch — public Capafy marketplace homepage)
The current public homepage search result displayed **CloneCut — Viral Clone, Seedance2.0** at **10.8k sold**, rated 4.5, at **US$12.50/month** (Capafy homepage search result, crawled 2026-09-27). This confirms sustained demand for short-form-video outcomes, but CloneCut explicitly relies on Seedance video generation and source-media transformation. A pure `run_online` Claude listing must not claim to render, edit, ingest, or remix video: the honest adjacent product is a text-only first-three-seconds diagnosis, hook rewrite, caption/title variants, and shot-list/prompt blueprint from a user-pasted transcript or brief. Source: https://capafy.ai/

## 14. MARKET SWEEP (2026-09-27, public Capafy homepage WebSearch)
The homepage's public trending results showed **CloneCut — Viral Clone, Seedance2.0** at 10.8k sold
($19.99/month), **Alpha Consensus — X's Best Traders** at 480 sold ($10.83/month), and **Odeo
Maker** at 39 sold. These are public listing observations, not evidence about our own sales. The
video leaders rely on a video-generation engine and Alpha Consensus describes live public-market
tracking, so neither literal service claim is valid for our pure-LLM run_online packages. Reuse
only the buyer job structure: an honest Hook Lab-style listing may turn a *pasted* transcript,
offer, or video description into text hooks, a shot list, and a self-critique; it must never claim
video rendering, live market data, X monitoring, or web retrieval.

## 13. MARKET SWEEP (2026-08-24, external WebSearch — Capafy homepage/search index)
The public marketplace result showed **"Commerce Video Ad Maker — Photos to Sales-Ready"** at 23 sold
for US$9.99/week, and **"Sales Enablement — Scale how your top rep sells"** at 1 sold for US$3.99/week.
The latter's public copy describes pasted product/buyer/proof inputs producing a pitch deck, one-pager,
objection handling document, demo script, sales playbook, buyer personas, and ROI calculator — evidence
that self-contained structured-output skills can sell without claiming external actions. Source:
https://www.capafy.ai/ (WebSearch 2026-08-24). This is marketplace evidence, not a claim about our own
sales. It does not override an attributable internal sales winner.
