# Writer Loop on Life Manager Main Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints. The installed Writer owner performs external effects; the development session never publishes in its place.

**Goal:** Make the existing Life Manager Writer owner publish one localized article per day through the active-four contract, extend it to Dev.to and Zenn after replay-zero, prove every result with native readback and truthful money receipts, and reproduce the same loop for an isolated local OSS owner.

**Architecture:** Reuse the single skills/writer-agent implementation and config/loop-registry.json. Follow the existing main cursor W2 → W21: close capacity/demand/generation first, then publish Note, Substack JA/EN, and X Article JA independently, prove replay-zero/reporting, add discovery surfaces, close money and learning, and only then package self-owned OSS. Eight workstreams may prepare independently in isolated branches, but shared state, account/browser effects, release application, and external publication stay serialized by their natural owners.

**Tech Stack:** Bash 3-compatible entrypoints, Python 3 standard library, SQLite ledgers, JSON/JSONL receipts, macOS launchd through bin/lm-loop, immutable Life Manager releases, provider-neutral Browser ACI, and the existing test runners. No new package or parallel scheduler.

**Spec:** docs/superpowers/specs/2026-09-17-writer-loop-life-manager-main-design.md

## Global Constraints

- Daisuke134/life-manager on origin/main is the only source authority; use a linked worktree from current origin/main before editing.
- docs/ARTICLE-LAUNCH-TODO.md is the execution cursor. W0/W1 are complete; W2 is the first unfinished item. Do not reorder it or revive historical queues.
- The one Writer implementation lives under skills/writer-agent. Do not create a second executor, scheduler, state tree, money ledger, or provider-specific fixed workflow.
- The binding active-four contract is Note JA, Substack JA, Substack EN, and X Article JA. Dev.to EN and Zenn JA are an independent discovery extension after active-four replay-zero.
- Start at one source article per JST day with independent JA/EN localization. Existing eight-hour beats handle recovery, money, learning, health, and reporting; cadence expansion requires recorded stability evidence.
- Only the installed natural owner performs provider mutations. Manual browser/API work is diagnostic evidence and cannot satisfy publication acceptance.
- Native URL/readback, immutable artifact identity, effect-ledger row, Telegram message ID, and replay-zero are required before claiming publication. Pending, draft, paywall, view, like, checkout, or process exit is not an external effect or payment.
- Money uses non-test external transaction, fee, refund, payout, renewal, and attribution receipts. Unknown stays unknown; one-time revenue never enters MRR.
- Preserve credentials, browser profiles, private state, active/loaded/open releases, and historical receipts. Never delete .openclaw, profitable-claude, or sibling-loop state.
- During Writer work, never apply or restart ai.anicca.life-manager-connector-native.
- Before authentication or payment preflight, inspect the private credential SSOT; never copy credential values into code, logs, plans, commits, or chat.
- Every production mutation uses bin/lm-loop; raw launchctl, Terminal/AppleScript bypasses, host restart, swapfile deletion, and sibling-owner restart are prohibited.

## File and ownership map

| Area | Files | Responsibility |
|---|---|---|
| Cursor/release | docs/ARTICLE-LAUNCH-TODO.md, config/loop-registry.json, config/writer/runtime-manifest.json, bin/lm-loop, bin/cut-loop-release.sh | one order and one source/release/argv/state lineage |
| Generation/capacity | skills/writer-agent/article-daily.sh, scripts/writer_capacity_floor.py, scripts/claim_supply.py, scripts/demand_card.py, scripts/gpt_image_headline.py | measured floor, payer-backed demand, unique topic, Image API receipt |
| Recovery | scripts/article-resume-pending.sh, scripts/article_daily_start_control.py, scripts/article_generation_state.py, scripts/quality_repair_control.py, scripts/quality_self_heal.py | same-run adoption and bounded repair |
| Publishers | scripts/publication_resume.py, scripts/note-publish/, scripts/substack-publish/, scripts/x-publish/, scripts/devto-publish/, scripts/zenn-publish/ | provider effect and native readback |
| Observability | scripts/writer_observability_trace.py, scripts/article-completion-notify.py, scripts/writer_report.py, scripts/writer_report_worker.py, scripts/article_weekly_audit.py | event graph, Telegram/report truth, dedupe |
| Economics | scripts/money_ledger.py, scripts/money_sync.py, scripts/writer_stripe_sync.py, scripts/artifact_attribution.py, config/revenue-surfaces.json | received money, fees/refunds/payouts, MRR, attribution |
| Learning/OSS | scripts/writer_learning_experiment.py, scripts/writer_learning_worker.py, scripts/self_improve_control.py, scripts/opportunity_*.py, reference/proven-writer-money-playbook.md, scripts/self_owned_article.py, install.sh | experiments, opportunities, and clean owner-isolated install |

