# Manager / Anicca — Phase 05 Full Implementation Handover

**Language to founder:** Japanese. **Development brief:** English.  
**Mission:** End suffering. **Current request:** Take over immediately and IMPLEMENT **Phase 05 K001–K014 to verified completion**, in dependency order. Do not restart from architecture brainstorming, duplicate prior work, or repeatedly ask for permissions already given for software research/development.

## 1. Canonical code and mandatory startup

- GitHub: https://github.com/Daisuke134/life-manager
- Existing **Manager research branch:** `research/manager-product-r006-20261020`
- **Manager-only root:** `products/manager/`
- Most recent *independently verified* branch tip before this handover was `440c9e6f8a9ce1cf891350aa8707c9abf48b9caf` (2026-10-21). **Fetch the CURRENT HEAD before edits**; it may have advanced, and this handover commit will itself advance it.
- Treat these files as authority, in order:
  1. root `AGENTS.md` (obey source/environment boundaries; its unrelated Life Manager operations do NOT authorize changes to production or its SSOT).
  2. `products/manager/README.md`
  3. `products/manager/docs/MANAGER_PRODUCT_SPEC.md`
  4. `products/manager/docs/architecture/ARCHITECTURE.md`
  5. `products/manager/docs/architecture/PHASE05_KERNEL_HANDOVER_JA.md`
  6. `products/manager/docs/roadmap/tasks.json` — **THE single canonical Manager task status**.
  7. `products/manager/docs/roadmap/ATOMIC_BACKLOG.md` — generated synchronized view only.
  8. `products/manager/docs/roadmap/PRODUCT_COMPLETION_GATES.md`
  9. `products/manager/docs/research/source-rights.json`
  10. `products/manager/docs/verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md`.
- Inspect the actual `manager_core/`, `tests/`, `scripts/` and `.github/workflows/manager-research-ci.yml` before choosing implementation. **No unverified assumption that the full Phase 05 kernel is already in code**.
- Use applicable installed development/research skills, e.g. test-first and smallest-solution discipline, and the official MaryCache/imozuru methodology for substantive research. Look for reuse before adding frameworks. If a local Mac checkout is not available, use the connected GitHub repository; do not claim you tested the owner's Mac or production deployment.
- Work in a Manager-owned branch/worktree derived from the latest applicable research head, preserving unrelated edits; confirm how changes are integrated under the repository's actual source rules. Do not touch Life Manager main/production/financial infrastructure or its independent project SSOT.

## 2. Current source-of-truth state (verified 2026-10-21)

**113 canonical Manager tasks:** **45 done / 65 todo / 2 blocked / 1 skipped**. Phases 00–02 scoped done; Phase 03 has 9 done plus H005 skipped because the original HeartSteps analytical population cannot be reconstructed exactly from the public CSV; **Phase 04 S001–S008 are 8/8 done only under their explicitly documented bounded research/engineering acceptance scopes. Phase 05 K001–K014 remain 0/14 done at the last verified readback.**

