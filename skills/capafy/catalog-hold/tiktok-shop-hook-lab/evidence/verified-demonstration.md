# Verified offline demonstration — TikTok Shop Hook Lab

## Concrete input

```text
video_goal: Help commuters notice a product feature before considering the product details.
buyer: Commuters who carry a drink in a bag.
brief_or_transcript: Rough opening: "This is my new tumbler."
product: A stainless-steel tumbler.
approved_product_facts: Its lid twists closed. The product comes in two colors: navy and cream.
tone: Direct and practical.
cta: "See the product details."
constraints: Do not claim that it is leak-proof, keeps a drink cold for a stated duration, or fits every bag.
```

## Actual output

# TikTok Shop Hook Lab: stainless-steel tumbler

## Evidence boundary

- Supplied: The buyer is a commuter who carries a drink in a bag.
- Supplied: The lid twists closed.
- Supplied: The tumbler is available in navy and cream.
- Unknown: `[ADD: approved evidence about leakage, insulation duration, capacity, or bag fit]`.

## Product-opening diagnosis

- First line: “This is my new tumbler.”
- Buyer cue: Unknown; the line does not name commuters or a carrying situation.
- Product discovery: The tumbler is named, but the supplied closing-lid feature is absent. This is an inference from the supplied line and approved facts.
- Friction: The line gives no reason to keep watching because it lacks a buyer situation or supported product detail.
- Unknown: No described visual beat or product-use demonstration was supplied.

## Five hook options

1. **Buyer interruption** — “Commuters, does your drink travel in your bag?” — Evidence: the supplied buyer carries a drink in a bag.
2. **Product contrast** — “This is not just a new tumbler: its lid twists closed.” — Evidence: the supplied lid feature.
3. **Feature reveal** — “Before this tumbler goes in my bag, I twist the lid closed.” — Evidence: the supplied buyer situation and lid feature.
4. **Objection reversal** — “The detail I check before carrying a tumbler is the lid.” — Evidence: the lid feature is supplied; `[ADD: confirm this represents the seller's intended buyer concern.]`
5. **Use-moment consequence** — “Going from desk to train? Start with the tumbler lid.” — Evidence: commuters are supplied; `[ADD: confirm desk-to-train fits the intended buyer.]`

## Recommended 0–3 second blueprint

| Time | Spoken line | On-screen text | Described visual beat |
| --- | --- | --- | --- |
| 0.0–1.0s | “Commuters,” | `CARRY A DRINK?` | Hold the tumbler beside an open bag; this is a described production cue, not inspected footage. |
| 1.0–2.0s | “before this goes in my bag,” | `BEFORE THE BAG` | Show a hand turning the lid until closed. |
| 2.0–3.0s | “I twist the lid closed.” | `TWIST THE LID` | Place the tumbler next to the bag; do not show or imply a leakage test. |

## Supporting copy

- Caption opening: “For commuters carrying a drink in a bag: start with the lid detail.”
- Caption opening: “A stainless-steel tumbler with a lid that twists closed.”
- Caption opening: “Available in navy and cream. Here is the lid step I show first.”
- Product-title text: `TWIST-CLOSED LID`
- Product-title text: `TUMBLER FOR COMMUTES`
- Product-title text: `NAVY OR CREAM`
- CTA: “See the product details.”

## Honesty check

- No leak-proof, insulation, capacity, universal-bag-fit, review, price, availability, sales, or performance claim is made.
- The visual directions are described production cues; no footage was inspected or edited.
- The buyer-concern framing in hooks 4 and 5 needs seller approval and remains marked `[ADD: ...]`.

## Verification notes

- This is an offline, text-only worked output: no Capafy API, UI, model call, media tool, browser, or remote platform was used.
- Every factual statement is traceable to the concrete input; unverified buyer framings are explicitly marked `[ADD: ...]`.
- The output contains five different named hook structures and exactly three one-second intervals covering 0.0–3.0 seconds.
- The listing's buyer-facing capabilities are bounded to text diagnosis, copy, and a described shot blueprint. It makes no claim of video editing, rendering, publishing, metrics access, or sales prediction.
