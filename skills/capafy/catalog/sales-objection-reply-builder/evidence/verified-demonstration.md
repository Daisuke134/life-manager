# Verified offline demonstration — Sales Objection Reply Builder

## Concrete input

```text
Synthetic scenario: this is not a real customer story or the price of this listing.
Customer's exact words: "The tool we use today is cheaper. Why should we pay $299/month?"
Seller-supplied facts: The fictional seller charges $299/month. Guided onboarding is included. The seller has no published ROI study. No other product capabilities, integrations, customer results, or competitor details are supplied.
Channel: email.
Relationship stage: prospect comparing vendors before a trial.
Desired next step: ask which single workflow matters most so the seller can assess fit.
Constraints: use only the facts above; do not claim savings, payback, integrations, results, urgency, or policy details.
```

## Actual output

### Diagnosis

Likely barrier: price justification against a lower-cost alternative. This is a hypothesis from the customer's words; the reason beyond the price comparison is unknown.

### Variant 1 — direct and transparent

Subject: Re: Comparing tools

Thanks for being direct about the price. The plan in this example is $299/month and includes guided onboarding. We don't have a published ROI study, so I can't claim that switching will pay for itself. If you share the one workflow that matters most, I can assess fit using only the information supplied.

### Variant 2 — concise

The plan is $299/month, with guided onboarding included. We don't have a published ROI study to quantify a return. Share the workflow you care about most, and I can check whether the available facts address it.

### Variant 3 — fit-first

If the lower monthly price is the deciding factor, the current tool may be the better fit. The plan in this example is $299/month and includes guided onboarding, but I can't support a savings claim with the evidence supplied. A useful next step is to compare one workflow using only the facts on hand.

### Proof gaps

- No published ROI study is available to substantiate payback or savings.
- The competitor's price and features are not supplied; only the buyer's statement that it is cheaper is available.
- No product capabilities or integrations beyond guided onboarding are supplied.

### Follow-up question

Which single workflow should we use to assess fit?

### Honesty check

- `$299/month`: supported by the fictional seller facts in the input; it is not the price of this PromptBase listing.
- Guided onboarding is included: supported by the input.
- The buyer says the current tool is cheaper: supported as a buyer-reported statement, not independently verified.
- The current tool may be the better fit if cost is decisive: softened as a conditional suggestion, not a claim about features or actual suitability.
- No published ROI study: supported by the input.
- Savings, payback, customer results, integrations, or additional product capabilities: remove/confirm before use.
- No browsing, CRM access, or message sending occurred.

## Verification notes

- This is a synthetic offline scenario, not a real customer interaction or performance claim.
- The response follows the skill's order and uses only the supplied facts. Each variant acknowledges the price concern and offers one proportionate next step.
- No model call, browser, provider, or PromptBase action was used to author this file.
