# Phase 04 — data-access and external-validation decision record (2026-10-21)

**Scope**: SocSci210, behavioral simulation, public and openly licensed alternatives. Research-only. This document does not contain participant records or personal profiles and is not an authorization token.

## User authorization

The project operator states they have special permission to work with SocSci210 and authorizes continuing the research. This is accepted as authorization for the assistant to investigate, code, test, and request access using credentials already properly configured. It is **not** evidence of permission from each source study's rights holder or participant. Record the actual grant's issuer, dataset/study IDs, processing purposes, allowed personnel, retention, location, commercial limits, permitted publication and redistribution before converting the machine-readable `local_research=hold` gate. If the grant covers all 210 studies, attach permitted proof privately and record a non-sensitive decision trace in public Git. Do not expose the grant itself publicly.

## Datasets evaluated and choice

| Source | Actual study question | Rights / privacy state | Responsible next evaluation |
|---|---|---|---|
| [SocSci210](https://huggingface.co/datasets/socratesft/SocSci210) | Held-out social-science experiment response prediction across 170 seen / 40 unseen studies | Published metadata split validated; per-source-study respondent rights not independently established; user's reported permission scope not in evidence | Verify grant scope for actual response shards, run allowed subset in ephemeral controlled compute, do not publish participant-level output |
| [UCI Bike Sharing](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset) | Predict held-out year aggregate usage | CC BY 4.0, official `day.csv` SHA matched mirror; no personal rows ingested | Existing independent 2011/2012 temporal holdout is verified; not an RCT/human survey |
| [HeartSteps V1](https://github.com/klasnja/HeartStepsV1) | Randomized walking notification and 30-minute steps | Public CC BY 4.0 release, participant-data governance conditions; original RData analysis set not reconstructed | Preserve H005 waived exact replication; do not confuse exploratory associations with RCT effect |
| [Concordia](https://github.com/google-deepmind/concordia) | Artificial agents and explicit environment transitions | Apache 2.0 upstream code; model/data rights separate | Move beyond two-agent mock to real LLM + validated externally observed human behavior when authorized |
| [UCI Online Shoppers Purchasing Intention](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset) | Binary outcome in observed browsing sessions | Needs source-specific license verification and personal/session leakage review | Potential *observational* held-out prediction alternative, **not** causal intervention |
| [UCI Student Performance](https://archive.ics.uci.edu/dataset/320/student+performance) | Educational outcomes and covariates | Sensitive participant characteristics; source-specific rights/ethical processing review required | Only approved non-sensitive aggregate evaluation; avoid individual profiling and deployment claims |
| [DoWhy](https://github.com/py-why/dowhy) / [EconML](https://github.com/py-why/EconML) | Causal inference code and methods | Code license and benchmark data licenses reviewed separately | Reuse tested methods on genuinely randomized permission-cleared trial with recorded treatment assignments |

## Acceptance remains literal

S002 needs actual outcome measures of 40 unseen studies (or a clearly documented scientific equivalence revision that preserves the original), training-set-only majority/frequency baselines, accuracy/TVD with denominators and source checks. S004 needs calibration and subgroup uncertainty on those actual held-out outcomes. S005 needs licensed pretrained model predictions on the *same* evaluations and measured inference cost. S006 analytic toy is not empirical causal fidelity; a separate human RCT benchmark must test effect predictions with a valid randomized comparator. S007 real engine mock does not validate human agents; S008 UCI observational temporal transfer is not unseen person/study generality.

Never change task statuses to force an end-of-phase claim. Permission uncertainty is an external access issue, not a request for human routine approvals when an autonomous policy loop is later deployed.

## Publication policy

Write original English-first explainers with source URLs, as-of/version, and meaningful visuals. The authoritative Anicca blog bridge is a signed content manifest on canonical GitHub main with source and media hashes; a separate site-build PR must pass before deployment. New articles must have live URL readback. Public blessing cards must say `NOT_MEASURED` until independently verified P1/P2/P3/P4/P5 evidence exists. X and other channels require an actual connected account and provider receipt: planned copy or a draft is not a posted tweet.
