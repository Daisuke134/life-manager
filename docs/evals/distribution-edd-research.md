# Distribution EDD: evidence and reuse study

This is a research reference. Execution order, ownership, and checkboxes belong only to [the canonical SSOT](../superpowers/specs/2026-09-25-life-manager-unified-ssot.md). Scope: read-only Capafy/Writer/marketing-engine audit, primary-source repository study, and a proposed distribution evaluation loop. No cadence, account, seller, publisher, credential, paid endpoint, or production state is changed.

## What the current evidence establishes

The first offline CFO probe did not establish production input-path equivalence, so its 18 unknown results alone are not a production-coverage finding. The actual sent B7 packet referenced by `last-result-report.json` was independently read: source release `a299acc0`, economic snapshot `2026-10-13T08:58:24.732964Z`, all 18 trailing-net statuses unknown with empty currencies, actual billed expenses unavailable/source-unconnected, Google billed expenses verified. Packet projection hash is `ccf66f60dde32860bf959d195340f36682bbac63c9759354b50f927d2f1dc515`. This confirms incomplete normalized net-profit evidence even though Capafy has observed historical gross sales.

Capafy's saved official analytics were observed at `2026-10-13T08:11:12Z`. The seller dashboard reports last-seven-day gross revenue `$0.00` and orders `0`. Last-30-day gross is `$43.83`; traffic attribution reports 17 paid orders and 6 trials. The account analytics field `orders=23` must not be relabeled as 23 paid orders. The `$6.82` contribution estimate uses a presumed 80% seller share less `$28.24` of actual OpenRouter charges; billing allocation/window differences, final fees, and payout coverage mean this is not settled net profit or true MRR. Saved payout readback reports paid-out `$0.00`.

The publication ledger's October 7–13 rows, through the observed 17:00 JST slot, contain 67 attempts: 65 site-publication records and 2 blocked records. The X destination records contain 62 `PUBLISHED`, 3 failed, 1 skipped, and 1 absent. These are ledger/provider-status observations, not 62 independently checked native post impressions. Two recent site URLs were freshly HTTP 200 and contained their recorded Capafy CTA links. The factory ledger contains 15 submissions in the same date range, all recorded as under review; submission is not listing approval or a sale. The first local inventory read was 46 listed, 7 occupied, 12 delisted, 1 retry, 66 observed. A later independent reader saw 47 listed/8 occupied/68 observed under the same `observed_at`; this mutable cache is not a frozen official inventory snapshot. Capture its payload hash and source time before using it for a change comparison.

### Fresh official funnel probe

Using the existing read-only `_post` and credential helper from `capafy_hourly_reconcile.py`, the authenticated endpoints `/app/developer/traffic-sources/v2/{impressions,visits,sales}/stats` were read at `2026-10-13T09:08:50Z`. Dates are UTC calendar dates October 7–13, with a partially elapsed final day; this is not an exact rolling 168-hour window. No provider mutation or charged data route occurs.

| Provider source | Listing exposures | Detail views | Trials | Paid |
|---|---:|---:|---:|---:|
| Internal search | 3,161 | 129 | 0 | 0 |
| Internal category | 538 | 3 | 0 | 0 |
| Internal hot | 705 | 1 | 0 | 0 |
| All sources | not a comparable denominator | 395 | 0 | 0 |
| Registered CT links | not supplied | 7 | 0 | 0 |
| Registered X CT links | not supplied | 0 | 0 | 0 |

Internal exposures sum to 4,404. All-source views include direct 130, search 129, other 71, AI overview 49, Google 4, category 3, hot 1, registered CT 7, Facebook 1. Do not divide all-source views by internal-only exposures or call these counts independent qualified humans. The provider exposes `userIdExposureCount`, but its deduplication, bot/self-view treatment, and exposure definition are not independently established here.

Provider response SHA-256: impressions `4d10adcdf92b0a292cfd408ca1b80e7c7d612bd58a88c62522fd735a0027f2e4`; visits `e11657745a7351e13d9b788d6d00d6696db37a73057a47dfbfb24356a9be81be`; sales `8c679601e0d6c332e4ecf6f5b6ffb35fa5888d416ba528a916047d1ddc23254a`.

The earlier saved snapshot has 376 views rather than the later fresh 395. Keep each timestamp with its values; do not silently mix snapshots. The existing hourly collector does not fetch impressions, despite documenting that endpoint. This is a concrete measurement gap.

### Attribution and runtime gaps

