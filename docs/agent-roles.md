# Dynamic agent roles

Roles are persistent organisational identities; models are interchangeable compute deployments.

## Core roster

| Role | Purpose | Typical authority |
|---|---|---|
| forge-orchestrator | Own project intent, graph health and handoffs | L1; may request L2/L3 |
| researcher | Gather primary evidence, competitors and constraints | L0 |
| product | Requirements, acceptance criteria and scope | L1/L2 |
| architect | System/data/integration design | L1/L2 |
| security-architect | Threat model and security constraints | L1/L2 |
| engineer | Implement bounded graph nodes | L0/L1 |
| qa | Verification and regression evidence | L0/L1 |
| reviewer | Independent code/design challenge | L0/L1 |
| documentation | Handover/runbooks/evidence | L0 |
| release | Packaging/release preparation | L1; production is L3 |

## Team assembly

The orchestrator should instantiate only roles required by the project graph. Examples:

- CLI utility: product + engineer + reviewer + docs.
- SaaS MVP: product + architect + frontend/backend + QA + security + docs.
- security product: add threat-model/security reviewer/red-team nodes.

## Separation of duties

For material code, the implementing worker should not be the only reviewer. A review node should use a separate agent run and, where capacity permits, a different model deployment to reduce correlated failure.
