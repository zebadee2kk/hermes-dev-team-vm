# Low-level design

## Process topology

```text
VM / control-plane host
├── Hermes Agent + gateway + Kanban dispatcher
├── forge-controller :8080
│   ├── graph service
│   ├── quota intelligence
│   ├── compute broker
│   └── decision service
├── LiteLLM :4000 (loopback only)
├── PostgreSQL
├── Redis
├── secret broker (M2/M4)
├── egress proxy/policy (M4)
└── sandbox manager
    ├── worker-<task-a>
    └── worker-<task-b>
```

Hermes and Forge are trusted relative to workers. Worker containers are untrusted even when they are executing repository-authored code.

## Hermes integration

Install Hermes with the supported upstream Linux installer. Point the main/delegation model endpoint at LiteLLM. Use separate Hermes profiles for durable specialist identities and enable the Kanban toolset only where required.

Recommended profile classes:

- `forge-orchestrator`
- `researcher`
- `product`
- `architect`
- `security-architect`
- `engineer`
- `reviewer`
- `qa`
- `documentation`

Do not create every role for every project. The organisation graph chooses a minimal team based on node requirements.

### Kanban mapping

A graph executable node stores a `kanban_task_id`. Hermes remains lifecycle truth for the actual worker attempt. Forge stores richer relationships and policy metadata. Events are correlated by project/node/task/run IDs.

Suggested completion metadata:

```json
{
  "changed_files": ["src/example.py"],
  "verification": ["pytest -q"],
  "dependencies": [],
  "blocked_reason": null,
  "retry_notes": null,
  "residual_risk": []
}
```

Never store secrets or raw credential-bearing logs in Kanban metadata.

## Graph node lifecycle

Forge node states:

`TRIAGE -> READY -> RUNNING -> REVIEW -> COMPLETE`

Side states:

- `WAITING_HUMAN`
- `WAITING_DEPENDENCY`
- `WAITING_COMPUTE`
- `FAILED`
- `CANCELLED`

A node is READY only when all hard dependencies are complete and policy permits execution.

## Compute request contract

Each inference request carries:

- capability required (`coding`, `reasoning`, `research`, `review`, `fast`, etc.)
- data sensitivity
- tool/structured-output requirements
- minimum context requirements
- latency preference
- project budget state
- agent identity (for trace only; not model affinity)

The broker returns a deployment, not a model identity to the agent.

## Quota state

Provider/model deployments are one of:

- AVAILABLE
- THROTTLED_SHORT
- QUOTA_EXHAUSTED
- CREDIT_EXHAUSTED
- PROVIDER_DEGRADED
- OFFLINE
- AUTH_FAILED
- POLICY_BLOCKED

Every non-available state carries `retry_at` where it can be determined and a confidence level/source.

## Persistence plan

M1 introduces relational tables for projects, graph_nodes, graph_edges, decisions, provider_deployments, quota_observations, capability_scores and events. Typed edges provide graph semantics without a separate graph database.

## Wake/resume

When no compatible deployment exists, the node transitions to `WAITING_COMPUTE`. The scheduler computes the earliest trustworthy `retry_at`. If all runnable nodes are waiting for compute, execution becomes QUIESCENT; worker sandboxes stop, but the control plane remains alive. A timer re-evaluates routes at wake time.

## API

The current service exposes pure decision primitives. Future endpoints should remain idempotent and service-oriented so an MCP facade and dashboard can use the same domain layer.
