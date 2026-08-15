# ADR-004: Hermes Kanban is the execution graph

**Status:** Accepted

## Context
The first design gave Forge responsibility for compiling and maintaining an executable project graph beside Hermes Kanban. Current Hermes already provides durable task/dependency/decomposition/worker/blocking/retry semantics.

## Decision
Hermes Kanban is the sole execution lifecycle/DAG for V1. Forge holds semantic, evidence, governance and compute graphs and correlates to Kanban task IDs. Forge may request new/revalidation work through Hermes but does not mirror task state as an independent workflow engine.

## Consequences
Less custom orchestration, fewer split-brain states and easier adoption of future Hermes improvements. Semantic/evidence state remains provider-neutral and can survive a future execution-engine replacement if ever required.