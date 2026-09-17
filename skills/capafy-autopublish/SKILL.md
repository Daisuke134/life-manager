---
name: capafy-autopublish
description: >
  THE single skill to publish profitable, rejection-proof skills to the Capafy
  marketplace end-to-end, verification-baked. Load this one skill and you can:
  pick a proven-profitable niche, generate the skill, write a best-practice listing,
  publish it (CP1 card + CP2 LLM-key host + CP3 submit) via the CloakBrowser
  daily-driver, and verify it (linter + browser + remote-status). Use for ANY
  Capafy publishing. This skill VENDORS the Capafy CLIs internally — never invoke
  capafy-publisher / capafy-user directly; everything routes through here.
---

# capafy-autopublish — one skill, full Capafy publishing + verification

★ This is the ONLY Capafy skill to invoke. ★ It vendors the Capafy seller CLI
(`vendor/capafy-publisher`) and the market-search CLI (`vendor/capafy-user`).
Other Claude instances: do NOT use those two directly — use this skill.

## What sells on Capafy vs what does not (read first)
Capafy has two agent types:
- **run_online** (cloud_hosted, subscription): the buyer CHATS with the skill in a
  **sandbox** — only the model + what the buyer pastes. NO web, tools, accounts,
  browser, files, or cron. **Sellable test:** "Does the buyer get full value by
  chatting, from model + pasted input alone?" YES → sellable.
  - ✅ humanizer, copywriter, slide-maker (HTML), data-analyst (pasted data), strategist
  - ❌ photo-publisher, auto-poster, scheduler, "researches the web/competitors"
    (sandbox can't act on the world or browse → useless / gets REJECTED, see C4).
- **download** (buyout, one-time): the buyer runs the package in THEIR own env — can
  include tools/browser. (The auto-publisher itself could be sold this way, not run_online.)

We publish **run_online subscription** skills that are sandbox-complete and
retain positive contribution after hosted model cost.

## Canonical publish flow (verification-baked)
Use the split, 0.9.11-compatible flow:

```
scripts/publish_prepare.sh <skill-dir> <LISTING.md> <icon.png>
→ `AGENT_ID` + `AGENT_VERSION_ID` + `EDIT_URL_FILE` / CP1_AGENTIC.md + cp1_agent.py (agentic card confirmation)
→ scripts/publish_finish.sh <agent-id> <skill-name> <LISTING.md> <agent-version-id>
```

The sequence is **Phase A discovery → confirmed selection/init → CP1 →
ordinary `publish-submit --action prepare` → strict same-Agent `security_ready`
readback → `publish-submit --action continue_upload` exactly once → final review
page CP2 → the same or refreshed `publish` review page CP3 exactly once → official
remote verify → ledger**. Fail closed at every step:
the finish wrapper requires `is_confirmed_skills=true`, validates the same Agent ID and
final review URL, polls CP2 config readback, and exits 0 only on
`platform_status=1 ∧ is_confirmed_config_keys=true`.

The deterministic wrapper never invents deep-scan findings or retries an uncertain
upload; a creator-approved agentic deep scan is outside this wrapper and must
complete before returning to ordinary prepare.

`scripts/publish_one.sh` is a legacy unsupported/reference-only no-op shim. Do not
invoke it; use the split flow above.
The browser opens only the exact URL read from `EDIT_URL_FILE`; do not reconstruct or
print it. After the split flow prints ✅, **you still do the browser render check yourself**
(HARD 0.31/0.38), then commit+push the ledger.

## Verification policy (verification is mandatory — anything unverified is slop)
1. **lint_listing.py** (embedded, every publish, fail-closed) — rejection-proof:
   blocks overclaim phrases (browse/scrape/fetch/live/real-time/retrieval/posts/
   sends/.pptx/guaranteed/undetectable…) unless negated, and enforces title≤50 /
   short≤500 / pricing table. This is the C4-rejection learning, made deterministic.
2. **VCSDD adversary** (`vcsdd:vcsdd-adversary`) — spawn for RISKY listings only
   (anything the linter can't judge: subtle retrieval/tool/guarantee claims). Pure
   writing skills can skip it.
3. **browser + remote-status** (me, every publish) — render check + publish-remote-status
   real data (status=1 ∧ cfg=1 ∧ run_online ∧ title ∧ model ∧ pricing).

## How to add ONE new listing (the repeatable recipe)
1. **Pick a winner**: `vendor/capafy-user/scripts/capafy_http.py POST /agent/agents/search`
   (X-Access-Token header) → find a proven seller; GET `/agent/agent/agents/<id>` for its
   pricing/category/structure. Copy facts verbatim; write original words. The paid-only policy
   below overrides any winner free-trial field.
2. **Build the skill** under `$LIFE_MANAGER_REPO/skills/<name>/` (pure-LLM, sandbox-complete,
   honest; no web/tool/account claims). Add `test/case1.md`. Grep for leaks (CLEAN).
3. **Write the listing** `$LIFE_MANAGER_STATE_HOME/features/capafy-<name>/LISTING.md` with the
   header (Primary Model / category / tags), a pricing table copied from the winner with
   `No Free Trial` on every plan, and
   `## Title / ## shortDescription / ## welcomeMessage / ## detailedDescription`.
4. **Icon**: reuse the owner-controlled listing icon when available; otherwise create a suitable 512px asset.
5. **Lint**: `scripts/lint_listing.py <LISTING.md>` until PASS.
6. **Review**: check the exact listing, package model/cap, and same-Agent version binding.
7. **Publish**: run `scripts/publish_prepare.sh <skill-dir> <LISTING.md> <icon>`,
   complete CP1 from `CP1_AGENTIC.md`/`cp1_agent.py`, then run
   `scripts/publish_finish.sh <agent-id> <skill-name> <LISTING.md> <agent-version-id>` → status=1.
8. **Browser-verify** + record in `state/published.jsonl` + commit+push.

## Hard-won rules (full detail in PUBLISHING_RUNBOOK.md)
- **ECONOMICS**: price/cap must retain positive hosted contribution; every plan uses `No Free Trial`.
- **LEAK GUARD**: publish from the isolated Agent HOME/workspace emitted by prepare, never the operator's live workspace.
- **LLM host (CP2)**: use the exact OpenRouter model ID and output cap from the listing contract, format `openai-responses`, key `CAPAFY_HOST_OPENROUTER_KEY`; delete any blockrun/localhost card.
- **CP1 15 gotchas** baked into `cp1_agent.py` (RHF element.fill, real mouse clicks,
  unique title, 下書き persist, monetization heading-click, Subscription scroll, provider
  field, per-plan trial = No Free Trial, On-Demand, DPA checkbox, price-tab SVG green,
  get_by_text form-mount, anchored Add Plan). See RUNBOOK §"NEW-AGENT CP1".
- **Cap**: max 5 unlisted (status 0-3) at once; publish-init fails when full. status=4 frees a slot.
- **Browser**: CloakBrowser daily-driver (CDP :9222), never close it (HARD 0.39).

## Folder map
```
capafy-autopublish/
├── SKILL.md (this) · BEST_PRACTICES.md · PUBLISHING_RUNBOOK.md
├── scripts/ publish_prepare.sh · publish_finish.sh · daily_loop.sh
│            · select_publish_agent.py · build_publish_selection.py
│            · save_review_url.py
│            · lint_listing.py
│            · build_config.py · cp1_agent.py
│            · drive_checkpoint2.py · drive_checkpoint3.py · niche_picker.py · logo_gen.js
├── vendor/  capafy-publisher/ (packager.py = Capafy seller CLI, self-updating)
│            capafy-user/      (capafy_http.py = market search CLI)
└── state/   published.jsonl (ledger)
```
Canonical copy lives in `$LIFE_MANAGER_REPO/skills/capafy-autopublish`; no repo-external skill mirror is an execution source.
