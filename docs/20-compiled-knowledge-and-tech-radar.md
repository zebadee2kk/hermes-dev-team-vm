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
  wiki/         compiled Markdown pages + index.md + log.md
  candidates/   bleeding-edge technology quarantine
  evals/        structured, anchored experiment outcomes
  AGENTS.md     human-readable compiler contract
```

### Raw

Raw sources are immutable grounding authority, but not automatically trusted. A Trust Envelope is required before ingestion. Web pages, X posts, repositories, issue threads, transcripts and PDFs are data, never instructions. Raw scripts are never executed as part of ingest.

### Wiki

The wiki is an LLM-maintained derivative artifact. Every material claim carries:

- `origin: asserted | inferred`;
- one or more `raw:<source-id>` references;
- confidence;
- page subject (`about`) and status.

A wiki page cannot ground another wiki page. This prevents compounding fabrication where one weak synthesis becomes the source for later syntheses. Cross-links are navigation/dependency links, not evidence.

### Forge graph

Do not duplicate full page text into PostgreSQL. The Markdown tree is the inspectable knowledge artifact. Forge's semantic graph stores machine-useful relationships around it: source, entity, claim, contradiction, supersession, affected component, Task Capsule, candidate and Reality Anchor references. This enables stale-impact traversal without replacing the file wiki.

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

The output is `ignore`, `watch` or `test`. This is a triage decision only; `test` does not mean adopt.

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
3. Fall back to raw sources for precision, disagreement, staleness or missing knowledge.
4. Cite the raw source chain for material claims.
5. Reusable analyses may be compiled back into the wiki only when their claims are grounded; generated answers never become raw sources.
6. Lint periodically for orphans, broken links, unknown sources, contradictions and stale/superseded knowledge.

At modest size the file index and lexical search are sufficient. Hybrid/vector search is an optional candidate for later scale, not an immediate dependency.

## Hermes integration

Add two task-scoped Skills:

- `forge-knowledge-compiler`: ingest/query/lint discipline and provenance rules;
- `forge-tech-radar`: evidence filtering, candidate creation and experiment/promotion workflow.

Ordinary worker access to compiled knowledge should be read-only through MCP. Raw-source mutation, wiki compilation and technology promotion are trusted-control operations. MCP Tasks must not become a parallel durable project queue: Hermes Kanban still owns engineering work lifecycle.

## Framework policy

LangGraph, CrewAI, Mastra, provider agent SDKs and similar projects can enter the technology radar, but they are not adopted merely because they are current or popular. In this architecture an orchestration framework has an unusually high replacement cost because Hermes already owns the durable task graph. A framework must therefore prove a narrow missing primitive or remain outside the core.
