# E09 scope-bound reference calibration (P0 diagnostic)

RED: required reference/calibrator interfaces absent; a separate partition-digest
regression also failed before correction. GREEN: eleven tests cover group and record
leakage, probability validity, missing references, language/population/scope shift,
coverage-risk arithmetic, exact reference joins and validation-only thresholds.
Full suite: 599 tests, OK, 5 optional-library skips.

Ruling: reuse the existing rights-cleared UCI daily aggregate dataset as references
for its own binary weather-conditioned rental forecast. This is a task-matched
aggregate diagnostic, not calibration of fictional advisory labels or human
behavior. Exact scope rejects owned-digital/human predictions. Cost if wrong:
no calibration inference transports outside this one declared retrospective task.

Original UCI archive was fetched read-only and day.csv matched the already pinned
57,569 bytes, Git blob d39017f2f1ad2e70a4a854d17aada04d45608575 and SHA256
 a6bcf826782d3c0fbfdcbeead17cd0884185a0dafe8ff10cd48a874ee7ba18be.
CC BY 4.0 / Hadi Fanaee-T / DOI10.24432/C5W894 attribution retained. No participant
records or raw data added to Git. Base fit 90 days, error fit 91, validation184,
test366; calendar-month groups and partition identities are disjoint/hash-bound.
The historical dataset was already studied here; this is NOT a fresh external
holdout or prospective field experiment.

The .25 squared-error risk target was fixed before this run; thresholds use only
validation. On 2012: pooled Brier .2409337384 at coverage1, but weather2 subgroup
.3075013363 and weather3 .2777777778 exceed that target. The model is therefore
NOT promoted; the report preserves DENIED_SUBGROUP_RISK. No test-label retuning,
human fidelity/welfare claim, or human-risk threshold is implied. Deterministic
technical link/accessibility checks do not require a fabricated human forecast.
Missing references return REFERENCE_DATA_REQUIRED, not invented confidence.

Reproduce with `python -m scripts.phase_calibration_reference --fetch-official
--output /path/report.json`. The read-only dedicated E09 CI fetches original bytes
and compares the complete report; a failure must not fall back to synthetic data.

The first dedicated CI (39767148200) fetched and verified the original data but
its exact JSON float comparison failed: Python3.11 vs3.12 summation differed by
~1e-15. A new RED→GREEN comparator test permits only finite float roundoff within
1e-12, while hashes, counts, types, fields, promotion status and source identity
stay exact. Changed substantive results still fail. No metric or source value
was rewritten to conceal that failure.
