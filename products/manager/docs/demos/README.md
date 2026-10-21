# Manager public NO_ACTION demo — 2026-10-22 JST

[Watch the 22.96-second MP4](manager-public-no-action-20261022.mp4).
[Captured code output](manager-public-no-action-20261022.json) is the input to the
recording, not a fictional success fixture.

At `2026-10-21T16:47:27.352145+00:00`, the read-only collector fetched the real
public support manifest and all six pages. All page bytes matched that manifest
at source `ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5`. The kernel compared this
observed state with the identical candidate and returned `NO_ACTION`, with zero
external writes and a valid local audit chain. This run did not publish anything.
It demonstrates observation, a bounded proposal, evidence and abstention.

The video visualizes this captured execution output. It is not a recording of
beneficiaries, live treatment, a new deployment or an achieved welfare gain.
Human outcomes are `NOT_MEASURED`. The presentation separates this observation
from previous, separately documented P2 artifact releases.

## Reproduce

From `products/manager`, with public read-only network access:

```bash
python scripts/demo_public_decision.py
npm --prefix tests/e2e ci --ignore-scripts --no-audit --no-fund
npm --prefix tests/e2e exec -- playwright install chromium
node scripts/record_public_demo.cjs
```

The capture uses the current public state, so a later run has a different source
commit and timestamp. The renderer uses the repository's locked Playwright and
an installed `ffmpeg` to produce an H.264 MP4. It contains no fake participant,
payment, measurement or application claim. Temporary browser videos and preview
images belong under the ignored `output/` directory.
