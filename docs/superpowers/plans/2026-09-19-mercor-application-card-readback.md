# Mercor application-card detail readback

## Goal

Prevent an existing Mercor application card from being classified as
`listing_detail_not_rendered` while it is only focused or visually selected.
The model must wait briefly for the provider's detail surface after the exact
card click and its existing DOM-click fallback.

## Scope

- Update `apps/job-search-loop/prompts/mercor-pass.md` only.
- Add prompt contract assertions in
  `apps/job-search-loop/tests/test_mercor_pass_contract.py`.
- Preserve the existing exact observed-button rule, fallback click, human gate
  boundary, and submission fence.

## Implementation steps

1. Add a failing contract assertion requiring a bounded five-second detail
   readback wait and a detail-surface signal before recording
   `listing_detail_not_rendered`.
2. Update the existing application-card instruction to poll for at most five
   seconds after each click attempt. Accept URL change or a visible detail
   heading/step summary; do not treat focus, border, or selected styling as
   detail readback.
3. Run the focused Mercor contract test and the surrounding job-search tests.
4. Commit and push the isolated branch, cut an immutable release, apply only
   `mercor-revenue-application`, and run one natural wake. Verify terminal
   evidence, official card/detail readback, and zero effect fence.

## Completion evidence

- Contract test passes with the new readback requirement.
- Loaded LaunchAgent points to the immutable release.
- Natural wake exits normally and records either a detail readback or an exact
  provider/human blocker; no focus-only false negative remains.
