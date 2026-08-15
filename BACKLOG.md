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

- [ ] PostgreSQL models/migrations for Task Capsules, semantic nodes/edges, reality anchors, trust envelopes, decisions, inference deployments, quota observations, capability/outcome scores, learning candidates and events
- [ ] Redis repository for cooldowns/leases/wake coordination
- [ ] append-only audit/event service
- [ ] idempotency keys and optimistic/concurrency protection
- [ ] recovery/replay tests

**Exit:** controller restart preserves assurance, quota, decision and handoff state without duplicating Hermes task lifecycle.

## M2 — Quota Intelligence + Inference Deployments

- [ ] provider discovery/adapter interfaces
- [ ] Groq, OpenRouter, Gemini, SambaNova adapters; generic OpenAI-compatible adapter
- [ ] account/tier/endpoint-specific deployment registry
- [ ] reset-time confidence, health probes and jitter
- [ ] privacy/terms evidence per deployment
- [ ] LiteLLM integration and virtual capability aliases
- [ ] `WAITING_COMPUTE` block/wake contract with Hermes

**Exit:** quota exhaustion swaps inference deployment using the same Task Capsule; all-compatible-compute exhaustion blocks then resumes safely.

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

- [ ] typed semantic/evidence vocabulary
- [ ] claim/anchor persistence and freshness
- [ ] impact/staleness traversal
- [ ] request re-validation work through Hermes when anchors become stale
- [ ] protected acceptance/security/Charter invariants
- [ ] risk-adaptive independent review policy

**Exit:** architecture/requirement change marks affected code/tests/docs/evidence stale and Hermes schedules only the necessary re-validation.

## M7 — Evaluation, learning quarantine and gardening

- [ ] canonical micro-evals for initial priors
- [ ] real-task anchored outcome scoring
- [ ] deployment/runtime capability learning with uncertainty
- [ ] regression detection/quarantine
- [ ] candidate lesson quarantine + offline/cross-project promotion workflow
- [ ] recurring documentation/dependency/architecture/security/test gardening tasks

**Exit:** routing/Skills improve from measured outcomes without allowing learned state to weaken Charter/policy/security.

## M8 — Deployment automation

- [ ] Proxmox/local Terraform + Ansible
- [ ] OCI ARM profile with multi-arch/gVisor validation and disposable-state recovery
- [ ] portable local VM
- [ ] client-safe restricted/high-isolation profile
- [ ] backup + off-host event/state restore drill

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
