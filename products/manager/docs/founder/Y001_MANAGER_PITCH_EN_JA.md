# Manager: English pitch with Japanese support

**Y001 draft for YC W27 preparation.** Prepared 2026-10-22 JST / 2026-10-21 UTC. This is a truthful product narrative and evidence ledger, not an application submission. No application deadline, interview date or presentation booking has been verified or asserted.

## One sentence

**English:** Manager is building autonomous software that improves access to public services and produces auditable evidence of what changed.

**日本語:** Managerは、公的支援へのアクセスを改善し、何が実際に変わったかを検証可能な証拠として残す自律型ソフトウェアを開発しています。

The sentence describes the product being built. The current prototype has demonstrated a public digital artifact, while improvement in people's access or wellbeing remains to be measured. Use the evidence sentence below immediately after this one-liner whenever the prototype's status matters.

## Who it is for and what it could improve

The first beneficiary hypothesis is a person trying to find the correct official route for financial hardship support. The first product surface is an owned public navigation page that links to authoritative Japanese support information. A possible customer or operating partner is an organization responsible for a support-information journey, such as a public-service or nonprofit operator. Customer demand, willingness to pay, procurement and distribution are unvalidated.

The candidate mechanism is reduced navigation friction: a person finds an appropriate official destination and can proceed with a support task. The downstream claim to test is whether this leads to actual access to useful support. Finding a page, submitting an application, being accepted and receiving a benefit must be recorded separately. The [provisional wedge](../product/FIRST_WEDGE.md) is not U003 completion because the prerequisite five consented interviews are absent.

