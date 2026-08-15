from datetime import UTC, datetime, timedelta

from forge_controller.knowledge import ClaimOrigin, KnowledgeStore
from forge_controller.knowledge_assurance import (
    CompiledKnowledgeAssurance,
    StructuredWikiClaim,
    StructuredWikiPage,
)


def _add_source(store: KnowledgeStore, source_id: str) -> None:
    store.add_raw_source(
        source_id=source_id,
        content=source_id.encode(),
        trust_envelope_ref=f"TE-{source_id}",
    )


def test_structured_compile_writes_sidecar_and_detects_fact_conflict(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    assurance = CompiledKnowledgeAssurance(store)
    _add_source(store, "old-doc")
    _add_source(store, "new-doc")

    assurance.compile_page(
        StructuredWikiPage(
            slug="mcp/old",
            title="Old MCP",
            summary="Older protocol description.",
            about=["MCP"],
            claims=[
                StructuredWikiClaim(
                    claim_id="transport",
                    text="The remote core is session-oriented.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:old-doc"],
                    fact_key="mcp.remote.core",
                )
            ],
        )
    )
    assurance.compile_page(
        StructuredWikiPage(
            slug="mcp/current",
            title="Current MCP",
            summary="Current protocol description.",
            about=["MCP"],
            claims=[
                StructuredWikiClaim(
                    claim_id="transport",
                    text="The remote core is stateless request/response.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:new-doc"],
                    fact_key="mcp.remote.core",
                )
            ],
        )
    )

    assert (store.wiki_dir / "_meta/mcp/current.yaml").exists()
    report = assurance.lint(now=datetime(2026, 8, 15, tzinfo=UTC))
    assert any(item.startswith("fact:mcp.remote.core:") for item in report.contradictions)


def test_supersession_resolves_fact_conflict_and_review_after_marks_stale(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    assurance = CompiledKnowledgeAssurance(store)
    _add_source(store, "old-doc")
    _add_source(store, "new-doc")
    now = datetime(2026, 8, 15, tzinfo=UTC)

    assurance.compile_page(
        StructuredWikiPage(
            slug="protocol/old",
            title="Old",
            summary="Old fact.",
            about=["protocol"],
            review_after=now - timedelta(days=1),
            claims=[
                StructuredWikiClaim(
                    claim_id="mode",
                    text="Mode A",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:old-doc"],
                    fact_key="protocol.mode",
                )
            ],
        )
    )
    assurance.compile_page(
        StructuredWikiPage(
            slug="protocol/current",
            title="Current",
            summary="New fact.",
            about=["protocol"],
            claims=[
                StructuredWikiClaim(
                    claim_id="mode",
                    text="Mode B",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:new-doc"],
                    fact_key="protocol.mode",
                    supersedes=["wiki:protocol/old#mode"],
                )
            ],
        )
    )

    report = assurance.lint(now=now)
    assert "wiki:protocol/old#mode" in report.superseded_claims
    assert "protocol/old" in report.stale_pages
    assert not any(item.startswith("fact:protocol.mode:") for item in report.contradictions)
