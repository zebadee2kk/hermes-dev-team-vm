# External runtime contract

External coding runtimes such as Codex, Claude Code, OpenCode or Gemini CLI are optional **Hands**, not project managers and not parallel workflow engines. Hermes Kanban remains the durable execution graph and a Task Capsule remains the handoff/checkpoint contract.

## V1 interface

A trusted Hermes/Forge integration may construct `ExternalRuntimeRequest` from the latest Task Capsule. The request contains only the information needed to execute one bounded task:

- project/task/capsule identity and exact capsule revision;
- objective, acceptance criteria and constraints;
- one bounded workspace plus allowed paths;
- references to capability grants rather than credential values;
- verification requirements;
- a bounded timeout; and
- the required structured worker-result schema.

The external runtime must return a result matching `schemas/worker-result.schema.json`. The result is evidence for Hermes/Forge to ingest; it does not directly complete or reassign the Kanban task.

## Security boundary

The request deliberately contains no provider API key, Forge database URL, LiteLLM master key, host-control token, Docker socket, or unrestricted network grant. Credential materialisation and external actions belong to trusted capability/secret gateways outside the Hand.

An external runtime adapter must eventually execute behind the M4 Sandbox Broker. It must not run directly in the Forge controller process or receive a host filesystem root simply because its CLI supports autonomous/yolo mode.

## Lifecycle

```text
Hermes Kanban task
  -> latest Task Capsule
  -> ExternalRuntimeRequest
  -> Sandbox Broker / capability grants
  -> external runtime Hand
  -> structured Worker Result + evidence
  -> Forge Reality Anchors / capsule checkpoint
  -> Hermes review / complete / block / handoff
```

## Enablement gate

`config/worker-lanes.yaml` keeps all external runtime adapters disabled until the Hermes-native path has passed a live staging smoke test and the sandbox/capability boundary needed for that runtime exists. Defining this interface does **not** enable external execution.

When an adapter is implemented, its activation must be an explicit policy/config change with tests proving:

1. it consumes the same Task Capsule revision that Hermes intended;
2. it cannot escape the assigned workspace or capability grants;
3. it returns structured results and independent evidence;
4. it cannot complete/reassign Kanban work directly;
5. it cannot weaken acceptance/security constraints; and
6. cancellation/timeout leaves a recoverable capsule/workspace state.
