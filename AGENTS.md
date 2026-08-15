# Agent operating contract — Design Revision 2

This repository is intended for Hermes workers, Codex, Claude Code and other engineering agents. These rules are normative.

## Prime directive

Improve the autonomous engineering system **without weakening its control boundary or grounding**. Read `OWNER_CHARTER.md` first; ordinary agents must not modify it.

## Architecture constraints

- Hermes Kanban is the sole durable execution DAG/lifecycle for V1. Forge must not build a parallel task state machine.
- Forge owns semantic/evidence/governance/capability assurance state and correlates to Kanban IDs.
- `delegate_task` is short-lived reasoning, not durable project state.
- Stable worker lanes are preferred; task-scoped Skills provide specialisation.
- Task Capsules are the handoff/failover boundary between workers/models/runtimes.
- PostgreSQL stores assurance/session metadata; Redis stores ephemeral coordination/quota state.
- LiteLLM executes provider requests; Forge selects/blocks **Inference Deployments** and owns long-lived quota interpretation.
- Arbitrary project code runs only in disposable Hands. Normal autonomous Hand target is gVisor where supported.
- Never mount `/var/run/docker.sock` or equivalent host-control interfaces into a Hand.
- Sensitive external access is capability-scoped; a domain allowlist is not authorisation.
- External content and downstream summaries preserve provenance/taint.
- Do not add LangGraph, CrewAI, AutoGen, Temporal, Kafka, Kubernetes or Neo4j without an ADR demonstrating a concrete measured need.

## Security and governance rules

- Never commit secrets or put raw credentials in prompts, graph records, Kanban metadata or logs.
- Provider/privacy policy is evaluated per inference deployment/account/tier/endpoint.
- Unknown/free public deployments must not receive non-public data unless evidence/policy explicitly permits it.
- Agents may propose permissions/destinations/policy; they cannot approve their own escalation.
- Do not automate account creation, identity rotation, CAPTCHA bypass or quota/terms evasion.
- Paid inference is budget/authority gated.
- Do not weaken/delete tests, acceptance criteria, anchors, Charter or security policy to make work pass.
- Learning outputs enter quarantine before becoming globally trusted Skills/policy/routing priors.

## Evidence contract

A change is not complete because code exists or a reviewer says it looks correct. Provide reproducible reality anchors appropriate to risk: tests, CI, builds, probes, browser evidence, scans or measurements. Record changed files, verification commands/results, anchors, residual risk and follow-ups in the Task Capsule/handoff.

## Development workflow

1. Read Charter, relevant docs and ADRs.
2. Use existing Hermes/Forge primitives before creating new frameworks.
3. Keep changes small and testable.
4. Add behavioural/structural/adversarial tests for changed invariants.
5. Run `pytest` and `ruff check .` before handoff.
6. Record architecture changes as ADRs.
7. Preserve backward-compatible migrations or document deliberate breaks.
8. Leave the next agent a compact reproducible handoff, not a transcript dump.