The official [MHLW livelihood-support overview](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html) verifies that such support routes exist. It does not verify this problem hypothesis or Manager's impact. [GOV.UK's completion-rate guidance](https://www.gov.uk/service-manual/measuring-success/measuring-completion-rate) helps define the distinction between navigating to information and completing an actual service transaction.

## The evidence sentence

**English:** We have shipped an owned public support-navigation prototype: at the recorded verification time, six HTML pages matched the release and 16 public browser checks passed. This verifies digital delivery; human outcomes and causal benefit have not been measured.

**日本語:** 自社管理の公的支援ナビゲーションを公開し、記録された検証時点で6つのHTMLページがリリース内容と一致し、公開サイトに対する16件のブラウザ検査が通りました。確認できたのはデジタル成果物の配信です。人の生活への結果や因果的な改善効果は、まだ測定していません。

Source: [Phase06 digital execution record](../verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md), verified 2026-10-21 14:36 UTC. [Source/build/readback run](https://github.com/Daisuke134/life-manager/actions/runs/39617848783) · [Pages deployment run](https://github.com/Daisuke134/life-manager/actions/runs/39618047098) · [Public prototype](https://daisuke134.github.io/life-manager/manager-support/). The pages are a single product release, not six beneficiary studies. The checks are software checks, not 16 people.

## Short spoken pitch

### English

Manager is building autonomous software that improves access to public services and produces auditable evidence of what changed. We are starting with an owned navigation page for people seeking official financial support. The prototype is live: six pages matched the release and 16 public browser checks passed at our recorded verification. We have not yet measured whether anyone obtained support or experienced better wellbeing. Our technical approach connects a bounded permission to a real action, an independent readback and a separately evaluated outcome. Our next product question is whether a service operator and consented users identify navigation as a meaningful barrier—and whether improving it leads to actual support access at an acceptable cost.

### 日本語補助

Managerは、公的支援へのアクセスを改善し、何が変わったかを証拠として残す自律型ソフトウェアです。最初の候補は、経済的な支援を探す人向けの公式情報へのナビゲーションです。試作サイトは公開済みで、記録時点では6ページの内容一致と16件のブラウザ検査を確認しました。ただし、実際に支援を受けられた人や、生活が改善した人は測定していません。技術的には、限定された権限、実行、独立した状態確認、その後の結果評価を結びます。次に確かめたいのは、サービス運営者と同意した利用者にとって、情報への到達が本当に障壁なのか、そして改善が費用に見合う支援到達につながるのかです。

## What exists, and what remains a hypothesis

| Claim | Supported status | Wording to use |
|---|---|---|
| Public digital product | Dated source, deployment and independent served-byte/browser evidence exist | “A live support-navigation prototype, verified at the recorded release.” |
| Existing kernel and simulations | Offline fixture and research artifacts are documented in the product spec; new integration work requires its own verification | “Research software and controlled execution components.” Avoid a claim of field autonomy from a fixture test. |
| Downstream human benefit | `NOT_MEASURED` | “We have not measured whether the prototype improves human outcomes.” Missing measurement does not mean the effect is zero. |
| Causal net benefit and replication | Not established | “Requires a credible comparator, costs and harms, uncertainty, and replication.” |
| Users, customers, revenue and product-market fit | No verified customer, revenue or conversion evidence is provided by this package | State as unvalidated; do not invent a user count, revenue number, pipeline or forecast. |
| Five consented interviews / selected first wedge | No qualifying interview evidence in this package; U003 remains provisional | “A candidate use case to validate with beneficiaries and operators.” |
| Real funding or indoor-environment interventions | Original permission/funding/site gates remain unresolved in the baseline | Do not imply a page release completed the original transfer or indoor-environment tasks. |

The product evidence categories are [P0 simulation/model score; P1 authentic receipt; P2 independently observed state change; P3 authentic human outcome; P4 causal net improvement; P5 replication](../MANAGER_PRODUCT_SPEC.md). The current public-delivery claim is **P2 artifact only**. A published artifact is real, but it is not P3 or P4 human benefit.

## Technical thesis and product hypothesis

The technical thesis is that an autonomous action should remain accountable to a specific authority and observable result. A scoped standing authorization can permit repeated actions within a bounded purpose, budget and expiry without inventing permission for every new situation. An execution receipt should connect to an independently verified change. A downstream outcome should retain its own units, uncertainty, costs and harms. The [completion gates](../roadmap/PRODUCT_COMPLETION_GATES.md) specify the evidence needed before broader completion claims.

The product hypothesis is that a service operator will value this traceability when maintaining and improving a public support journey. A business model has not been validated. Operator-paid software or evaluation tooling is a candidate to investigate, not existing revenue or a pricing commitment. No market-size estimate is asserted in this draft.

This is not an exclusivity claim. For example, [Simile's official site](https://www.simile.com/) already describes human validation and uncertainty for behavior simulation. Manager should test whether its particular connection from authority through actual delivery to independently observed outcomes is useful to customers. It should not claim that other companies never use human validation, or that a plausible simulation already demonstrates causal benefit.

## Short answers for a review or application

**What can you demonstrate today?** A real owned public support-navigation artifact and its dated verification record. The demo must label fixture examples and simulation outputs separately. It must show “not measured” for human outcomes rather than fill in a success result.

**What is the first meaningful success?** The engineering success is a correct, usable official-support route on the owned surface. The first human success would be a valid observation that someone completed a meaningful support step. The first causal success would require a predeclared comparison showing net improvement after costs and harms. These are different milestones.

**What is unknown?** Whether the proposed population experiences a material navigation barrier, whether an operator can measure the downstream task, whether the intervention changes it, how much it costs, and whether an operator will pay for the product.

**What help would be useful?** A service operator willing to discuss a real information journey and a researcher willing to critique the measurement design. This is proposed pitch language only; no invitation has been sent and no collaboration is claimed.

**What are you claiming about AGI?** The work explores autonomous action with rigorous outcome evidence. No general intelligence, human-level performance or comprehensive reduction in suffering has been demonstrated by this prototype.

## Publication and reuse checks

The short pitch can be reused with its evidence sentence and timestamp. Update factual status only when a new receipt or independently verified outcome exists. A newly passing test must not retroactively change the 2026-10-21 baseline. Remove no uncertainty merely to shorten a slide. YC W27 is the planning context from the task registry; this artifact does not verify eligibility, deadlines, admission, an interview or an application submission.

Y001's one-liner, beneficiary/customer hypothesis and truthful evidence level are now drafted in English and Japanese. Y003 application submission, Y005 conversations, U002 interviews and U003 final selection remain separate work. Primary-source retrieval details are in [the source registry](../research/COMPLETION_PRIMARY_SOURCES_20261022.json).
