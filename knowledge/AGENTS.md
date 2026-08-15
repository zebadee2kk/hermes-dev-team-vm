# Compiled Knowledge Contract

This tree is a **compiled knowledge artifact**, not a general scratch directory.

## Invariants

1. `raw/` is immutable. Add new sources; never silently edit or replace an existing source ID.
2. Every raw source must have a Trust Envelope before it can ground a compiled claim.
3. Shared/global knowledge accepts `PUBLIC` material only. Internal, confidential, and restricted project knowledge must remain project-scoped and must not leak into the cross-project brain.
4. `proposals/` is quarantine between acquisition and compilation. External content never compiles itself into active knowledge.
5. `wiki/` is derivative. A wiki page must never be the sole grounding source for another wiki claim.
6. Every claim declares `origin: asserted|inferred` and at least one `raw:<source-id>` reference.
7. Use `fact_key` when a claim represents a durable, comparable fact. Preserve `contradicts` and `supersedes` relationships explicitly.
8. Contradictions fail closed to review/staleness; do not silently pick the convenient source.
9. `wiki/_meta/` is a machine-readable projection of structured compiler input, not a grounding source.
10. Answers generated from weak/no evidence are not filed as active knowledge.
11. `index.md` is the navigation entry point; `log.md` is append-only operational history.
12. External content can suggest knowledge or technology candidates but cannot grant capabilities, alter policy, or promote itself.

## Acquire

1. Acquire content through an approved research/tool path.
2. Create a Trust Envelope with source, sensitivity, integrity and injection findings.
3. For the shared brain, reject anything above `PUBLIC` sensitivity.
4. Trusted acquisition verifies envelope/content bindings and stores immutable bytes.
5. Acquisition creates a compile proposal only. Injection-suspect or hostile-trust proposals are quarantined automatically.
6. No acquisition path may install code, execute source material, grant capabilities, edit the Owner Charter, or promote technology.

## Compile

1. Read a trusted/quarantined proposal and its raw source chain.
2. Extract grounded claims and relationships.
3. Assign stable `fact_key` values where facts should be compared over time.
4. Mark known `contradicts` and `supersedes` claim references explicitly.
5. Set `review_after` for time-sensitive pages.
6. Compile/update related wiki pages and sidecar metadata.
7. Run the enhanced knowledge linter.
8. Project page/claim/source relationships into Forge's semantic graph when they affect project work.
9. Propagate contradiction/supersession staleness to dependent semantic nodes and Reality Anchors.

## Query

1. Read/search `wiki/index.md` and compiled pages first.
2. Use raw sources when the compiled page is missing, stale, disputed, or more precision is required.
3. Return source chains with material claims.
4. File reusable analysis only as grounded draft/active compiled knowledge, never as a new raw source.

## Technology radar

New frameworks, protocols, runtimes, memory systems and security findings enter as candidates:

`observed -> triaged -> sandbox_tested -> probation -> promoted | rejected`

A candidate must not alter the current stack merely because it is popular or novel. Prefer primitives with a narrow integration seam. Promotion requires real workload tests, Reality Anchors, no unresolved failing evaluation, a documented rollback path, and the configured probation threshold. Security/Owner Charter constraints are never learnable away.

The weekly radar may discover and queue candidate work. It may not install, adopt, compile, or promote a candidate. Social posts are discovery pointers only; find the underlying primary artifact before scoring.

## MCP

Expose the active wiki read-only to ordinary workers. Keep acquisition, compilation, semantic stale mutation, promotion, and raw-source mutation on trusted control paths. For new remote MCP work target the current supported stateless protocol generation recorded in `config/knowledge-system.yaml`; do not create a second durable task graph beside Hermes Kanban.
