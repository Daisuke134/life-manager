# CP1 — Agentic Agent-Card Save (two-layer: thin tool + YOUR eyes)

You are the JUDGMENT layer. `scripts/cp1_agent.py` is the thin DETERMINISTIC tool.
It performs ONE browser primitive per call against a LEASED CloakBrowser identity
and prints a screenshot path + a compact state readout. YOU look at the screenshot,
decide the next click/type, and call it again — LOOP until the real success signal
appears. **Never hardcode coordinates from this doc; they change. Read the
state/screenshot each step and decide.**

Why this exists: the old `drive_cp1.py` hardcoded DOM positions and silently broke
when Capafy changed the pricing widget (plan cards re-sort on period change → a
positional price/cap script scrambles values → price tab red → card never saves →
`is_confirmed_skills=false` → the daily loop STOPs). This procedure is robust to UI drift
because a human-like agent verifies each step by looking.

## Lease the browser — NEVER probe a port directly
Capafy's seller session lives on its own identity `capafy:kosuke` (declared
in `~/.config/ai/registry/browsers.toml`; override with `CAPAFY_BROWSER_IDENTITY`
only for a deliberately different leased identity). `cp1_agent.py` refuses to
guess a debugging port (the 2026-07-26 incident: `:9222` turned out to be a proxy
onto the SAME browser as production `:9223`, so two sessions drove one Chrome and
a save silently never landed). Wrap **every** call through
`skills/browser/with-browser.sh`, which acquires the identity for exactly that one
command, verifies its CDP UUID, exports `CLOAK_CDP_BASE_URL`/`CDP` for the child,
and releases on exit — you do not call `browser-guard.sh` yourself.

If the identity is busy (another loop is driving `capafy:kosuke` right now),
`with-browser.sh` waits up to `BROWSER_WAIT_SECONDS` (default 300s) and then exits
`75` — a retryable resource-busy signal, not a bug. Skip this pass and let the
next scheduled drainer run retry; do not fall back to a bare port.

