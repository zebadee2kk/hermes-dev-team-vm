# High-level design

## Purpose

Hermes Autonomous Engineering Forge converts a human idea into a researched, designed, implemented, tested and documented working system with minimal owner interaction. It is not a single autonomous prompt loop; it is a governed engineering organisation whose work is represented as durable graphs and whose model compute is replaceable.

## Logical components

### Hermes control plane

Hermes is the executive/orchestration layer. Durable work is represented in Hermes Kanban boards/tasks/runs. Short reasoning fan-out may use `delegate_task` inside a worker. Hermes profiles provide persistent role identities and skills.

### Graph Controller

Maintains project, execution, organisation, governance, capability and trace relationships. It compiles project intent into graph nodes, maps executable nodes to Hermes tasks, performs impact analysis and prevents mandatory verification nodes from being silently removed.

### Compute Broker + Quota Intelligence

Selects compatible model deployments by capability, privacy, cost and current availability. LiteLLM executes provider calls and short retry/cooldown behaviour. Forge owns long-lived quota exhaustion/reset state and decides when a provider re-enters the pool.

### Decision Service

Calculates authority levels and exposes only material decisions to the owner. L0/L1 continue automatically; L2/L3 require owner action according to policy. DEFER blocks only dependent graph nodes.

### Worker Sandbox Manager

Creates disposable development sandboxes. Workers may receive broad/root privileges inside the sandbox but cannot access control-plane secrets, raw provider keys or unrestricted network paths.

### Secret Broker

Provides scoped, task-specific access to credentials/tools without placing raw secrets into model context. The implementation may later use Vaultwarden or another secret backend, but the broker contract is provider-neutral.

### Egress Policy

All worker Internet access is mediated. Baseline developer registries/docs are allowlisted. Automatic additions require deterministic trust-chain evidence.

## Data stores

- **Hermes Kanban SQLite:** canonical Hermes task/run lifecycle within one VM/host.
- **PostgreSQL:** project graph, decisions, provider observations, model capability/outcome data, trace/evidence and configuration metadata.
- **Redis:** cooldowns, leases, short-lived availability state and concurrency coordination.
- **Git/GitHub:** source and durable engineering artefacts.

## Deployment model

One autonomous Forge instance maps to one enclosed VM/control-plane host in V1. This deliberately aligns with Hermes Kanban's single-host dispatcher semantics. Multiple projects can use separate Hermes boards on the same host.

Workers may be containers or stronger microVM sandboxes later. External/cloud deployment changes policy, not the application architecture.

## Critical invariants

1. Agent identity survives model changes.
2. A worker cannot modify its own outer security boundary.
3. Provider quota exhaustion never triggers identity/quota evasion.
4. Public/free providers see only data permitted by their privacy classification.
5. The owner is interrupted only for decisions above configured authority thresholds.
6. Every meaningful result has evidence: source, code change, verification, model/agent/run and residual risk.
