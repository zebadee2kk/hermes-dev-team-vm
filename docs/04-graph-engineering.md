# Graph engineering model

The design follows the principle that useful autonomous engineering is not one giant reasoning loop. Loops remain local execution mechanics; the overall organisation is a dynamic graph of dependencies, evidence, people/agents and decisions.

## Six graph views

### 1. Execution graph
Nodes are work. Edges encode dependencies, review gates and repair cycles.

Example:

`idea -> research -> requirements -> architecture -> build -> verify -> release`

Parallel branches are first-class. A failed verification node creates/activates repair nodes rather than recursively prompting forever.

### 2. Project knowledge graph
Relationships between requirements, decisions, components, files, tests, risks and documentation.

Example:

`Requirement R17 -> IMPLEMENTED_BY -> Component C4 -> VERIFIED_BY -> Test T27`

### 3. Organisation graph
Maps work types to persistent role identities and dynamically instantiated teams. Roles are stable; model deployments are replaceable.

### 4. Model capability graph
Stores empirical capability, reliability, latency, cost class, quota state and data-policy compatibility for each deployment.

### 5. Governance graph
Represents who/what may perform an action on a resource under a policy and whether owner authority is required.

### 6. Trace/evidence graph
Connects task -> agent -> model deployment -> tool -> source -> code change -> test -> review -> decision. This supports real provenance instead of retrospective LLM explanations.

## Typed edge vocabulary (initial)

- DEPENDS_ON
- DERIVED_FROM
- IMPLEMENTS
- IMPLEMENTED_BY
- VERIFIED_BY
- REVIEWS
- SUPERSEDES
- AFFECTS
- EVIDENCED_BY
- BLOCKED_BY
- DECIDED_BY
- PRODUCED_BY
- ASSIGNED_TO
- EXECUTED_WITH

Add edge types conservatively; semantics belong in code/tests, not only prose.

## Graph compilation

Input intent is classified, researched and expanded into candidate requirements. A graph compiler applies mandatory templates (security, review, verification, documentation) and project-specific nodes. The graph may evolve during delivery, but protected node classes cannot be deleted by ordinary workers.

## Impact analysis

When a decision/requirement changes:

1. traverse outbound AFFECTS/IMPLEMENTS/VERIFIED_BY relationships;
2. mark affected artefacts stale;
3. schedule re-analysis/re-test nodes;
4. preserve the old decision/evidence as superseded history.

## Local loop contract

Every executable node may run a bounded loop:

`PLAN -> EXECUTE -> OBSERVE -> CRITIQUE -> TEST -> REPAIR -> VERIFY`

The loop has max attempts, elapsed time, repeated-failure detection and escalation. Its result is a graph update plus evidence, not merely a chat message.
