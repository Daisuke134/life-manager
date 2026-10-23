# Test: fact-bound branded script QA

## Input

Brand brief: Launch a reusable insulated bottle for commuters. Required facts: keeps drinks cold up to 12 hours; 600 ml; available in blue and black. Required CTA: “See colors in the link in bio.” Avoid environmental claims, health claims, price claims, and words such as “best.” Audience: commuters. 25 seconds.

Draft script: “This is the best eco bottle ever. It keeps your coffee hot all day and costs less than lunch. Grab every color now!”

## Expected checks

- Flags unsupported “best,” “eco,” hot-all-day, price, and “every color” claims.
- Preserves only the supplied cold-duration, capacity, and two-color facts.
- Produces a 25-second revised script with spoken line, on-screen text, visual cue, and the exact CTA.
- Labels any missing approval rather than inventing it.
