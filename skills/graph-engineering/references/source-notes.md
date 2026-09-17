# Graph source notes

## What to read upstream

- `getzep-graphiti/graphiti_core/graphiti.py`: `add_episode`, triplet ingestion, and search boundaries
  separate episodic source facts from derived entity/edge queries.
- `getzep-graphiti/graphiti_core/models/nodes/` and `models/edges/`: typed node/edge identities,
  temporal fields, and database query helpers; `search/` shows bounded retrieval configuration.
- `getzep-graphiti/graphiti_core/telemetry/telemetry.py` and `OTEL_TRACING.md`: graph operations can
  be traced without turning telemetry into graph authority.
- `langchain-langgraph/libs/langgraph/langgraph/` Pregel/state modules and `tests/test_subgraph*`:
  graph topology and checkpoint state are execution structure, while the checkpointer preserves the
  durable cursor.
- `langchain-langgraph/examples/subgraph.ipynb` and `examples/multi_agent/`: subgraphs compose
  independently owned work while state channels stay explicit.

## Life Manager mapping

- `apps/life-manager/lib/context-graph.js::contextEntries` extracts a bounded set of calendar-derived
  context fields; it is a projection, not an external truth source.
- `scripts/integration-onboarding.py::graph` builds the readiness projection from manifests. Its
  validation and graph commands are deterministic and side-effect free.
- `config/loop-registry.json` is the lifecycle graph input; `skills/registry.json` is the capability
  graph input. Keep their ownership separate from runtime ledgers.
- `apps/life-manager/lib/effect-reconciler.js` is the authority boundary for unknown effects; a graph
  edge may reference its receipt but cannot replace `reconcileUnknownEffect`.
- The Coconala TODO defines the initial competency questions and vocabulary (goals, opportunities,
  contracts, capabilities, artifacts, effects, readbacks, revenue; `requires`, `produced_by`,
  `sent_to`, `proved_by`, `earned`). It remains another workstream's file and is not edited here.

## Adopted lessons

1. Model relationships needed by a query, not every possible entity.
2. Preserve temporal/provenance metadata so a projection can be rebuilt and audited.
3. Keep graph traversal useful for planning while official state remains the effect authority.
4. Prefer a local in-memory/index projection before adding a database dependency.
