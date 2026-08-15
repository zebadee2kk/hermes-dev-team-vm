# Graph engineering model — Revision 2

Graph engineering is not a reason to duplicate Hermes' workflow graph. Hermes Kanban is the execution DAG. Forge maintains orthogonal graphs that explain what the work means, what evidence supports it, what authority applies and what compute is suitable.

## 1. Execution graph — Hermes owned

Nodes are durable Kanban tasks; links express dependencies, decomposition, review/repair and human blocking. Forge correlates to these tasks but never becomes a competing task state machine.

## 2. Semantic project graph — Forge owned

Relates ideas, requirements, decisions, components, interfaces, files, tests, risks and documentation.

Example:
`Requirement R17 -> IMPLEMENTED_BY -> Component C4 -> IMPLEMENTED_IN -> commit abc -> VERIFIED_BY -> Anchor A27`

## 3. Evidence/trace graph — Forge owned

Connects claims and actions to provenance:
`task -> lane -> inference deployment -> tool/action -> source -> artefact -> anchor -> review -> decision`.

### Reality anchors
A graph can self-confirm bad conclusions; therefore material claims must terminate in independent observations. Anchors include executed tests/CI, actual HTTP/browser behaviour, measurements, scans, authoritative external evidence and explicit owner decisions. Model agreement is not sufficient where mechanical verification is available.

## 4. Governance graph — Forge owned

Represents subject, action, resource, policy, capability and owner authority. Security controls are anchored outside the optimisation loop by `OWNER_CHARTER.md` and protected policy/tests.

## 5. Compute capability graph — Forge owned

Stores measured performance and availability for **Inference Deployments** and worker runtimes. Routing is based on actual deployment behaviour, not model brand alone.

## Stable organisation + dynamic expertise

Persistent role identities are intentionally few. Dynamic project teams are assembled by selecting lanes and attaching task Skills. This avoids persona explosion while retaining durable organisational identities.

## Typed semantic/evidence edges — seed

- DERIVED_FROM
- REQUIRES
- IMPLEMENTS / IMPLEMENTED_BY
- IMPLEMENTED_IN
- VERIFIED_BY
- CLAIMS
- ANCHORED_BY
- REVIEWS
- SUPERSEDES
- AFFECTS
- EVIDENCED_BY
- DECIDED_BY
- PRODUCED_BY
- EXECUTED_WITH
- INFLUENCED_BY
- TAINTED_BY

Hermes owns execution dependency links; do not mirror every Kanban dependency as a Forge edge unless it has semantic value.

## Impact/staleness analysis

When a requirement/decision/interface changes:
1. traverse semantic `AFFECTS/IMPLEMENTS/VERIFIED_BY` relationships;
2. mark dependent claims/anchors/artefacts stale rather than deleting history;
3. create or request required re-validation work through Hermes Kanban;
4. preserve prior evidence as superseded historical provenance.

## Bounded local loops

Within a Kanban task a worker may run:
`PLAN -> EXECUTE -> OBSERVE -> CRITIQUE -> VERIFY -> REPAIR`.

Each loop has budgets and a circuit breaker. Completion output is a Task Capsule update plus anchored evidence. The loop may not redefine its own acceptance criteria, Charter or mandatory security controls.