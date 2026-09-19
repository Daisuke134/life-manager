# Verified demonstration — Privacy Notice Change Brief Deck

## Concrete input

```text
Build a stakeholder change brief from only the supplied material. Do not decide
whether the proposed notice is compliant or approved.

Audience: Product, Privacy, and Customer Support leads.
Requested decision: decide whether the proposed notice wording is ready for
accountable-reviewer approval. No approval has been recorded.
Product context: The team plans to add an optional feature that lets an account
holder upload a profile image. The feature target date is 2026-11-03. No storage
location, retention period, recipient, or implementation evidence is supplied.

Prior notice excerpt
"We use account information to provide and improve the service."

Proposed notice excerpt
"We use account information, including an optional profile image when you
provide one, to provide and improve the service."

Supplied reviewer note: Customer Support needs a response for users who ask how
to remove a profile image. No response text, owner, or deadline is supplied.
```

## Actual output

### Change headline

The supplied material describes a proposed privacy-notice revision for an
optional profile-image feature targeted for 2026-11-03. The requested decision
is whether the proposed wording is ready for accountable-reviewer approval;
no approval is supplied. The audience is Product, Privacy, and Customer Support
leads.

### Notice change ledger

| Topic | Prior supplied wording | Proposed supplied wording | Supported textual change | Open question |
|---|---|---|---|---|
| Account information | “We use account information to provide and improve the service.” | “We use account information, including an optional profile image when you provide one, to provide and improve the service.” | The proposal adds an example: an optional profile image when the user provides one. | No separate definition of account information is supplied. |
| Purpose | “to provide and improve the service” | “to provide and improve the service” | This phrase is unchanged in the supplied excerpts. | No additional purpose is supplied. |
| Image removal | No prior wording supplied. | No proposed removal wording supplied. | No before-and-after comparison is available. | `[TBD — RESPONSE TEXT, OWNER, AND DEADLINE NEEDED]` for the Customer Support question. |

### Slide storyboard

| Slide | Title | Takeaway | Supplied evidence | Visual direction | Presenter note |
|---|---|---|---|---|---|
| 1 | Proposed profile-image notice change | The review concerns wording for an optional profile-image feature targeted for 2026-11-03. | Supplied product context and target date. | Title card with audience and target date. | Do not state that the feature is implemented. |
| 2 | Exact wording change | The proposed sentence adds an optional profile image to the account-information example. | Supplied prior and proposed excerpts. | Side-by-side excerpt card with the added phrase highlighted. | Read the supplied wording exactly. |
| 3 | What the notice text does and does not say | The supplied purpose phrase remains unchanged; the excerpts do not supply storage, retention, recipient, or implementation details. | Both excerpts and supplied context. | Two-column “supplied” and “not supplied” list. | Do not infer processing details from the added example. |
| 4 | Customer Support review question | Support needs an answer about profile-image removal, but the material supplies no response text, owner, or deadline. | Supplied reviewer note. | Open-question card with three `[TBD]` fields. | Keep the missing ownership visible. |
| 5 | Requested checkpoint | The supplied request is for accountable-reviewer readiness, not an approval decision. | Requested decision; no approval recorded. | Decision card. | Confirm the final wording and review outcome outside this brief. |

### Review questions and checkpoints

- Is the proposed wording ready to be presented to the accountable reviewer? This is the supplied requested decision; no decision outcome is supplied.
- What response text should Customer Support use for profile-image removal questions?
- Who owns that response, and what is its deadline?
- What storage location, retention period, recipient, and implementation detail, if any, should be supplied for review? The input does not state them.

### Traceability check

- Retained exactly: optional profile image; “when you provide one”; “to provide and improve the service”; 2026-11-03; the three named audience groups; and the Customer Support removal question.
- The statement that the profile-image phrase was added is a direct before-and-after text comparison.
- Excluded: a claim that the feature operates, that images are stored for any period, that a removal process exists, or that the notice is compliant or approved.
- Produced a local text storyboard only; no notice, record, system, or remote platform state was changed.

## Verification notes

1. Every date, audience, product detail, and quoted notice phrase in the output appears in the concrete input.
2. The output marks the storage location, retention period, recipient, implementation detail, removal response, owner, and deadline as unknown because the input does not supply them.
3. The only supported comparison is the addition of the optional-profile-image phrase; unchanged purpose wording remains unchanged.
4. The output does not give legal advice or claim compliance, approval, feature implementation, or an operating removal process.
5. Offline duplicate check: the current source catalog and cached candidate backlog contain no privacy-notice, data-processing, or policy-change workflow. Existing deck skills cover board updates, customer escalations, experiments, launches, research, sales, security exceptions, and talent reviews; none compares pasted privacy-notice revisions while separating notice text, supplied product context, and reviewer gaps.
6. Offline selector readback: the release-owned `sales_selector.select_signal` function was run only against the cached local ranking record. It returned `signal: "sales"` with “Slide Maker — Any Content Into a Styled Deck” as the cached official seller winner. No Capafy endpoint or UI was called. This candidate follows the deck format without claiming direct demand for privacy-notice work.
