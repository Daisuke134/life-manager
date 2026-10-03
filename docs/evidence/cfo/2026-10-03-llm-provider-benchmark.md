# LLM provider benchmark evidence

Status: `partial` — evaluator contract is implemented and fail-closed; no user-facing model switch occurred.

## Scope

- Fixture: `apps/life-manager/fixtures/provider-benchmarks/location-decision-cases.jsonl`
- Runner: `apps/life-manager/scripts/provider-benchmark-llm.js`
- Candidates: `gemini-current`, `local-codex-shadow`
- Release SHA: `unreleased`
- Digest: `3b1e4bf9064eff18b730bec13c2c7b3b6bbe0bf1adaa89742c0e52067b058350`
- Recommendation: `keep_current`

## Result

Both candidates were deliberately run with `candidate_not_configured` runners so no external model call or new API adapter was created. Accuracy and receipt completeness were `0` for both, and neither candidate became eligible for shadow. This proves the evaluator's fail-closed behavior, not model quality.

The next live shadow run must use the existing Life Manager routing boundary, scrubbed cases, bounded latency, token/cost metadata, and durable receipts. It must compare location grounding, online/no-travel classification, ask-user precision, privacy status, and latency before any user-facing change.

## Candidate references

- Current Gemini pricing and free/paid tiers: <https://ai.google.dev/gemini-api/docs/pricing>
- Local runtime candidate: <https://github.com/ollama/ollama>
- C/C++ local inference candidate: <https://github.com/ggml-org/llama.cpp>
- Hosted throughput candidate: <https://github.com/vllm-project/vllm>

No candidate is promoted by this artifact. Gemini remains the production path for current voice/high-risk behavior.
