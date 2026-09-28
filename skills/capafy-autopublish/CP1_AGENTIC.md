# CP1 — Agentic Agent-Card Save (two-layer: thin tool + YOUR eyes)

You are the JUDGMENT layer. `scripts/cp1_agent.py` is the thin DETERMINISTIC tool.
It performs ONE browser primitive per call against the running CloakBrowser
daily-driver (CDP :9222) and prints a screenshot path + a compact state readout.
YOU look at the screenshot, decide the next click/type, and call it again — LOOP
until the real success signal appears. **Never hardcode coordinates from this doc;
they change. Read the state/screenshot each step and decide.**

Why this exists: the old `drive_cp1.py` hardcoded DOM positions and silently broke
when Capafy changed the pricing widget (plan cards re-sort on period change → a
positional price/cap script scrambles values → price tab red → card never saves →
`is_confirmed_skills=false` → the daily loop STOPs). This procedure is robust to UI drift
because a human-like agent verifies each step by looking.

## The tool (run with the resolved browser Python)
```
SHOT=<scratchpad>/cp1.png
CP1_EXPECTED_MODEL="<the exact model in CONFIG_PATH>" \
CP1_SHOT=$SHOT scripts/cp1_python.sh scripts/cp1_agent.py <cmd> ...
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
useless) · `into "<text>"` · `toast`. After each call, **Read the screenshot** and use
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
| 価格設定 | often **red ✗** — the real work | fix the plan cards until GREEN |

## Fixing 価格設定 (the common breakage)
1. Read the exact URL bytes from `EDIT_URL_FILE` emitted by `publish_prepare.sh` and
   open that value. Do not reconstruct, append query parameters, or print the URL.
   Read the shot, then click the 価格設定 tab (find it in `buttons`/`markers`, click
   its coords).
2. Confirm 収益化モデル = **Capafy で実行** and Billing = **Subscription** and
   container mode = **On-Demand** are selected (orange). If not, click them.
3. `scroll` down to reveal the plan cards. Each subscription plan card = a Period
   dropdown (Daily/Weekly/Monthly) + Price + Request-Limit + a 無料トライアル choice.
4. The init usually creates 3 cards (day/week/month) but with **scrambled or empty
   price/cap**. Set each to the TARGET printed by publish_prepare.sh. The price/cap
   inputs carry a unique per-period placeholder you can target precisely:
   `Daily → price ph "0.07", cap ph "50"` · `Weekly → "0.5" / "200"` · `Monthly → "2" / "500"`.
   (Confirm the placeholders in `state` before trusting them — if the UI changed,
   just read each card's visible Period label and fill that card's two number inputs.)
5. Each plan needs a trial choice (required). **"No Free Trial" is the safe, proven
   default** (Enable Free Trial reveals extra required fields). Only set trials if the
   target explicitly asks and the tab stays green after.
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
8. Click **下書きを保存** (save draft) → then **提出を確認** (confirm). Read the shot:
   you want the 「カードを保存しました」 card-done page.
9. Verify server-side: `packager.py publish-remote-status --agent-id <ID>` →
   `latest_version.is_confirmed_skills == true`. Only then is CP1 done; hand off to
   `publish_finish.sh` with the exact `AGENT_VERSION_ID` emitted by prepare.

## Guardrails
- One capafy tab: `cp1_agent.py` reuses an existing capafy tab or opens a NEW one.
  NEVER hijack a daily-driver tab (coconala/discord/etc) — its watchdog reverts the
  URL and your work vanishes. Never close the daily-driver.
- If a click seems to do nothing, Read the screenshot — the layout probably moved.
  Re-target from the fresh `fields`/`buttons` coords. Do not blindly retry old coords.
