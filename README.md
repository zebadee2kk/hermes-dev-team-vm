# Hermes Autonomous Engineering Forge

A self-contained, provider-independent autonomous engineering environment built around Hermes Agent, LiteLLM, an assurance graph, quota-aware free-model routing, disposable worker sandboxes, and lightweight human governance.

> **Architecture baseline: Design Revision 2.** Hermes owns the execution graph and durable system-of-work lifecycle. Forge augments Hermes with semantic/evidence/governance/capability graphs, quota intelligence, model placement, trust controls, policy, evaluation and deployment profiles. Do not build a second workflow engine beside Hermes.

## Target experience

Give Hermes an idea. Hermes should decompose it into durable Kanban work, select a minimal team of stable worker lanes plus task-scoped Skills, execute bounded engineering loops, verify results against reality anchors, and interrupt the owner only for material decisions using `YES / NO / DEFER / MORE INFO`.

When an inference deployment reaches quota, the persistent agent/task survives. Its Task Capsule and working state are checkpointed and compute moves to another compatible free deployment. If no compatible compute is available, the work enters `WAITING_COMPUTE` and resumes when capacity is expected to return.

## Core principles

1. **Hermes Kanban is the execution graph.** Forge must not duplicate task/dependency/run lifecycle.
2. **Models are fungible compute; agents/tasks are persistent organisational entities.**
3. **Brain / Session / Hands are separate failure domains.** Reasoning, durable state and arbitrary code execution must survive one another failing.
4. **Graph engineering means grounded graphs.** Claims require independent reality anchors such as executed tests, CI, browser evidence, measurements, immutable policy or owner decisions.
5. **YOLO belongs in disposable Hands, not the control plane.** Normal untrusted workers use gVisor where supported; stronger isolation is available for high-risk profiles.
6. **Egress is a capability, not a trusted domain.** Destination allowlists alone are insufficient. Credentials and permitted operations are injected by trusted gateways outside workers.
7. **External content is tainted until proven otherwise.** Provenance and trust metadata survive subagent handoffs.
8. **Stable lanes + dynamic Skills.** Create persistent organisational identities sparingly; specialise tasks with Skills and lane capabilities.
9. **Free API tiers first.** Paid fallback is explicit and budget-gated. Quota evasion is forbidden.
10. **Learning is quarantined before promotion.** Project lessons cannot write directly into global trusted skills/policy.
11. **Owner attention is scarce.** Deny-and-continue and defer-and-continue are defaults where safe.
12. **Deployment is policy.** The same release should run on Proxmox/local VMs, OCI ARM and portable/client-safe profiles.

## Responsibility map

| Capability | System of record / owner |
|---|---|
| Task lifecycle and dependencies | Hermes Kanban |
| Basic decomposition | Hermes Kanban decomposer |
| Durable worker assignment | Hermes worker lanes/profiles |
| Task expertise | Hermes Skills |
| Short-lived reasoning fan-out | `delegate_task` |
| Semantic project relationships | Forge semantic graph |
| Evidence, provenance and stale-impact analysis | Forge assurance graph |
| Provider quota/reset state | Forge Quota Intelligence |
| Inference placement | Forge Compute Broker |
| Provider API execution | LiteLLM |
| Arbitrary code/browser execution | Sandbox Broker / Hands |
| Credentials and external actions | Capability/Secret Gateways |
| Human blocking lifecycle | Hermes Kanban |
| Human decision policy and UI | Forge Decision Adapter |
| Source trust/taint | Content Trust Gateway |
| Code truth | Git/GitHub |
| Verification truth | executable reality anchors / CI |

## Process shape

```text
Owner
  |
Decision adapter + notifications
  |
Hermes orchestrator
  |
Hermes Kanban execution DAG
  |        |          |
profiles  Skills   worker lanes
  \        |          /
        Task Capsule
             |
      Execution Gateway
             |
     disposable Hands
      (gVisor default)
             |
       code/test/browser

Forge assurance plane, orthogonal to execution:
- semantic/evidence/governance/capability graphs
- quota intelligence + compute broker
- content trust + capability/secret gateways
- evaluation + learning quarantine
- policy + audit + observability
```

## Repository map

- `OWNER_CHARTER.md` — high-authority objectives and non-self-modifiable principles.
- `docs/` — HLD/LLD, graph, security, routing, governance and research design.
- `config/` — policy-as-data, deployment/sandbox/worker-lane/provider/capability seeds.
- `schemas/` — Task Capsule, reality anchor, trust envelope and existing API contracts.
- `src/forge_controller/` — executable assurance/control primitives.
- `tests/` — deterministic tests; expand with adversarial and structural tests.
- `BACKLOG.md` — Revision 2 implementation sequence and gates.
- `AGENTS.md` — normative contract for any coding agent working on this repository.

## V1 anti-goals

Do not add LangGraph, CrewAI, AutoGen, Temporal, Kafka, Kubernetes or Neo4j unless an ADR demonstrates a measured limitation. Do not expose the Docker socket to workers. Do not automate account creation, rotate identities to bypass quotas, treat trial capacity as durable free compute, weaken tests to obtain a green result, or allow project agents to edit the Owner Charter/security policy.

## Quick start

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
uvicorn forge_controller.api:app --reload
```

The current Python code remains a foundation; Revision 2 is primarily an architecture correction before M1 implementation.