## The tool (run with the resolved browser Python, under the lease)
```
SHOT=<scratchpad>/cp1.png
CP1_EXPECTED_MODEL="<the exact model in CONFIG_PATH>" \
CP1_SHOT=$SHOT \
  bash skills/browser/with-browser.sh capafy:kosuke -- \
  scripts/cp1_python.sh scripts/cp1_agent.py <cmd> ...
```
`CP1_EXPECTED_MODEL` bakes an `expectedModel`/`modelDropdownVisible`/`modelSelected`
readout into every `state`/`shot` call, IF a Primary Model dropdown exists on the
card. **Verified live 2026-09-28: the current Capafy card UI has no Primary Model
field anywhere in CP1** (checked every field on 基本情報 and 価格設定, both tabs,
full scroll). Displayed model comes from CP2 (`drive_checkpoint2.py` writes the
OpenRouter provider's model into the hosted LLM Config) — CP1 has nothing to select.
Treat `modelDropdownVisible: false` as the **expected, normal** reading, not a
blocker: do not withhold 下書きを保存/提出を確認 waiting for it. This exposure only
matters if Capafy reintroduces a model field on the card in the future; if you ever
see `modelDropdownVisible: true`, then do select the option matching
`CP1_EXPECTED_MODEL` before saving, using the coords in `markers['Primary Model']`.
`cp1_python.sh` selects a locally installed Python with both `playwright` and
`websocket` (normally `/opt/homebrew/bin/python3`) and fails clearly if none is
available. Override it only when necessary with `CP1_PYTHON=/path/to/python`.
Commands: `open <url>` · `shot` · `state` · `click <x> <y>` · `clicktext "<text>" [nth]`
· `fill <idx> "<v>"` · `typeinto <idx> "<v>"` · `press <key>` · `upload <idx> <path>`
· `scroll <dy>` (mouse-wheel; page uses an INNER scroll container, window.scrollTo is
useless) · `into "<text>"` · `toast` · `prices <LISTING.md>` (read-only pre-confirm
price gate — see the mandatory step before 提出を確認 below). After each call, **Read the screenshot** and use
the `fields`/`buttons`/`markers` coords (viewport-relative, map 1:1 to `click`).

## Success signal (the ONLY thing that means done)
- toast **「カードを保存しました」** (`toastOK:true`) or url→`cardDone:true`, AND
- server `publish-remote-status … latest_version.is_confirmed_skills == true`.
A green price tab alone is NOT done — you must still 提出を確認 and confirm the save.
The official Agent detail's `model` field is set by CP2, not CP1 — do not expect or
wait for it here; `publish_finish.sh` verifies it after CP2 runs.

## Switching an EXISTING agent's hosted model resets Skill confirmation
Re-running `publish_prepare.sh` with a different `model`/`model_id` (e.g. Sonnet →
DeepSeek on Agent 4243672453) makes Capafy treat it as a monetization/hosting
change: `is_confirmed_skills` resets to unset and a **third tab, "Agent
ワークスペース"**, appears showing "収益化モデルを切り替えたため、Skill 一覧と
キーのホスティングがクリアされました". Its instructional prompt is boilerplate
for a manual user with a different local tool; it does NOT require running any
extra CLI — `publish_prepare.sh`'s own `publish-init` rebind already re-registered
the skill server-side. What's actually needed is a plain UI click: open the tab,
find the skill card (title matches the skill dir name, badge says "保留中"
pending), and `clicktext` it once — the badge flips to "確認済み" and the tab
turns green. Do this before 価格設定/基本情報 will show correct saved values on a
fresh page load (a stale reused tab can show pre-reset cached values; always treat
the state right after `open` as ground truth, not what a moment-old screenshot
showed).

## The card has THREE tabs (top): verify each is green ✓
| tab | usually | what to do |
|---|---|---|
| 基本情報 | may still be red after init | fill every value from `<CONFIG_PATH>` (the path emitted by `publish_prepare.sh`): title, short/detailed descriptions, tags, category, icon, privacy URL, support email |
| Agent ワークスペース (Skill) | red after a model switch, else auto-confirmed ✓ | click the pending skill card once (see above) |
| 価格設定 | often **red ✗** — the real work | **always open it, even when green**, and set every plan card to the TARGET values (fix until GREEN) |

**An incomplete 基本情報 is work to do, never a reason to stop.** A resumed draft
(`resume_draft`, an orphan stub) usually opens with 基本情報 red and 提出を確認
disabled. Open 基本情報, fill every empty or red field from `<CONFIG_PATH>`, save the
draft, and continue with the remaining tabs. Stopping there leaves the draft holding
a review slot forever (2026-10-08: draft 9531771963 stopped twice on "基本情報 is
incomplete" while every new Agent waited for that slot). The only exception is the
price-only update recipe below, which leaves 基本情報 as-is.

**A green 価格設定 tab is not proof of the right price.** On 2026-09-29 the Hook Lab
reprice (agent 8123079349, v1.0.4) was saved with a green tab still holding the OLD
prices (day $1.99/week $4.99/month $9.99, no year row) and was approved that way; the
LISTING target was day $3.99/week $9.99/month $19.99/year $99.99. Every CP1 pass must
compare each card's Period/Price/Request-Limit/trial to the TARGET lines printed by
`publish_prepare.sh`, change any that differ, and add a missing plan (e.g. Yearly) with
"Add Plan". This is the only chance: after the card is confirmed Capafy issues no edit
URL. `scripts/verify_pricing.py --agent-id <ID> --listing <LISTING.md>` reads the saved
billing rows AFTER confirmation (right before CP3) and can only warn by then —
measured 2026-10-05 on YouTube Script Writer (agent 7686597754): CP1 switched cards
to week/month/year and saved month price=$9.99 (target $19.99) and year cap=8640
(target 720), and `publish_finish.sh`'s `PRICE_MISMATCH_WARNING` was the only signal,
with no edit URL left to fix it. **Use `scripts/cp1_agent.py prices <LISTING.md>`
instead, BEFORE confirming** (see the required gate before step 8 below) — it reads
the CURRENTLY OPEN card's plan cards directly (no server round-trip, no confirmation
needed first) and can still be fixed because the card is still editable.

## Fixing 価格設定 (the common breakage)
1. Read the exact URL bytes from `EDIT_URL_FILE` emitted by `publish_prepare.sh` and
   open that value. Do not reconstruct, append query parameters, or print the URL.
   Read the shot, then click the 価格設定 tab (find it in `buttons`/`markers`, click
   its coords).
2. Confirm 収益化モデル = **Capafy で実行** and Billing = **Subscription** and
   container mode = **On-Demand** are selected (orange). If not, click them.
3. `scroll` down to reveal the plan cards. Each subscription plan card = a Period
   dropdown (Daily/Weekly/Monthly/Yearly) + Price + Request-Limit + a 無料トライアル choice.
4. The init usually creates 3 cards (day/week/month) but with **scrambled or empty
   price/cap**. Set each to the TARGET printed by publish_prepare.sh. The price/cap
   inputs carry a unique per-period placeholder you can target precisely:
   `Daily → price ph "0.07", cap ph "50"` · `Weekly → "0.5" / "200"` · `Monthly → "2" / "500"`.
   (Confirm the placeholders in `state` before trusting them — if the UI changed,
   just read each card's visible Period label and fill that card's two number inputs.)
   **Use `typeinto`, never `fill`, for price and Request-Limit inputs.** Measured
   2026-10-05 on Hook Lab v1.0.5: `fill` (JS `.value` + dispatchEvent) showed the new
   price on screen, but the form's React state kept the old value, and the saved
   billing was still $1.99/$4.99/$9.99 — the same failure that let the 2026-09-29
   reprice go live at old prices. `typeinto` (CDP `Input.insertText`) updated the
   preview price immediately and saved correctly. After saving, run
   `scripts/verify_pricing.py --agent-id <ID> --listing <LISTING.md>`; on
   `PRICING_MISMATCH` re-open the edit URL (`publish_prepare.sh` re-issues it) and
   re-enter the prices with `typeinto`.
   The card has exactly three plan cards and no "Add Plan" button (2026-10-05). Use each
   card's Period dropdown to make the three cards match the LISTING table — normally
   Weekly / Monthly / Yearly (the top Capafy subscription sellers use exactly these three,
   no Daily). Re-check every card's Period, Price and Request-Limit after switching, since
   cards can re-sort when a period changes.
5. Each plan needs a trial choice (required). Read the TARGET line printed by
   `publish_prepare.sh` for that plan's `trial=` value:
   - `trial=No Free Trial` → click **"No Free Trial"**.
   - `trial=Free Trial <H>h / <N> requests` → click **"Enable Free Trial"**, which
     reveals a duration field and a free-request-count field; fill them with the
     printed `<H>` and `<N>` exactly, then re-check the 価格設定 tab is still green.
     If the revealed fields don't match what you expect (wrong units, missing
     field, still red after filling), do NOT block the submission on it — fall
     back to **"No Free Trial"** for that plan and note why in your report.
