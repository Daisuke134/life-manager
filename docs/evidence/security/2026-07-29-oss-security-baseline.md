# OSS security baseline evidence

## Scope and result

| Gate | Before | Current local evidence |
|---|---:|---|
| gitleaks current tree | 16 findings | 0 |
| gitleaks full history | 852 findings / 851 unique fingerprints / 143 files | 0 after fingerprint adjudication baseline |
| PII shape gate | 63 broad-grep hits | 0; exact rule/path/value fingerprints allow only synthetic fixtures |
| TruffleHog filesystem | not independently measured | 4,441 chunks / 26,063,885 bytes / verified secrets 0 |
| TruffleHog full history | 7 verified Postgres hits pointing to one endpoint | same full-history Postgres detector: verified secrets 0 after remediation |
| Python security contract | missing packages and stale expectations | 12 tests pass with an explicit pure-stdlib security manifest |
| Shell syntax | pass | pending final exact-five rerun |

No raw secret or matched personal-data value is stored in this evidence.

## Gitleaks adjudication

| Class | Count | Disposition |
|---|---:|---|
| generic-api-key | 830 | generated-code fragments, public identifiers, placeholders, and historical inactive provider values; current-tree fixtures were changed to explicit placeholders |
| jwt | 10 | historical inactive fixture/token-shaped values |
| stripe-access-token | 4 | synthetic test values; current fixtures use explicit placeholders |
| gcp-api-key | 4 | historical credentials; provider verification returns invalid key |
| curl-auth-user | 2 | historical credential-shaped command material; no verified active secret |
| private-key | 1 | historical self-signed TLS key; paired certificate expired |
| slack-bot-token | 1 | provider verification returns `invalid_auth` |

The 851 unique historical fingerprints are recorded in `.gitleaksignore`.
The baseline is fingerprint-specific, so a value added at a new
commit/path/line is not suppressed. A mutation check with a new synthetic AWS
key was rejected by the configured detector.

