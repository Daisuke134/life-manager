# Review guide

Read by every reviewer (human, subagent, or the self-build merge guard) before reviewing a Life Manager PR.
Pattern copied from "How the Claude Code team does code review" (claude.dev, 2026-10-15).

## What failure looks like here

Flag these first. Each comes from a real incident; cite file and line, not a guess from a name.

| Area | Failure | Incident |
|---|---|---|
| Effect fences / reconcile adapters | A fence closes without an official readback bound to the exact occurrence (a time window or a sibling run is not proof). | #8230 (closed) paired a resume fence to a run the occurrence never owned |
| Result hints / verified effects | A model-controlled process can write a "verified" receipt (env path inherited, guessable file). | #8247 hint path leaked into the model pass |
| Money / CFO / ledgers | `unknown` becomes 0, a stale aggregate reads as current revenue, or revenue moves between loops. | CFO 未確認 rows, #8280–#8282 |
| Publication | A gate verdict (identity FAIL, conscience BLOCK) can be re-judged into PASS for the same bytes. | #8251 first draft |
| Caching / retry | A transient provider failure is cached as a final answer, or a retry re-bills every tick. | #8257 first draft memoized 429 for 24 h |
| Links / CTAs | Link text and destination diverge, or a tracked link fails closed for real users. | #8278 rewrote pricing citations; `/go/af_*` 503 |
| Contracts | Two files encode the same contract (destination pairs, timeouts) and drift. | x-article/ja dormant in one file, active in another |
| Runtime | A killed process (75/124/128+N) is treated as a finished one. | #8243 review |

## Rules for findings

- Start the summary with a count: "N findings (X blocking)". Say plainly when there is nothing to fix.
- Tag each finding Blocking, Nit, or Pre-existing. Pre-existing bugs are not the author's fault; list them separately.
- At most 3 nits. Skip style, naming, and formatting unless they change behavior.
- Name the bug class so the author fixes every instance, not one line.
- Every finding is answered: fixed, or closed with a reason.

## Convergence

- Round 1 reviews the whole change. Later rounds review only the new diff and never repeat an earlier finding.
- After 3 rounds, stop and ask the author to reconsider the approach instead of reviewing again.

## Risk tier (sets review depth, not the author)

- Low: docs, SSOT, comments, tests only. CI green is enough.
- Medium: ordinary loop code. One fresh-context reviewer.
- High: anything touching fences, admission, money, credentials, publication, result hints, merge/release scripts, or CI workflows. Fresh-context reviewer, production dry-run evidence, and a one-unit canary before fleet rollout.

## Merging

Merge only when every check has finished and none failed: `bin/merge-when-green <pr>`.
