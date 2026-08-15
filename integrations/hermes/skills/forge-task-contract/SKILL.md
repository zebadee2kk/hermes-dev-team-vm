---
name: forge-task-contract
description: Keep Hermes work aligned with durable Forge task state.
version: 0.1.0
author: Richard Ham (zebadee2kk), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [forge, kanban, task-capsule, handoff]
    related_skills: []
---

# Forge Task Contract Skill

Use Hermes Kanban for task lifecycle and Forge Task Capsules for restart-safe assurance state. A capsule is a snapshot/handoff contract, never a second task queue.

## When to Use

- A Kanban worker starts, resumes, hands off, blocks, requests review, or completes durable work.
- A task must survive model/provider failover or another named profile must continue it.
- Don't use for short fork/join reasoning inside one worker; `delegate_task` is appropriate there.

## Prerequisites

- The current worker was spawned from Hermes Kanban.
- MCP server `forge-assurance` is loaded.
- Use the `kanban_*` tools for lifecycle changes; do not shell out to `hermes kanban`.

## Procedure

1. Call `kanban_show` immediately and read the full task, comments, dependencies, attachments, workspace, and acceptance context. Completion criterion: the task identity and current board state are known.
2. Call `mcp_forge_assurance_latest_capsule` with the Kanban task id. If a capsule exists, preserve its `capsule_id`, increment its `revision` only when checkpointing changed state, and carry forward previous results/open questions. Completion criterion: new work starts from the latest durable snapshot rather than reconstructed memory.
3. If no capsule exists, construct one with the Kanban task id as both `task_id` and `kanban_task_id` unless a project adapter supplied a separate stable task id. Include objective, at least one acceptance criterion, constraints, workspace facts, verification plan, capability requirements, and open questions. Call `mcp_forge_assurance_checkpoint_capsule`. Completion criterion: Forge has revision 1 before substantive work crosses an agent boundary.
4. Work only on the Kanban task's scope. Use task-scoped Skills for expertise; do not create persistent profiles or a parallel dependency graph to organize subwork. Completion criterion: every durable dependency/handoff remains visible on Kanban.
5. Before `kanban_block`, `kanban_request_review`, reassignment/handoff, or `kanban_complete`, checkpoint a new capsule revision with current artifacts, previous results, unresolved questions, and residual risk. Completion criterion: another worker can continue from the capsule without reading private reasoning.
6. On completion, use `kanban_complete` with structured evidence metadata. Include changed files, verification performed, dependency changes, Reality Anchor references, and residual risk. Completion criterion: the Kanban row is authoritative for lifecycle and the Forge capsule/anchors are authoritative for assurance evidence.

## Pitfalls

- Never use `delegate_task` as a durable handoff substitute.
- Never mark acceptance satisfied from model confidence alone.
- Never reduce or remove acceptance/security constraints merely to make a task pass.
- Never overwrite an older capsule revision with conflicting content; preserve the id and advance the revision.
- `WAITING_COMPUTE` is not task failure. Do not rewrite the objective or acceptance criteria because a model deployment is exhausted.

## Verification

- `kanban_show` reflects the real lifecycle state.
- The latest capsule revision matches the current task/workspace facts.
- Every completion claim that matters has executable evidence or an explicit residual-risk entry.
