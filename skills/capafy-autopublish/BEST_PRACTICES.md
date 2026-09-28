# Capafy BEST PRACTICES — the "brain" (proven across 13 live listings, 2026-06-25→27)

This is the knowledge that makes a listing **profitable AND rejection-proof**. Every rule here is
backed by real winner data (read via `vendor/capafy-user`) or a real publish/rejection we lived through.
`lint_listing.py` enforces the hard ones deterministically.

## 0. The ONE rule above all — WE COPY A WINNER VERBATIM
Originality = lost sales + rejection risk. For each new listing: search a proven seller, read its live
data (`GET /agent/agent/agents/<id>`), and **copy its price / cap / category / structure verbatim**.
Write original *words* (avoid plagiarism), copy the *facts/structure*. NEVER invent a price or cap
"to be safe" — the winner already proved the numbers convert and the cap keeps cost < revenue.
Follow the free-trial DEFAULT in §3 for new skills rather than copying a winner's exact trial value.

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

## 3. TRIAL config — new skills default to a trial (2026-09-28 policy, supersedes the old paid-only rule)
Measured 2026-09-28: every seller with revenue in our own catalog is short-form/recurring-input content
(Hook Lab, Slide Maker, Marketing Strategist, TikTok Script Pro, YouTube Script Writer), the marketplace
winners in those verticals nearly all carry a free trial, and 69 of our 98 historical units were free-trial
units before we banned trials outright. Banning trials cost us conversion volume for no measured benefit.

**New skills** (not yet published): set a trial on the **week** and **month** plans; the **day** plan
stays **No Free Trial** (day-plan buyers are already impulse-converting, a trial there just delays revenue).
Defaults unless a specific winner's data says otherwise:
- week plan: `Free Trial 24h / 3 requests`
- month plan: `Free Trial 72h / 5 requests`

`lint_listing.py` and `build_config.py` accept exactly two trial cell shapes: `No Free Trial` or
`Free Trial <hours>h / <N> requests` (e.g. `Free Trial 24h / 3 requests`); anything else is rejected.
`build_config.py` emits `{"trial": {"hours": H, "requests": N}}` or `null` per plan.

**Already-published skills are never retroactively edited** to add a trial — touching a live agent's
pricing config is out of scope for routine catalog work (would require a CP1 edit + re-review on an
Agent that is already earning). Only NEW skills use this default.

See `CP1_AGENTIC.md` §"Fixing 価格設定" for how the agent enables the trial in the CP1 UI and what to
do when the revealed fields don't match the target.

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
- header line: `Primary Model: DeepSeek V4.1 Flash · category: <JP> ... tags: a, b, c` (new skills default to DeepSeek V4.1 Flash — cheaper hosted model, see `build_config.py MODEL_IDS`; already-published Sonnet skills are not migrated)
- a pricing table: `| cycle | price | cap | trial |` rows (trial = `No Free Trial` or
  `Free Trial <hours>h / <N> requests`; see §3 for the new-skill default)
- `## Title` / `## shortDescription` / `## welcomeMessage` / `## detailedDescription`
(internal notes above `## Title` are NOT submitted — only the labeled sections are.)
- optional `Demand rank: <int>` line (lower = publish first; `inventory_status.py` sorts
  `create_fresh` candidates by this instead of alphabetically; missing = published last).

## 9. REFERENCE — winners we cloned (verified live)
| ours | winner cloned | proof |
|---|---|---|
| O1 JP Humanizer | Unscore 4097802482 (19 sales) | historical: day No / wk24 / mo72 trial |
| O2 Academic Humanizer | Unbot 2098780796 (9) | historical: wk72 / mo168 trial |
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

## 13. MARKET SWEEP (2026-09-28, own-seller + marketplace revenue audit) — WINNER FAMILY SUPPLY
Measured, not invented: every one of our own listings with actual revenue is short-form creator
content — Hook Lab (hooks, $34.88), Slide Maker, Marketing Strategist, TikTok Script Pro, YouTube
Script Writer. Marketplace winners cluster in the same families: hook optimization, finance summaries,
sports analysis, video, priced $9.99–27.99/month, most with a free trial (see §3). Portfolio Tracker
(stock tracking, 781 sold at $9.99/wk) is the highest-demand qualifying vertical not yet in our catalog
after football fixture analysis — both are now `Demand rank`ed (see §8) to publish before anything else.

**Next candidates, in priority order, are variants inside these already-proven families — not novel
categories:**
1. Hook Lab variants for a specific platform or niche (Reels, YouTube Shorts, ads, podcasts,
   newsletters) — same recurring-input shape (buyer pastes new raw footage/topic each time), new
   audience.
2. Finance summaries (earnings/market recap style, not stock-tracking — that's Portfolio Tracker).
3. Sports analysis beyond football fixtures (a different league/sport with the same weekly-fixture
   recurring-input shape as `football-match-analyst`).
Use **DeepSeek V4.1 Flash** as Primary Model (§5's cheaper default) and set the trial per §3.

### Description template (derived from Hook Lab's live listing style)
Use this shape for every new listing in this family — outcome headline, buyer identity, 3 concrete
outcomes, one real example, then the plan table:
```
## Title
<Outcome-first name — what the buyer gets, not the model or method>

## shortDescription
<one sentence: the outcome + the recurring input the buyer pastes each time>

## welcomeMessage
👋 I <do X> from your <pasted input>. Example: "<a real, specific example input>"

## detailedDescription
✨ What you get
- <concrete outcome 1>
- <concrete outcome 2>
- <concrete outcome 3>

⚙️ How it works
1. Paste your <input> (new each time — <what changes>).
2. I <transform/analyze/generate> it into <output shape>.
3. You get <deliverable> ready to use.

💡 Example
Input: "<real pasted input>"
Output: "<real generated output, trimmed to the essential lines>"

👤 Who it's for
<buyer persona 1>, <buyer persona 2>, <buyer persona 3>.

Honesty: <what this does NOT do — no live data / no posting / no file export, per §6>.

| cycle | price | cap | trial |
|---|---:|---:|---|
| day   | $X.XX | N | No Free Trial |
| week  | $X.XX | N | Free Trial 24h / 3 requests |
| month | $X.XX | N | Free Trial 72h / 5 requests |
```
