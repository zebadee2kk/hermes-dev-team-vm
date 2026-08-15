# Agent operating contract

This repository is intended to be worked on by Hermes workers, Claude Code, Codex and other engineering agents. These rules are normative.

## Prime directive

Improve the autonomous engineering system **without weakening its control boundary**. Worker convenience never justifies exposing control-plane secrets, disabling policy enforcement, bypassing human gates or creating quota-evasion mechanisms.

## Architecture constraints

- Hermes Kanban is the durable system of work for V1.
- `delegate_task` is for short-lived isolated reasoning, not durable project state.
- PostgreSQL is the project/trace/decision graph store for V1; Redis is ephemeral coordination/quota cache.
- LiteLLM is the inference gateway. Provider-specific quota interpretation belongs in the Forge quota layer.
- Worker sandboxes are disposable and untrusted. Control-plane services are not executed inside worker sandboxes.
- Do not add LangGraph, CrewAI, AutoGen, Temporal, Kafka, Kubernetes or Neo4j without an ADR showing a concrete limitation and measurable benefit.

## Security rules

- Never commit credentials, tokens, cookies or `.env` contents.
- Never put raw secrets in prompts, graph records, Kanban metadata or logs.
- New outbound domains must be justified in `config/egress-allowlist.yaml`.
- A model/provider marked `public_only` may never receive INTERNAL, CONFIDENTIAL or RESTRICTED material.
- Do not automate account creation, identity rotation, CAPTCHA bypass or any attempt to evade provider quotas/terms.
- Paid inference must remain budget-gated.

## Development workflow

1. Read the relevant docs/ADRs before editing.
2. Keep changes small and testable.
3. Add/adjust tests for behavioural changes.
4. Run `pytest` and `ruff check .` before handoff.
5. Record architectural changes as ADRs.
6. Leave structured handoff evidence: changed files, verification, residual risk and follow-ups.

## Definition of done

A change is not done because code was written. It is done when behaviour is tested, security implications are considered, documentation/contracts are updated, and the next agent can reproduce the verification.
