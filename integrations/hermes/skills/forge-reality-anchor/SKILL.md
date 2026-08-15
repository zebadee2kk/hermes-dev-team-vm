---
name: forge-reality-anchor
description: Ground engineering claims in reproducible external evidence.
version: 0.1.0
author: Richard Ham (zebadee2kk), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [forge, evidence, verification, reality-anchor]
    related_skills: []
---

# Forge Reality Anchor Skill

Reality Anchors bind engineering claims to observations outside the model's own narrative: executed tests, CI, browser behavior, measurements, immutable policy, or explicit owner decisions.

## When to Use

- Claiming implementation, verification, performance, security, compatibility, or release readiness.
- Producing evidence that another reviewer or later session must reproduce.
- Don't use model self-review or a prose summary as the sole anchor for a material claim.

## Prerequisites

- MCP server `forge-assurance` is loaded.
- The relevant command/test/browser action has actually been executed or an immutable source has actually been read.

## Procedure

1. State one specific claim being verified. Completion criterion: `claim_ref` can identify exactly what the evidence supports.
2. Execute the independent check using the appropriate Hermes tool. Prefer deterministic tests/CI for code, browser evidence for UI, measurements for performance, and explicit policy/owner records for governance. Completion criterion: an observation exists outside model-generated prose.
3. Capture the workspace revision when code is involved, normally the current Git commit or exact worktree state. Record environment facts needed to interpret the result. Completion criterion: the observation can be tied to the artifact version it evaluated.
4. Call `mcp_forge_assurance_record_reality_anchor` with `project_id`, `task_id`, anchor `type`, `claim_ref`, executor, workspace revision, environment, structured result, artifact references, and a concise reproduction instruction. Completion criterion: Forge returns the durable anchor id.
5. Put the returned anchor id into the next Task Capsule checkpoint and Kanban completion/review metadata. Completion criterion: reviewers can traverse from the lifecycle record to the evidence.

## Pitfalls

- A passing unit test does not anchor an unrelated browser or deployment claim.
- Screenshots without environment/revision context are weak evidence.
- Do not call a check independent if the same model merely restated its own output.
- Mark evidence stale when the relevant requirement, architecture, code, dependency, or environment changes.

## Verification

- The anchor identifies a specific claim, task, artifact revision, executor, result, and reproduction path.
- A later worker can rerun the check without access to private chain-of-thought.
