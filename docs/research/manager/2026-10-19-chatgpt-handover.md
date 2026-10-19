# ChatGPT handover for Manager

Continue this project from GitHub, not from assumed access to the previous cloud filesystem. Speak Japanese to the user. The user dictates by voice, so resolve typos using established names.

## Identity and intent

- Company: Anicca. Product: Manager / マネージャー. Mission exactly **End suffering.** Keep technology as a means, not the mission headline.
- Manager proactively finds problems, changes the conditions behind them, executes, checks outcomes and improves. Primary direction is **macro intervention on shared environments, systems, information, resources and access**, not highly personalized nudging.
- Divine intervention is a philosophical metaphor for proactive help, not supernatural power, infallibility or authority over people. Retain the broad long-term ambition while separating measured capabilities.
- Build first. Discuss/refine architecture now, then implement the smallest useful complete loop. Learn missing components as needed. Do not make finishing the curriculum a prerequisite.

## Repository and branch

- Canonical repository: https://github.com/Daisuke134/life-manager
- Current research branch: docs/manager-learning-20261017. Read this branch explicitly; new materials may not be on main.
- Read AGENTS.md and docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md. The latter is the ONLY ordered task/progress authority.
- Architecture: docs/superpowers/specs/2026-10-19-manager-build-first-architecture.md. Its latest macro-intervention correction supersedes the earlier personal-event prototype.
- Philosophy and future English website copy: docs/research/manager/articles/2026-10-19-manager-philosophy-intervention-en.md
- Research map: docs/research/manager/2026-10-19-manager-philosophy-source-map.md
- Source/evidence scope: docs/research/manager/evidence/2026-10-19/manager-build-first-research.json
- Japanese diagram: docs/research/manager/learning/assets/2026-10-19-manager-build-first-architecture-ja.png

## What exists and what does not

Population8A/8B are implemented/evaluated. 8B expanded20,182 Rhode Island sample households to441,570 synthetic households/1,042,763 persons. This is population reconstruction, not observed behavior or intervention benefit. Reuse the machinery if the selected domain needs it; don't regenerate automatically.

Lessons9.1–9.4 have explanation and small fictional demonstrations.9.5 is explicitly paused. No real behavioral prediction improvement was established by the toy scripts.

apps/life-manager already contains context/intent/opportunity/adapter/job/receipt/reconciliation implementations. Existing components can be reused for a Manager action layer; they are not proof of a completed macro Manager. Main ran34 tests across opportunity-engine, agent-graph, loop-adapter-registry, effect-reconciler and connector-candidate-outcome, all passing at the reviewed tree. Re-run relevant checks before implementation claims. Live accounts, loaded runtime releases and provider activity were not verified by this architecture audit.

Comedy: old anicca-comedy-factory inventory reference found, active source/owner unverified. Music source not located in the reviewed checkout. Do not claim the user's prior work never existed; locate/reuse it. Separate creative quality, actual delivery, short-term relief and sustained benefit.

## Reuse decisions and cautions

Use existing Node CommonJS runtime, versioned contracts, jobs/leases, Postgres/domain stores and content-addressed artifacts. Python apps/manager supplies analysis/prediction. Do not add a second runtime, queue, DB or huge agent framework by default. Observe -> problem case -> valid actions including no_action -> execute -> independent provider readback -> actual outcome -> next decision.

Existing effect adapter: plan/execute/reconcile/verify/report. Unknown external result is not proof of absence; reconcile before retry. Keep case/attempt/effect/outcome distinct, source timestamps and tenant boundaries. General-agent loop IDs differ in some existing files: verify before integrating.

Population, learned behavior and simulation are optional modules when a selected macro problem actually requires them. A rule or optimization may suffice for the first loop.

Jev is an optional bounded classifier/router, not a validated human simulator. Read docs/research/manager/articles/2026-10-19-typesafe-jev-system-one-en.md. Official stable1.13/preview1.14 and input$.042/Mtokens were checked2026-10-19; recheck before use. Community badgerbees/jev-oasis selects actions and uses an LLM for generated text; no evidence reviewed establishes official Aaru/Simile/MiroFish adoption. No Jev inference was run.

## Publication, research and teaching preferences

All NEW article publication is on hold, including own website. Do not deploy, merge publication branches or publish to Zenn/note/Substack. Existing ownsite archive remains live. Save drafts/assets in GitHub. New article drafts English only; English image generation is paused. Japanese diagrams for explanations remain welcome; reuse saved diagrams where helpful.

Use free full-source reading, scraping/crawling and citation/link following, not search snippets alone. imozuru was installed in the previous cloud under /home/agent/.agents/skills/imozuru, upstream MaryCache/imozuru commit0d656febbc3f5e0a20cb03d3e011b703e69fe034. Do not assume installed on the next host; inspect/reinstall if needed. User authorized its install/use. Primary URLs and hashes are in repo evidence; downloaded third-party originals stayed private in that cloud and are NOT in GitHub. Retrieve originals again as needed; do not redistribute full copies. Avoid paid crawling unless separately authorized.

## Next conversation

Start with a brief confirmation of the macro-intervention direction and current architecture. Discuss two or three concrete shared-environment use cases we can actually operate; select using access, meaningful outcomes, observability, measurable comparison and implementation cost. The first real macro environment is NOT yet selected. Do not automatically implement personal event registration, travel assistance or individual nudges.

Explain the chosen architecture simply, then specify exact inputs/state/operator/outcomes, what existing code is reused, what glue is missing, and the smallest end-to-end acceptance demonstration. Update the unified SSOT. Follow the repo's normal design/implementation/review/promotion process and preserve the distinction between local source, GitHub branch, main integration and production effects. Credit precedents and don't claim nobody has connected these ideas before.
