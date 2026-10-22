# E08 frozen matched comparison (engineering scope)

RED: comparison interface absent. GREEN: nine tests for family isolation, hidden
labels, equal public context binding, preserved NO_ACTION, frozen-byte mutation,
reproducibility, all-attempt failure accounting and family-cluster intervals.
Full suite: 588 tests, OK, 5 optional-library skips.

Before provider outputs: 12 authored fictional families × 5 variants are frozen;
4 families (20 variants) are development and 8 (40 variants) evaluation. Rules and
manifest are hash-bound. Three scheduled repeats yield 120 attempts per policy;
deterministic repeats do not add independent information. Paired differences
resample the eight families 2000 times; no worldwide/human superiority follows.

Reproduction:
`python -m scripts.phase_collaboration_v2 --output /path/to/report.json`
The committed E08_OFFLINE_COMPARISON_20261022.json contains raw deterministic
baseline decisions and scores. Optional provider records must match the exact
manifest and every public context hash, retaining failed attempts. Supplied
records are not authenticated by their own metadata. The comparison runner has
no network callback and cannot create billable work or silently retry it.

Ruling: use the existing durable/budgeted provider lab as the execution boundary,
with recorded-output ingestion for comparison, rather than arbitrary callbacks
inside a scorer. Cost if wrong: a separately configured v2 live acquisition
adapter is needed before new Ampersand evaluation. Live is optional in E08 and
was NOT_RUN; no provider comparison, semantic safety validation, rationale quality
or human utility claim is made. Dollar CPU/provider costs are unknown, not zero.
