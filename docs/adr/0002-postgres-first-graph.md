# ADR-0002: Represent Forge graphs in PostgreSQL first

**Status:** Accepted

## Context
The system needs typed relationships and traversal but V1 graph scale is modest. Adding Neo4j introduces another stateful subsystem before traversal requirements are proven.

## Decision
Use PostgreSQL tables for nodes, typed edges, evidence and metadata. Add indexes/recursive queries as needed. Keep domain interfaces graph-oriented so the storage backend can change later.

## Consequences
- Lower operational complexity.
- Transactional graph/decision/event updates are straightforward.
- Complex traversal may eventually justify a specialised graph projection/store; that requires a later ADR with measured evidence.