- Four seller slugs have explicit registered CT mappings in `capafy-distribute-daily.sh`. `marketing-strategist` does not. Fifteen recent ledger entries promote it; a freshly checked article emits `ct=capafy-distribute-marketing-strategist`, which is absent from the observed provider CT rows. Its registered-token association needs official confirmation. The observed `marke` row belongs to **Japanese Humanizer Pro**, so it must not be guessed as the Marketing Strategist token.
- Per-product/channel static CT values can establish channel attribution but do not identify each creative. Reuse the existing owned redirect/click receipt mechanism for `campaign_id`/`creative_id`, retain the actual seller-issued downstream CT, and keep per-creative sales unknown unless a provider supports a valid click-to-order join. A UTM or same-day sales increase alone is not causal attribution.
- Writer's installed `article-daily` plist has 18 hourly entries, 06:00–23:00. The primary paid Writer is currently held by `resource_effect_unknown`, not simply limited to one scheduled article per day.
- The installed Capafy distributor has calendar minutes 19/49, equivalent to every 30 minutes, and release `a299acc0`. Current source also requests 30-minute wakes. Its latest observed attempt is blocked by `resource_capacity_busy`. High configured cadence does not establish successful throughput.
- The registered marketing-engine products are `anicca-ios`, `honne-ai`, `ebook-en`, `ebook-ja`, `life-manager-cloud`. The shared Treg monitor adds `dhamma-quotes`, `sleep-reset`, `studio-cherie`, `thankful`: nine research targets. Capafy, Writer, PromptBase, and Affiliate are not in that profile set. This is a shared research task with incomplete product coverage, not a complete shared distribution agent. Its latest runtime attempt is held by `resource_effect_unknown`.
- `experiment-manifest.schema.json` and `experiment_attribution.py` already carry product/creative/account/hook/renderer/publish identities, maturity, evidence refs, and deterministic/aggregate/modeled/unknown attribution. The manifest does not carry an explicit control, allocation unit, randomization, exposure count, or stopping protocol. Reuse and extend this contract minimally rather than creating another framework.
- The common Postiz adapter currently selects the hosted `https://api.postiz.com/public/v1` endpoint. The existing hosted route must not be advertised as a universally free self-hosted path.

These facts support a distribution problem, but not the claim that awareness alone explains everything. Thousands of marketplace exposures, hundreds of detail views, and zero trials/purchases also leave click-through, targeting, offer, trust, trial design, and product fit as live hypotheses. Preserve the five frozen sellers and separate their editable draft status from `has_online_version=true`.

## What can actually be reused for free

Source and license checks are made against primary repositories, not a directory's description of an "end-to-end agent." Free software, free trial credit, provider usage fees, model inference, and hosting are distinct.