## Common task protocol

Every code task uses a separate linked worktree from the latest origin/main and a scripts/worktree-lease.py lease. Write a focused failing fixture, run it red, patch only the named boundary, run the focused suite, run syntax and git diff --check, commit, push, and record evidence. Do not cut or apply a release until the branch is integrated through the normal repository path. Every operational task records source SHA, immutable release SHA, loaded ProgramArguments, state root, owner/lease state, terminal event, provider readback, and effect IDs outside Git.

### Task 1: Bind the current cursor and production owner

**Files**
- Read: docs/ARTICLE-LAUNCH-TODO.md, docs/superpowers/specs/2026-08-20-writer-loop-life-manager-consolidation.md, config/loop-registry.json, config/writer/runtime-manifest.json
- Read: bin/lm-loop, scripts/verify-source-boundary.sh, scripts/worktree-lease.py
- Evidence outside Git: ~/.local/state/life-manager/evidence/writer-plan-20260917/preflight.json

**Interfaces**
- Consumes current origin/main, the 14 Writer registry rows, loaded owner definitions, and private Writer state.
- Produces a SHA-bound preflight receipt naming the actual W2 run/cursor, leases, loaded release paths, state root, and sibling-loop invariants.

- [ ] Step 1: Verify repository and branch boundary.

~~~
git fetch origin main
bash scripts/verify-source-boundary.sh
git rev-parse HEAD origin/main
git status --short --branch
git worktree list --porcelain
~~~

Expected: canonical Life Manager origin, clean task worktree, and current origin/main recorded.

- [ ] Step 2: Assert the Writer registry is complete without mutating it.

~~~
python3 - <<'PY'
import json
from pathlib import Path
rows = json.loads(Path("config/loop-registry.json").read_text())
writer = [
    v for v in rows.values()
    if v.get("domain") == "earn"
    and str(v.get("label", "")).startswith(("ai.anicca.article-", "ai.anicca.writer-"))
]
assert len(writer) == 14, len(writer)
assert {v["state_root"] for v in writer} == {"~/.local/state/life-manager/writer"}
print("writer_labels=14 state_root=shared-writer-root")
PY
~~~

- [ ] Step 3: Capture read-only doctor/status and the actual run cursor.

