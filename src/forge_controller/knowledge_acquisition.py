from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select

from .assurance import SemanticEdge, SemanticKind, SemanticNode
from .contracts import TrustEnvelope
from .knowledge import KnowledgeError, KnowledgeStore, RawSourceManifest
from .models import Sensitivity
from .persistence import TrustEnvelopeRow
from .repository import AssuranceRepository


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    QUARANTINED = "quarantined"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class CompilationProposalSeed(BaseModel):
    suggested_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9/_-]*$")
    title: str = Field(min_length=1)
    about: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class SourceAcquisitionRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    source_id: str = Field(pattern=r"^[A-Za-z0-9._:-]+$")
    approval_ref: str = Field(min_length=1)
    source_url: str | None = None
    media_type: str = "text/markdown"
    suffix: str = ".md"
    shared_global_knowledge: bool = True
    proposal: CompilationProposalSeed


class CompilationProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    task_id: str | None = None
    source_refs: list[str] = Field(min_length=1)
    suggested_slug: str
    title: str
    about: list[str]
    tags: list[str] = Field(default_factory=list)
    rationale: str
    status: ProposalStatus
    approval_ref: str
    trust_envelope_ref: str
    blocked_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AcquisitionResult(BaseModel):
    source: RawSourceManifest
    proposal: CompilationProposal
    source_node_id: str
    proposal_node_id: str


class TrustedKnowledgeAcquisition:
    """Trusted-control pipeline for external content.

    It can persist immutable raw data and a compilation proposal. It cannot compile an active
    wiki page, grant capabilities, or promote technology. Tainted/injection-suspect content is
    retained as evidence but its proposal is quarantined.
    """

    def __init__(self, store: KnowledgeStore, repository: AssuranceRepository) -> None:
        self.store = store
        self.repository = repository
        self.proposals_dir = store.root / "proposals"
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    async def acquire(
        self,
        request: SourceAcquisitionRequest,
        envelope: TrustEnvelope,
        content: bytes,
    ) -> AcquisitionResult:
        self._validate_request(request, envelope, content)
        await self._record_envelope_idempotently(envelope)

        source = self.store.add_raw_source(
            source_id=request.source_id,
            content=content,
            trust_envelope_ref=envelope.envelope_id,
            suffix=request.suffix,
            media_type=request.media_type,
            source_url=request.source_url,
        )
        proposal = self._make_proposal(request, envelope)
        self._save_proposal(proposal)

        source_node_id = self._stable_id(request.project_id, f"raw:{request.source_id}")
        proposal_ref = f"proposal:{proposal.proposal_id}"
        proposal_node_id = self._stable_id(request.project_id, proposal_ref)
        await self.repository.upsert_semantic_node(
            SemanticNode(
                node_id=source_node_id,
                project_id=request.project_id,
                kind=SemanticKind.SOURCE,
                external_ref=f"raw:{request.source_id}",
                label=request.source_id,
                data={
                    "sha256": source.sha256,
                    "source_url": source.source_url,
                    "trust_envelope_ref": envelope.envelope_id,
                    "approval_ref": request.approval_ref,
                },
            )
        )
        await self.repository.upsert_semantic_node(
            SemanticNode(
                node_id=proposal_node_id,
                project_id=request.project_id,
                kind=SemanticKind.KNOWLEDGE_PROPOSAL,
                external_ref=proposal_ref,
                label=proposal.title,
                data=proposal.model_dump(mode="json"),
                stale=proposal.status == ProposalStatus.QUARANTINED,
            )
        )
        await self.repository.add_semantic_edge(
            SemanticEdge(
                edge_id=self._stable_id(request.project_id, f"{proposal_ref}->raw:{request.source_id}"),
                project_id=request.project_id,
                source_id=proposal_node_id,
                relationship="derived_from",
                target_id=source_node_id,
                metadata={"trust_envelope_ref": envelope.envelope_id},
            )
        )
        await self.repository.append_event(
            "knowledge.source_acquired",
            project_id=request.project_id,
            task_id=request.task_id,
            payload={
                "source_id": request.source_id,
                "sha256": source.sha256,
                "proposal_id": proposal.proposal_id,
                "proposal_status": proposal.status.value,
            },
            idempotency_key=(
                f"knowledge.source_acquired:{request.project_id}:{request.source_id}:{source.sha256}"
            ),
        )
        return AcquisitionResult(
            source=source,
            proposal=proposal,
            source_node_id=source_node_id,
            proposal_node_id=proposal_node_id,
        )

    def _validate_request(
        self,
        request: SourceAcquisitionRequest,
        envelope: TrustEnvelope,
        content: bytes,
    ) -> None:
        if request.project_id != envelope.project_id:
            raise KnowledgeError("acquisition project does not match Trust Envelope")
        if request.task_id and envelope.task_id and request.task_id != envelope.task_id:
            raise KnowledgeError("acquisition task does not match Trust Envelope")
        if request.shared_global_knowledge and envelope.data_sensitivity != Sensitivity.PUBLIC:
            raise KnowledgeError("shared global knowledge accepts PUBLIC content only")

        digest = hashlib.sha256(content).hexdigest()
        if envelope.integrity_hash:
            expected = envelope.integrity_hash.removeprefix("sha256:")
            if expected != digest:
                raise KnowledgeError("Trust Envelope integrity hash does not match source bytes")

    async def _record_envelope_idempotently(self, envelope: TrustEnvelope) -> None:
        async with self.repository.sessions() as session:
            existing = await session.get(TrustEnvelopeRow, envelope.envelope_id)
            if existing is not None:
                if existing.payload != envelope.model_dump(mode="json"):
                    raise KnowledgeError("Trust Envelope id is already bound to different content")
                return
        await self.repository.record_trust_envelope(envelope)

    def _make_proposal(
        self,
        request: SourceAcquisitionRequest,
        envelope: TrustEnvelope,
    ) -> CompilationProposal:
        blocked: list[str] = []
        if envelope.injection_findings:
            blocked.append("prompt-injection findings require trusted review")
        if envelope.trust.casefold() in {"blocked", "malicious", "untrusted"}:
            blocked.append(f"source trust classification is {envelope.trust}")
        status = ProposalStatus.QUARANTINED if blocked else ProposalStatus.PROPOSED
        return CompilationProposal(
            project_id=request.project_id,
            task_id=request.task_id,
            source_refs=[f"raw:{request.source_id}"],
            suggested_slug=request.proposal.suggested_slug,
            title=request.proposal.title,
            about=request.proposal.about,
            tags=request.proposal.tags,
            rationale=request.proposal.rationale,
            status=status,
            approval_ref=request.approval_ref,
            trust_envelope_ref=envelope.envelope_id,
            blocked_reasons=blocked,
        )

    def _save_proposal(self, proposal: CompilationProposal) -> Path:
        path = self.proposals_dir / f"{proposal.proposal_id}.yaml"
        path.write_text(yaml.safe_dump(proposal.model_dump(mode="json"), sort_keys=True))
        return path

    @staticmethod
    def _stable_id(project_id: str, external_ref: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"forge:{project_id}:{external_ref}"))
