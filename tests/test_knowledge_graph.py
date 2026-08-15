from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import select

from forge_controller.assurance import SemanticEdge, SemanticKind, SemanticNode
from forge_controller.contracts import RealityAnchor
from forge_controller.knowledge import ClaimOrigin, KnowledgeStore
from forge_controller.knowledge_assurance import (
    CompiledKnowledgeAssurance,
    StructuredWikiClaim,
    StructuredWikiPage,
)
from forge_controller.knowledge_graph import KnowledgeGraphProjector
from forge_controller.persistence import (
    RealityAnchorRow,
    SemanticNodeRow,
    create_schema,
    make_engine,
    make_session_factory,
)
from forge_controller.repository import AssuranceRepository


def _stable(project_id: str, external_ref: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"forge:{project_id}:{external_ref}"))


@pytest.mark.asyncio
async def test_fact_conflict_marks_dependants_and_reality_anchors_stale(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'forge.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.create_project("forge", "Forge")
    store = KnowledgeStore(tmp_path / "knowledge")
    assurance = CompiledKnowledgeAssurance(store)
    for source_id in ("old", "new"):
        store.add_raw_source(
            source_id=source_id,
            content=source_id.encode(),
            trust_envelope_ref=f"TE-{source_id}",
        )

    assurance.compile_page(
        StructuredWikiPage(
            slug="protocol/old",
            title="Old protocol",
            summary="Older mode.",
            about=["protocol"],
            claims=[
                StructuredWikiClaim(
                    claim_id="mode",
                    text="The protocol is stateful.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:old"],
                    fact_key="protocol.mode",
                )
            ],
        )
    )
    assurance.compile_page(
        StructuredWikiPage(
            slug="protocol/new",
            title="New protocol",
            summary="Newer mode.",
            about=["protocol"],
            claims=[
                StructuredWikiClaim(
                    claim_id="mode",
                    text="The protocol is stateless.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:new"],
                    fact_key="protocol.mode",
                )
            ],
        )
    )

    projector = KnowledgeGraphProjector(assurance, repository)
    await projector.sync_all(project_id="forge")

    old_claim = "wiki:protocol/old#mode"
    component_ref = "component:gateway"
    component_id = _stable("forge", component_ref)
    await repository.upsert_semantic_node(
        SemanticNode(
            node_id=component_id,
            project_id="forge",
            kind=SemanticKind.COMPONENT,
            external_ref=component_ref,
            label="Gateway",
        )
    )
    await repository.add_semantic_edge(
        SemanticEdge(
            edge_id=_stable("forge", f"edge:{component_ref}:depends_on:{old_claim}"),
            project_id="forge",
            source_id=component_id,
            relationship="depends_on",
            target_id=_stable("forge", old_claim),
        )
    )
    await repository.record_anchor(
        RealityAnchor(
            anchor_id="RA-knowledge",
            project_id="forge",
            task_id="T-1",
            type="test",
            claim_ref=old_claim,
            result={"passed": True},
        )
    )

    report = await projector.sync_all(project_id="forge")
    assert any(item.startswith("fact:protocol.mode:") for item in report.contradictions)
    assert old_claim in report.stale_external_refs
    assert component_ref in report.stale_external_refs

    async with repository.sessions() as session:
        component = (
            await session.execute(
                select(SemanticNodeRow).where(SemanticNodeRow.external_ref == component_ref)
            )
        ).scalar_one()
        anchor = await session.get(RealityAnchorRow, "RA-knowledge")
        assert component.stale is True
        assert anchor is not None and anchor.stale is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_explicit_supersession_stales_old_claim_without_conflicting_new_claim(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'forge.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    store = KnowledgeStore(tmp_path / "knowledge")
    assurance = CompiledKnowledgeAssurance(store)
    for source_id in ("v1", "v2"):
        store.add_raw_source(
            source_id=source_id,
            content=source_id.encode(),
            trust_envelope_ref=f"TE-{source_id}",
        )

    assurance.compile_page(
        StructuredWikiPage(
            slug="tool/v1",
            title="Tool v1",
            summary="Old behavior.",
            about=["tool"],
            claims=[
                StructuredWikiClaim(
                    claim_id="behavior",
                    text="Behavior one.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:v1"],
                    fact_key="tool.behavior",
                )
            ],
        )
    )
    assurance.compile_page(
        StructuredWikiPage(
            slug="tool/v2",
            title="Tool v2",
            summary="New behavior.",
            about=["tool"],
            claims=[
                StructuredWikiClaim(
                    claim_id="behavior",
                    text="Behavior two.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:v2"],
                    fact_key="tool.behavior",
                    supersedes=["wiki:tool/v1#behavior"],
                )
            ],
        )
    )

    report = await KnowledgeGraphProjector(assurance, repository).sync_all(project_id="forge")
    assert "wiki:tool/v1#behavior" in report.superseded_claims
    assert "wiki:tool/v1#behavior" in report.stale_external_refs
    assert "wiki:tool/v2#behavior" not in report.stale_external_refs

    await engine.dispose()
