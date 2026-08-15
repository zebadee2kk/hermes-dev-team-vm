# Research basis and upstream assumptions

Architecture was re-reviewed on 2026-08-15. Volatile provider quotas/models/terms and cloud free-tier limits must be revalidated at deployment/runtime rather than hardcoded as truth.

## Graph engineering

The design is influenced by the "From Loop Engineering to Graph Engineering" argument: local agent loops remain useful, but reliable systems need graph-level structure plus anchors to reality that the optimiser cannot simply redefine. Forge therefore separates Hermes' execution DAG from semantic/evidence/governance/capability graphs and introduces protected Reality Anchors/Owner Charter.

Reference:
- https://medium.com/intuitionmachine/from-loop-engineering-to-graph-engineering-d3ebeb08511c

## Hermes Agent

Current Hermes Kanban is treated as the durable execution primitive: multi-agent task board, dependencies/decomposition, worker profiles/lanes, retries/runs, blocking and engineering pipeline use. `delegate_task` remains shorter-lived isolated fan-out. Forge intentionally avoids building a parallel workflow engine.

Upstream:
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://hermes-agent.nousresearch.com/docs/reference/tools-reference/

## Long-running agent harness design

Recent Anthropic engineering material reinforces separation of reasoning/orchestration, durable session state and contained execution environments; structured handoffs and executable verification are more robust than relying on long transcripts. Forge adopts this as Brain / Session / Hands plus Task Capsules/Reality Anchors.

References:
- https://www.anthropic.com/engineering/managed-agents
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps

## Containment and capability security

Anthropic's published containment/sandboxing experience supports deterministic execution containment and demonstrates why destination allowlisting alone is not sufficient authority. Forge therefore uses gVisor as the normal Linux autonomous-worker target where supported and introduces operation/resource-scoped Capability Gateways with trusted credential injection.

References:
- https://www.anthropic.com/engineering/how-we-contain-claude
- https://www.anthropic.com/engineering/claude-code-sandboxing
- https://gvisor.dev/docs/user_guide/install/

## Agent-first repository engineering

OpenAI's harness-engineering material reinforces repository-local durable plans/docs, mechanical architectural constraints, outcome-based evaluation and continuous cleanup/gardening under high autonomous coding throughput.

References:
- https://openai.com/index/harness-engineering/
- https://openai.com/index/separating-signal-from-noise-coding-evaluations/

## LiteLLM and quotas

LiteLLM provides the common provider gateway, retry/fallback telemetry and budget primitives. Forge layers long-lived deployment availability/reset interpretation above it. Provider examples such as Groq/OpenRouter expose useful rate-limit/reset signals, but exact limits change.

References:
- https://docs.litellm.ai/
- https://console.groq.com/docs/rate-limits
- https://openrouter.ai/docs/faq

## OCI and portability

The OCI free/low-cost profile is deliberately disposable and ARM-aware. Current resource assumptions are deployment metadata only; Terraform/Ansible, backup and restore must make host loss routine.

Reference:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
