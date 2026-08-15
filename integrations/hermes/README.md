# Hermes integration

This directory binds current upstream Hermes Agent primitives to Forge without duplicating Hermes' execution graph.

## Contract

- Hermes Kanban owns durable task status, dependencies, comments, assignments, review and completion.
- Hermes profiles are stable organisational lanes defined once in `config/worker-lanes.yaml`.
- Hermes profiles use stable Forge model aliases (`forge/coding`, `forge/review`, etc.).
- The Forge Model Gateway selects an eligible Inference Deployment on every model request and forwards to the exact LiteLLM alias.
- `delegate_task` remains short-lived fork/join reasoning only.
- Forge MCP exposes narrow assurance/governance operations plus **read-only** compiled-wiki search/read/lint.
- Trusted knowledge acquisition, raw mutation, compilation, semantic stale mutation and technology promotion are deliberately not worker MCP tools.
- Routing is implicit through the Model Gateway; workers cannot pick a provider deployment through MCP.
- Worker shell processes do not need `DATABASE_URL`, provider credentials, or the LiteLLM master key.

## Bootstrap

Install Hermes Agent and install this Python package on the same trusted control host, then configure the Forge controller/LiteLLM services. Set a strong `FORGE_GATEWAY_KEY` in the Hermes gateway service environment and run:

```bash
./integrations/hermes/bootstrap.sh
hermes gateway restart
hermes kanban init
```

The script is idempotent for profile configuration: it reads `config/worker-lanes.yaml`, creates missing durable lanes, refreshes descriptions/model config, replaces the narrow `forge-assurance` MCP entry, and refreshes all Forge Skills into each durable profile.

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
  -> forge-assurance MCP
     -> Task Capsule / Reality Anchor / Trust Envelope / Decision classification
     -> read-only knowledge_search / knowledge_read_page / knowledge_lint
  -> loopback Forge assurance/governance API or local compiled-wiki reader
```

The MCP process receives only `FORGE_INTERNAL_URL` and `FORGE_KNOWLEDGE_ROOT`, which are non-secret local references. It has no task-lifecycle mutation tool, provider-selection tool, acquisition tool, compile tool, candidate-promotion tool, or credential tool. Full network/process privilege separation is completed by the Sandbox Broker/capability gateway in M4.

## Knowledge maintenance cron

Hermes cron is used only as a scheduler. It does **not** become another project/workflow graph.

The optional setup is:

```bash
FORGE_ENABLE_KNOWLEDGE_CRON=true ./integrations/hermes/bootstrap.sh
```

or independently:

```bash
./integrations/hermes/configure-knowledge-cron.sh
```

Default jobs:

- `Forge knowledge lint` — daily script-only job. Uses no LLM tokens; actionable findings are queued onto Hermes Kanban with an idempotency key and the `forge-knowledge-compiler` Skill.
- `Forge knowledge digest` — daily script-only health/count digest. Uses no LLM tokens.
- `Forge weekly technology radar` — weekly agent scan using `config/technology-radar-sources.yaml`, `forge-tech-radar`, and `forge-knowledge-compiler`. It may create `TEST`-tier research/triage tasks but may not install, adopt, compile, change policy, or promote technology.

`FORGE_KNOWLEDGE_DELIVER` defaults to `local`; set it to a configured Hermes delivery target such as Telegram when desired. The cron platform should expose only the web/research and Kanban toolsets required by the weekly radar. Cron-run sessions cannot create additional cron jobs, matching Forge's runaway-scheduling constraint.

## `WAITING_COMPUTE`

Forge already returns structured `WAITING_COMPUTE` when no policy-compatible inference deployment is usable. The current Hermes custom-provider request path does not expose a supported dynamic Kanban task identifier to Forge, so Forge does **not** mutate Hermes' Kanban database behind its back. Automatic compute block/unblock remains an explicit M3 integration item pending a supported Hermes hook/request-context bridge. Until then, the execution graph remains correctly owned by Hermes rather than duplicated in Forge.

## Upstream compatibility target

The integration was designed against the reviewed August 2026 Hermes Agent generation and MCP Python SDK v2. Before upgrading Hermes or MCP, rerun the compatibility review for profile commands, Kanban tools/statuses, cron behavior, MCP configuration and model/custom-provider behavior.
