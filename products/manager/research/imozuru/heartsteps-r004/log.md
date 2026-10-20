# R004 research/execution log — 2026-10-20

## Scope and rulings
Ruling: Execute exactly R004, not the whole 69-task plan; this is the user's requested unit of work.
Ruling: Research notes and a task-status update only; no estimator, runtime, or participant intervention is implemented. No TDD claim is made for document creation. Existing tests and upstream quote verification are rerun.
Ruling: Preserve the independent product boundary. Work from the existing ZIP and its Git history; do not assume previous hosts exist, and do not write Life Manager.
Ruling: The current roadmap generator hardcodes task status. Change R004 in that source and regenerate its existing JSON/Markdown views so a subsequent generator run cannot undo the update. No new competing backlog.

## Workspace evidence
Archive supplied in conversation, also found at Library /Manager/manager-independent-starter-2026-10-20.zip.
Baseline commit 275cd4a7cb6c893692ee5c0939b71a84a72e6cd4, clean extraction, no remote.
Branch research/r004-heartsteps-20261020 in /mnt/data/r004-work/manager-independent.
Baseline existing unit tests: 25 passed in this session.

## Round 0 — two evidence routes, no subagents
No subagent tool is available; searches and readings were performed directly.
Route A: Firecrawl query "HeartSteps" "kay067" methods analysis availability 2019; search ID 01a157e9-da4d-75bd-bffb-3e2cb3b3899b. Located PMC original, PubMed and author data repository. Search snippets were not treated as the finished reading.
Route B: Firecrawl query "HeartSteps" "compensatory" "missing"; search ID 01a157ed-387c-749d-862f-255888635790 returned no results. This is a search miss, not absence of limitations. Read the original Discussion and Limitations and the missing-data methods directly instead.

## Round 1 — original source and link following
Firecrawl retrieved the full original HTML, then the supplement linked by that paper. Read Methods, Results, Discussion, Limitations and supplement I–V.
Followed reference 23 to Boruvka et al.; only metadata/abstract was accessible on that route. Firecrawl research passage lookup returned empty. No claim to have read its full original text.
Followed authors' data README to StatisticalReinforcementLearningLab/HeartstepsV1Code; inspected the pinned Main Effects Analysis.R, lines 1–240. Code not executed and raw participant records not acquired.
Main-result correction: 24% belongs to walking-only secondary analysis; the any-suggestion primary mean result is 14%, p=.06.
Source discrepancies are recorded without pretending they are resolved.

## Acquisition and checking limits
Direct container curl failed DNS resolution for raw.githubusercontent.com. Supplement download in the container also failed. Original full text was read in tools; it is not saved or redistributed in this package.
Web PDF parsing succeeded for the publisher copy. Three screenshot attempts failed with cache misses; visual figure/table verification is not claimed. Native supplement visuals were not inspected; missing math labels in scraped text remain uncertain.
The unmodified upstream imozuru report.py checks short saved excerpt locators, not a byte-identical full-paper snapshot. Its script hash is separately verified. This is an explicit adaptation of imozuru, not a claim that fetch.py or chain.py ran successfully.

## Stop rule
Stopped after original → supplement/reference/code link following and grounding all R004 acceptance fields. No saturation statistic or exhaustive review claim. This is a scoped research task, not proof of complete scientific certainty.

## Next state
Only R004 may transition from todo to done after acceptance checks. User comprehension is not inferred. R005, R006, H-series and all field tasks remain unchanged.

## Verification and task completion
2026-10-20: official report.py confirmed 4/4 R004 locators. Existing offline unittest suite passed 25/25. Acceptance checks verified all required fields, sample-flow arithmetic, unchanged manager_core, and pinned report SHA. Only R004 status changed; 69 total tasks remain. Next ready task R005; user comprehension not assumed. No raw-data analysis or external intervention.
