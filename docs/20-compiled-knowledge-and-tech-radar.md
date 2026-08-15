# Compiled knowledge + technology radar

## Purpose

Forge needs to stay current without turning every social-media trend, framework launch or security rumor into architecture churn. The knowledge plane therefore has two jobs:

1. compile curated source material into a persistent, inspectable Markdown wiki that compounds across sessions;
2. keep bleeding-edge technology in quarantine until evidence and real project tests justify promotion.

This is deliberately **not** a new orchestration engine. Hermes Kanban remains the sole durable execution graph. Forge Task Capsules, Trust Envelopes, Reality Anchors and learning quarantine remain the authority for work, provenance and promotion.

## Research basis

Andrej Karpathy's `llm-wiki` idea file (2026-04-04) describes the core pattern used here: immutable raw sources, an LLM-maintained interlinked Markdown wiki, a schema/agent contract, plus ingest/query/lint operations, `index.md`, and append-only `log.md`.

Primary source: `https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f`

MCP's 2026-07-28 release moves the protocol core to stateless request/response, adds header-based routing and cache hints, hardens authorization, formalises extensions, and moves Tasks into an extension. New remote MCP integrations should target that generation rather than building new dependencies on deprecated Roots/Sampling/Logging or legacy HTTP+SSE transport.

Primary source: `https://blog.modelcontextprotocol.io/posts/2026-07-28/`

MCP is housed in the Linux Foundation's Agentic AI Foundation ecosystem. This reinforces the choice to treat MCP as connective infrastructure rather than a model/provider-specific convenience layer.

Primary source: `https://www.linuxfoundation.org/press/agentic-ai-foundation-announces-global-2026-events-program-anchored-by-agntcon-mcpcon-north-america-and-europe`

## Layers

```text
knowledge/
  raw/          immutable, content-addressed sources + manifests
  proposals/    trusted-acquisition output awaiting compile/review
  wiki/         compiled Markdown pages + index.md + log.md
    _meta/       machine-readable projection of structured compiler input
  candidates/   bleeding-edge technology quarantine
  evals/        structured, anchored experiment outcomes
  AGENTS.md     human-readable compiler contract
```

### Raw

Raw sources are immutable grounding authority, but not automatically trusted. A Trust Envelope is required before acquisition. Web pages, social posts, repositories, issue threads, transcripts and PDFs are data, never instructions. Raw scripts are never executed as part of acquisition.

The shared/global brain accepts only `PUBLIC` content. Higher-sensitivity material remains project-scoped and must not be copied into cross-project knowledge.

### Proposals

Acquisition and compilation are separate trust stages:

```text
approved normalized acquisition
  -> Trust Envelope + integrity/project/task/source binding
  -> immutable raw source
  -> proposed | quarantined compile proposal
  -> trusted compiler/reviewer
  -> compiled page
```

`TrustedKnowledgeAcquisition` verifies the request against its Trust Envelope, checks the content hash when present, binds the source URL to `content_ref`, and refuses cross-project or non-public shared-brain ingestion. It records the raw source before creating a proposal. Injection findings or hostile trust classifications force the proposal into `quarantined` state.

A proposal is **not** active knowledge. Acquisition has no authority to compile a page, grant capabilities, edit policy, install a candidate, or promote technology.

### Wiki

The wiki is an LLM-maintained derivative artifact. Every material claim carries:

- `origin: asserted | inferred`;
- one or more `raw:<source-id>` references;
- confidence;
- optional stable `fact_key` for facts that should be compared over time;
- optional explicit `contradicts` / `supersedes` claim references;
- page subject (`about`), status, and optional `review_after` deadline.

A wiki page, sidecar, or proposal cannot ground another wiki claim. This prevents compounding fabrication where one weak synthesis becomes the source for later syntheses. Cross-links are navigation/dependency links, not evidence.

`wiki/_meta/` contains the structured compiler projection used for machine comparison and graph sync. It is deliberately not grounding authority.

### Forge graph

Do not duplicate full page text into PostgreSQL. Markdown remains the inspectable knowledge artifact. The semantic graph stores machine-useful relationships around it:

- `SOURCE`, `WIKI_PAGE`, `CLAIM`, `KNOWLEDGE_PROPOSAL` nodes;
- page `contains` claim;
- claim `derived_from` raw source;
- claim `contradicts` / `supersedes` claim;
- project components/tests/docs that `depend_on`, `implement`, `reference`, `document` or are `verified_by` knowledge claims.

`KnowledgeGraphProjector` mirrors structured pages into this graph. A review-due fact, explicit supersession, or unresolved contradiction becomes a stale root. Staleness then walks **backwards through dependency edges** so artifacts that rely on stale knowledge are invalidated. Reality Anchors whose `claim_ref` becomes stale are marked stale as well.

The projector is fail-closed: later sync does not silently clear stale state. Revalidation must establish fresh evidence.

## Contradiction and supersession semantics

`fact_key` is the stable identity for one comparable fact, for example `mcp.remote.core` or `provider.free_tier.daily_limit`.

If two active claims share a `fact_key` but normalize to different values, the linter/projector treats that as an unresolved contradiction. Both claims can stale dependent work until a trusted compiler resolves the relationship.