6. Below the plan cards there may be more required fields (test input, AI
   provider, third-party data sharing, DPA checkbox) depending on the exact
   card version Capafy renders for this Agent — **verified 2026-09-28: none of
   these exist on Agent 4243672453's card**, only "Add Plan"/"Add one-time
   pack" buttons after the last plan. Always re-run `state` after the last
   plan card to see what's actually there before assuming a field from an
   older doc revision still exists; do not block on a field you cannot find.
7. Re-read all tabs: every tab must be green (基本情報 / Agent ワークスペース /
   価格設定 — see above if a hosted-model switch put a 4th requirement on the
   workspace tab). The 価格設定 tab's `priceSvg` should NOT contain
   `229, 83, 75`/`255, 106, 43` (red/orange = invalid); if it does, something
   is still empty/invalid — screenshot, find the red field, fix it.
8. **Mandatory gate — run `scripts/cp1_agent.py prices <LISTING.md>` and read its
   exit line BEFORE clicking 提出を確認. Never confirm the card on a `PRICES_MISMATCH`.**
   This re-reads the plan cards exactly as they currently stand (after any period
   switches) and prints `PRICES_MATCH <n>` or `PRICES_MISMATCH <cycle: field
   target=… actual=…; …>`. On `PRICES_MISMATCH`:
   - For each named cycle, re-find that card by its CURRENT Period label (`state`),
     not by its earlier screen position — cards re-sort when a period changes, so
     "the second card" can silently become a different plan after any switch.
   - `typeinto` the correct value into that card's price/Request-Limit input (never
     `fill` — see the measured React-state gotcha above).
   - Re-run `prices` and repeat until it prints `PRICES_MATCH`. Only then proceed.
   - `<cycle>: missing` means that plan card has not been entered on this new
     version yet (a same-Agent update draft starts with no saved billing). It is
     the normal starting state, not a reason to stop: open 価格設定, add / switch a
     card to that Period, `typeinto` its price and Request Limit from TARGET
     PRICING, then re-run `prices`. Stopping on a mismatch leaves the draft
     occupying a review slot and the update never ships (2026-10-07: TikTok
     Script Pro update stopped on `day: missing; week: missing; month: missing`).
