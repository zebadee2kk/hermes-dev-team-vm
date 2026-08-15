# Low-level design — Revision 2

## Reference topology

```text
Enclosed VM / control-plane host
├── Hermes Agent + gateway + Kanban dispatcher
├── forge-controller :8080
│   ├── task-capsule / assurance graph APIs
│   ├── quota intelligence + compute broker
│   ├── decision adapter
│   ├── trust/provenance service
│   └── evaluation/learning quarantine
├── LiteLLM :4000 (not reachable by workers directly unless explicitly mediated)
├── PostgreSQL
├── Redis
├── capability + secret gateway
├── content trust gateway
├── sandbox broker
└── Hands
    ├── gVisor worker-<task-a>
    ├── gVisor worker-<task-b>
    └── optional high-risk VM/microVM worker
```

Hermes/Forge policy services are trusted relative to Hands. Arbitrary repository code never executes in the trusted service processes.

## Hermes integration

### Durable execution
Hermes Kanban owns task state/dependencies, decomposition, blocking, retries and worker assignment. Forge stores `kanban_task_id` as a correlation pointer only.

### Stable lanes
Initial lane classes:
- `forge-orchestrator`
- `research`
- `product`
- `architecture`
- `engineering`
- `security`
- `qa-review`
- `documentation-release`

Do not create a new persistent profile for every speciality. Attach task Skills such as `postgresql-performance`, `oauth-threat-model`, `react-accessibility` or `terraform-oci` to a suitable stable lane.

### External runtimes
Codex/Claude Code/OpenCode/Gemini CLI adapters implement a common worker-lane contract: receive Task Capsule + workspace + scoped capabilities; emit structured result + evidence + usage + residual risk. They do not become separate project managers.

## Task Capsule lifecycle

1. Kanban task becomes runnable.
2. Forge composes capsule from Kanban objective + semantic graph + policy + latest attempt.
3. Compute Broker chooses an eligible inference deployment or lane runtime.
4. Sandbox Broker creates/attaches a Hand.
5. Worker executes bounded loop.
6. Structured observations update capsule/evidence graph.
7. On quota/model failure, checkpoint capsule and re-place compute without changing task identity.
8. On completion, required reality anchors are checked before Kanban completion is accepted.

## Reality anchors

Anchor types include: unit/integration/E2E execution, CI check, build/package output, HTTP probe, browser/Playwright evidence, database migration verification, static/security scan, benchmark/measurement, signed owner decision or authoritative external evidence.

A reviewer model approving text is evidence, but is not by itself a reality anchor for claims that can be tested mechanically.

## Inference Deployment

Atomic routing object:

`provider + model + account/tier + endpoint + credential binding + terms/privacy policy`

Fields include capabilities, context/tool/structured-output support, data classes permitted, cost class, quota state, retry_at, reliability, measured outcomes, development-only flag and quarantine state.

## Compute unavailability

If no eligible inference deployment/runtime exists:
- affected task/capsule enters `WAITING_COMPUTE` in Forge metadata;
- Hermes task is blocked with a machine-readable compute reason;
- unrelated work continues;
- scheduler selects earliest credible `retry_at` plus jitter;
- if all runnable work is compute-blocked, stop Hands and enter QUIESCENT mode;
- wake re-evaluates the whole eligible pool rather than blindly retrying the previous deployment.

## Capability gateway

A capability is at least `(subject, destination/service, resource scope, allowed operation, credential binding, expiry, audit policy)`. Example: push branch `forge/T184` to repository X, not generic access to `github.com`.

Network controls still deny loopback/RFC1918/link-local/cloud metadata by default, but destination filtering is defence-in-depth rather than the authorisation mechanism.

## Deny-and-continue

Policy denial returns a structured reason and permitted alternatives. Worker must attempt a safe alternative. Escalate after configurable repeated denials or when no safe path exists; do not wake the owner for the first ordinary denial.

## Persistence

M1 persists assurance state without duplicating Kanban execution state: Task Capsules, semantic nodes/edges, anchors, trust envelopes, decisions, inference deployments, quota observations, capability scores, learning candidates and append-only events. All state-changing APIs are idempotent.