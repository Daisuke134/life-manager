# Manager current execution plan — 2026-10-25

This is an execution-oriented view of the existing roadmap, not a second task ledger. **`docs/roadmap/tasks.json` remains the only status/dependency source.** Keep its original task IDs and receipts; do not mark a task complete because code exists, a draft was written, or the public website changed.

## Current state

| Area | Verified state | What that evidence does not prove |
|---|---|---|
| E01–E15 | Source implementation and prior CI receipts recorded in Manager verification docs. | Production operation or human outcomes. |
| E16 source | E16 code fix commit `72f1c4150d549e25f98fa0220bffd7c06ba592d9`; current PR #8527 head `ea27aef0b1d41b6297ac9e15b6ae07238fffcbb0`. Product CI run `40160504641` and browser CI run `40160504639` succeeded; canonical worktree Python suite: 730 passed, 5 skipped. | Main promotion, Railway deployment, a live canary, external commit/readback, or restart/restore/replay-zero. |
| Git integration | PR #8527 targets research PR #8526. #8526 is `CONFLICTING` against `research/manager-product-r006-20261020`; no associated open PR for that base branch was found. | A usable promotion path to `main`. The source chain is the first blocker to resolve. |
| Railway | Railway selected; existing `life-manager` project is known. | A dedicated Manager worker, persistent volume, owner secrets, staging preflight, or production operation. |
| Public website | PR #711 merged as `989f027f4990db5a66c97905384ca242bb263cbb`; Netlify run `40159524904` succeeded. `/en`, `/ja`, `/blog/manager`, release JSON, and latest articles read back successfully; all 67 article routes and 34 media hashes matched their manifests. | E16 deployment, model quality, behavior change, welfare improvement, customers, or revenue. |
| Original roadmap | 113 tasks: 69 done, 41 todo, 3 skipped. | The E16 implementation sequence is not an extra 16 tasks. The 41 items are still the original product/research/operations acceptance gates. |

The website has published the accumulated research more fully, but it remains a communication surface. The Manager strategy is behavior simulation, evaluation, and intervention, including persuasion as one candidate intervention. The existing `manager-support/` site is a bounded engineering testbed for E16, not the definition of the final entity or proof of behavior change.

## Order of work

### 1. Repair the Git promotion path before cloud deployment

1. Inspect PR #8526 conflicts against its base and decide the intended release base. Its base branch has no associated open promotion PR, so do not assume merging #8526 or #8527 would put E16 on `main`.
2. Preserve the E16 commits while resolving the stack onto a path that reaches current `main` through the repository’s normal review. Re-run `bash scripts/verify-source-boundary.sh`, Manager tests, `python scripts/check_boundaries.py`, `python scripts/make_roadmap.py --check`, and the required GitHub CI on the exact resulting commit.
3. Promote the reviewed source to `main`. E16’s protected publisher accepts `main`; a research-branch CI result is not release evidence.

**Pass condition:** the exact E16 source SHA is on the approved release path and the required checks are green. Until then, Railway setup must remain isolated and non-writing.

### 2. Create and verify the isolated Railway staging runtime

1. Keep current services intact. Create a dedicated `manager-owned-digital-worker` with `rootDirectory=products/manager`, `deploy/owned-digital/Dockerfile`, one replica, an hourly schedule, and a persistent `/data/manager` volume.
2. Set the expected Railway project/environment/service/volume identity and owner configuration. Keep Railway’s dispatch credential separate from GitHub’s protected `MANAGER_OWNER_ID` and `MANAGER_RELEASE_ENABLED` values. Set a numeric spend ceiling and explicit stop/disable procedure before any live call.
3. Run the runtime preflight read-only. Check the actual mounted volume, permissions, single-owner lock, health/termination behavior, backup/isolated restore, and source/release identity. A successful plugin connection or service creation is not a deployment receipt.

**Pass condition:** only the named staging runtime passes read-only identity and persistence checks; every wrong or missing identity fails closed.

### 3. Run one reviewed, one-shot canary and prove recovery

1. Dispatch one exact main-SHA workflow request through the protected publisher. Bind the request to the owner, current `gh-pages` parent, verified artifact and the existing seven-file allowlist.
2. Record the exact request/run IDs and provider commit. Independently fetch the deployed public bytes and compare every allowed file/hash; verify unrelated paths did not change.
3. Test duplicate request, timeout/unknown response, process restart, volume restore, one-slot catch-up, and replay-zero. Reconcile the original occurrence before any new request. Any unresolved state stays `UNKNOWN` and stops dispatch; never retry to make the dashboard green.

**Pass condition:** P1 publisher receipt and P2 independent readback match, recovery receipts are complete, and no unauthorized path or duplicate effect occurred. Only then review E16 acceptance and production promotion.

### 4. Complete the Phase06 evidence gates in their declared order

1. **F005:** exact authorized commit + independent public GET, replay-zero, unrelated paths unchanged. Human benefit remains `NOT_MEASURED`.
2. **F006:** versioned before/after, comparator, missingness, costs, harms and evidence level. Do not invent a confidence interval without an appropriate sample.
3. **F008:** second owned information-access surface with its own URL, hash, independent readback and recovery proof.
4. **F009:** integrate the two P2 technical cases using the same kernel and describe limits. Two pages are not two human experiments.

### 5. Make the behavior-change thesis testable while E16 is being prepared

