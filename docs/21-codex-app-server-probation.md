# Probation trial 001 — Hermes Codex app-server runtime

## Decision

The first real technology candidate is Hermes' optional Codex app-server runtime, scoped strictly to bounded **engineering leaf-worker turns**.

This is not a new project manager, graph, queue or Forge external-runtime adapter. Hermes Kanban remains the durable execution graph. During probation the orchestrator, research, product, architecture, security, QA and release lanes remain on the standard Hermes runtime.

Candidate record: `knowledge/candidates/hermes-codex-app-server-runtime.yaml`

Probation policy: `config/probation/hermes-codex-app-server-runtime.yaml`

Start: `2026-08-15T20:36:00Z`

Earliest time-only promotion gate: `2026-08-29T20:36:00Z`

The date is necessary but insufficient. Promotion still requires two real-workload passes, current non-stale task-bound Reality Anchors, isolation evidence and a demonstrated rollback.

## Why this candidate

Hermes currently provides an opt-in `codex_app_server` runtime for OpenAI/Codex turns. The runtime delegates the turn's terminal, patch and related execution to Codex while Hermes remains the surrounding session/gateway/Kanban shell. Hermes documents support for ChatGPT-subscription authentication through Codex rather than requiring an API key for that runtime.

Primary evidence:

- `https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/codex-app-server-runtime.md`
- `https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md`
- `https://github.com/NousResearch/hermes-agent/issues/61360`

This is a narrow seam with an immediate Forge benefit: additional high-quality coding capacity can potentially be consumed without spending free API quota and without replacing Hermes' durable work model.

## Known limitations treated as test requirements

The candidate is beta and changes the tool-loop failure domain. Hermes documents that `delegate_task`, Hermes memory, session search and Hermes todo are unavailable inside Codex app-server turns. That makes it unsuitable for the Forge orchestrator during this trial.

Hermes also currently has an open upstream issue around configuring the Codex binary path for gateway/service/Kanban contexts with a minimal `PATH`. Forge therefore requires deterministic absolute binary discovery before any real workload is credited.

Codex app-server supports local stdio and other transports. The probation profile uses stdio only; experimental/unsupported websocket transport is not part of the trial.

## Preflight

Run:

```bash
python integrations/hermes/codex-probation-preflight.py
```

The preflight is deliberately non-mutating. It verifies:

1. Hermes CLI is present;
2. Codex CLI is present;
3. Codex is at least the Hermes-documented minimum version;
4. Codex resolves to an absolute path;
5. `codex app-server generate-json-schema` succeeds for the installed version.

It does **not** enable `codex_app_server`, change Hermes config, perform login, or start a real workload.

## Real workload gates

A real workload must not start until the outer disposable-Hand/isolation boundary is acceptable for the trial. Each workload uses the same Task Capsule acceptance criteria as its standard `forge/coding` baseline.

Two initial workloads are required:

### 1. Single-file repair

A bounded defect with an existing failing test. The candidate must repair it without weakening the test, leaving the workspace boundary, or modifying control-plane state.

### 2. Multi-file refactor

A bounded refactor with unit/integration coverage and independent review. The candidate must preserve behaviour and acceptance requirements while producing current Reality Anchors.

For both workloads record completion, acceptance pass rate, retries, elapsed time, human gates and tool/patch counts. These metrics are evidence, not a benchmark that can waive security requirements.

## Promotion assurance

`forge-knowledge promotion-check` remains a structural/offline report.

The state-changing `forge-knowledge promote` path now requires `--project-id` plus `--database-url` or `DATABASE_URL`. Before the candidate file is changed to `promoted`, Forge resolves the Reality Anchor IDs from passing real-workload evaluations in the assurance database and rejects:

- missing anchors;
- stale anchors;
- anchors belonging to another project;
- anchors whose task does not match the evaluation task; or
- fewer than the configured number of verified current anchors.

This closes the failure mode where fabricated anchor strings in YAML could otherwise satisfy a promotion count.

## Rollback

Rollback is part of the acceptance test, not merely documentation:

1. switch the probation worker runtime back to `auto`;
2. terminate the candidate Codex app-server subprocess;
3. preserve the assigned workspace and latest Task Capsule;
4. redispatch through the normal `forge/coding` lane;
5. verify the task can continue without weakening acceptance criteria;
6. record rollback Reality Anchor/evidence.

No probation-only configuration is promoted to default lanes until that rollback has been demonstrated.
