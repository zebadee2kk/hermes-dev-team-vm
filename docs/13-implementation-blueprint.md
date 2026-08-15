# Implementation blueprint

This document translates Revision 2 into concrete module/data/API boundaries. It is the starting point for M1/M2 coding.

## Build order

### Slice A — persistent assurance core
Implement storage first without trying to install every external provider.

Suggested Python packages/modules:
- `domain/task_capsule.py`
- `domain/anchors.py`
- `domain/trust.py`
- `domain/inference.py`
- `domain/capabilities.py`
- `domain/decisions.py`
- `repositories/*`
- `services/event_ledger.py`
- `services/assurance_graph.py`
- `services/capsules.py`

PostgreSQL tables (initial):
- `projects`
- `task_capsules` + immutable/revision history
- `semantic_nodes`
- `semantic_edges`
- `claims`
- `reality_anchors`
- `trust_envelopes`
- `decisions`
- `inference_deployments`
- `quota_observations`
- `capability_scores`
- `learning_candidates`
- `events`

Do not create an execution-task table that attempts to replace Hermes Kanban. Store only correlation IDs and assurance metadata.

### Slice B — quota + broker vertical test
Implement a fake provider adapter first, then one real provider. Required sequence:
1. create two fake Inference Deployments;
2. place a capability request on deployment A;
3. simulate daily exhaustion with known reset;
4. persist observation/state;
5. rebuild route and choose B;
6. exhaust both;
7. produce `WAITING_COMPUTE` with earliest wake;
8. restart process and prove state survives;
9. advance time and prove A re-enters only after policy re-evaluation.

Then implement provider adapters incrementally.

### Slice C — Hermes adapter
Do not make Hermes integration dependent on all providers/sandboxes.

Define interfaces:
- `KanbanTaskRef`
- `TaskCapsuleBuilder`
- `WorkerAssignmentRequest`
- `StructuredWorkerResult`
- `BlockReason(compute|human|dependency|policy)`
- `RealityAnchorIngest`

Use Hermes Kanban for task lifecycle; Forge APIs/MCP provide context, placement and assurance.

### Slice D — Hand/sandbox boundary
Implement the Sandbox Broker with a fake/local process adapter for tests, then gVisor. The Broker receives a capsule/workspace/capability set and returns a Hand ID. It must not expose host Docker control or Forge credentials.

### Slice E — capability gateway
Start with GitHub repository operations because they are easy to scope and central to engineering. Implement read and task-branch write capabilities separately. Add package/web/infrastructure services only as requirements emerge.

## API principles

All state mutation is idempotent. APIs accept caller/task identity and return structured machine-readable denial/block reasons. Never make model prose part of an authorisation decision.

Potential endpoints/MCP tools:
- `capsule.get_or_build`
- `capsule.checkpoint`
- `anchor.record`
- `anchor.query_required`
- `assurance.impact`
- `trust.wrap`
- `trust.derive`
- `compute.place`
- `compute.observe`
- `compute.next_wake`
- `decision.classify`
- `decision.record_owner_action`
- `capability.request`
- `capability.use`

## Transaction boundaries

Quota observation + deployment state change + affected wait decision should commit atomically where practical. Anchor creation references an immutable workspace revision/artefact digest. Owner decisions are immutable events with superseding records rather than mutable history.

## Time handling

All persisted timestamps are timezone-aware UTC. Reset parsing records both raw provider signal and parsed value/confidence. Tests use an injectable clock; avoid sleeping in quota/scheduler tests.

## Minimum observability

Every event includes `project_id`, `kanban_task_id`, `capsule_id/revision`, `lane`, `hand_id`, `inference_deployment_id` where applicable, event type and correlation/trace ID. Do not log raw prompts by default if they may contain sensitive data.

## First implementation PR target

The first substantial implementation should be M1 plus the **fake-provider portion of M2**, not every provider adapter. Acceptance:
- migrations run on clean DB;
- capsule round-trip/history tests;
- anchor/trust objects persist;
- fake quota failover/wait/restart test passes;
- event ledger proves the transition sequence;
- no Hermes execution lifecycle duplicated.

This yields a testable vertical foundation before external integration complexity is introduced.