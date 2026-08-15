# Research basis and upstream assumptions

This architecture was checked against current upstream documentation on 2026-08-15. Revalidate unstable quotas/models before deployment.

## Hermes Agent

- Kanban is a durable multi-agent task board with dispatcher-spawned named profiles, retries/runs, human blocking and engineering-pipeline use cases.
- `delegate_task` creates isolated child contexts and is appropriate for shorter fan-out; Kanban is the durable primitive.
- Kanban is single-host in its current design, making one enclosed VM a natural V1 fault/security domain.
- Hermes supports custom model endpoints and can be pointed at a LiteLLM gateway.

Upstream:
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://hermes-agent.nousresearch.com/docs/user-guide/configuration/
- https://hermes-agent.nousresearch.com/docs/getting-started/installation

## LiteLLM

LiteLLM provides a unified gateway for many LLM providers with router retry/fallback logic plus proxy usage/budget controls. Forge intentionally layers longer-lived quota intelligence above it.

Upstream:
- https://docs.litellm.ai/

## OCI Always Free

Oracle currently documents Ampere A1 Always Free as 1,500 OCPU-hours and 9,000 GB-hours per month, equivalent to 2 OCPUs and 12 GB RAM for an Always Free tenancy, and warns idle compute may be reclaimed.

Upstream:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## Provider examples

Groq documents remaining/reset rate-limit headers and 429 handling. OpenRouter documents free model variants/free router, free-model rate limits dependent on account credit state, and `Retry-After` on relevant errors. These are examples of why Forge stores provider-specific observations rather than one generic retry counter.

Upstream:
- https://console.groq.com/docs/rate-limits
- https://openrouter.ai/docs/faq
- https://openrouter.ai/docs/api/reference/errors-and-debugging

The provider registry is deliberately conservative and disabled-by-default until credentials/terms are verified for the deployment.
