# Hermes integration

This directory binds current upstream Hermes Agent primitives to Forge without duplicating Hermes' execution graph.

## Contract

- Hermes Kanban owns durable task status, dependencies, comments, assignments, review and completion.
- Hermes profiles are stable organisational lanes.
- Hermes profiles use stable Forge model aliases (`forge/coding`, `forge/review`, etc.).
- The Forge Model Gateway selects an eligible Inference Deployment on every model request and forwards to the exact LiteLLM alias.
- `delegate_task` remains short-lived fork/join reasoning only.
- Forge MCP exposes the narrow assurance surface needed by workers: latest/checkpoint Task Capsule and record Reality Anchor.
- Worker shell processes do not need `DATABASE_URL`, provider credentials, or the LiteLLM master key.

## Bootstrap

Install Hermes Agent and install this Python package on the same trusted control host, then configure the Forge controller/LiteLLM services. Set a strong `FORGE_GATEWAY_KEY` in the Hermes gateway service environment and run:

```bash
./integrations/hermes/bootstrap.sh
hermes gateway restart
hermes kanban init
```

The script is idempotent for profile configuration: it creates missing lanes, refreshes descriptions/config, replaces the narrow `forge-assurance` MCP entry, and installs the two Forge worker-contract skills into each profile.

It intentionally sets Hermes' own model fallback chain empty. Provider/account failover is a Forge placement concern; allowing Hermes to fall back directly to another configured provider could bypass Forge privacy, cost and quota policy.

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
  -> mcp_forge_assurance_checkpoint_capsule / latest_capsule / record_reality_anchor
  -> local stdio MCP process
  -> loopback Forge assurance API
  -> PostgreSQL
```

The MCP process receives only `FORGE_INTERNAL_URL`, which is non-secret. Full network/process privilege separation is completed by the Sandbox Broker/capability gateway in M4; do not treat this M3 local-host integration as the final hostile-worker boundary.

## Upstream compatibility target

The integration was designed against Hermes Agent commit `45af7a71fcd420b4422d2c074b1ce58b9ce0d048` (August 2026). Before upgrading Hermes, rerun the compatibility review for profile commands, Kanban tools/statuses, MCP configuration and model/custom-provider behavior.