A newer claim can explicitly `supersede` an older claim. The old claim becomes stale and is excluded from active same-fact conflict detection; the newer claim is not automatically marked stale merely because its value differs.

This gives the system a durable distinction between:

- **contradiction:** competing claims remain unresolved;
- **supersession:** evidence says the old claim is obsolete;
- **staleness:** a claim/page or something depending on it needs revalidation.

## High-signal intake

`assess_candidate_signal()` ignores likes/follows/reposts. It scores evidence characteristics:

Positive:
- primary source;
- concrete repo/spec/gist/advisory;
- reproducible artifact;
- production evidence;
- measurable results;
- postmortem/failure analysis;
- independent corroboration;
- credible security research/advisory.

Negative:
- rumor only;
- marketing only;
- no concrete artifact.

The output is `ignore`, `watch` or `test`. This is a triage decision only; `test` does not mean adopt. `config/technology-radar-sources.yaml` codifies the source and kill-criteria policy. Social material is discovery-only: the radar should find the underlying primary artifact before scoring it as a test candidate.

## Technology candidate lifecycle

```text
observed
  -> triaged
  -> sandbox_tested
  -> probation
  -> promoted | rejected
```

Prefer primitives, protocols and narrow patterns over frameworks that would replace established tracing, retry, auth, orchestration or sandbox boundaries.

Every testable candidate gets a Hermes Kanban task and Task Capsule. Experiments run through the Sandbox Broker when executable code is involved. Results become `CandidateEvaluation` records and executable Reality Anchors.

Default promotion gates:

- at least 14 days in probation;
- at least two passing real-workload evaluations;
- at least two distinct Reality Anchor references;
- no unresolved failing evaluation;
- documented rollback path;
- no violation of Owner Charter/security invariants.

The thresholds are configuration, not a claim that every technology needs exactly 14 days. Material owner decisions can change policy explicitly; agents cannot silently waive it.

## Query/compounding loop

1. Start at `wiki/index.md` or local wiki search.
2. Read compiled pages first.
3. Run knowledge lint before relying on disputed/time-sensitive areas.
4. Fall back to raw sources for precision, disagreement, staleness or missing knowledge.
5. Cite the raw source chain for material claims.
6. Reusable analyses may be compiled back into the wiki only when their claims are grounded; generated answers never become raw sources.
7. Lint periodically for orphans, broken links, unknown sources, contradictions, superseded claims and review-due pages.
8. Project material claim changes into the semantic graph so downstream impact is visible.

At modest size the file index and lexical search remain sufficient. Hybrid/vector search is an optional candidate for later scale, not an immediate dependency.

## Hermes integration

Two task-scoped Skills carry the process:

- `forge-knowledge-compiler`: acquire/compile/query/lint discipline, structured fact metadata and provenance rules;
- `forge-tech-radar`: evidence filtering, candidate creation and experiment/promotion workflow.

Ordinary worker access to compiled knowledge is read-only through `forge-assurance` MCP: search, read and enhanced lint. Raw-source mutation, trusted acquisition, wiki compilation, semantic stale mutation and technology promotion are control-plane operations and are not worker MCP tools.

MCP Tasks must not become a parallel durable project queue: Hermes Kanban still owns engineering work lifecycle.

## Scheduled maintenance and radar

Hermes cron is used only as a scheduler around the existing Kanban/system-of-work boundary. Cron is opt-in during deployment via `FORGE_ENABLE_KNOWLEDGE_CRON=true`.

Default definitions:

- **daily knowledge lint** — no-agent script; no inference. Clean runs are silent/short. Findings create an idempotent Hermes Kanban repair task rather than mutating the wiki directly;
- **daily knowledge digest** — no-agent script producing compact counts/health;
- **weekly technology radar** — agent job with the radar/compiler Skills. It can report WATCH items and create idempotent research tasks for TEST-tier items with concrete primary artifacts. It may not install, execute, adopt, compile active knowledge, change policy or promote a candidate.

No-agent wrappers are materialized under Hermes' script sandbox and bind the versioned repo/knowledge paths before calling the repo-owned scripts. The weekly radar uses the repo as its workdir and should receive only the research/web and Kanban capabilities it needs.

These job definitions being present in the repository does not mean a deployed host has enabled them. Runtime installation is an explicit deployment action.

## Adversarial invariants

Regression tests cover the most important compiled-knowledge trust boundaries:

- derivative wiki/sidecar/proposal references cannot become claim grounding;
- a worker MCP session has no acquisition/compile/promotion tool;
- tainted/control-like source content cannot rewrite source IDs or approval metadata;
- source URL, project, sensitivity and integrity bindings fail closed;
- injection-suspect content can be retained as raw evidence while its proposal remains quarantined;
- conflicting/superseded facts propagate stale state to semantic dependants and Reality Anchors.

This is a targeted foundation, not a substitute for the broader M9 multi-agent prompt-injection and memory-poisoning corpus.

## Framework policy

LangGraph, CrewAI, Mastra, provider agent SDKs and similar projects can enter the technology radar, but they are not adopted merely because they are current or popular. In this architecture an orchestration framework has an unusually high replacement cost because Hermes already owns the durable task graph. A framework must therefore prove a narrow missing primitive or remain outside the core.
