# Coconala paid lane: every paid client

## Goal

Reflect Ryu0820119's latest four requests in the existing Colors site, publish the
actual revision, send it once as the formal delivery, and make the paid lane admit every
live paid order while keeping bounded worker
concurrency.

## Non-goals

- Do not resend after official formal-delivery readback succeeds.
- Do not change unrelated marketplace lanes; every tracked paid room is in scope.
- Do not add a new scheduler, provider, database, or browser automation framework.

## Acceptance criteria

1. The public Colors site has the four requested changes: HOME campaign banners removed;
   pricing's provisional-reservation panel removed; the WEB予約 `RESERVE` intro removed;
   the supplied guide banner appears first and its old introductory copy is absent.
2. Ryu's talkroom contains the revision message submitted with `正式な納品` enabled, and
   official readback proves the resulting terminal state.
3. Paid admission includes Ryu `18211957` and admits all available orders in the pass;
   only the worker pool remains bounded at eight concurrent projects.
4. Focused site behavior and paid-lane tests pass; Codex account 2 is evidenced in the
   live paid-runner selection.

## Planned change set

- `work/colors-site-review-v64/index.html`: four small markup changes, about 4 lines.
- `work/colors-site-review-v64/app.js`: remove the provisional-reservation card and
  render the supplied guide banner before the guide list, about 4 lines.
- `work/colors-site-review-v64/site-content.js`: remove HOME campaign data and the old
  guide intro text, about 6 lines.
- `skills/earn/gig/scripts/paid_direct.py`: remove fixed paid-room exclusions and pass
  all available paid items to the existing bounded executor, about 2 lines.
- `skills/earn/gig/tests/test_paid_remote_wait.py`: one regression for admission beyond
  eight items, about 12 lines.

No other files are intended to change.
