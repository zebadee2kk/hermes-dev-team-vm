# Hermes integration

This directory binds current upstream Hermes Agent primitives to Forge without duplicating Hermes' execution graph.

## Contract

- Hermes Kanban owns durable task status, dependencies, comments, assignments, review and completion.
- Hermes profiles are stable organisational lanes defined once in `config/worker-lanes.yaml`.
- Hermes profiles use stable Forge model aliases (`forge/coding`, `forge/review`, etc.).
- The Forge Model Gateway selects an eligible Inference Deployment on every model request and forwards to the exact LiteLLM alias.
- `delegate_task` remains short-lived fork/join reasoning only.
- Forge MCP exposes only narrow assurance/governance operations: latest/checkpoint Task Capsule, record Reality Anchor, record Trust Envelope, and classify Decision Request.
- Routing is implicit through the Model Gateway; workers cannot pick a provider deployment through MCP.
- Worker shell processes do not need `DATABASE_URL`, provider credentials, or the LiteLLM master key.

## Bootstrap

Install Hermes Agent and install this Python package on the same trusted control host, then configure the Forge controller/LiteLLM services. Set a strong `FORGE_GATEWAY_KEY` in the Hermes gateway service environment and run:

```bash
./integrations/hermes/bootstrap.sh
hermes gateway restart
hermes kanban init
```

The script is idempotent for profile configuration: it reads `config/worker-lanes.yaml`, creates missing durable lanes, refreshes descriptions/model config, replaces the narrow `forge-assurance` MCP entry, and installs the two Forge worker-contract skills into each profile.

It intentionally disables Hermes' own direct model fallback chain. Provider/account failover is a Forge placement concern; allowing Hermes to fall back directly to another configured provider could bypass Forge privacy, cost and quota policy.

## Model path

```text
Hermes profile (stable forge/coding)
  -> Forge /v1/chat/completions
  -> capability = coding
  -> Forge placement policy
  -> forge/deployment/<provider>/<account>/<model>
  -> LiteLLM
  -> provider API
```

A retryable 429/502/503/504 from LiteLLM is recorded against the selected deployment. Forge then performs one fresh placement attempt; it does not mutate the Hermes profile identity.

## MCP path

```text
Hermes model tool call
  -> mcp_forge_assurance_{latest/checkpoint/anchor/trust/decision}
  -> local stdio MCP process
  -> loopback Forge assurance/governance API
  -> PostgreSQL / deterministic policy
```

The MCP process receives only `FORGE_INTERNAL_URL`, which is non-secret. It has no task-lifecycle mutation tool and no provider-selection or credential tool. Full network/process privilege separation is completed by the Sandbox Broker/capability gateway in M4; do not treat this M3 local-host integration as the final hostile-worker boundary.

## `WAITING_COMPUTE`

Forge already returns structured `WAITING_COMPUTE` when no policy-compatible inference deployment is usable. The current Hermes custom-provider request path does not expose a supported dynamic Kanban task identifier to Forge, so Forge does **not** mutate Hermes' Kanban database behind its back. Automatic compute block/unblock remains an explicit M3 integration item pending a supported Hermes hook/request-context bridge. Until then, the execution graph remains correctly owned by Hermes rather than duplicated in Forge.

## Upstream compatibility target

The integration was designed against Hermes Agent commit `45af7a71fcd420b4422d2c074b1ce58b9ce0d048` (August 2026) and MCP Python SDK v2. Before upgrading Hermes or MCP, rerun the compatibility review for profile commands, Kanban tools/statuses, MCP configuration and model/custom-provider behavior.
