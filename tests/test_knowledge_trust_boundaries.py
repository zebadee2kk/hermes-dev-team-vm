import hashlib

import pytest
from pydantic import ValidationError

from forge_controller import mcp_server
from forge_controller.contracts import TrustEnvelope
from forge_controller.knowledge import ClaimOrigin, KnowledgeError, KnowledgeStore
from forge_controller.knowledge_acquisition import (
    CompilationProposalSeed,
    ProposalStatus,
    SourceAcquisitionRequest,
    TrustedKnowledgeAcquisition,
)
from forge_controller.knowledge_assurance import StructuredWikiClaim
from forge_controller.models import Sensitivity
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.repository import AssuranceRepository


async def _service(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'forge.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.create_project("forge", "Forge")
    store = KnowledgeStore(tmp_path / "knowledge")
    return engine, TrustedKnowledgeAcquisition(store, repository), store


def _request(**updates) -> SourceAcquisitionRequest:
    request = SourceAcquisitionRequest(
        project_id="forge",
        task_id="T-1",
        source_id="primary-artifact",
        approval_ref="policy:trusted-research",
        source_url="https://primary.example/artifact",
        proposal=CompilationProposalSeed(
            suggested_slug="radar/artifact",
            title="Primary artifact",
            about=["agent technology"],
            rationale="Evidence for a quarantined technology review.",
        ),
    )
    return request.model_copy(update=updates)


def _envelope(content: bytes, **updates) -> TrustEnvelope:
    envelope = TrustEnvelope(
        envelope_id="TE-primary",
        project_id="forge",
        task_id="T-1",
        content_ref="https://primary.example/artifact",
        source={"kind": "web", "authority": "primary"},
        trust="verified",
        data_sensitivity=Sensitivity.PUBLIC,
        integrity_hash="sha256:" + hashlib.sha256(content).hexdigest(),
    )
    return envelope.model_copy(update=updates)


def test_derivative_knowledge_cannot_be_used_as_claim_grounding() -> None:
    for derived_ref in ("wiki:trusted/page", "wiki-meta:trusted/page", "proposal:P-1"):
        with pytest.raises(ValidationError):
            StructuredWikiClaim(
                claim_id="derived",
                text="Derivative material must not become primary grounding.",
                origin=ClaimOrigin.ASSERTED,
                source_refs=[derived_ref],
            )


def test_worker_mcp_does_not_expose_trusted_mutation_operations() -> None:
    assert not hasattr(mcp_server, "knowledge_acquire")
    assert not hasattr(mcp_server, "knowledge_compile")
    assert not hasattr(mcp_server, "knowledge_promote")
    assert not hasattr(mcp_server, "promote_candidate")


@pytest.mark.asyncio
async def test_tainted_content_cannot_rewrite_control_metadata(tmp_path) -> None:
    engine, service, store = await _service(tmp_path)
    content = b"external content containing control-like labels and alternate identifiers"
    envelope = _envelope(
        content,
        trust="untrusted",
        injection_findings=[{"kind": "control_like_content", "confidence": 1.0}],
    )
    try:
        result = await service.acquire(_request(), envelope, content)
        assert result.proposal.status == ProposalStatus.QUARANTINED
        assert result.source.source_id == "primary-artifact"
        assert result.proposal.approval_ref == "policy:trusted-research"
        assert store.source_ids() == ["primary-artifact"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_source_url_must_match_trust_envelope_content_ref(tmp_path) -> None:
    engine, service, store = await _service(tmp_path)
    content = b"primary source"
    envelope = _envelope(content, content_ref="https://different.example/artifact")
    try:
        with pytest.raises(KnowledgeError, match="source URL"):
            await service.acquire(_request(), envelope, content)
        assert store.source_ids() == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_project_envelope_cannot_seed_shared_brain(tmp_path) -> None:
    engine, service, store = await _service(tmp_path)
    content = b"other project evidence"
    envelope = _envelope(content, project_id="other-project")
    try:
        with pytest.raises(KnowledgeError, match="project"):
            await service.acquire(_request(), envelope, content)
        assert store.source_ids() == []
    finally:
        await engine.dispose()
