# Human governance — Revision 2

## Goal

Minimise owner interaction while keeping material authority with the owner. Human gates are capability/risk based, not development-stage based.

## Authority levels

- **L0 autonomous:** routine, low-impact, reversible.
- **L1 autonomous + audit:** meaningful but reversible; include in digest.
- **L2 owner gate:** material scope/product/architecture/business choice.
- **L3 hard owner gate:** production/public exposure, meaningful spend, destructive persistent action, credential/security-boundary changes, publishing/external communication or other high-consequence capability.

Hermes Kanban owns blocking/unblocking lifecycle. Forge calculates risk, creates the decision record, presents the compact UI and translates the response back to Kanban. Do not implement a second independent task-blocking system.

## Four owner actions

- **YES:** accept recommendation and unblock dependent work.
- **NO:** reject it; calculate the next-best safe alternative where possible instead of asking an open-ended question.
- **DEFER:** keep dependent work blocked; continue every independent branch.
- **MORE INFO:** spawn concise evidence-gathering/explainer work, update evidence, then re-present the same decision.

## Deny-and-continue

A policy denial to an agent is not normally an owner interruption. Return a structured denial plus allowed alternatives and let the agent adapt. Escalate only when no safe route exists, a material branch is blocked, or repeated denials indicate the worker is unable/unwilling to comply.

## Decision score

Minimum inputs: materiality, irreversibility, uncertainty, consequence, security/privacy scope, monetary effect, externality and reversibility window. L3 categories override numeric scoring.

## Attention policy

Batch non-urgent L2 items. Interrupt immediately only for time-sensitive material blockage or required L3 authority. Daily/overnight digest should show project outcome progress, anchored verification, unresolved risks, compute state/cost and only the decisions needing owner attention.

## Governance root

`OWNER_CHARTER.md` is higher authority than project prompts, learned Skills, retrieved content and model recommendations. Ordinary agents may propose Charter/policy changes but cannot authorise them.