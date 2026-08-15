# Human governance

## Goal

Minimise owner interaction without pretending uncertainty does not exist. Human gates are exception-based rather than stage-based.

## Authority levels

### L0 — autonomous
Routine, low-impact, reversible implementation choices. No notification.

### L1 — autonomous + audit
Meaningful but reversible decisions. Continue and include in digest.

### L2 — owner gate
Material product/scope/architecture decisions. Present `YES / NO / DEFER / MORE INFO`.

### L3 — hard owner gate
Production exposure, meaningful spend, persistent destructive actions, credentials/security-boundary changes, publishing and external communications. DEFER may leave dependent work blocked; it may not be converted into silent approval.

## Decision object

A decision stores:

- question
- recommended action
- confidence
- materiality
- irreversibility
- consequence
- rationale/evidence pointers
- blocking graph nodes
- authority level
- current action/status

## Owner actions

**YES** — accept recommendation and unblock dependencies.

**NO** — reject recommendation; system should normally compute the next-best safe alternative instead of immediately asking an open-ended question.

**DEFER** — leave decision unresolved and continue all independent work.

**MORE INFO** — spawn/execute a concise explainer/research node, then re-present the same decision.

## Attention policy

Do not interrupt for multiple low-value questions. Batch non-urgent L2 decisions when possible. Interrupt immediately only when a high-value project branch is blocked or policy requires it.

## Example digest

```text
Project ALPHA — 82% complete
Tests: 143/145 passing
Model cost: £0.00
2 decisions need you

D47 Use Entra authentication? [YES] [NO] [DEFER] [MORE INFO]
D51 Public demo deployment?    [YES] [NO] [DEFER] [MORE INFO]
```
