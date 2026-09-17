# Context source notes

## What to read upstream

- `langchain-deepagents/libs/deepagents/deepagents/_messages_reducer.py`: message reduction is a
  middleware concern; it keeps the agent graph usable while the full source can remain offloaded.
- `langchain-deepagents/examples/llm-wiki/`: `ingest.py`, `query.py`, `models.py`, and `log.py` show a
  file-backed context index with explicit retrieval rather than injecting every document.
- `langchain-langgraph/libs/langgraph/langgraph/pregel/` and checkpoint tests: state is carried by
  checkpoint/config identity and can resume after interruption; inspect `StateGraph` compilation and
  checkpoint/store fixtures before adding persistence.
- `getzep-graphiti/graphiti_core/graphiti.py`, `search/`, `models/nodes/`, and `models/edges/`: episodes,
  temporal nodes/edges, search configuration, and provenance-aware graph writes model long-lived
  memory without flattening all history into one prompt.
- `nous-hermes-agent/hermes_state_compression.py`, `hermes_state_sessions.py`, and
  `hermes_state_search.py`: inspect how session state, compression, and search remain separate stores.
- `nous-hermes-self-evolution/evolution/skills/skill_module.py`: `load_skill`, `find_skill`, and
  `reassemble_skill` preserve skill frontmatter while evolving only the body.

## Life Manager mapping

- `runtime/loop/prompt.mjs::buildSystemPrompt` and `buildUserMessage` already separate tool docs,
  active slots, recent slot history, balance, and reinforcement. Extend the context contract there;
  do not create a second prompt builder.
- `apps/life-manager/lib/context-graph.js::contextEntries` and `inferCalendarContext` derive places
  from calendar facts; `backfillCalendarContext` persists only the bounded extracted entries.
- `apps/life-manager/lib/event-cache.js` and the event-provider cursor modules define freshness and
  source identity for calendar/provider observations.
- The Paid Project Context Capsule in `skills/earn/gig/TODO.md` names ten source groups (identity,
  original job, proposal, full DM, requirements, commitments, buyer interpretation, artifact lineage,
  effects, and decision boundary). Treat that contract as the local high-signal checklist.
- `runtime/loop/index.mjs` stores only bounded safe observations in ledger records; use its redaction
  boundary instead of echoing child-process output into context.

## Adopted lessons

1. Keep source facts and derived summaries distinguishable and hash-bound.
2. Offload large outputs instead of shortening identifiers or dropping commitments.
3. Refresh mutable sources immediately before an effect; context compilation is not authorization.
4. Share graph facts between loops, not mutable transcripts or browser sessions.