~~~
bin/lm-loop doctor all > /tmp/writer-doctor-before.json
bin/lm-loop status all > /tmp/writer-status-before.json
python3 - <<'PY'
import json
import pathlib
import subprocess
out = pathlib.Path.home() / ".local/state/life-manager/evidence/writer-plan-20260917"
out.mkdir(parents=True, exist_ok=True)
payload = {
    "source_sha": subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip(),
    "doctor_before": pathlib.Path("/tmp/writer-doctor-before.json").read_text(),
    "status_before": pathlib.Path("/tmp/writer-status-before.json").read_text(),
}
(out / "preflight.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(out / "preflight.json")
PY
~~~

Expected: no historical run is assumed current; the private state is authoritative.

- [ ] Step 4: Read owner and lease evidence. If a Writer owner is active, do not kickstart it; pass its exact run ID into Task 2.

### Task 2: Close W2 capacity, demand, and headline generation

**Files**
- Modify only if a focused regression fails: skills/writer-agent/scripts/writer_capacity_floor.py, skills/writer-agent/article-daily.sh, skills/writer-agent/scripts/claim_supply.py, skills/writer-agent/scripts/demand_card.py, skills/writer-agent/scripts/gpt_image_headline.py
- Test: skills/writer-agent/tests/test_publication_guard_disk.py, test_gpt_image_headline.py, test_claim_demand_normalization.py, and new test_writer_w2_capacity.py
- Evidence outside Git: private capacity receipts, run directories, and evidence/writer-w2/

**Interfaces**
- Consumes resolve_disk_floor_bytes(state_dir), claim_supply.py --db --queue --receipt, gpt_image_headline.generate(...), and article-daily preflight.
- Produces a hash-bound demand card, unique topic/run, exact Image API intent/receipt, and a natural canary terminal event or truthful blocker.

- [ ] Step 1: Add a production-shaped failing fixture. Assert malformed capacity receipts, a lower environment override, duplicate selected observation IDs, a headline candidate without a receipt, and a delivery-unknown Image API result all fail closed.

~~~
def test_w2_boundaries_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTICLE_DISK_MIN_FREE_BYTES", "1")
    with pytest.raises(CapacityFloorError):
        resolve_disk_floor_bytes(tmp_path)
    with pytest.raises(HeadlineImageRefused, match="reconcile-before-retry"):
        generate(prompt_path=prompt, alt_path=alt, candidate=candidate,
                 intent_path=intent, receipt_path=receipt, opener=unknown_opener)
~~~

- [ ] Step 2: Run the red fixture.

~~~
python3 -m pytest -q skills/writer-agent/tests/test_writer_w2_capacity.py skills/writer-agent/tests/test_gpt_image_headline.py skills/writer-agent/tests/test_claim_demand_normalization.py
~~~

Expected: the new assertions fail at the described boundary.

- [ ] Step 3: Implement the smallest root-cause change. Keep writer_capacity_floor.py as the single floor resolver; reject malformed receipts and floor-lowering overrides. Normalize demand observation IDs before card validation. Preserve Image API intent-before-request and receipt-before-replay; never retry an unknown delivery without reconciliation. Keep article-daily returning the inner provider/capacity code.

- [ ] Step 4: Run green focused tests and syntax.

~~~
python3 -m pytest -q skills/writer-agent/tests/test_writer_w2_capacity.py skills/writer-agent/tests/test_publication_guard_disk.py skills/writer-agent/tests/test_gpt_image_headline.py skills/writer-agent/tests/test_claim_demand_normalization.py
bash -n skills/writer-agent/article-daily.sh
python3 -m py_compile skills/writer-agent/scripts/writer_capacity_floor.py skills/writer-agent/scripts/claim_supply.py skills/writer-agent/scripts/demand_card.py skills/writer-agent/scripts/gpt_image_headline.py
~~~

- [ ] Step 5: Commit and push.

~~~
git diff --check
git add skills/writer-agent/article-daily.sh skills/writer-agent/scripts/writer_capacity_floor.py skills/writer-agent/scripts/claim_supply.py skills/writer-agent/scripts/demand_card.py skills/writer-agent/scripts/gpt_image_headline.py skills/writer-agent/tests/test_writer_w2_capacity.py
git commit -m "fix(writer): close capacity and demand canary gates"
git push -u origin HEAD
~~~

- [ ] Step 6: After integration, cut one immutable release and apply only article-daily through bin/lm-loop. Read back release SHA, ARTICLE_ROOT, ARTICLE_SKILL_DIR, LIFE_MANAGER_REPO, state root, and rollback release before waking it.

- [ ] Step 7: Run exactly one natural W2 canary. It must create a non-duplicate topic, JA/EN artifacts, and a GPT Image 2 receipt with model gpt-image-2-2026-04-21, x-request-id, request/prompt/response/file hashes, 1536x1024, alt text, and rights provenance. Capacity/provider absence is a persisted blocker, not a fabricated article.

### Task 3: Publish and read back Note JA (W3)

**Files**
- Modify only if the focused contract fails: skills/writer-agent/scripts/publication_resume.py, scripts/publish-note-managed.py, scripts/note-publish/publish-paid.py, scripts/note-publish/verify-note.py
- Tests: test_note_paid_publish_readback.py, test_note_422_publish_only_surface.py, test_note_live_media_recovery.py, publish-note-managed-contract.sh
- Evidence outside Git: current run publication-state.json, articles.jsonl, Note provider receipt, effect ledger

**Interfaces**
- Consumes the W2 run note/ja intent and stable artifact hash.
- Produces a Note native live receipt with public URL, owner, title/body hash, authenticated price/paywall, eyecatch, body-media evidence, and one effect ID.

- [ ] Step 1: Run the existing success/refusal fixtures. A draft/autosave or HTTP 422 must not set state=live.

~~~
python3 -m pytest -q skills/writer-agent/tests/test_note_paid_publish_readback.py skills/writer-agent/tests/test_note_422_publish_only_surface.py skills/writer-agent/tests/test_note_live_media_recovery.py
bash skills/writer-agent/tests/publish-note-managed-contract.sh
~~~

- [ ] Step 2: If a live-shape regression is missing, add one assertion set.

~~~
assert receipt["state"] == "live"
assert receipt["live_url"].startswith("https://note.com/")
assert receipt["content_verified"] is True
assert receipt["monetization_verified"] is True
~~~

- [ ] Step 3: Let article-resume perform the real Note effect through bin/lm-loop. Read the authenticated Note API and anonymous public HTML for the same stable target. An editor overlay, autosave, or selected price without public readback remains intent.

- [ ] Step 4: Save W3 evidence and update only the W3 cursor row with URL, owner, artifact hash, paywall/price, media hashes, effect ID, source/release SHA, and terminal event. Revenue remains unknown until purchase/payout evidence.

### Task 4: Publish and read back Substack JA/EN (W4/W5)

**Files**
- Modify only if the focused contract fails: skills/writer-agent/scripts/publication_resume.py, scripts/publish-substack-managed.py, scripts/substack-publish/substack_refresh_intent.py, scripts/substack-publish/verify-preview.py
- Tests: publish-substack-managed-contract.sh, test_substack_http.py, test_substack_refresh_boundary.py, test_publication_identity_contract.py
- Evidence outside Git: authenticated publication/profile receipts, public URLs, publication-state.json, effect ledger

**Interfaces**
- Consumes substack/ja and substack/en intents from the same W2 artifact pair.
- Produces two distinct native live receipts with publication IDs/hosts, language, paid-audience state, body/media hashes, and effect IDs.

- [ ] Step 1: Run the identity-isolation fixtures. Missing identity, equal JA/EN identities, draft-only response, or a URL assembled from an expected host must refuse.

~~~
bash skills/writer-agent/tests/publish-substack-managed-contract.sh
python3 -m pytest -q skills/writer-agent/tests/test_substack_http.py skills/writer-agent/tests/test_substack_refresh_boundary.py skills/writer-agent/tests/test_publication_identity_contract.py
~~~

- [ ] Step 2: Verify identity before upload or PUT. Require SUBSTACK_PUBLICATION_JA and a distinct SUBSTACK_PUBLICATION_EN. Resolve publication_id through the authenticated publication profile; do not reuse the historical mixed publication.

- [ ] Step 3: Let the natural resume owner publish each pair independently. A JA failure cannot cancel EN and EN cannot rewrite JA. Persist live, pending, blocked, or terminal with pair-specific reason and retry owner.

- [ ] Step 4: Read back both public URLs and append W4/W5 evidence: owner, publication identity, language, paid audience/paywall, artifact hash, body/media, public HTML, effect ID, and duplicate check.

### Task 5: Publish and read back X Article JA (W6)

**Files**
- Modify only if the focused contract fails: skills/writer-agent/scripts/publication_resume.py, scripts/x-publish/x_anchor.py, scripts/x-publish/x_chunked.py, scripts/x-publish/x_fullverify.py, scripts/x-publish/x_inplace_repair.py
- Tests: existing X parser/readback tests under skills/writer-agent/tests/, test_publication_identity_contract.py, platform-dispatch-isolation.sh
- Evidence outside Git: authorized Writer Browser ACI session on CDP 9222, stable edit URL, public Article URL, rendered-body/media receipt

**Interfaces**
- Consumes the W2 JA artifact and X Article JA intent.
- Produces an X native live receipt with owner, immutable body hash, readable body-media projection, cover, public URL, and effect ID.

- [ ] Step 1: Run parser/media and isolation tests before editing.

~~~
python3 -m pytest -q skills/writer-agent/tests/test_publication_identity_contract.py
bash skills/writer-agent/tests/platform-dispatch-isolation.sh
~~~

- [ ] Step 2: Use the existing Writer Browser ACI on CDP 9222 and the authorized job-search profile; never use the Coconala 9223 profile. Re-observe after every meaningful UI transition.

- [ ] Step 3: Verify body-media readability before publish. Reject projection outside the existing 110–650px rendered range and reject missing/mismatched image count without clicking Publish.

- [ ] Step 4: Let article-resume publish the stable X target and read it back. An editor URL alone remains intent.

### Task 6: Prove observability, replay-zero, and Telegram truth (W7)

**Files**
- Modify only if focused tests fail: writer_observability_trace.py, article-completion-notify.py, writer_report.py, writer_report_worker.py, article_weekly_audit.py, article_completion.py
- Tests: test_public_effect_predicate.py, test_writer_observability_trace_portable.py, test_writer_report_truth.py, self-improve-notification-wiring.sh
- Evidence outside Git: effect ledger, provider mutation logs, report snapshot, Telegram message IDs

**Interfaces**
- Consumes the four native publication receipts and the run/effect ledger.
- Produces an append-only receipt graph, a truthful report with unknown revenue when no payment exists, a Telegram delivery receipt, and a second-wake effect=0 proof.

- [ ] Step 1: Run the public-effect and report suite. Four pending rows must be false; published=true, nonempty live_url, state=live, and reality_gate=PASS must be true.

~~~
python3 -m pytest -q skills/writer-agent/tests/test_public_effect_predicate.py skills/writer-agent/tests/test_writer_observability_trace_portable.py skills/writer-agent/tests/test_writer_report_truth.py
~~~

- [ ] Step 2: Wake the natural resume owner once with unchanged state; capture pre-wake effect IDs and provider mutation counts.

- [ ] Step 3: Wake it a second time and compare receipts. Require identical URLs/effect IDs, no new model recovery receipt, no duplicate publication row, and a terminal second-wake event.

- [ ] Step 4: Deliver through the repository-owned Telegram transport. Require a real message_id, semantic-hash dedupe, natural-language status, publication URLs, remaining blockers, and money unknown/zero truth.

### Task 7: Add Dev.to EN and Zenn JA discovery extension

**Files**
- Modify only if existing adapters fail: scripts/publish-devto.sh, scripts/devto-publish/devto.py, scripts/publish-zenn.sh, scripts/zenn-publish/, scripts/zenn-deferred-control.py, scripts/zenn-deferred-worker.py
- Tests: test_devto_tags.py, test_zenn_checkout.py, zenn-deferred-terminal.sh, zenn-deferred-retry.sh
- Evidence outside Git: Dev.to/Zenn native URLs or provider-specific pending/terminal receipts

**Interfaces**
- Consumes the W2 artifact pair after active-four receipts and Task 6 replay-zero.
- Produces independent Dev.to EN and Zenn JA discovery intents, native readback, and no revenue credit.

- [ ] **Step 1: Run existing extension tests.**

~~~
python3 -m pytest -q skills/writer-agent/tests/test_devto_tags.py skills/writer-agent/tests/test_zenn_checkout.py
bash skills/writer-agent/tests/zenn-deferred-terminal.sh
bash skills/writer-agent/tests/zenn-deferred-retry.sh
~~~

- [ ] **Step 2: Register one stable key per run_id + artifact_id + destination with the existing effect fence.** Do not add a selector list, DOM script, or scheduler.

- [ ] **Step 3: Let the natural owner publish/read back each extension.** A provider window becomes pending and never blocks the active-four revenue set.

### Task 8: Close demand, winner observations, and one-variable learning (W8-W12)

**Files**
- Create: skills/writer-agent/config/winner-observation.schema.json
- Modify: scripts/writer_learning_experiment.py, scripts/writer_learning_worker.py, scripts/self_improve_control.py, reference/proven-writer-money-playbook.md
- Test: skills/writer-agent/tests/test_winner_observation.py and test_writer_learning_experiment.py

**Interfaces**
- Consumes demand cards, native publication receipts, costs, and money snapshots.
- Produces immutable winner observations and experiments with one changed field, held-out replay, matched canary, and later production consumption.
- The new validator is `writer_learning_worker.validate_winner_observation(value: Mapping[str, Any]) -> dict[str, Any]`; it returns a normalized immutable observation or raises `ValueError`.

- [ ] **Step 1: Write failing schema tests.** Require source, timezone-aware observed_at, evidence excerpt and SHA, fact_or_inference, transfer_hypothesis, variable, baseline/candidate references, and KEEP/REVERT/INCONCLUSIVE. Reject absent or self-asserted evidence.

~~~
def test_winner_observation_requires_provenance():
    with pytest.raises(ValueError, match="evidence_sha256"):
        validate_winner_observation({"source": "x"})
~~~

- [ ] **Step 2: Run red, implement the schema through the existing content-addressed ExperimentStore, then run green.**

~~~
python3 -m pytest -q skills/writer-agent/tests/test_winner_observation.py skills/writer-agent/tests/test_writer_learning_experiment.py
~~~

- [ ] **Step 3: Connect the winning mechanism to the Agent prompt.** It may change exactly one of topic, headline, offer, price, preview, or channel; deterministic code validates the boundary but never chooses the method.

- [ ] **Step 4: Record later-run consumption.** KEEP changes a later production prompt, REVERT restores the prior strategy, and INCONCLUSIVE cannot promote a unit.

### Task 9: Reconcile money and attribution (W13-W16)

**Files**
- Modify only when a receipt shape is unrepresentable: scripts/money_ledger.py, scripts/money_sync.py, scripts/writer_stripe_sync.py, scripts/artifact_attribution.py, config/revenue-surfaces.json
- Test: create skills/writer-agent/tests/test_money_sync.py and extend test_writer_report_truth.py
- Evidence outside Git: provider transaction, fee, refund, payout, subscription, attribution receipts, and money.sqlite3

**Interfaces**
- Consumes Note/Substack/editorial/self-owned provider receipts and artifact index rows.
- Produces idempotent money.sqlite3 rows for verified received money and active subscriptions, with one-time revenue separate from MRR.

- [ ] **Step 1: Add fixtures for received, pending, test, refund, fee, payout, and active/canceled subscriptions.** Every fixture includes external receipt ID, source URL, currency, occurred timestamp, artifact or account scope, and test flag.

- [ ] **Step 2: Run the red money suite.**

~~~
python3 -m pytest -q skills/writer-agent/tests/test_money_sync.py skills/writer-agent/tests/test_writer_report_truth.py
~~~

- [ ] **Step 3: Implement only missing typed bindings.** Reject test/internal/estimated money, deduplicate external IDs, subtract fees/refunds, preserve source currency, and count MRR only for active external subscriptions or recurring writing retainers. Pending and available are never received.

- [ ] **Step 4: Run sync/report against private state and read back the first non-test payment.**

~~~
python3 skills/writer-agent/scripts/money_sync.py --state-dir "$HOME/.local/state/life-manager/writer"
python3 skills/writer-agent/scripts/writer_report.py --state-dir "$HOME/.local/state/life-manager/writer" --cadence daily
~~~

Expected before payment: truthful zero or unknown, with no synthetic revenue row. W16 closes only after official transaction → artifact → fee/refund/payout → attribution evidence.

### Task 10: Operate the daily loop and sequential economic gates

**Files**
- Read/update only the current cursor/evidence sections in docs/ARTICLE-LAUNCH-TODO.md and docs/superpowers/specs/2026-08-20-writer-loop-life-manager-consolidation.md
- Read config/loop-registry.json, article_weekly_audit.py, writer_report_worker.py, money_ledger.py
- Evidence outside Git: daily runs, native receipts, reports, payment ledger, FX receipts

**Interfaces**
- Consumes publication/report receipts and money events.
- Produces seven consecutive daily active-four receipts, the 14-day learning/cost observation, and S0-S4 milestone receipts.

- [ ] **Step 1: Observe seven natural JST daily runs.** For each run record unique topic, JA/EN hashes, four native URLs, terminal event, Telegram message ID, effect count, and provider errors. A missed run is repaired by the same owner; it is not replaced by a new identity.

- [ ] **Step 2: Run weekly audit/report and verify all seven rows.**

~~~
python3 skills/writer-agent/scripts/article_weekly_audit.py --help
python3 skills/writer-agent/scripts/writer_report.py --state-dir "$HOME/.local/state/life-manager/writer" --cadence weekly
~~~

- [ ] **Step 3: Operate the optional three-slot W7c experiment only after official HubPages/Kompasiana eligibility, payout, policy, and account receipts. Use separate topics/runs; otherwise keep those surfaces discovery-only.**

- [ ] **Step 4: Close S0 first payment, S1 at least $400/month, S2 at least $1,000/month plus three positive-net weeks, S3 at least $10,000 gross/net-positive attributed month for three consecutive months, and S4 at least $10,000 active MRR with renewal/churn/fee/refund/payout evidence for three consecutive months. Missing FX remains unknown.

### Task 11: Package the proven loop for an independent local owner (W19-W20)

**Files**
- Modify: install.sh, skills/writer-agent/SKILL.md, skills/writer-agent/scripts/self_owned_article.py, config/writer/runtime-manifest.json
- Tests: test/install-isolation.test.mjs, test/oss-self-contained.test.mjs, test_portable_publisher_identity.py, and new test_writer_owner_isolation.py
- Documentation: README.md, README.ja.md, and public evidence index only after receipts exist

**Interfaces**
- Consumes Dais-proven source/release schemas and publication/money contracts.
- Produces a clean install with device-generated owner identity/publication/payment destination, isolated state, idempotent rerun/rollback, and an independent owner's real publication/payment/report/restart receipts.

- [ ] **Step 1: Add the two-owner isolation fixture and run the baseline.**

~~~
node --test test/install-isolation.test.mjs test/oss-self-contained.test.mjs
python3 -m pytest -q skills/writer-agent/tests/test_portable_publisher_identity.py skills/writer-agent/tests/test_writer_owner_isolation.py
~~~

- [ ] **Step 2: Run red, implement the smallest path resolver/identity boundary using existing self-owned article and installer code, then run green.**

- [ ] **Step 3: Verify a fresh install, second-install idempotency, rollback preservation, state modes, and hashes in two temporary LIFE_MANAGER_HOME roots.**

- [ ] **Step 4: Let the independent owner produce a public URL, a non-test external payment, a local report, and restart/replay-zero without the product developer choosing topics, publishing, repairing, or reconciling that owner's work.

- [ ] **Step 5: Document setup/KYC/provider requirements, costs, rollback, measured Dais evidence, and the absence of a universal $10K guarantee.**

### Task 12: Final acceptance and handoff

**Files**
- Read/update: docs/ARTICLE-LAUNCH-TODO.md, docs/superpowers/specs/2026-08-20-writer-loop-life-manager-consolidation.md, config/writer/runtime-manifest.json
- Read: all task receipts, merged commit, release manifest, bin/lm-loop doctor/status/watch

**Interfaces**
- Consumes all focused test output, immutable release receipt, natural-owner terminal events, native provider readbacks, money ledger, Telegram IDs, replay-zero, daily evidence, and independent-owner evidence.
- Produces a requirement-by-requirement acceptance report and a clean pushed integrated branch. The goal remains open while any required external money or independent-owner gate is unproven.

- [ ] **Step 1: Run the integrated lifecycle checks.**

~~~
python3 -m pytest -q skills/writer-agent/tests/test_prepublication_adoption.py skills/writer-agent/tests/test_article_resume_prepublication_adoption.py skills/writer-agent/tests/test_article_daily_start_control.py skills/writer-agent/tests/test_public_effect_predicate.py skills/writer-agent/tests/test_writer_report_truth.py
python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'
node --test apps/life-manager/lib/loop-adapter-registry.test.js
bin/lm-loop doctor all
git diff --check
~~~

- [ ] **Step 2: Verify source/release lineage.** Read source SHA, immutable release SHA/tree hash, all 14 Writer loaded ProgramArguments, state root, rollback target, owner leases, latest terminal event, and unchanged Connector argv. Unknown launchd readback keeps acceptance open.

- [ ] **Step 3: Verify external contract.** Check active-four native URLs/readbacks, Dev.to/Zenn extension results, report message IDs, effect IDs, duplicate count, money receipts, and per-owner attribution. List PASS, FAIL, PENDING, UNKNOWN, and NOT CHECKED separately.

- [ ] **Step 4: Update only cursor rows with current evidence.** Preserve history; do not mark complete from a plan, draft, PID, screenshot, or process exit.

- [ ] **Step 5: Push and finish only after acceptance is true.** Keep the worktree until integration, release readback, and leases are resolved; remove only this exact clean, merged, unused worktree.

## Plan self-review

- The plan follows the main cursor W2-W21 and uses only files present in Life Manager main.
- Active-four, Dev.to/Zenn extension, and dormant platform boundaries are explicit.
- Each code task names files, interfaces, tests, expected red/green behavior, and a commit boundary.
- Operational tasks require natural-owner effects and native provider readback; no manual publication substitute exists.
- Money, MRR, daily reliability, and independent-owner OSS are separate evidence gates with no universal income claim.
- No step adds a framework, duplicate pipeline, unbounded retry, or destructive cleanup.
