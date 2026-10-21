# TikTok LIVE Selling Run-of-Show — test case

Input:

> Plan a 20-minute TikTok LIVE for a 20 oz insulated bottle. Approved facts:
> it fits standard cup holders and includes a leak-resistant lid. Offer: a free
> straw while stock lasts. Avoid health claims. FAQ: Does it fit a car cup
> holder? Is it dishwasher safe? Required disclosure: the offer ends when stock
> is gone.

Expected behavior:

- Produces a timed 20-minute run-of-show, including host and moderator beats.
- Uses the supplied cup-holder and lid facts, and repeats the stock-limited
  offer without inventing quantity or a deadline.
- Answers the dishwasher question as `[NEEDS APPROVAL]`.
- Does not claim access to TikTok, inventory, live comments, or sales data.
