# Delivery backlog

The backlog is ordered to create a safe vertical slice early. Each milestone has an exit criterion.

## M0 — Foundation (this commit)

- [x] Architecture and ADR baseline
- [x] Policy/provider/deployment configuration contracts
- [x] Typed quota/routing/decision primitives
- [x] FastAPI control-service skeleton
- [x] Unit tests + CI
- [x] Docker Compose support services

**Exit:** repo can be cloned, tests run, and the design is unambiguous enough for an implementation agent to continue.

## M1 — Persistent control plane

- [ ] SQLAlchemy/asyncpg persistence for projects, nodes, edges, provider observations, decisions and events
- [ ] Alembic migrations
- [ ] Redis repository for short-lived leases/cooldowns
- [ ] append-only audit/event service
- [ ] idempotency keys on state-changing APIs

**Exit:** restart the controller without losing project/quota/decision state.

## M2 — Quota Intelligence

- [ ] provider adapter interface
- [ ] Groq header adapter
- [ ] OpenRouter error/credit adapter
- [ ] Gemini quota/backoff adapter
- [ ] SambaNova adapter
- [ ] generic OpenAI-compatible adapter
- [ ] reset-time confidence and jitter
- [ ] provider health probes
- [ ] `WAITING_COMPUTE` scheduler

**Exit:** a simulated provider exhaustion test automatically routes to a second provider, then sleeps/resumes when all providers are unavailable.

## M3 — Hermes integration

- [ ] install/configure Hermes on reference Ubuntu VM
- [ ] LiteLLM endpoint profile
- [ ] Forge MCP server exposing graph/routing/decision tools
- [ ] Hermes profiles for orchestrator/research/architecture/engineering/review/security/docs
- [ ] Kanban graph-to-task compiler
- [ ] structured task completion metadata contract
- [ ] block/resume mapping for human and compute waits

**Exit:** an idea entered into Hermes becomes a durable Kanban task graph and reaches a working prototype without manual task assignment.

## M4 — Disposable worker sandbox

- [ ] sandbox manager abstraction
- [ ] Docker root-capable worker prototype with non-root host boundary
- [ ] per-project worktree mounts
- [ ] CPU/RAM/PID/time limits
- [ ] outbound proxy-only networking
- [ ] secretless GitHub write path / scoped credential broker
- [ ] destroy/recreate/checkpoint tests

**Exit:** deliberately compromise a worker and demonstrate it cannot read control-plane secrets or bypass egress policy.

## M5 — Human governance

- [ ] persistent decision queue
- [ ] `YES / NO / DEFER / MORE INFO` transitions
- [ ] Telegram delivery adapter
- [ ] compact dashboard
- [ ] decision batching/digest
- [ ] L0/L1/L2/L3 policy tests
- [ ] external communication / production / spend hard gates

**Exit:** owner can operate a project from four-choice mobile decisions only.

## M6 — Graph engineering

- [ ] project graph compiler
- [ ] typed relationship vocabulary
- [ ] impact analysis
- [ ] dynamic node insertion
- [ ] mandatory verification-node policy
- [ ] evidence graph and provenance
- [ ] retrospective learning updates

**Exit:** changing an architectural decision identifies affected requirements, code, tests and documentation and schedules re-validation.

## M7 — Capability learning

- [ ] canonical micro-benchmark suite
- [ ] real-task outcome scoring
- [ ] model capability graph persistence
- [ ] routing weights learned from outcomes with conservative bounds
- [ ] regression detection / quarantine

**Exit:** route selection demonstrably improves from observed project outcomes without bypassing policy.

## M8 — Deployment profiles

- [ ] Proxmox Terraform/Ansible implementation
- [ ] OCI Always Free ARM implementation
- [ ] portable local VM implementation
- [ ] client-safe restricted profile
- [ ] backup/rebuild drill

**Exit:** same release can be rebuilt from scratch in at least two deployment profiles.

## M9 — Adversarial acceptance

- [ ] prompt-injection corpus
- [ ] malicious dependency test
- [ ] secret exfiltration tests
- [ ] egress bypass tests
- [ ] runaway-loop tests
- [ ] quota storm tests
- [ ] budget escape tests
- [ ] corrupt graph/checkpoint recovery

**Exit:** all mandatory controls pass and residual risks are documented before calling the system autonomous.
