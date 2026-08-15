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
- [ ] `WAITING_COMPUTE` block/wake contract with Hermes — durable Forge placement/wake behaviour and structured Model Gateway 503 exist; supported Hermes task-context block/unblock bridge remains M3 work

**Exit:** quota exhaustion swaps inference deployment using the same Task Capsule; all-compatible-compute exhaustion blocks then resumes safely.

**Current status:** M2 now has a complete provider lifecycle foundation: discover -> quarantine -> qualify -> persist -> Forge place -> exact LiteLLM deployment alias. Fake-provider restart-safe failover is covered by CI and four real provider adapters are implemented from current provider contracts. Remaining M2 work is active health probing/evidence automation and one live credentialed end-to-end provider/LiteLLM failover test; Hermes block/unblock integration intentionally remains with M3.

## M3 — Hermes execution integration

- [x] reference Hermes integration/config foundation — compatibility target pinned to the reviewed upstream Hermes release; manifest-driven bootstrap implemented and exercised against a fake Hermes CLI
- [x] stable lane/profile definitions generated from authoritative `config/worker-lanes.yaml`
- [x] task-scoped Skills convention/library foundation — Task Capsule, Reality Anchor, compiled-knowledge and technology-radar process Skills installed per durable lane
- [x] Task Capsule adapter foundation for Kanban start/resume/handoff/review/completion through Skills + narrow Forge MCP checkpoints
- [x] stable Forge Model Gateway — Hermes lanes retain `forge/<capability>` identities while Forge performs policy/quota placement to exact LiteLLM deployment aliases
- [x] Forge MCP/API facade for capsule, evidence, trust/provenance and decision classification; provider selection remains implicit through the Model Gateway
- [x] compiled wiki read-only MCP surface — search/read/lint only; acquisition, compilation, stale mutation and technology promotion remain trusted-control operations
- [x] structured result/anchor ingestion foundation — worker-result schema, Reality Anchor MCP path and bounded external-runtime result contract
- [ ] live Hermes-native staging smoke: raw idea -> Kanban decomposition -> lane dispatch -> capsule checkpoint -> implementation -> Reality Anchor -> review/complete
- [ ] human/compute block-unblock mapping — Forge returns structured `WAITING_COMPUTE`, but the reviewed custom-provider request path exposes no supported dynamic Kanban task id; do not mutate Hermes SQLite behind its back
- [x] external runtime lane interface contract — bounded Task Capsule/workspace/grant/result schema defined
- [ ] implement one external runtime adapter only after Hermes-native staging passes and the M4 Sandbox Broker/capability boundary exists

**Exit:** raw idea -> Hermes decomposition -> durable work -> Task Capsules -> autonomous implementation/verification without a Forge-owned parallel DAG.

**Current status:** M3 integration foundation is implemented without introducing a second execution queue. All durable profile/model configuration comes from one lane manifest, direct Hermes provider fallback is disabled, compiled knowledge is available through a narrow local MCP facade, and external runtime adapters remain disabled by policy. M3 exit is not yet satisfied: it requires a live Hermes staging vertical test and a supported task-context bridge for automatic compute blocking/unblocking.

## M4 — Sandbox Broker + capability gateway

- [x] sandbox manager/planner abstraction foundation with fail-closed normal profile
- [x] gVisor host preflight, x86_64/ARM64-compatible install path, digest-built Hand image and evidence-producing live smoke harness; actual target-host execution proof remains open
- [ ] high-risk stronger isolation adapter design
- [x] per-task workspace/resource-limit policy foundation — one validated workspace mount, read-only root, non-root worker, CPU/RAM/PID/tmpfs limits
- [ ] live proof Docker/containerd sockets and host/LAN metadata are unreachable from a running Hand — compromise probe exists but must run on the deployed target
- [x] hard `network=none` baseline for ordinary autonomous Hands
- [x] first narrow capability-egress implementation for Probation 001 — internal-only Codex Hand network, exact-host CONNECT proxy, dedicated auth volume and Brain-side UDS bridge; no Docker/sudo authority granted to Hermes
- [ ] general capability gateway with subject/service/resource/operation/credential/expiry model and GitHub task-branch scoped write path
- [ ] secret broker / trusted credential injection for general external services
- [x] trusted Sandbox Broker service/API + controller UDS client foundation; execution disabled by default and timeout force-cleanup defined
- [x] Codex probation bridge lifecycle guards — one exact workspace/image/network/auth volume, app-server/preflight command whitelist, bounded frame/elapsed time and force-cleanup on disconnect/error/timeout
- [ ] destroy/recreate/checkpoint live tests

**Exit:** compromised Hand cannot access Brain secrets/host control/LAN metadata or use an approved service outside its granted operation/resource scope.

**Current status:** M4 now has a CI-green normal gVisor Hand boundary plus a deliberately narrow capability-egress implementation sufficient to deploy Probation 001 without giving Hermes Docker or sudo. This is not the generic M4 exit: live compromise evidence, generic capability/secret/GitHub grants, a stronger high-risk backend and destroy/recreate/checkpoint recovery remain open. Do not enable Codex probation workloads until the target VM records the required Reality Anchors.

