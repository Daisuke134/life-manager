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
CP1_SHOT=$SHOT scripts/cp1_python.sh scripts/cp1_agent.py <cmd> ...
```
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

## The card has THREE tabs (top): verify each is green ✓
| tab | usually | what to do |
|---|---|---|
| 基本情報 | may still be red after init | fill every value from `<CONFIG_PATH>` (the path emitted by `publish_prepare.sh`): title, short/detailed descriptions, tags, category, icon, privacy URL, support email |
| Skill / プラグイン | auto-confirmed ✓ green (your skill shows 確認済み) | glance; leave |
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
6. Continue below the plan cards and fill the remaining required card fields from
   `<CONFIG_PATH>`: model, estimated runtime, **test input**, **welcomeMessage**,
   and AI provider. Leave **other third-party** data sharing unchecked unless the
   listing truly uses an additional service; when checked, its service name and purpose
   become required. Check the final **DPA** agreement checkbox.
7. Re-read all three tabs: every tab must be green. The `priceSvg` must contain
   **`61, 220, 132`** (green). If it's
   `229, 83, 75` (red), something is still empty/invalid — screenshot, find the red
   field, fix it. Do not proceed while red.
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
