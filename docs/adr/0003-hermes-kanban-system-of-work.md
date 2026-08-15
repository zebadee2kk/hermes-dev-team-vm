# ADR-0003: Hermes Kanban is the V1 durable system of work

**Status:** Accepted

## Context
Hermes already provides durable Kanban tasks/runs, named profiles, dispatcher workers, blocking/human input and engineering-pipeline semantics. Adding a second workflow engine would create duplicate lifecycle truth.

## Decision
Use Hermes Kanban as canonical worker/task lifecycle on a Forge VM. Forge graph nodes map to Kanban tasks and enrich them with cross-domain relationships/policy/evidence. Use `delegate_task` only for short-lived sub-reasoning inside a durable worker where appropriate.

## Consequences
- V1 naturally remains single-host per Forge instance because current Kanban coordination is single-host.
- No CrewAI/LangGraph/Temporal task engine is added.
- If multi-host dispatch becomes necessary, add an explicit bridge/federation design rather than sharing the Kanban SQLite database.