Run discovery and literature/data-rights work in parallel with the engineering gates, but do not claim an intervention result. Select one specific behavior and lived outcome, population/context, intervention class, comparator, time horizon, data rights, and harm/stop criteria. Use existing publications, public/licensed datasets, code and benchmarks first; add only the missing adapter or test. Treat persuasion as a method to evaluate, not a score to maximize.

The current U002/U003 backlog language still centers the public-support wedge. If the first market is behavior-evaluation or intervention research, update those task scopes and their acceptance criteria in `tasks.json` through a dated scope amendment before counting interviews or a pilot toward them. The amendment must preserve old wording and status history. Interview actual stakeholders (researchers/operators/affected people as appropriate); do not substitute synthetic personas or web research for customer evidence.

For the first behavior benchmark, freeze scenario families and held-out groups; separate desired response, observed behavior, persistence, lived outcome, autonomy, fairness and adverse effects. Compare NO_ACTION, a deterministic baseline, and existing models/providers on equal information and disclosed cost. Synthetic respondents are P0. Use an existing benchmark where its construct and license fit; create a new case only for a documented gap. Do not infer population effects from model preference or simulation accuracy.

### 6. Run user validation, a permitted pilot and outcome readback

- **U002 → U003:** gather at least five consented stakeholder interviews across the roles in the chosen wedge, compare present alternatives/costs, and select or reject the first use case.
- From **U003**, do **U004** (pre-register target, unit, comparator, duration, outcome, harms and stop rule) and **U005** (read-only proof explorer with provenance/P0–P2 distinctions) in parallel where their listed dependencies allow.
- **U006 → U007 → U008:** only after the required permissions and F005/F006 evidence, retain one authorized pilot’s external receipt; independently evaluate outcomes and missingness; then verify repeat-use/payment intent, actual invoices/payments/refunds/costs, and revenue coverage separately.

**Pass condition:** a negative, null, mixed, or unknown result is retained; no receipt, interview, model output or intent is counted as a human benefit or revenue without its own evidence.

### 7. Finish the original Phase09 branches and join at D016

The original roadmap still defines these branches; complete them in dependency order unless a later scope amendment formally retires one:

- **Finance:** D001 → D002 → D003 → D004; D004 also requires U007.
- **Indoor environment:** D005 → D006 → D007 → D008 → D009; D009 also requires U007.
- **Income/work evidence:** D011 → D012.
- **Public-interest collaboration and protection:** D014 → D015.
- **Join:** D016 requires D015, D012 and D009. Do not add D004 as a dependency; the canonical graph does not.

D005–D009 are not prerequisites for the first behavior-evaluation release, but they remain `todo` in the canonical source and block D016/V001 in the full original completion graph. If the decided scope is to remove indoor air/energy/noise measurement from Manager’s intended program, the next planning patch must explicitly retire/re-scope these tasks and update D016/V001 dependencies, the scope amendment, and generated roadmap together. Do not describe the full 113-task roadmap as complete while leaving that branch unresolved.

### 8. Build and validate the benchmark; train only after the evidence gate

After D016 and K014, follow **V001 → V002 → V003 → V004 → V005 → V006**: common adapter contract; independent scoring of behavior prediction/intervention effects/readback/harms; held-out and out-of-distribution design; shadow-to-limited-canary promotion; rights-cleared reproducibility package; and portfolio-level evidence including failures and costs.

**Model plan:** first compare existing API and open-weight models plus simple baselines. Fine-tune only if (a) a repeatable failure is measured, (b) licensed/consented training data exist, (c) train/dev/test groups and an untouched holdout are frozen, and (d) evaluation covers benefit, autonomy, harm and cost. Start with a small SFT/adapter experiment; consider preference optimization only with reviewed preference data and a valid target. Foundation pretraining is a later, separate decision requiring sufficient rights-cleared data, measured advantage and sustainable compute economics. There is no model-training task in the current canonical ledger, and no training date should be promised before these gates pass.

### 9. Complete YC, publishing, and long-term governance on their own evidence

- **YC/outreach:** Y003 follows Y002; Y005 follows Y004; C002 follows F006; Y008 follows both Y007 and C002. Prepare from verified demos/results and honest unknowns. Application, contact, reply, meeting, interview and acceptance are different receipts.
- **Editorial:** continue the existing P01–P07 derived publishing track from evidence already logged. The public homepage and 67-article research library are current; next publish an article/chapter/carousel only from a named source-backed claim or a completed case. A manuscript, slide draft, live URL, audience response and sales are separate states.
- **Governance:** G001 → G002 → G003 → G004 → G005 → G006, respecting K007/V001 and V006 dependencies. Establish charter/stop rights, independent incident review, multiple-context evaluation, interface/authority contracts, sustainable operating economics, and a recurring audit of harms/unknowns.

**Finite completion point:** an approved, recoverable bounded runtime; independently reproducible behavior evaluations; at least one honestly measured permitted use case; transparent costs/harms/limits; validated repeat use or a recorded no-go; and operating/governance review. “End suffering for all” remains the mission, not a finite milestone that a single release, YC decision, or benchmark can prove.

## Full original remaining task IDs

The canonical 41 todo items are: **Phase06:** F005, F006, F008, F009. **Phase07:** C002. **Phase08:** U002–U008. **Phase09:** D001–D009, D011, D012, D014–D016. **Phase10:** V001–V006. **Phase11:** Y003, Y005, Y008. **Phase12:** G001–G006. The detailed original acceptance text and dependencies remain in `roadmap/tasks.json` and `roadmap/START_TO_END_20261022.md`.
