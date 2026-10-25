# Real Ampersand v0.1 API inference — authenticated evidence

**2026-10-22 JST | First successful authenticated API readback | Research only, not publication.**

## Verification boundaries

- Provider/API: humans& Ampersand `ampersand-v0.1`, `https://ampersand.humansand.ai/v1`, official documented Agents API.
- Caller: GitHub-hosted Actions runner, **not a playground**, on research branch `research/manager-ampersand-live-api-20261022`.
- Evidence: [GitHub Actions run 39710166900, successful attempt 2](https://github.com/Daisuke134/life-manager/actions/runs/39710166900).
- Workflow source revision: `95700e5c3ead36c89703d64da43dc8f265fdb4ec`.
- Result: workflow `completed / success`; Python 3.12 and `openai==3.24.0` installed, authenticated `GET /models` includes `ampersand-v0.1`.
- One fresh **authenticated and billed-eligible** fictional, no-tools Agent session was created using a repository Actions secret; its server event reached `agent.session.idle`. The SDK returned `output_text` containing 502 characters.
- No direct access to account token totals or exact settled cost was read. Do **not** claim $0 cost or verified accounting based on a single successful log. One synthetic model reply is not an independent quality benchmark.
- **No real-world external tools, interventions, confidential user data, or production Manager effects** were supplied or executed.
- The previously blocked `AMPERSAND_API_KEY` secret was configured, then revised by the user. The successful attempt used the updated secret. Neither this document nor the workflow prints key contents.

## Exact fictional prompt

> A three-person project team plans a Friday review. Earlier, Sam explicitly said they cannot attend Friday. Should the assistant flag this issue, ask something, or wait? Give your recommendation and why.

## Actual Ampersand model response — unedited (502 characters)

> The assistant should flag the conflict proactively, since Sam's unavailability is known, relevant, and unlikely to be surfaced by the team otherwise — waiting risks a scheduling decision that excludes Sam without anyone realizing. It should mention the fact briefly and neutrally (e.g., "Sam said earlier they can't do Fridays — want to check with them before locking this in?") rather than deciding on their behalf, leaving the team to choose whether to reschedule, get Sam's input, or proceed anyway.

## What this establishes / does not establish

**Established:** This repository's GitHub-hosted execution environment can authenticate with the actual Ampersand v0.1 provider and retrieve an authentic complete model response from the Agents API using an existing secret. No playground, Mac, or personal computer required. The sampled response preferred flagging a known conflict while leaving the group decision to people.

**Not established:** A secure general production SDK adapter; correct handling of session follow-ups, recovery, usage, billing and retries; an independent model-vs-baseline assessment; Persimmon access; simulated long-horizon improvement; private user alignment; causal improvement in any real person's life; success for the entire Manager roadmap. This one synthetic reply has proof level **P0**.

## Ordered immediate next work

1. Rotate any API key or account password previously shared in chat, and replace GitHub Actions secret with a freshly copied ASCII key directly from the provider console. The one-off workflow includes bounded in-memory Unicode confusable normalization, but **should not become the permanent credential-management strategy**.
2. Add a one-session follow-up test verifying session history, exact final completed turn, idempotency for events, and failure/silent handling; ensure token usage and settled cost are recorded without credentials or private prompts.
3. Introduce an optional, provider-neutral Manager `PASS/ASK/PROPOSE` adapter and strictly type-check all output; disallow action execution, authorization changes, unsupported causal conclusions, unknown sources, and uncontrolled spending.
4. Run a held-out synthetic suite against deterministic Manager baseline including refusal, prompt injection, privacy, unwanted coaching and the `NO_ACTION` option; report negative and inconclusive findings.
5. Keep all Manager observational and intervention evidence independent of model self-report; field intervention requires scoped lawful authorization, comparison, stopping rules and independent readback.
6. Update both English and Japanese book/research manuscripts in GitHub, but **do not publish articles or deploy the blog** until explicitly requested.

## References

- [Official getting started](https://ampersand.humansand.ai/docs/)
- [Official integration guide](https://ampersand.humansand.ai/docs/GUIDES.html)
- [Existing Ampersand research archive](https://github.com/Daisuke134/life-manager/tree/research/manager-ampersand-deep-dive-20261022/products/manager/docs/research/ampersand-20261022)
