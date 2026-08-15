# High-level design — Revision 2

## Purpose

Hermes Autonomous Engineering Forge converts a human idea into researched, designed, implemented, tested and documented working software with minimal owner interaction. Hermes is the engineering organisation and execution system; Forge is its assurance, compute, trust and governance plane.

## Foundational split

### Brain
Hermes orchestrator, stable role profiles, Skills, decomposition/judging logic and Forge decision/placement services. Brain reasons but does not execute arbitrary project code on the trusted control plane.

### Session
Hermes Kanban task/run history, Task Capsules, PostgreSQL semantic/evidence/governance state, append-only events and Git. Session state survives model swaps and worker destruction.

### Hands
Disposable untrusted environments where code, package scripts, browsers, builds and project services run. Root may be available inside the sandbox. Normal profile uses gVisor where supported; high-risk work may use a stronger VM/microVM boundary.

## Execution ownership

Hermes Kanban is the canonical execution graph: task state, dependencies, decomposition, worker assignment, retries, blocking and durable work history. Forge does **not** maintain a parallel executable DAG.

Stable organisational lanes are kept intentionally small: orchestrator, research, product, architecture, engineering, security, QA/review, documentation/release. Task-scoped Skills add specialised expertise. External coding runtimes such as Codex, Claude Code or OpenCode are integrated as worker lanes/adapters rather than separate orchestration systems.

## Forge assurance plane

### Semantic and evidence graph
Relates requirements, decisions, components, files, tests, risks, sources, commits and reality anchors. It performs impact/staleness analysis but does not own Kanban lifecycle.

### Quota Intelligence + Compute Broker
Tracks availability of **Inference Deployments**: provider + model + account/tier + endpoint. Privacy, quota and capability belong at deployment level. LiteLLM performs actual provider calls and short request-level retry/fallback behaviour.

### Task Capsule service
Creates compact durable handoff state containing objective, acceptance criteria, constraints, relevant graph pointers, working revision, attempts, verification requirements, open questions and residual risk. Model failover reconstructs from the capsule instead of replaying an entire conversation.

### Content Trust Gateway
Attaches provenance, trust and taint metadata to web/tool/subagent content. A downstream agent cannot promote externally influenced material to trusted merely by summarising it.

### Capability + Secret Gateway
External access is represented as scoped capabilities, not trusted domains. The gateway validates destination, identity, resource and operation, then injects credentials outside the worker. Workers never receive provider master keys or broad GitHub credentials.

### Decision Adapter
Scores materiality/irreversibility/uncertainty/consequence, maps required owner choices to Hermes block/unblock lifecycle and supports deny-and-continue/defer-and-continue.

### Evaluation and Learning
Records real task outcomes and reality anchors. Candidate lessons are quarantined, evaluated and cross-validated before promotion to global Skills/routing priors.

## Data stores

- **Hermes Kanban state:** canonical execution lifecycle on the enclosed host.
- **PostgreSQL:** semantic/evidence/governance/capability graphs, Task Capsules, decisions, inference deployments, observations and learning candidates.
- **Redis:** short-lived cooldowns, leases, concurrency and wake scheduling.
- **Git/GitHub:** code and durable engineering artefacts.
- **Append-only event ledger:** attributable actions and state transitions; later replicated off-host.

## Critical invariants

1. No second workflow engine beside Hermes in V1.
2. Agent/task identity survives model and worker replacement.
3. A compromised Hand cannot alter its outer security boundary or retrieve control-plane secrets.
4. No worker Docker socket access.
5. Destination allowlisting alone never grants authority; sensitive external actions pass through capability-aware gateways.
6. Externally influenced content preserves provenance/taint through handoffs.
7. Every material completion claim has a reality anchor.
8. Independent evaluation is risk-adaptive; high-risk work requires an independent reviewer and executable anchor.
9. Policy/privacy is evaluated per inference deployment, not provider brand.
10. Learning cannot directly modify the Owner Charter, security policy or trusted global Skills.
11. Paid inference and L3 actions are impossible without explicit policy/authority records.
12. The control plane can become QUIESCENT while retaining enough state to resume when compute returns.