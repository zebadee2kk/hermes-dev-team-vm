# Hermes Autonomous Engineering Forge

A self-contained, provider-independent autonomous engineering environment built around Hermes Agent, LiteLLM, durable graph state, quota-aware free-model routing, disposable worker sandboxes, and lightweight human governance.

> **Status:** architecture + executable V1 foundation. Hermes remains the orchestration system, LiteLLM remains the inference gateway, and the Forge layer adds graph control, quota intelligence, policy, governance and deployment profiles without introducing a second agent framework.

## Target experience

Give the system an idea. It should research it, turn it into a project graph, assemble the specialist roles it needs, build/test/review the result, and only interrupt the owner for material decisions using `YES / NO / DEFER / MORE INFO` gates.

When a free model/provider reaches quota, the agent role survives: state is checkpointed and work moves to another suitable free provider. If no compatible compute is available, affected work enters `WAITING_COMPUTE` and resumes when capacity is expected to return.

## Core principles

1. **Models are fungible compute; agents are persistent organisational entities.**
2. **Hermes Kanban is the durable system of work.** Do not build a parallel task queue unless a proven limitation requires it.
3. **Graph engineering above loop engineering.** Bounded loops execute individual nodes; the project is a living dependency/evidence/decision graph.
4. **YOLO belongs in disposable workers, not the control plane.** Workers may have root inside their sandbox; secrets, policy, graph state, routing and audit remain outside.
5. **Free API tiers first.** Local models handle cheap routine work where available; a small paid emergency budget is explicit policy, never an implicit fallback.
6. **No raw secrets in prompts, graph memory, logs or repositories.**
7. **Human attention is scarce.** Ask only material questions; continue all non-blocked work while a decision is deferred.
8. **Deployment is a policy profile.** The same stack should run on Proxmox/local VMs, OCI Always Free, portable laptops and later client-safe environments.

## Architecture

```text
Owner (Web / Telegram)
        |
Human Gate + Decision Service
        |
Hermes Orchestrator + Hermes Kanban
        |
Graph Control Plane
  |          |            |
Agent      Scheduler    Governance
Factory       |          / Policy
  \           |           /
       Compute Broker
            |
  Quota Intelligence
            |
         LiteLLM
            |
 Free API providers + optional local models
            |
 Disposable worker sandboxes
            |
 Controlled egress / GitHub / package registries
```

See [`docs/01-hld.md`](docs/01-hld.md) and [`docs/02-lld.md`](docs/02-lld.md).

## Repository map

- `docs/` — architecture, threat model, graph model, routing, governance and deployment design.
- `config/` — policy-as-data, provider registry, deployment profiles, egress policy and LiteLLM seed config.
- `src/forge_controller/` — executable V1 quota/router/decision control service.
- `schemas/` — machine-readable contracts.
- `tests/` — deterministic tests for quota, routing and human-gate behaviour.
- `infra/` — deployment scaffolding and environment notes.
- `AGENTS.md` — rules for Claude Code, Codex and other engineering agents working in this repo.
- `BACKLOG.md` — staged implementation plan and exit criteria.

## V1 boundaries

V1 deliberately does **not** introduce LangGraph, CrewAI, AutoGen, Temporal, Kafka, Kubernetes or Neo4j. PostgreSQL + Redis + Hermes Kanban are sufficient until evidence says otherwise.

V1 also does not automate account creation, evade provider quotas, rotate identities to bypass limits, or treat promotional/trial capacity as durable free compute.

## Quick start

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn forge_controller.api:app --reload
```

Local support services:

```bash
docker compose up -d postgres redis litellm
```

Hermes is installed on the VM/control-plane host using its supported installer and pointed at the local LiteLLM endpoint; see `docs/02-lld.md`.

## Current implementation state

The Python layer is intentionally small: typed provider/model observations, quota state transitions, capability-aware route selection, authority-level decisions and a FastAPI surface. Persistence, provider-specific adapters, Hermes MCP integration, sandbox lifecycle and deployment automation are the next milestones in `BACKLOG.md`.

## Safety boundary

A compromised worker must be assumed hostile. It must not be able to retrieve provider master keys, mutate control-plane policy, erase audit state, contact arbitrary LAN targets, or disable its own egress enforcement. `docs/03-threat-model.md` is normative for implementation.
