# Manager S001 — SocSci210 study-level split source audit

**2026-10-21 JST; real official metadata verified; respondent-level training and evaluation NOT performed.**

## Evidence and version pin

- Dataset source: https://huggingface.co/datasets/socratesft/SocSci210
- Immutable dataset revision: `048481111a4425ed83dc0eacf15f8431f252b21a`
- Public study-level mapping: `metadata/participant_mapping.json`
- Source file Git-compatible blob SHA-1: `8aa37bd598ce8bb00103a5a885948299f75f5ce7`; byte count **1,710**.
- Pinned URL: https://huggingface.co/datasets/socratesft/SocSci210/resolve/048481111a4425ed83dc0eacf15f8431f252b21a/metadata/participant_mapping.json
- Original peer-reviewed paper: https://aclanthology.org/2025.emnlp-main.1530/ and https://arxiv.org/html/2509.05830v2 , Sec. 5.3.
- Authors' code/data readme: https://github.com/akaashkolluri/socrates and https://huggingface.co/datasets/socratesft/SocSci210/blob/048481111a4425ed83dc0eacf15f8431f252b21a/README.md

The mapping contains **study identifiers**, despite its file name `participant_mapping.json`; its two top-level arrays are `seen` and `unseen`. No survey answer rows, demographics, participant profiles or individual person IDs are required to validate the split. This distinction was checked in the public original mapping. Study identifiers are examined only in ephemeral memory and never written to generated audit output.

## Fresh actual-source verification (not a simulated result)

GitHub Actions: https://github.com/Daisuke134/life-manager/actions/runs/39536829220

| Acceptance | Actual |
|---|---:|
| Source mapping bytes, pinned hash | 1,710; match |
| Known/seen studies | 170 |
| Unseen studies | 40 |
| Total unique studies | 210 |
| Train vs unseen overlap | 0 |
| Focused synthetic contract tests | 4 passed |
| Downloaded respondent records | 0 |
| Output containing study IDs | 0 |

Implementation: `scripts/socsci_split_audit.py`; tests: `tests/test_socsci_split_audit.py`; hosted research workflow: `.github/workflows/manager-socsci-metadata.yml`. Hosted aggregate artifact name `socsci-s001-study-split-aggregate` contains only scalar counts and hashes.

## Study-rights / empirical benchmark gate

The author README says derivative works retain source-study licenses. Manager R006 `docs/research/source-rights.json` sets **SocSci210 local participant-level research / redistribution / product use = HOLD** pending per-original-study rights, consent and ethical review. This S001 work uses only provenance and study-ID metadata; it does not change respondent-level rights.

Therefore **S001's split/provenance condition is satisfied**, but S002 onward cannot honestly claim empirical metrics on all 40 unseen studies until permissions, secure data processing, model access and inference resources are resolved. No fabricated holdout predictions will be called measured behavior.
