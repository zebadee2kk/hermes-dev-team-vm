# Task Capsules and Reality Anchors

## Why Task Capsules exist

Long-running autonomous work cannot depend on one provider session or an ever-growing transcript. A Task Capsule is the compact durable contract passed between models, worker lanes and replacement Hands.

A capsule contains:
- task/project identity and Kanban correlation;
- objective and immutable-for-attempt acceptance criteria;
- constraints/data sensitivity;
- relevant requirements/decisions/evidence pointers;
- workspace/revision/worktree identity;
- attempt budget and current attempt;
- previous structured results/failures;
- required reality anchors/review level;
- open questions/blockers;
- capability requirements;
- current residual risks and produced artefacts.

The capsule should contain references/digests rather than blindly copying large history. Context reconstruction retrieves only relevant graph/code evidence.

## Handoff contract

Workers return a structured result containing changed artefacts, commands/actions performed, verification observations, anchors created, unresolved failures, proposed graph updates, taint/provenance and residual risk. Free-form narrative is supplementary.

## Reality Anchor model

An Anchor is an observation outside the generating model's assertion loop. Seed types:
- `TEST_EXECUTION`
- `CI_CHECK`
- `BUILD_ARTIFACT`
- `HTTP_PROBE`
- `BROWSER_E2E`
- `DB_MIGRATION`
- `STATIC_SCAN`
- `SECURITY_SCAN`
- `BENCHMARK_MEASUREMENT`
- `AUTHORITATIVE_SOURCE`
- `OWNER_DECISION`

An anchor records subject/claim, executor/tool, environment/revision, observed result, timestamp, artefact pointers, reproducibility command/method and freshness/staleness.

## Risk-adaptive verification

- **low:** one suitable executable anchor where practical;
- **medium:** anchor + independent review lane/deployment;
- **high:** multiple anchors as appropriate + independent reviewer preferably on a different provider/runtime + explicit residual risk;
- **L3/production:** owner authority plus required technical anchors.

## Anti-gaming rules

A worker cannot satisfy a failing task by deleting/weakening acceptance criteria, mandatory tests, security policies or anchor requirements. Changes to protected criteria require the corresponding authority workflow. A test newly written by the same worker is useful evidence, but high-risk completion should also include an independently determined or pre-existing acceptance anchor.