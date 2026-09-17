# Observability source notes

## What to read upstream

- `arize-openinference` Python/JS semantic-convention packages: use standard span kinds and attribute
  names so model, agent, chain, tool, evaluator, and retriever spans can be joined across runtimes.
- `arize-phoenix/packages/phoenix-otel/src/phoenix/otel/otel.py::register`,
  `TracerProvider`, and `BatchSpanProcessor`: production exports should be batched, configurable,
  and compatible with standard OTLP. Phoenix's server is ELv2; use OpenInference semantics as the
  portable part unless a license review approves hosting the server.
- `openai-symphony/elixir/docs/logging.md`: stable `key=value` fields include issue and session IDs,
  action outcome, concise reason, and no large payloads.
- `OpenHands/OpenHands/AGENTS.md`: one telemetry client owns identity/consent and canonical business
  events; do not create duplicate event producers.
- `nous-hermes-agent/hermes_logging.py` and state modules: inspect how session/turn/tool records are
  persisted and separated from memory compression.

## Life Manager mapping

- `runtime/loop/harness-health-snapshot.mjs` derives `harness-health.json` from the ledger; its output
  is a health projection, not a provider receipt.
- `skills/self/self-improve/lib/harness_health.py::classify_layer`,
  `compute_slot_health`, `compute_brain_transport_health`, and `should_escalate` keep failure layers
  separate and make escalation pure/testable.
- `apps/life-manager/lib/effect-reconciler.js::reconcileUnknownEffect` records present/absent/unknown
  provider proof and dead-letters aged unknowns instead of retrying blindly.
- `runtime/loop/index.mjs` and `runtime/loop/run-skill.mjs` already attach wake/slot/attempt fields,
  redact child output, and bound skill timeouts. Extend these events instead of adding a new logger.
- Shared receipt and ledger modules are authoritative for revenue/effects; Telegram is a report sink,
  not a readback.

## Adopted lessons

1. Instrument boundaries, not every line; stable IDs make one run reconstructable.
2. Keep telemetry failure non-blocking while preserving a durable degradation event.
3. Use traces for diagnosis and ledgers/readbacks for truth.
4. Measure the failure layer before choosing a recovery action.
