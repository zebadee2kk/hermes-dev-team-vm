# LiteLLM runtime contract

Forge is the source of truth for inference-deployment eligibility, privacy policy, quota/reset state and placement. LiteLLM is the provider execution boundary for a deployment Forge has already selected.

## V1 rules

1. Forge emits one exact LiteLLM alias per eligible Inference Deployment: `forge/deployment/<deployment-id>`.
2. Forge never asks LiteLLM to choose between providers for the same task. Cross-provider placement remains a Forge decision.
3. Discovery does not populate LiteLLM directly. A model must pass the quarantine/qualification gate first.
4. Generated config contains environment-variable references, never provider credential values.
5. A deployment that is disabled, quarantined, development-only outside a development profile, or waiting for a future quota reset is omitted from the generated model list.
6. Unknown OpenAI-compatible providers require an explicit LiteLLM provider mapping; Forge does not guess protocol compatibility.
7. Provider-reported `retry_at` is durable truth. Jitter applies only to the later health-probe schedule.

## Publish and reload

`forge_controller.litellm_publish.publish_config` writes generated YAML to a temporary file in the destination directory, fsyncs it and atomically replaces the active file. It returns a SHA-256 digest and a `changed` flag.

Deployment automation should restart or roll the LiteLLM process only when `changed` is true. The generated config should live in a directory/volume shared read-only with LiteLLM and writable only by the trusted control/deployment plane. Do not expose that volume to worker Hands.

V1 intentionally prefers startup YAML plus controlled restart over making LiteLLM's database-backed model-management API another source of truth. A later ADR may change this only after the selected LiteLLM release has regression coverage for dynamic add/update/delete behavior and Forge can reconcile it deterministically.

## Failure behavior

- Publish failure leaves the previous config path intact.
- A LiteLLM restart failure must not change PostgreSQL deployment truth; Forge should report the execution gateway degraded and retry the deployment action.
- If no deployment is eligible, Forge should retain `WAITING_COMPUTE`; deployment automation must not invent a fallback model.
- Removing a deployment from generated config is a consequence of Forge policy/quota state, not a LiteLLM routing decision.
