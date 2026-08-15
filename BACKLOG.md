# Delivery backlog — Design Revision 2

The backlog is ordered to reach a safe autonomous vertical slice early while avoiding duplicated Hermes orchestration.

## M0 — Foundation + architecture correction

- [x] Initial control-service skeleton, tests and CI
- [x] Design Revision 2 research review
- [x] Hermes Kanban established as sole execution graph
- [x] Brain / Session / Hands boundary
- [x] Task Capsule + Reality Anchor contracts
- [x] Content Trust + capability-egress design
- [x] Inference Deployment routing unit
- [x] stable lanes + dynamic Skills design
- [x] Owner Charter + learning quarantine principles

**Exit:** no major implementation milestone depends on the superseded dual-orchestrator design.

## M1 — Durable assurance/session state

- [x] PostgreSQL models/migrations for Task Capsules, semantic nodes/edges, reality anchors, trust envelopes, decisions, inference deployments, quota observations, capability/outcome scores, learning candidates and events
- [x] Redis repository for cooldown/lease/wake coordination primitives
- [x] append-only audit/event append service
- [x] idempotency/concurrency foundation — idempotent events, owner-safe Redis leases, monotonic/idempotent Task Capsule revision checkpoints with conflict rejection
- [x] restart/recovery vertical test preserves Task Capsule + deployment quota state and resumes placement
- [x] PostgreSQL migration chain validated in CI against PostgreSQL 16
- [x] persistence-backed FastAPI surface validated across controller restart

**Exit:** controller restart preserves assurance, quota, decision and handoff state without duplicating Hermes task lifecycle.

**Current status:** M1 core exit is satisfied and green in CI. Deeper off-host event replay, encrypted backup/restore and host-loss drills remain deliberate M8/M9 hardening work rather than reasons to expand the M1 control plane.

## M2 — Quota Intelligence + Inference Deployments

- [x] provider discovery/adapter interfaces
- [x] provider adapters — Groq, OpenRouter, Gemini, SambaNova and explicit generic OpenAI-compatible adapter implemented
- [x] persistent discovery sync adds new models as quarantined deployments without regressing already-qualified deployment state
- [x] account/tier/endpoint-specific Inference Deployment registry
- [ ] reset-time confidence, health probes and jitter — request/token reset parsing plus deterministic post-reset/exponential jitter implemented; active provider probe loop remains
- [ ] privacy/terms evidence per deployment — qualification gate now requires terms evidence, passing smoke test and positive capability measurements; automated evidence collection/classification remains
- [x] LiteLLM integration foundation — Forge-approved exact deployment aliases, environment-reference credentials, deterministic config materialization, atomic publish and PostgreSQL-backed renderer implemented
- [ ] LiteLLM runtime reconciliation — controlled restart/roll only on config hash change and post-reload verification belong to deployment automation
- [ ] `WAITING_COMPUTE` block/wake contract with Hermes — durable Forge placement/wake behaviour exists; Hermes block/unblock adapter remains M3 integration work

**Exit:** quota exhaustion swaps inference deployment using the same Task Capsule; all-compatible-compute exhaustion blocks then resumes safely.

**Current status:** M2 now has a complete provider lifecycle foundation: discover -> quarantine -> qualify -> persist -> Forge place -> exact LiteLLM deployment alias. Fake-provider restart-safe failover is covered by CI and four real provider adapters are implemented from current provider contracts. Remaining M2 work is active health probing/evidence automation and one live credentialed end-to-end provider/LiteLLM failover test; Hermes block/unblock integration intentionally starts in M3.

## M3 — Hermes execution integration

- [ ] reference Hermes installation/config
- [ ] stable lane/profile definitions from `config/worker-lanes.yaml`
- [ ] task-scoped Skills convention/library
- [ ] Task Capsule adapter for Kanban task start/handoff/completion
- [ ] Forge MCP/API facade for assurance/routing/decision/trust services
- [ ] structured result/anchor ingestion
- [ ] human/compute block-unblock mapping
- [ ] external runtime lane interface; implement at least one of Codex/Claude Code/OpenCode after Hermes-native lane works

**Exit:** raw idea -> Hermes decomposition -> durable work -> Task Capsules -> autonomous implementation/verification without a Forge-owned parallel DAG.

## M4 — Sandbox Broker + capability gateway

- [ ] sandbox manager abstraction
- [ ] gVisor normal worker prototype on x86_64 and ARM64 target paths
- [ ] high-risk stronger isolation adapter design
- [ ] per-task/worktree workspace lifecycle and resource limits
- [ ] prove Docker socket is unavailable
- [ ] hard network denies + destination proxy
- [ ] capability gateway with GitHub task-branch scoped write path
- [ ] secret broker / trusted credential injection
- [ ] destroy/recreate/checkpoint tests

**Exit:** compromised Hand cannot access Brain secrets/host control/LAN metadata or use an approved service outside its granted operation/resource scope.

## M5 — Content Trust + governance UX

- [ ] trust-envelope ingestion for web/tool/repo/subagent outputs
- [ ] taint propagation through transformations/handoffs
- [ ] injection/suspicion hook interface
- [ ] L0–L3 decision records and risk scoring
- [ ] `YES / NO / DEFER / MORE INFO` adapter
- [ ] deny-and-continue/repeated-denial circuit breaker
- [ ] Telegram/mobile notification adapter and compact digest/dashboard

**Exit:** owner operates material decisions with four choices; prompt-injected/tainted content cannot self-authorise capabilities.

## M6 — Semantic/evidence graph + reality anchors

- [x] typed semantic node/edge persistence foundation
- [x] reality-anchor persistence foundation
- [ ] claim/anchor freshness and stale-impact traversal
- [ ] request re-validation work through Hermes when anchors become stale
- [ ] protected acceptance/security/Charter invariants
- [ ] risk-adaptive independent review policy

**Exit:** architecture/requirement change marks affected code/tests/docs/evidence stale and Hermes schedules only the necessary re-validation.

## M7 — Evaluation, learning quarantine and gardening

- [ ] canonical micro-evals for initial priors
- [ ] real-task anchored outcome scoring
- [x] persistent deployment capability-score foundation with uncertainty metadata
- [ ] regression detection/quarantine
- [x] quarantined learning-candidate persistence foundation
- [ ] offline/cross-project promotion workflow
- [ ] recurring documentation/dependency/architecture/security/test gardening tasks

**Exit:** routing/Skills improve from measured outcomes without allowing learned state to weaken Charter/policy/security.

## M8 — Deployment automation

- [ ] Proxmox/local Terraform + Ansible
- [ ] OCI ARM profile with multi-arch/gVisor validation and disposable-state recovery
- [ ] portable local VM
- [ ] client-safe restricted/high-isolation profile
- [ ] wire atomic LiteLLM config publish to controlled restart/roll + health verification
- [ ] encrypted backup + off-host event/state restore drill

**Exit:** same release rebuilds from scratch in at least two profiles and resumes a checkpointed project.

## M9 — Adversarial autonomous acceptance

- [ ] prompt-injection and multi-agent trust-laundering corpus
- [ ] malicious dependency/container-escape assumptions tests
- [ ] Docker-socket/host-control negative tests
- [ ] credential/approved-domain exfiltration tests
- [ ] LAN/metadata/egress bypass tests
- [ ] test/acceptance-weakening detection
- [ ] runaway/repeated-denial/quota-storm/budget-escape tests
- [ ] memory/learning poisoning tests
- [ ] corrupt/replayed capsule/graph recovery
- [ ] L3 capability bypass tests

**Exit:** mandatory controls and recovery drills pass with residual risks documented before unattended autonomous operation is declared ready.
