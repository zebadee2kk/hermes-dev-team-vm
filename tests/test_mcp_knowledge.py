import pytest

from forge_controller.knowledge import ClaimOrigin, KnowledgeStore, WikiClaim, WikiPage
from forge_controller.mcp_server import knowledge_lint, knowledge_read_page, knowledge_search


@pytest.mark.asyncio
async def test_mcp_exposes_compiled_wiki_without_raw_mutation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "knowledge"
    store = KnowledgeStore(root)
    store.add_raw_source(
        source_id="source-1",
        content=b"MCP stateless protocol source",
        trust_envelope_ref="TE-1",
    )
    store.compile_page(
        WikiPage(
            slug="protocols/mcp",
            title="MCP",
            summary="Agent tool protocol.",
            about=["MCP"],
            claims=[
                WikiClaim(
                    claim_id="C1",
                    text="MCP connects agents to tools and data.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:source-1"],
                )
            ],
        )
    )
    monkeypatch.setenv("FORGE_KNOWLEDGE_ROOT", str(root))

    assert await knowledge_search("agent tool") == ["protocols/mcp"]
    page = await knowledge_read_page("protocols/mcp")
    assert "raw:source-1" in page
    lint = await knowledge_lint()
    assert lint["broken_links"] == []
    assert "protocols/mcp" in lint["orphan_pages"]

    # The MCP surface exposes no raw-source read/write primitive; raw content remains behind
    # the trusted ingestion path and only provenance references appear in compiled pages.
    assert "MCP stateless protocol source" not in page
