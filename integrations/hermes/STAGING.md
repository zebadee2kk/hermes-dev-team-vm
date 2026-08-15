# Hermes-native staging acceptance

This runbook is the remaining M3 vertical-test gate. It validates the real Hermes integration before any external coding runtime is enabled.

## Preconditions

- Forge controller, PostgreSQL and Redis are running from the same reviewed release.
- Alembic is at `head`.
- LiteLLM is running with a Forge-generated runtime config.
- At least one qualified `coding` deployment and one qualified `review` or `reasoning` deployment are `AVAILABLE`.
- Provider credentials exist only in the trusted LiteLLM/control environment.
- `FORGE_GATEWAY_KEY` is present in the Hermes gateway service environment.
- Hermes Agent version/commit is compatible with the target recorded in `integrations/hermes/README.md`.
- No external runtime adapter is enabled in `config/worker-lanes.yaml`.

## 1. Bootstrap and inspect

```bash
./integrations/hermes/bootstrap.sh
hermes profile list
hermes gateway restart
hermes kanban init
```

Acceptance:

- all eight durable profiles exist;
- each profile's default model is the expected stable `forge/<capability>` alias;
- direct Hermes provider fallbacks are empty;
- `forge-assurance` MCP is configured for each durable lane;
- the two Forge worker-contract Skills are present in each lane;
- Kanban dispatcher is enabled with `forge-orchestrator` and default assignee `engineering`.

Do not continue if a profile points directly at Groq/OpenRouter/Gemini/SambaNova or an exact `forge/deployment/...` alias.

## 2. Gateway/model smoke

From the trusted host, call the Forge OpenAI-compatible gateway with a stable alias:

```bash
curl -fsS http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer $FORGE_GATEWAY_KEY"
```

Then submit a tiny non-sensitive chat completion through `forge/coding`.

Acceptance:

- `/v1/models` exposes stable Forge aliases only;
- successful completion includes `X-Forge-Deployment-ID`;
- the selected deployment is policy-compatible and currently qualified;
- no provider credential appears in Hermes config, Forge logs or the response.

## 3. Minimal Kanban fixture

Create a disposable repository/worktree with one intentionally failing test and one very small implementation task, for example:

> Implement `add(a, b)` in `fixture/math.py` so `pytest tests/test_math.py` passes. Do not change the test. Record a test Reality Anchor and request independent review before completion.

Submit the idea to the normal Hermes orchestrator/Kanban path rather than manually invoking a worker profile.

Acceptance:

- Hermes creates durable Kanban work rather than using `delegate_task` as a substitute;
- a named durable lane receives the work;
- the worker calls `kanban_show` before substantive work;
- Task Capsule revision 1 exists before a durable handoff;
- later capsule revisions preserve the same capsule identity and increase monotonically;
- implementation occurs in the assigned workspace;
- the acceptance test is executed rather than inferred;
- a Reality Anchor records claim, revision, environment, result and reproduction instruction;
- review/completion metadata references the evidence;
- Hermes Kanban, not Forge, owns final task status.

## 4. Inference failover smoke

Use two qualified deployments for the same capability in a non-production staging profile. Arrange for the first deployment to produce a controlled retryable quota/capacity response without violating provider terms; a fake/stub LiteLLM upstream is acceptable for this integration stage if real quota exhaustion cannot be safely induced.

Acceptance:

- the Hermes lane remains `forge/coding` throughout;
- Forge records the first deployment's degraded/quota state;
- the retry is freshly placed onto the second compatible deployment;
- the Task Capsule/Kanban task identity does not change;
- direct Hermes provider fallback is not invoked.

A later M2/M8 gate must repeat the path with real credentials/providers before unattended production use.

## 5. No-compute behavior

Temporarily make all compatible staging deployments unavailable using controlled test state.

Acceptance:

- Forge returns structured `WAITING_COMPUTE` including `retry_at` when known;
- no paid/development/incompatible deployment is invented;
- no acceptance criterion is weakened;
- Forge does not write Hermes' Kanban SQLite database directly.

Automatic Hermes `kanban_block`/unblock is **not** an acceptance requirement until a supported dynamic task-context bridge exists. Record this as the known M3 gap rather than adding an unsupported database mutation shortcut.

## 6. Evidence to retain

Record as Reality Anchors or attach to the staging issue:

- Hermes version/commit;
- Forge commit;
- LiteLLM version/config digest;
- lane/profile inspection output with secrets redacted;
- Kanban task IDs and state transitions;
- Task Capsule IDs/revisions;
- test/CI output;
- Reality Anchor IDs;
- selected deployment IDs for normal and failover calls;
- any residual risk or unsupported upstream behavior.

## Pass gate

M3 can be declared vertically functional only when sections 1-4 pass end-to-end through a real Hermes installation. Section 5 must fail safely as specified; automatic compute block/unblock remains separately open until supported by Hermes request/task context.
