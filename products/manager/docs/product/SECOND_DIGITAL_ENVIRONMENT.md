# Second digital support pathway: mental support and physical information

**Prepared 2026-10-22 JST / 2026-10-21 UTC. Status: EXISTING_PUBLIC_ARTIFACT / HUMAN_OUTCOMES_NOT_MEASURED.** The second pathway is the existing [mental-support page](https://daisuke134.github.io/life-manager/manager-support/mental.html), with the separately labeled [physical-information page](https://daisuke134.github.io/life-manager/manager-support/physical.html). These are distinct information topics within the **same owned six-page bundle and publisher**. They are not an independently operated second service, a second participant cohort or two clinical interventions.

## 1. Controlled change and mechanism hypothesis

The controlled surface presents short, original Japanese navigation text and links to official resources. It does not provide therapy, diagnose a person, prescribe exercise, collect questionnaire answers or act on a third party's behalf. The proposed mechanism is reduced difficulty in finding an appropriate official source through a clear topic label, readable link and accessible path. That is a design hypothesis: no interviews or observed user study establish that information navigation is the limiting barrier.

Alternative explanations for unmet support include service capacity, cost, eligibility, language, trust, an unavailable preferred communication method or a need for immediate professional care. A clearer page cannot be assumed to resolve those constraints. Possible negative effects include an unsuitable referral, distraction or delay, disappointment, accessibility regression, inferred endorsement or pressure to disclose. The page's source and limits must remain visible.

| Pathway | Owned page and selected source | Technical endpoint | Human endpoint not observed |
|---|---|---|---|
| Mental support | `mental.html`; catalog ID `mental-support`; [MHLW consultation directory](https://www.mhlw.go.jp/mamorouyokokoro/soudan/) | A visible, correctly labeled link to the official directory and an urgent-help notice | Actual contact, appropriate help received, change in distress or validated wellbeing |
| Physical information | `physical.html`; catalog ID `physical-activity`; [MHLW physical-activity information](https://kennet.mhlw.go.jp/information/information/exercise) | A visible, correctly labeled link to official general information | Changed behavior, functioning, health, disease incidence or an indoor environmental exposure |

The [source catalog](../../public_goods/service/catalog.json) contains link-only rights and explicit review dates. The same [renderer](../../manager_core/digital_environment.py) supplies navigation, skip link, disclosure, `NOT_MEASURED` footer and control/source links to all pages. No separate renderer or hidden personalization is introduced.

## 2. Baseline, reference and anonymous tasks

The [baseline journey index](BASELINE_DIGITAL_JOURNEY.md) specifies the source commit, public readback time, exact official URLs, keyboard/mobile protocol, screenshots and limits of the 16 recorded browser cases. Its dated 2026-10-21 release can serve as a historical baseline for a later change. There is no prepublication screenshot of a Manager page: the earlier hosting state did not have this prefix.

For mental support, begin at home, choose **こころの相談** in `main`, inspect the urgent-help notice and activate **電話・SNS・地域の相談先を探す**. For physical information, begin at home, choose **健康づくり**, then **身体活動・運動の公的情報**. Each source-defined route has two content-link activations from home; this is not measured user effort. The keyboard procedure uses **本文へ移動**, visible focus and labeled links. Mobile uses the same content in Chromium's iPhone 13 emulation, not a Safari trial.

The [reference view](https://daisuke134.github.io/life-manager/manager-support/control.html) exposes the same four official resources as an ordinary list. Both views are openly available; **there is no real random assignment or enrolled control cohort**. The browser suite verifies Manager navigation and expected outbound hrefs; a separate source audit checks official reachability. It does not establish actual receipt of support or a health effect.

## 3. Scope, shared release and rollback

Existing owner authority covers the allowlisted `manager-support/` prefix through the same release path documented in the [surface inventory](DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md). Mental and physical pages do not create an additional grant, budget or independent revocation channel. The historical evidence is one shared bundle publication and its independent readback, not two independently operated releases. The seven allowed files are the six HTML pages and `manifest.json`.

Routine updates inside the real standing scope need neither an NPO/facility agreement nor per-run human approval. Existing release admission, budget, source freshness, concurrent-update protection, stop and rollback continue to apply. Unknown external effects require reconciliation, not repeated writes. A rollback restores only an authorized known-good Manager prefix and is independently read back; its sources and authority must still be valid. This document changes none of those controls and makes no claim that a second independent live authority has been exercised.

## 4. Safety and separate outcome families

The operational content boundary is [SECOND_DIGITAL_ENVIRONMENT_SAFETY](../../pilot/SECOND_DIGITAL_ENVIRONMENT_SAFETY.md). It requires factual official links, a visible exit and help option, no personal-state inference, no covert enrollment, no unsolicited messaging, and stop/correction of misleading, coercive or unsafe content. A high-risk claim or unresolved harm does not receive clearance from a model prediction. Existing ordinary support remains available when an optional study component is paused.

Any future human study separately follows the [collaboration/consent protocol](../../pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md) and [independent safety/review protocol](../../pilot/MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md). Those are **unactivated proposals**, not prerequisites for routine anonymous publication. They do not supply an actual partner, reviewer, consent record or dataset.

The [measurement map](../research/MENTAL_PUBLIC_AGGREGATE_MAP.md) separates positive mental wellbeing, loneliness, functioning and financial outcomes. WHO-5 or another justified mental measure would require the exact valid version, rights and voluntary administration; WHODAS or another functioning measure would require its own version/scoring/context. No questionnaire is embedded here. Financial-navigation N=120 in FIRST_STUDY is a proposed sample for that optional study; it cannot be reused as an enrolled mental/physical cohort.

## 5. Evidence and acceptance boundary

The [second-domain boundary](../verification/PHASE06_SECOND_DOMAIN_BOUNDARY.md), [outcome report](../verification/PHASE06_SECOND_DOMAIN_OUTCOMES.md) and [cross-domain causal report](../verification/PHASE06_CROSS_DOMAIN_FIELD_CAUSAL.md) preserve the current result: genuine digital delivery evidence at `P2_ARTIFACT_ONLY`, human outcome **NOT_MEASURED**, actual outcome sample size **null**, enrolled participants **0**, and costs/harms **unknown**. Two topics do not constitute independent populations, replications or a causal comparison.

Original indoor-facility control and PM2.5 conditions are unchanged; there is no observed indoor intervention, exposure reduction or health effect in these pages. Any scope amendment belongs in the sole task registry with original acceptance retained. This design note changes no task status, public authority or source/runtime/workflow code.
