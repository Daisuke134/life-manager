# Explicit unresolved external conditions

These are research and deployment unknowns, NOT errors that can be silently assumed away.

| Issue | Why it matters | Resolution needed before proceeding | Current status |
|---|---|---|---|
| Manager GitHub source branch | User expressly approved storage under Life Manager repository. `products/manager/` is an isolated subtree in `research/manager-product-r006-20261020`; no shared runtime. | New standalone repository is optional later; old standalone `.git` history remains in Library backup ZIP, not migrated into GitHub root history. | P006 verified in GitHub readback (commit 68a2214...) |
| Direct DNS to GitHub and primary papers from container | External network unavailable from code runtime | Use connected Firecrawl and GitHub tools to inspect primary sources; fetch large trial CSV only once a supported data handoff to container is available. | NO NETWORK |
| Public HeartSteps participant-level CSV and terms | Public release may contain potentially sensitive records and special attribution terms | Source and licensing audit, and minimum data with no redistribution/participant-level display. | PENDING H001 |
| SocSci210 underlying source terms | Aggregation of many studies does not imply one uniform license | Review study-by-study terms and subsets before redistribution/training. | PENDING S001 |
| Real-world donation or actuation | Published data gives no right to move money or touch devices | Designated fund or facility authority, bounded budget, safety review, written authorization. | BLOCKED F004/F007 |
| Real-world **causal** impact | Single receipt or unchanged comparator does not prove net human benefit | Pre-registration, credible comparisons, outcome visibility, effect uncertainty, adverse-impact measurement. | NO PILOT |
| IACS / lab presentations | Dates and audience may be provisional | Confirm schedule and scope separately; no unapproved publication | NOT SCHEDULED BY THIS PROJECT |

| Li & Ji (2026) reproducibility | R005 is a literature/figure extraction task, not a local reproduction | Independent raw data/prompt/model execution and check original ICCP cohort discrepancy (63/59,440 vs 62/59,508), licenses and model snapshots before making causal-performance claims | RESEARCH GAP, NOT A FIELD RESULT |