Gitleaks documents that a long-history repository can use a baseline and that
each finding has a unique fingerprint:
[Gitleaks README](https://github.com/gitleaks/gitleaks#creating-a-baseline) —
“When scanning large repositories or repositories with a long history, it can
be convenient to use a baseline.”

## Active database finding and remediation

The first full-history TruffleHog run found seven verified Postgres occurrences
in old backup/docs commits. They all resolved to one Railway database endpoint.
Direct readback showed:

| Check | Before | After |
|---|---|---|
| `pg_hba_file_rules` | local/IPv4/IPv6 `trust` | local/IPv4/IPv6 `scram-sha-256` |
| wrong password | connection accepted | connection rejected |
| old password | connection accepted | connection rejected |
| new password | n/a | connection accepted before public endpoint removal |
| public TCP proxy | 1 | 0 |
| consumer database route | mixed public/internal | internal Railway hostname only |

The database password was rotated, seven consumer variables across
`life-call`, `API`, `nudge-cron`, `nudge-cronp`, and `x402-agents` were updated,
and those five services were redeployed. Production readback after cutover:

| Service | Deployment | State | Health |
|---|---|---|---:|
| `life-call` | `3356efa6-e565-4f21-967b-d03fe088d739` | SUCCESS | 200 |
| `API` | `243b35b8-6b02-4daa-b800-eb31de31183d` | SUCCESS | 200 |
| `nudge-cron` | `6431065a-cf6d-4614-a714-9c3f61f8838b` | SUCCESS | 200 |
| `nudge-cronp` | `88fbc733-4953-4025-b712-f1a683ee202d` | SUCCESS | private service |
| `x402-agents` | `5ee685de-b623-4b7a-8d57-b12c027837be` | SUCCESS | 200 |

GitHub’s remediation guidance says a committed secret must be treated as
compromised and rotated:
[GitHub secret scanning](https://docs.github.com/en/code-security/secret-scanning/managing-alerts-from-secret-scanning/resolving-alerts) —
“Once a secret has been committed to a repository, you should consider the
secret compromised.”

Railway documents that public networking exposes a service to the internet:
[Railway public networking](https://docs.railway.com/networking/public-networking) —
“Public networking allows you to expose your Railway services to the
internet.” The database no longer has a public TCP proxy.

## Completion

PR #1274 merged after gitleaks, PII, TruffleHog, Python, and Shell all
reported green on the merged head. `OSS-SECURITY-BASELINE-1` is complete.
The ordered program cursor advances to `REPO-V0-RETIRE-1`.

## Addendum 2026-08-18 — twelve fingerprints adjudicated

The history scan failed on every pull request because twelve findings post-date
this baseline. All twelve were read at the commit that introduced them.

| finding | commit | what it actually is |
|---|---|---|
| eleven `generic-api-key` hits in `skills/earn/gig/tests/` | `f1209ea69` | the literal fixture `0123456789abcdef0123456789abcdef`, used as a fencing token in state-machine tests |
| one `generic-api-key` hit in `.claude/handovers/2026-08-13_1236_capafy-observability.md` | `54a8fac78` | the 40-hex git commit SHA `22dfc0cb983c763732b483edc73b33278854e52c` |

Neither shape can authenticate anything, so nothing is rotated. The
fingerprints are pinned to commit, path, rule and line, so the baseline still
fails on a real secret at a new location — verified by the gate continuing to
run the full history scan rather than being narrowed.

## Addendum 2026-09-17 — Mobile question identifiers

The full-history scan reported 15 `generic-api-key` findings from Mobile
import commit `603d6810256510ac3d8e9f6c309cc70126e3d863`, all in
`DeepDiveQuestionsData.swift`. Every reported line is a
`DeepDiveQuestion.questionKey` string, not an authentication field. The 15
distinct namespaced identifiers are each present in both English and Japanese
`Localizable.strings`. No matched value is copied into this evidence.

Only the 15 exact commit/path/rule/line fingerprints are added to
`.gitleaksignore`. The current-tree scan, full-history scan and detection of
any new value at another location remain enabled. No credential rotation is
indicated for these localization keys.

## Addendum 2026-10-07 — generated runtime occurrence identifier

The full-history scan reported one `generic-api-key` finding in commit
`d5ce0d1302e206a5df3744ed998901d069d610f9`, at
`docs/evidence/main-agents/health.json:7757`. The matched field is
`jobs[154].diagnostic.occurrence_id`. Its value is exactly the same row's
`owner_id + ":" + run_id`; `owner_id` also matches `job_id`. The introducing
commit's runtime code constructs `run_id` from `time.time_ns()` and the process
ID, then constructs `occurrence_id` from the loop ID and run ID; the health
projection copies that field. A fresh read-only review and a local shape/hash
check confirmed this generation path without printing the value.

The commit is reachable from `docs/main-agents-readiness` only; it is not an
ancestor of current `main`, the PR #6823 base, or its head, and PR #6823 does
not change the finding file. The CI full-history scan explicitly uses
`--log-opts=--all`, so the unrelated branch finding blocked the CFO PR. This is
a generated execution identifier, not an authentication credential. No
credential rotation is indicated.

Only this exact fingerprint is added to `.gitleaksignore`:
`d5ce0d1302e206a5df3744ed998901d069d610f9:docs/evidence/main-agents/health.json:generic-api-key:7757`.
The current-tree scan and full-history scan remain enabled; a new value at a
different commit, path, rule, or line is still detected.

## Addendum 2026-10-07 — refresh one existing OSS inventory exception

PR #6823's full repository check reported one existing
`manifest_inventory_mismatch` for `skills/capafy-autopublish`. The source
manifest still declares 241 files while the current tracked root has 242, so
the manifest mapping itself remains a known mismatch. The existing baseline
entry for this exact code and path was refreshed from evidence hash
`645a77c780a26baa215b2c2003bd88594cf4f8a37a9668c9de120a3d5de2f948` to
`7619a21b30f651d7c8f62102e785ff4a8992807fabfa6ff053b4f44a9f47ed5e` after
reviewing the current tree and its recent source changes. Then origin/main
advanced to `a77ce93ffea90598a65de4b1fcb3edb8bf1a788e`, editing
`inventory_status.py` and its test inside the same root. The tracked count
remained 242 and the exact evidence hash changed to
`d5946679ecf2405bc291550f8de4880d5f13de02f4fd858278c154f21c91a043`. Main
advanced again to `84261ec74ebd13f8e49753c48c741cccafcf8863` with further edits
to that inventory status source/test. The root still contains 242 tracked
files; its exact hash is now
`f2dde0db2faef66a490cb43420b956c5472a9b567b5c7fc930d0e1755b3907c1`, and the
baseline entry was refreshed to that merge tree. The source manifest still
declares 241 files, so the provenance mismatch remains. The manifest and
verifier are unchanged; this records the accepted current state, not a claim
that the manifest inventory was repaired.

The baseline still matches only `manifest_inventory_mismatch` at
`skills/capafy-autopublish` with that exact tracked-tree hash. The verifier
returns no current violations after the refresh, and its existing 12 tests
pass. A further tree change produces a different hash and fails again; other
violation codes, paths, and source roots remain unsuppressed.

## Addendum 2026-10-09 — historical Web-first wording false positive

The full-history Gitleaks run for PR #7337 found one generic-api-key fingerprint
from closed PR #7334, at commit 68e8bc2888ff119b59c6f65c67ef63759af20af9 in
docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md:3848. The
redacted match was ordinary prose describing reuse of the existing Calendar
connection; it contained no credential. The line is reworded in the current
tree. Gitleaks current-tree scan reports zero findings, and TruffleHog
filesystem/history reports verified secrets zero on the clean PR head.

Only this exact fingerprint is added to .gitleaksignore:
68e8bc2888ff119b59c6f65c67ef63759af20af9:docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md:generic-api-key:3848

## Addendum 2026-10-14 — synthetic Hook Lab attribution fixtures

PR #7971's first Gitleaks run (`38472309335`) found five `generic-api-key`
fingerprints in earlier revisions of `skills/earn/marketing-engine/measure/test_experiment_attribution.py`.
They were deterministic first-party campaign IDs placed in test-only
`attribution_token` fields; they are not provider credentials and were not sent
to Capafy. Current fixtures derive those IDs from the public test identity via
`publication_campaign_token`, so the current-file redacted Gitleaks scan reports
zero findings. The five old commit/path/rule/line fingerprints are individually
recorded in `.gitleaksignore`; no rule, path, or directory-wide suppression was
added. The full-history scan is rerun on the PR head before merge.

The full-history scan remains enabled. A match at a different commit, path,
rule, or line is not suppressed.

## Addendum 2026-10-17 — historical paper-access prose

PR #7768's full-history Gitleaks job (`117372519104`, workflow `39024344781`)
reports one `generic-api-key` finding at commit
`d8be0702`, in
`docs/research/manager/evidence/2026-10-17/numerai-methods-research.json:59`.
An independent read-only review confirms that `access_limit` contains ordinary
prose about a publisher's HTTP 403 response, retrieval from the author's HAL
repository, and the distinction from an earlier paper. The matched substring
is a public publisher/status label, not an authentication credential. No
credential rotation is indicated.

The commit is on `docs/manager-learning-20261017` and is not an ancestor of the
reviewed investment head or `origin/main`. The current-tree scan passes; the
unrelated commit is included by the existing `--log-opts=--all` history scan.
Only the exact commit/path/rule/line fingerprint for this finding is added to
`.gitleaksignore`; the full fingerprint remains in that canonical baseline.
The current-tree and full-history scans remain enabled. Different commits,
paths, rules, and lines remain subject to detection.

## AI monk runtime documentation CI: public fixture effect identity

PR #8545's workflow `39809108919` passes the current-tree scan but reports one
`generic-api-key` history finding at commit
`9ea03355acbcb8e251e3f4c79df6ca16da8a09f9`,
`products/manager/docs/verification/E16_RECOVERY_REVIEW_20261022.md:51`.
The `effect_key` is a deterministic SHA-256 effect identity, not a credential.
An independent read-only verifier recomputes it from the same commit's public
`test_candidate_verification.py:24–32` fixture and
`digital_handoff.py:27–33,53–64` canonical-JSON hashing path. The recomputed value
matches exactly, with no credential access, network request, or file write.
The older `ea646b27` demo exceptions have different values and are not reused
as evidence for this finding.

Only this exact commit/path/rule/line fingerprint is added to `.gitleaksignore`.
No rule, path, directory, or new finding is suppressed; current-tree and
full-history scans remain enabled. No credential rotation is indicated.

## Mobile release CI: public effect identifiers

The full-history scan in GitHub Actions run `39904613742` reports two
`generic-api-key` findings at commit `17d400f225ab4ee320daae337b2e866e0c32884a`,
`products/manager/docs/verification/PHASE06_DIGITAL_V2_RESULT_20261022.json`,
lines 64 and 191. Both fields are `effect_key` identifiers in public digital
release receipts, not authentication material.

The producer in `products/manager/manager_core/digital_handoff.py` derives
`effect_key` as the SHA256 of the canonical public release identity
(repository, ref, workflow, target, candidate manifest, and allowed paths).
The source contains no signing or provider token in that identity. The two
values have the expected 64-hex shape and neither matches a registered secret.
Only these two exact commit/path/rule/line fingerprints are added to
`.gitleaksignore`; current-tree scanning and detection at new locations remain
enabled. The introducing commit is on another fetched branch, so changing
only this PR's current tree cannot remove the historical findings.

## Fresh Mac installer CI: historical authority-control prose

PR #8776's workflow `40018436759` passes the current-tree scan and TruffleHog,
but the full-history scan reports one `generic-api-key` finding at commit
`a6f8deaf743033dae21132be54d27223293b09f7`,
`products/manager/docs/verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md:22`.
An independent read-only review reproduces the finding from that line alone.
The candidate consists of four ordinary lowercase words separated by slashes,
describing authority controls; it is not authentication material. Adding spaces
around those separators in memory removes the finding. No credential is read,
used, or rotated for this adjudication.

The commit exists only on another fetched research branch. Its document is
absent from this PR's current tree, so rewriting the current tree cannot remove
the historical finding. Only this exact commit/path/rule/line fingerprint is
recorded in `.gitleaksignore`. Scanner rules, path allowlists, current-tree
scanning, and detection of findings at new locations remain unchanged.

## PR #8745 — synthetic browser-redaction test placeholder

Security Scan `40229736789` passes the current-tree Gitleaks scan but its
full-history scan finds one `generic-api-key` occurrence at commit
`dbd128f27c963d049ee47c66887720ffa3340cd2`,
`apps/life-manager/maritime/test_browser_mcp.py:65`. The value is deterministic
test-only text used to verify that browser page observations redact API-key
assignments. It was never a provider credential and was not sent to any service.
The current test uses a low-entropy placeholder, and the current-tree Gitleaks
scan passes. Only this exact historical commit/path/rule/line fingerprint is
recorded in `.gitleaksignore`; full-history scanning and detection at all other
locations remain enabled. No credential rotation is indicated.
