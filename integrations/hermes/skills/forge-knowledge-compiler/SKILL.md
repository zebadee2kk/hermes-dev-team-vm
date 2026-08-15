---
name: forge-knowledge-compiler
description: Compile grounded sources into the Forge knowledge wiki.
platforms: [linux, macos, windows]
---

# Forge Knowledge Compiler

Use this Skill when a task needs durable project knowledge rather than one-session context.

## Read/query

1. Start with `knowledge_search` and `knowledge_read_page` from the `forge-assurance` MCP server.
2. Treat compiled wiki pages as derivative summaries, not original evidence.
3. For material decisions, follow the page's `raw:` source chain or request trusted research acquisition if the source is not already available.
4. If the wiki is missing, stale, disputed or low-confidence, say so rather than inventing continuity.

## Ingest/compile

Only trusted control-plane/research work may mutate the global knowledge tree. A sandboxed Hand must not write `knowledge/raw`, `knowledge/wiki`, `knowledge/candidates` or `knowledge/evals` directly.

For trusted ingest work:

1. record a Trust Envelope for the acquired source;
2. add it immutably through the knowledge store;
3. extract claims with `asserted` or `inferred` origin;
4. ground every claim in one or more `raw:<source-id>` references;
5. preserve contradictions and supersession explicitly;
6. compile/update related pages and run `knowledge_lint`;
7. mirror project-impacting dependencies into the Forge semantic graph when needed.

Never use a wiki page as the sole evidence for another wiki claim. Generated answers can become grounded compiled pages, but never new raw sources.