| Component | Verified role | Cost/licensing finding | Recommendation |
|---|---|---|---|
| [Life Manager marketing engine](../../skills/earn/marketing-engine/README.md) | Existing manifests, publication adapters, measurement, product routing, experiment attribution | Already present; existing hosted/provider/model routes can still have costs | Keep as the shared foundation; audit actual caller paths, not README promises |
| [Marketing Skills](https://github.com/coreyhaines31/marketingskills) | Channel, CRO, research, content and experiment playbooks | MIT; external partner/data services are optional and may be paid | Reuse the installed skills and suitable repo-owned licensed prompts; not a standalone executor |
| [Postiz](https://github.com/gitroomhq/postiz-app) | Multi-channel scheduling and publication | AGPL-3.0 self-hosted code; infrastructure, AI provider keys and platform access can cost money | Reuse current adapter; make a self-hosted endpoint an optional OSS path when needed, without switching live owners during this study |
| [Umami](https://github.com/umami-software/umami) | First-party traffic, campaigns and conversion events | MIT; self-hosted PostgreSQL/compute needed | Optional only if existing click/event capture cannot answer the selected experiment |
| [Mautic](https://github.com/mautic/mautic) | Segmentation, email/campaign automation and nurture | GPL-3.0-or-later; server/SMTP delivery remain resources | Study/reuse for an actual owned-audience requirement, not an initial replacement for current loops |
| [GrowthBook](https://github.com/growthbook/growthbook) | Assignment, feature flags, experimentation and statistics | MIT outside explicitly commercial enterprise directories | Optional established statistics/assignment component after events and traffic exist; no need to deploy it before a minimal two-variant experiment |
| [GEPA](https://github.com/gepa-ai/gepa) | Optimize prompts/programs with evaluator feedback and reflective search | MIT; reflection/model execution has its own cost | Use the measured-candidate pattern; not proof of marketing lift, and not an immediate new dependency |
| [OpenSEO](https://github.com/every-app/open-seo) | SEO data/MCP, research, rank/backlink/audit workflows | MIT code; DataForSEO key required and data calls paid, AI visibility may use OpenRouter | Optional paid/BYOK research, excluded from the mandatory zero-additional-spend path |
| [Treg](https://github.com/superdesigndev/treg) | Tool/data proxy and catalog, including some free public/own-account routes | Hosted catalog can charge per call. Current source LICENSE is Apache-2.0 **with additional hosted/embedded third-party service restrictions**; homepage's AGPL label disagrees | Do not bundle the server or treat its catalog as universally free. Reuse existing gated task for explicitly eligible zero-cost data only; paid use remains optional |
| [ViewTrack](https://www.viewtrack.app/) | Cross-platform social metrics | Current public client defines Free 50 accounts/50 videos but `refreshesPerDay=0`; Basic $24.99/month enables refresh. Earlier actual account onboarding was paid-gated | Exclude as a required free live-measurement source; an MCP registration does not make refresh usable |
| [Vercel marketing-team Eve template](https://github.com/vercel-labs/marketing-team-eve-template) | Team lead plus content, SEO, email, product and social specialists; brand context and tracking conventions | MIT template; Eve/Vercel Blob and Notion/Typefully/Resend connectors, model/runtime services; approval before irreversible publication | Useful architecture/source examples; not a proven zero-cost autonomous revenue engine or a reason to replace existing owner loops |
| [LangChain Social Media Agent](https://github.com/langchain-ai/social-media-agent) | URL to X/LinkedIn content, scheduling, review | MIT; documented Anthropic, Firecrawl, Arcade and LangSmith integrations; human review/auth flow | Narrow content/publishing reference, not free end-to-end growth |
| [UnifAPI Agents](https://github.com/unifapi-agent/agents) | SEO/GEO/social listening/influencer research | MIT skills over remote data APIs with trial credits; explicitly read-only and never posts | Adjacent research recipes, not distribution execution or an unlimited free service |
| [Autonomous Marketing Agent](https://github.com/abandini/autonomous-marketing-agent) | Broad orchestration/optimization design and sample modules | No explicit repository license was found in the inspected root/metadata; README breadth is not deployment or receipt-backed revenue proof | Study only; do not select as a freely reusable production replacement |

OpenSEO source pin `89e5a00717cdf049b7c2b4e29646edb3a7d4995b`: [DataForSEO requirements](https://github.com/every-app/open-seo/blob/89e5a00717cdf049b7c2b4e29646edb3a7d4995b/docs/DATAFORSEO_API_KEY.md). Treg source pin `7f34f531d1ace1e55be24e4b056a09012719a342`: [actual license](https://github.com/superdesigndev/treg/blob/7f34f531d1ace1e55be24e4b056a09012719a342/LICENSE). ViewTrack's `/pricing` URL returns 404; the fallback official homepage HTML/JavaScript supplied the current plan definitions. No fresh authenticated ViewTrack onboarding is attempted in this study.

No inspected candidate establishes all of research, content, native publication, reliable attribution, causal optimization, and settled net revenue with universally free execution. This is a finding about the inspected set, not proof that no such project exists anywhere. The default proposed path has zero additional paid-data/API spend, reuses owned resources, and makes paid services optional; it must still state compute, hosting, account and model requirements honestly.

## Evaluation-driven marketing is a feedback loop with two kinds of evidence

[Microsoft ExP](https://www.microsoft.com/en-us/research/group/experimentation-platform-exp/) embeds hypothesis testing and measured real-world impact into product development. [GrowthBook's statistics documentation](https://docs.growthbook.io/statistics/overview) supplies established experiment-analysis approaches. [Google Meridian](https://github.com/google/meridian) and [Meta Robyn](https://github.com/facebookexperimental/Robyn) show marketing impact/budget optimization from aggregated data; they are modeling packages requiring suitable historical inputs, not autonomous acquisition agents. With seven CT visits, introducing marketing mix modeling would not create the missing observations.

Use two linked loops:

1. **Offline engineering evaluation:** a real failure trace becomes a small case. Code grades destination availability, seller/CT association, receipt shape, identity, deduplication and cost coverage. A calibrated model may grade one subjective content failure. Repair the observed cause; replay the same cases and held-out cases. These checks can prevent broken distribution but do not establish demand.
2. **Online growth experiment:** freeze one product/offer and one channel/account, record a hypothesis and one change, assign comparable exposure units, wait for the conversion/refund window, and compare qualified traffic/activation/paid contribution against control. Views and click-through diagnose the funnel; mature receipt-backed contribution is the economic outcome. A selected native social account cannot generally randomize viewers, so randomizing creative/time slots must be described honestly and account/time clustering retained.

Repeated comparisons require a predefined finite-horizon or valid sequential protocol. Record sample, effect interval, costs, account/channel and conversion maturity. Sparse or incomplete data yields `inconclusive`/`unknown`, not an automatic winner. Increasing article count alone does not increase independent buyer exposure.

### Smallest proposed pilot after Writer A8 calibration

Keep the Writer A8a → A9 → A8b calibration prerequisite for this EDD lane. The existing Capafy CD1–CD10 business plan and its owners proceed independently. DD03–DD07 refine CD1's shared measurement/evaluation contract; DD08–DD10 refine experiment acceptance for CD2–CD5. They do not create another collector, scheduler, or publication owner. Then use the existing Hook Lab distribution lane: its frozen seller has historical paid demand and 28 of the 67 recent promotion entries, making it an already exercised path. Keep the listing/price/live version fixed. First observe native post impressions and qualified CTA clicks. Then compare one concrete before/after product demonstration with the existing generic article-promotion creative on the same allowed channel/account and comparable assigned slots. Do not increase every cadence or change all offers at once.

The common component consists of a product/offer manifest, existing trace/publication/attribution ledgers, a small evaluator for observed failure classes, and a bounded experiment/decision record. Product manifests differ in audience, offer, permitted channels, outcome source and conversion delay. Share machinery; validate the winning hypothesis for each product instead of assuming that a Capafy creative sells mobile subscriptions, paid writing, and affiliate offers equally.

Existing authorized channels keep operating within their owners and zero-additional-spend allowance. A one-channel controlled experiment is an evaluation unit, not a decision to remove other channels. ED2's per-slot reach check requires an actual creative/slot-to-click receipt join; static product/channel CT totals alone establish only a channel-window observation. Never credit one shared-token visit as success for every slot.

Distribution options include marketplace-native search and recommendations, search-intent pages, useful free tools/templates/demos, existing social accounts, an owned newsletter, relevant communities and partners/referrals. [Search Console](https://search.google.com/search-console/about) supplies first-party query/impression/click/position observations; it does not create search demand or index pages merely because an agent publishes more articles. Publication or outreach through each channel remains with its existing authorized owner.

Self-healing restores a known broken route and verifies recurrence/replay safety. Low click-through is not a crash and must not trigger an account restart. Self-improvement changes one creative, targeting or offer hypothesis and retains it only on appropriate measured outcomes. The optimizer must not alter grader definitions, labels, split, receipts, identities, resource caps or effect fences to make itself pass.

## Questions that remain visible

| Question | Current answer / next evidence |
|---|---|
| Is zero revenue in the last week confirmed? | Yes for the provider's observed calendar window; sales/trials are zero. This is separate from 30-day gross and bank settlement. |
| Does distribution alone explain it? | No such causal conclusion follows. Exposure and detail views exist; targeting/offer/trust/activation are still hypotheses. |
| Is once-a-day cadence the main Writer bottleneck? | Current installed calendar already has 18 hourly entries; unresolved effect and actual outputs matter. |
| Did 62 X status records reach qualified buyers? | Native impressions/engagement/qualified click evidence is absent from the inspected ledger. Collect that before optimizing publication count. |
| Are Marketing Strategist CT links valid? | Its emitted token is absent from observed CT rows; confirm registration and product binding. Do not substitute the unrelated `marke` token. |
| Can seven CT visits identify a revenue winner? | No credible precision is established. First improve/verify reach and qualified traffic, then collect mature conversions. |
| Is an OSS dependency costless and automatically compatible? | Verify license, provider charges and runtime requirements separately. Installed/registered does not establish production capability. |
| Will this make the benchmark leading or establish AGI? | It can create reproducible operational/economic evidence. Adoption and broad AGI claims remain unproven. |

Best case: tracking/receipt gaps close, qualified traffic rises, and a replicated experiment produces paid contribution. Base case: better observability and visits, with too few mature purchases to establish profit lift. Worst case: optimized views/content scores do not improve demand or economics. The strongest replacement argument is faster access to an existing template's specialists/connectors; the existing engine already has the difficult owner/fence/receipt boundaries, while inspected replacements do not supply our financial evidence. The likeliest reason the distribution-first hypothesis is wrong is an offer/trust/activation mismatch among the already exposed visitors.
