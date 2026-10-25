# Ampersand authenticated console access and next engineering actions
2026-10-22 JST. Research-only handoff. **No article publication or deployment.**

## Confirmed via TinyFish browser
- The user successfully saved Google sign-in, and the authenticated Ampersand console became accessible.
- Console: https://ampersand.humansand.ai/ ; account tier Normal; promotional credit shown; sections Overview, API keys, Usage, Webhooks, Docs.
- The correct API-key management route is **https://ampersand.humansand.ai/#keys** by clicking the sidebar menu. A guessed /api-keys path returned 404; this does NOT prove keys are unavailable.
- The console shows **two active Manager-labelled API keys**, masked. No plaintext token was read or written.
- Usage view https://ampersand.humansand.ai/#usage showed 'No settled usage yet' at inspection time. No integrated model playground was evident.
- Browser runs: https://agent.tinyfish.ai/runs/a3c6feef-fea2-4d7f-85ee-62ac2ca59928 and https://agent.tinyfish.ai/runs/38873b6b-ef61-4857-9acc-4de77845fce0 .
- No new key, credits purchase, billing change, or authenticated model inference was performed in the browser.

## Runtime limits and credential handling
- Direct container socket DNS for ampersand.humansand.ai AND github.com failed with gaierror. This is not evidence of provider outage or key failure.
- Model tenant availability via authenticated GET /v1/models remains **unverified**.
- Credentials that were shared in chat should be treated as exposed; rotate the shared account password and API key and configure replacements in a backend-only secret store. Do not paste credentials into GitHub, public logs, browser automation instructions or manuscripts.
- The existing research probe currently creates a session but does NOT retrieve the finished answer. A SESSION_CREATED receipt is not evidence of completed inference.

## Ordered next implementation work
1. Rotate the chat-shared key at the authenticated console while preserving unrelated keys until usages are understood; inject the new key securely into a network-capable trusted backend.
2. Call official GET https://ampersand.humansand.ai/v1/models with a backend Bearer header, check ampersand-v0.1, never log token.
3. Run a minimal low-cost, no-tools session; use official SSE or saved turns/items API to get completed final output and verify follow-up in the same session; record sanitized model ID, result and usage.
4. Implement the optional model adapter with PASS/ASK/PROPOSE advisory output; source allowlisting, schema validation, mandatory NO_ACTION and all permission/execution rules remain in Manager.
5. Compare provider against existing deterministic planner on held-out scenarios, refusal, privacy, silence, over-coaching, safety and cost; treat model output as P0 evidence only.
6. Add negative, positive, and inconclusive outcomes to the English/Japanese research manuscripts on GitHub. **No automatic publication**.

Official docs: https://ampersand.humansand.ai/docs/ , https://ampersand.humansand.ai/docs/GUIDES.html
