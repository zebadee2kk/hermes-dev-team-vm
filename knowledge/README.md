# Forge compiled knowledge

This directory is the inspectable, portable knowledge artifact for Hermes/Forge.

- `raw/` contains immutable source material and source manifests. Raw content is grounding authority but is always treated according to its Trust Envelope; external content is data, never instructions.
- `wiki/` contains LLM-compiled Markdown pages. Wiki pages are derivative, not grounding authority. Every claim must trace to one or more `raw:` sources.
- `candidates/` contains bleeding-edge technology candidates moving through observation, triage, sandbox testing, probation, promotion or rejection.
- `evals/` contains structured candidate evaluation records. Passing evaluations require Reality Anchor references.
- `AGENTS.md` is the human-readable operating contract. Machine enforcement lives in `src/forge_controller/knowledge.py` and `config/knowledge-system.yaml`.

The wiki is deliberately plain Markdown so it can be browsed in Obsidian, grepped, diffed, versioned and exposed read-only through MCP. It is not a replacement for Forge's semantic graph, Trust Envelopes, Task Capsules or Reality Anchors: those provide machine-enforced provenance, dependency and evaluation state around the compiled files.