9. Click **下書きを保存** (save draft) → then **提出を確認** (confirm). Read the shot:
   you want the 「カードを保存しました」 card-done page.
10. Verify server-side: `packager.py publish-remote-status --agent-id <ID>` →
   `latest_version.is_confirmed_skills == true`. Only then is CP1 done; hand off to
   `publish_finish.sh` with the exact `AGENT_VERSION_ID` emitted by prepare.

## Guardrails
- One capafy tab: `cp1_agent.py` reuses an existing capafy tab or opens a NEW one.
  NEVER hijack a daily-driver tab (coconala/discord/etc) — its watchdog reverts the
  URL and your work vanishes. Never close the daily-driver.
- If a click seems to do nothing, Read the screenshot — the layout probably moved.
  Re-target from the fresh `fields`/`buttons` coords. Do not blindly retry old coords.

## Download-mode price-only update (one-time fee, no hosted model)
`build_config.py` emits `"pricing_mode": "download"` when the LISTING.md pricing
table has a single `| download | $X | - | - |` row instead of day/week/month. This
is the CP1 recipe for a same-Agent `target_one_time_fee` update (added 2026-09-28
to fix agent 3332784488 shipping with billings=download/price=null — confirmed via
`publish-remote-status`: agent_type=download, is_confirmed_config_keys=false).
1. On 基本情報, leave every field (title/short/detail/logo) AS-IS — a price-only
   update never touches Basic Info. Do not re-upload a logo.
2. On 価格設定, the billing-mode card should already show **Download** selected
   (it is the Agent's existing type). If it shows Subscription instead, STOP and
   report — do not toggle modes for a price-only update (toggling
   download↔run_online rolls the version back to draft and clears the confirmed
   skill selection; see PUBLISHING_RUNBOOK.md "UPGRADING a LISTED download agent").
3. Set the **oneTimeFee** field to the exact value from `CONFIG_PATH`'s
   `one_time_fee` (e.g. `9.99`). Check the Data Processing Agreement checkbox if
   present and unchecked.
4. No CP2 for Download mode — go straight from CP1 card-done to
   `publish_finish.sh`, which skips key hosting for a null `model`/`model_id`.
5. Verify via `publish-remote-status`: `latest_version.is_confirmed_skills=true`
   and (after finish) the billings row shows the new price — `billings=null`
   still visible means the price did not save; re-open Pricing and retry.