## M5 — Content Trust + governance UX

- [ ] general trust-envelope ingestion for all web/tool/repo/subagent outputs — compiled-knowledge acquisition now provides the first concrete trusted path
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
- [x] compiled-wiki source/page/claim/contradiction/supersession graph mirroring
- [x] compiled-knowledge reverse-dependency stale-impact traversal + affected Reality Anchor invalidation
- [ ] broader claim/anchor freshness policy outside the compiled-knowledge graph
- [ ] request re-validation work through Hermes when anchors or compiled knowledge become stale
- [ ] protected acceptance/security/Charter invariants
- [ ] risk-adaptive independent review policy

**Exit:** architecture/requirement/knowledge change marks affected code/tests/docs/evidence stale and Hermes schedules only the necessary re-validation.

## M7 — Compiled knowledge, evaluation, learning quarantine and gardening

- [x] Karpathy-style compiled knowledge foundation — immutable content-addressed `raw/`, derivative Markdown `wiki/`, generated index and append-only log
- [x] machine-enforced claim provenance — asserted/inferred origin, `raw:` grounding only and no wiki-to-wiki self-grounding
- [x] deterministic local wiki search + orphan/broken-link/unknown-source lint foundation
- [x] structured fact lifecycle — `fact_key`, explicit contradiction/supersession relations, review deadlines and machine-readable `wiki/_meta/` sidecars
- [x] trusted acquisition pipeline foundation — approved normalized acquisition + Trust Envelope/integrity bindings -> immutable raw source -> proposed/quarantined compile proposal
- [x] shared/global knowledge rejects non-PUBLIC content and cross-project/URL/integrity binding mismatches
- [x] contradiction/supersession/staleness automation linked to semantic graph reverse-impact traversal and Reality Anchors
- [x] evidence-weighted high-signal technology intake filter (`ignore | watch | test`) that ignores social engagement metrics
- [x] technology candidate lifecycle/contracts — observed -> triaged -> sandbox_tested -> probation -> promoted/rejected
- [x] anchored candidate promotion gate — probation, passing real-workload evaluations, Reality Anchors, no unresolved failure and rollback required
- [x] Hermes task-scoped knowledge compiler + technology radar Skills
- [x] Hermes read-only compiled-wiki MCP access; acquisition/raw mutation/compilation/promotion not exposed to ordinary workers
- [x] recurring maintenance/radar configuration — script-only lint + digest and weekly evidence-gated radar through Hermes cron; findings/candidates flow into Hermes Kanban; deployment remains explicit opt-in
- [x] targeted compiled-knowledge trust-boundary/poisoning regression foundation
- [ ] canonical micro-evals for initial priors
- [ ] real-task anchored outcome scoring
- [x] persistent deployment capability-score foundation with uncertainty metadata
- [ ] regression detection/quarantine
- [x] quarantined learning-candidate persistence foundation
- [ ] offline/cross-project promotion workflow
- [ ] run at least one real bleeding-edge technology through the full 14+ day default probation path and record deletion/rollback outcome
- [ ] recurring documentation/dependency/architecture/security/test gardening tasks

**Exit:** project knowledge compounds as a grounded inspectable artifact, while routing/Skills/technology choices improve from measured outcomes without allowing learned or externally sourced state to weaken Charter/policy/security.

**Current status:** the compiled-knowledge assurance slice is implemented in code: trusted acquisition stops at a proposal, fact conflicts/supersession can stale dependent graph nodes and Reality Anchors, and Hermes maintenance/radar jobs are defined with script-only zero-model paths where reasoning is unnecessary. Runtime cron installation is intentionally opt-in and still needs to be enabled on a deployed Hermes host. The largest unproven knowledge-radar item is now a real 14+ day candidate probation/rollback trial; broader evaluation/gardening work remains open.

## M8 — Deployment automation

- [ ] Proxmox/local Terraform + Ansible
- [ ] OCI ARM profile with multi-arch/gVisor validation and disposable-state recovery
- [ ] portable local VM
- [ ] client-safe restricted/high-isolation profile
- [ ] wire atomic LiteLLM config publish to controlled restart/roll + health verification
- [ ] encrypted backup + off-host event/state restore drill

**Exit:** same release rebuilds from scratch in at least two profiles and resumes a checkpointed project.

## M9 — Adversarial autonomous acceptance

- [ ] broad prompt-injection and multi-agent trust-laundering corpus
- [ ] malicious dependency/container-escape assumptions tests
- [ ] Docker-socket/host-control negative tests
- [ ] credential/approved-domain exfiltration tests
- [ ] LAN/metadata/egress bypass tests
- [ ] test/acceptance-weakening detection
- [ ] runaway/repeated-denial/quota-storm/budget-escape tests
- [x] targeted compiled-knowledge poisoning/trust-boundary regression foundation
- [ ] memory/learning poisoning tests
- [ ] corrupt/replayed capsule/graph recovery
- [ ] L3 capability bypass tests

**Exit:** mandatory controls and recovery drills pass with residual risks documented before unattended autonomous operation is declared ready.