Phase 04 genuinely executed:
- Pinned SocSci210 17 Parquet files: 210 studies, **2,901,390 actual response records**; 170 seen / 40 unseen (zero study overlap), 2,418,748 training-side and 482,642 heldout-side rows. These are real source data, **not synthetic people**. Published results from a deliberately coarse 0..10 + OTHER code baseline **do not preserve question-specific answer meanings across the studies**. The original Socrates paper's task-conditioned Wasserstein/individual behavior claim is **NOT independently reproduced**.
- S004 heldout distribution errors, study-level bootstrap, 20/20 study-size subgroup errors, training-only error threshold; action selection remains **ABSTAIN** when task semantics/calibration are unknown.
- S005 actual public frozen MiniLM encoder + trained-on-seen-only logistic head vs frequency/majority **on exactly 800 unseen response records**, 24.50% versus 19.375% coarse-code accuracy. A separate SmolLM2-135M checkpoint compared **on a DIFFERENT but internally matched 320-record set** returned 42.5% valid numeric answers and 9.0625% accuracy counting invalid answers wrong. No original 8B/14B Socrates author checkpoint was benchmarked. Do not compare 320 and 800 as though they were the same sample.
- Existing other studies: ZOZO's real historical Open Bandit Dataset 60,000 public impressions, IPS/SNIPS and importance overlap diagnostic (women ESS about 2.078/10,000); UCI Bike Sharing real out-of-year observational forecast; real Concordia upstream engine with *fictional mock* agents only; H005 documented skip. None is Manager-caused human welfare improvement.
- **Scientific Gate 1 is NOT MET**. No human causal intervention fidelity replicated independently, and **Manager has zero independently verified beneficiary improvements**. A code/test run, simulation, provider receipt, or historic external RCT is not a verified Manager 'Blessing'.
- Last independently verified research CI: [208/208 tests, Manager boundary and 113-task backlog check SUCCESS](https://github.com/Daisuke134/life-manager/actions/runs/39565175720). Actual full research + open-model receipts are linked from `docs/verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md`.

## 3. Mission, product architecture and inviolable constraints

Vision: a general-purpose, proactive **Digital Buddha / Digital God** only as a *long-term metaphor*: a system that observes public world state, forms testable hypotheses, compares alternatives, safely acts using **pre-existing legitimate scoped authority**, independently checks external results, assesses net improvements and learns. This is NOT achieved AGI or actual omniscience.

- **Manager != Life Manager**. Separate code, runtime, data, budget, memory, accounts, credentials, outcome registry, permissions. Do not import its unrelated modules or mutate its production systems.
- **No human in routine operation** *once* explicit standing rights/budgets/time limits are established. External oversight, appeal, revocation, immutable audit and safe shutdown still exist. **Founder approval to develop code or analyze released data is not a real-world grant to spend funds, control third-party facilities, or handle someone else's sensitive accounts.**
- Public/nonpersonal observations first; do not publish individual respondent rows, prompts, profiles, credentials or third-party copyrighted material. The founder explicitly authorizes SocSci210 research; process within documented research boundary. Distinguish public data access, research, redistribution, commercial reuse and **real-world actuation**.
- Hard separation: (a) prediction fit (Brier/TVD/MAE), (b) counterfactual/causal effects (ATE error vs credible experiment), (c) real external execution receipt, (d) independent readback, (e) actual beneficiary impact, net of fees, harms, displacement and uncertainty.
- `manager_core/config.py` currently **defaults all external writes, public posting, transfers, physical actuation and private-person runtime capabilities to FALSE**. Keep fail-closed while building isolated contracts and test adapters. Do not enable effects merely to pass a demo.
- Never silently promote unknown/failed results to success, infer 0 harm from missing measurements, or claim an external outcome without independent corroboration. No speculative impact numbers.

### Shared kernel to implement

```text
Source (URL/rights/hash/freshness)
  → Observation (time/unit/missingness)
  → Problem (mechanism + alternative explanations + evidence)
  → Alternatives including NO_ACTION (cost/risk)
  → Prediction / counterfactual estimates (distinct metrics)
  → Authority gate (issuer, signed scope, expiry, revocation, budget)
  → Idempotent execution / durable outbox
  → External reconcile (present / absent / UNKNOWN)
  → Independent readback (NOT the executor's claim)
  → Outcome evaluation (preregistered comparator, CI, harms and cost)
  → Safe versioned learning + rollback
  → Public, challengeable source-to-action-to-impact audit / Blessing record
```

## 4. Implement **K001–K014**, atomically and in dependency order

Follow the exact current `tasks.json` acceptance criteria; the table below is your checklist, not a replacement for the canonical registry.

| ID | Build | Minimum acceptance test |
|---|---|---|
| K001 | `manager_core/models/source.py`: public URL, license/rights, content hash, timestamp, sensitivity flag | Unknown rights, content provenance or PII classification => fail closed |
| K002 | `manager_core/models/observation.py`: typed measure, unit, timestamp, missingness | Same numeric value with different unit/time cannot be treated as identical observation |
| K003 | `manager_core/models/problem.py`: harm mechanism, target metric, alternative causal explanations and evidence references | Unsupported causal claim must fail validation |
| K004 | `manager_core/models/intervention.py`: scoped options with NO_ACTION, expected effect distribution, costs and risk | Never drop NO_ACTION on high uncertainty or missing evidence |
| K005 | `manager_core/forecast.py`: calibrated forecast separate from causal effect estimates | Descriptive forecast scores and randomized-treatment-effect errors remain separate |
| K006 | `manager_core/state_machine.py`: enumerated legal transition graph, explicit NO_ACTION/REJECTED/UNKNOWN/ROLLBACK states | Every illegal transition rejected; UNKNOWN never means SUCCESS |
| K007 | `manager_core/authority.py`: signed/verified issuer, grant scope, expiry, revocation and budget | Missing, forged, expired, revoked, wrong-domain or over-budget grant **cannot execute** |
| K008 | `manager_core/outbox.py`: durable idempotency key and effect reservation | Repeating the same request 10 times => at most one effect; process restart preserves invariant |
| K009 | `manager_core/reconcile.py`: external present / absent / unknown | On uncertain network outcome, do not blindly retry; reconcile first |
| K010 | `manager_core/verifier.py`: independent readback with timestamp/source separation | Executor says success without independent external evidence => NOT VERIFIED |
| K011 | `manager_core/evaluator.py`: comparator, effect size, confidence interval, negative results, cost and harms | Raw activity counts cannot be presented as causal net improvement |
| K012 | `manager_core/learning.py`: versioned candidate policy, holdout/shadow check and automatic rollback | Rejected model or regression cannot silently replace the safe version |
| K013 | `manager_core/audit.py`: trace source→decision→authority→effect→receipt→readback | Every run can be inspected without secrets, with UNKNOWN preserved |
| K014 | The **same kernel** with finance and environment **offline fixture adapters** | New domain does not change authorization, evidence, idempotence or welfare-proof invariants |

- First inspect existing `manager_core/evidence.py`, `calibration.py`, `evaluation.py`, `outcome_ladder.py`, `outcome_windows.py`, research scripts/tests, and the architecture note; reuse their verified invariants rather than starting another framework. Use Python standard library where sufficient; add dependencies only with a concrete testable need.
- Implement deliberately small units: RED unit tests / code / GREEN focused tests / integration tests / security edge cases / readback. **Keep moving K001 through K014 without needless founder clarification**. If external provider access is missing, test safe sandbox adapters while preserving proper authority gates and explicitly record which external integration is unverified.
- Think adversarially: forged signatures, timestamp shifts, stale public sources, schema drift, missing license, private data in supposedly public pages, budget overrun, exact-once crash/retry, provider timeout after executing, replay, source collusion, bad independent evidence, negative treatment effects, spillovers and rollback failure.
- Require an end-to-end offline two-domain demonstration covering every kernel state, rejection path and a negative/unknown outcome; archive original code/tests/diagrams and aggregate result in version-controlled Manager-only GitHub paths.

## 5. Verification and source-of-truth update on EACH verified milestone

From `products/manager/`, when runnable:

```bash
python3 -m manager_core
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
```

- Read `.github/workflows/manager-research-ci.yml`, execute and inspect **actual hosted GitHub Actions** and failed-step logs, not only local/mock results. Fix regressions; do not report that a job passed merely because you pushed code.
- **Only update `docs/roadmap/tasks.json` for genuinely verified milestones**. Then run the existing `scripts/make_roadmap.py` to regenerate `docs/roadmap/ATOMIC_BACKLOG.md` and verify exact consistency. Do not create a new task SSOT or edit Life Manager's `docs/superpowers` progress register.
- Write test scope, external evidence, commit SHA, original and changed acceptance language, unresolved scientific limitations. Do not change genuine Phase 04 limitations or mark Gate 1 achieved through relabeling.
- Preserve root source restrictions, present source results and the user's uncommitted work. Only use the normal PR/merge process if the permitted repository workflow supports it. No direct changes to unrelated main/production modules.
- After K014, show a checkable final Phase05 report: exact 14 IDs verified/not verified, all new files, CI runs, test counts, state transitions, demo traces, security and unknown-effect failures, known risks, remaining 113-task statuses, and next dependencies for Phase06.

## 6. Research and founder objectives

Manager's ultimate goal is evidence-backed real-world welfare improvement, not simulation theater. Borrow primary published methods/official code from Generative Agents, Concordia, Socrates/SocSci210, HeartSteps, DoWhy, EconML, Simile, Aaru, Artificial Societies/Radiant and other credible prior work; distinguish independent validation from vendor claims. Source-link original code/papers with versions, counterexamples and limitations, applying imozuru-style research when a design decision materially needs it.

Do not stall Phase05 for unrelated book/article/slide work. The existing public research content, 26-company map (including Radiant), 39-slide seminar and daily Behavior × AGI newsletter live in different workflows; preserve them. YC Winter 2027 and English research outreach are parallel founder tracks, not proof of kernel completion.

## 7. How to communicate and what to do right now

**Respond to the founder in natural JAPANESE.** Explain useful concepts/mechanisms, equations/flow diagrams where helpful, but **write and test code before merely presenting a plan**. The founder wants the entire Phase05 K001–K014 done, not periodic permission requests. Continue through atomic tasks, using tool calls for actual source changes and externally verifying receipts, with no need to ask again for routine software-engineering approval.

First reply with a **very brief** Japanese explanation of the first implementation step, then immediately:
1. Fetch research branch current HEAD and files above.
2. Start K001 with test-first work, then K002…K014, respecting canonical dependencies.
3. Commit code and tests, run independent CI/readback, synchronize task registry and backlog.
4. Finish by reporting exactly what is DONE, what failed or remains blocked, and what Phase06 / scientific gates still require. No fabricated finish line.

**Never confuse the noble mission "End suffering" with an already verified reduction in suffering.** Keep the objective large, the claims precise, and the execution real.
