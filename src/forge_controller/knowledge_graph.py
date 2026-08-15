from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from itertools import combinations
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import select

from .assurance import SemanticEdge, SemanticKind, SemanticNode
from .knowledge import WikiPageStatus
from .knowledge_assurance import CompiledKnowledgeAssurance, StructuredWikiClaim, StructuredWikiPage
from .persistence import RealityAnchorRow, SemanticEdgeRow, SemanticNodeRow
from .repository import AssuranceRepository


STALE_PROPAGATION_RELATIONSHIPS = {
    "based_on",
    "contains",
    "depends_on",
    "derived_from",
    "documents",
    "implements",
    "references",
    "verified_by",
}


class KnowledgeGraphSyncReport(BaseModel):
    projected_nodes: int = 0
    projected_edges: int = 0
    stale_external_refs: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    superseded_claims: list[str] = Field(default_factory=list)


class KnowledgeGraphProjector:
    """Projects inspectable compiled metadata into Forge's machine-useful assurance graph."""

    def __init__(
        self,
        assurance: CompiledKnowledgeAssurance,
        repository: AssuranceRepository,
    ) -> None:
        self.assurance = assurance
        self.repository = repository

    async def sync_all(
        self,
        *,
        project_id: str,
        now: datetime | None = None,
    ) -> KnowledgeGraphSyncReport:
        now = now or datetime.now(UTC)
        pages = self.assurance.pages()
        node_count = 0
        edge_count = 0
        claim_index: dict[str, StructuredWikiClaim] = {}
        fact_index: dict[str, list[str]] = {}
        stale_roots: set[str] = set()
        contradictions: set[str] = set()
        superseded: set[str] = set()

        for page in pages:
            nodes, edges = await self._project_page(project_id, page)
            node_count += nodes
            edge_count += edges
            page_ref = f"wiki:{page.slug}"
            if page.status in {WikiPageStatus.REVIEW_DUE, WikiPageStatus.SUPERSEDED}:
                stale_roots.add(page_ref)
            if page.review_after and page.review_after <= now:
                stale_roots.add(page_ref)
            for claim in page.claims:
                claim_ref = f"wiki:{page.slug}#{claim.claim_id}"
                claim_index[claim_ref] = claim
                if claim.fact_key:
                    fact_index.setdefault(claim.fact_key, []).append(claim_ref)

        for claim_ref, claim in claim_index.items():
            for target in claim.supersedes:
                superseded.add(target)
                stale_roots.add(target)
                edge_count += await self._ensure_relation(
                    project_id, claim_ref, "supersedes", target
                )
            for target in claim.contradicts:
                stale_roots.update({claim_ref, target})
                contradictions.add(self._pair_key(claim_ref, target))
                edge_count += await self._ensure_relation(
                    project_id, claim_ref, "contradicts", target
                )

        for fact_key, claim_refs in fact_index.items():
            active_refs = [ref for ref in claim_refs if ref not in superseded]
            values = {
                self._normalize_fact(claim_index[ref].text)
                for ref in active_refs
                if ref in claim_index
            }
            if len(active_refs) <= 1 or len(values) <= 1:
                continue
            stale_roots.update(active_refs)
            for left, right in combinations(sorted(active_refs), 2):
                contradictions.add(f"fact:{fact_key}:{self._pair_key(left, right)}")
                edge_count += await self._ensure_relation(
                    project_id,
                    left,
                    "contradicts",
                    right,
                    metadata={"fact_key": fact_key, "detected": "conflicting_active_values"},
                )

        stale_refs = await self._propagate_stale(project_id, stale_roots)
        await self.repository.append_event(
            "knowledge.graph_synced",
            project_id=project_id,
            payload={
                "projected_nodes": node_count,
                "projected_edges": edge_count,
                "stale_count": len(stale_refs),
                "contradiction_count": len(contradictions),
                "superseded_count": len(superseded),
            },
        )
        return KnowledgeGraphSyncReport(
            projected_nodes=node_count,
            projected_edges=edge_count,
            stale_external_refs=sorted(stale_refs),
            contradictions=sorted(contradictions),
            superseded_claims=sorted(superseded),
        )

    async def _project_page(self, project_id: str, page: StructuredWikiPage) -> tuple[int, int]:
        page_ref = f"wiki:{page.slug}"
        page_id = self._stable_id(project_id, page_ref)
        await self.repository.upsert_semantic_node(
            SemanticNode(
                node_id=page_id,
                project_id=project_id,
                kind=SemanticKind.WIKI_PAGE,
                external_ref=page_ref,
                label=page.title,
                data={
                    "status": page.status.value,
                    "about": page.about,
                    "tags": page.tags,
                    "updated_at": page.updated_at.isoformat(),
                    "review_after": page.review_after.isoformat() if page.review_after else None,
                },
            )
        )
        node_count = 1
        edge_count = 0

        for claim in page.claims:
            claim_ref = f"{page_ref}#{claim.claim_id}"
            claim_id = self._stable_id(project_id, claim_ref)
            await self.repository.upsert_semantic_node(
                SemanticNode(
                    node_id=claim_id,
                    project_id=project_id,
                    kind=SemanticKind.CLAIM,
                    external_ref=claim_ref,
                    label=claim.text[:512],
                    data={
                        "origin": claim.origin.value,
                        "confidence": claim.confidence,
                        "fact_key": claim.fact_key,
                        "source_refs": claim.source_refs,
                    },
                )
            )
            node_count += 1
            edge_count += await self._ensure_edge(
                project_id, page_ref, "contains", claim_ref
            )
            for source_ref in claim.source_refs:
                await self._ensure_source_node(project_id, source_ref)
                edge_count += await self._ensure_edge(
                    project_id, claim_ref, "derived_from", source_ref
                )
        return node_count, edge_count

    async def _ensure_source_node(self, project_id: str, source_ref: str) -> None:
        await self.repository.upsert_semantic_node(
            SemanticNode(
                node_id=self._stable_id(project_id, source_ref),
                project_id=project_id,
                kind=SemanticKind.SOURCE,
                external_ref=source_ref,
                label=source_ref.removeprefix("raw:"),
            )
        )

    async def _ensure_relation(
        self,
        project_id: str,
        source_ref: str,
        relationship: str,
        target_ref: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> int:
        if not await self._external_ref_exists(project_id, source_ref):
            return 0
        if not await self._external_ref_exists(project_id, target_ref):
            return 0
        return await self._ensure_edge(
            project_id,
            source_ref,
            relationship,
            target_ref,
            metadata=metadata,
        )

    async def _ensure_edge(
        self,
        project_id: str,
        source_ref: str,
        relationship: str,
        target_ref: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> int:
        edge_id = self._stable_id(
            project_id, f"edge:{source_ref}:{relationship}:{target_ref}"
        )
        await self.repository.add_semantic_edge(
            SemanticEdge(
                edge_id=edge_id,
                project_id=project_id,
                source_id=self._stable_id(project_id, source_ref),
                relationship=relationship,
                target_id=self._stable_id(project_id, target_ref),
                metadata=metadata or {},
            )
        )
        return 1

    async def _external_ref_exists(self, project_id: str, external_ref: str) -> bool:
        async with self.repository.sessions() as session:
            stmt = select(SemanticNodeRow.node_id).where(
                SemanticNodeRow.project_id == project_id,
                SemanticNodeRow.external_ref == external_ref,
            )
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    async def _propagate_stale(self, project_id: str, root_refs: set[str]) -> set[str]:
        if not root_refs:
            return set()
        stale_ids: set[str] = set()
        stale_refs: set[str] = set()
        queue: deque[str] = deque()

        async with self.repository.sessions.begin() as session:
            roots = (
                await session.execute(
                    select(SemanticNodeRow).where(
                        SemanticNodeRow.project_id == project_id,
                        SemanticNodeRow.external_ref.in_(sorted(root_refs)),
                    )
                )
            ).scalars().all()
            for row in roots:
                queue.append(row.node_id)

            while queue:
                node_id = queue.popleft()
                if node_id in stale_ids:
                    continue
                row = await session.get(SemanticNodeRow, node_id)
                if row is None or row.project_id != project_id:
                    continue
                stale_ids.add(node_id)
                row.stale = True
                if row.external_ref:
                    stale_refs.add(row.external_ref)

                incoming = (
                    await session.execute(
                        select(SemanticEdgeRow).where(
                            SemanticEdgeRow.project_id == project_id,
                            SemanticEdgeRow.target_id == node_id,
                            SemanticEdgeRow.relationship.in_(
                                sorted(STALE_PROPAGATION_RELATIONSHIPS)
                            ),
                        )
                    )
                ).scalars().all()
                for edge in incoming:
                    if edge.source_id not in stale_ids:
                        queue.append(edge.source_id)

            if stale_refs:
                anchors = (
                    await session.execute(
                        select(RealityAnchorRow).where(
                            RealityAnchorRow.project_id == project_id,
                            RealityAnchorRow.claim_ref.in_(sorted(stale_refs)),
                        )
                    )
                ).scalars().all()
                for anchor in anchors:
                    anchor.stale = True

        if stale_refs:
            await self.repository.append_event(
                "knowledge.stale_propagated",
                project_id=project_id,
                payload={"root_refs": sorted(root_refs), "stale_refs": sorted(stale_refs)},
            )
        return stale_refs

    @staticmethod
    def _stable_id(project_id: str, external_ref: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"forge:{project_id}:{external_ref}"))

    @staticmethod
    def _pair_key(left: str, right: str) -> str:
        first, second = sorted((left, right))
        return f"{first}<->{second}"

    @staticmethod
    def _normalize_fact(value: str) -> str:
        return " ".join(value.casefold().split())
