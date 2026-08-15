import json

import httpx
import pytest

from forge_controller.contracts import RealityAnchor, TaskCapsule
from forge_controller.mcp_server import ForgeAssuranceClient
from forge_controller.models import DecisionRequest
from forge_controller.trust_gateway import SourceDescriptor


@pytest.mark.asyncio
async def test_mcp_facade_only_calls_narrow_assurance_endpoints() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "capsule_id": "C1",
                    "revision": 1,
                    "project_id": "P1",
                    "task_id": "T1",
                    "objective": "Implement feature",
                    "acceptance": ["tests pass"],
                },
            )
        if request.url.path == "/v1/decisions/classify":
            return httpx.Response(
                200,
                json={
                    "authority": "L1",
                    "autonomous": True,
                    "defer_allowed": True,
                    "score": 0.2,
                },
            )
        if request.url.path == "/v1/governance/trust/ingest":
            assert request.headers["authorization"] == "Bearer control-secret"
            payload = json.loads(request.content)
            assert "trust" not in payload
            return httpx.Response(
                200,
                json={
                    "envelope_id": "E1",
                    "project_id": payload["project_id"],
                    "task_id": payload["task_id"],
                    "content_ref": payload["content_ref"],
                    "source": payload["source"],
                    "trust": "untrusted_external",
                    "taint": ["external_content"],
                    "data_sensitivity": payload["sensitivity"],
                    "integrity_hash": "sha256:" + "a" * 64,
                    "injection_findings": [],
                    "parent_refs": [],
                    "acquired_at": "2026-08-15T23:00:00Z",
                },
            )
        return httpx.Response(200, json=json.loads(request.content))

    capsule = TaskCapsule(
        capsule_id="C1",
        project_id="P1",
        task_id="T1",
        objective="Implement feature",
        acceptance=["tests pass"],
    )
    anchor = RealityAnchor(
        project_id="P1",
        task_id="T1",
        type="test",
        claim_ref="acceptance:tests-pass",
        result={"passed": True},
    )
    decision = DecisionRequest(
        id="D1",
        question="Use the existing test fixture?",
        recommendation="YES",
        confidence=0.9,
        materiality=0.1,
        irreversibility=0.1,
        consequence=0.1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ForgeAssuranceClient(
            "http://forge.invalid",
            control_key="control-secret",
            client=http,
        )
        assert (await client.checkpoint_capsule(capsule))["capsule_id"] == "C1"
        assert (await client.latest_capsule("T1"))["task_id"] == "T1"
        assert (await client.record_reality_anchor(anchor))["type"] == "test"
        trust = await client.ingest_trust(
            project_id="P1",
            task_id="T1",
            content_ref="web://example",
            content="external content",
            source=SourceDescriptor(kind="web", url="https://example.invalid"),
        )
        assert trust["trust"] == "untrusted_external"
        assert (await client.classify_decision(decision))["authority"] == "L1"

    assert seen == [
        ("POST", "/v1/capsules"),
        ("GET", "/v1/capsules/T1"),
        ("POST", "/v1/anchors"),
        ("POST", "/v1/governance/trust/ingest"),
        ("POST", "/v1/decisions/classify"),
    ]


@pytest.mark.asyncio
async def test_governed_trust_requires_control_credential() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as http:
        client = ForgeAssuranceClient("http://forge.invalid", client=http)
        with pytest.raises(RuntimeError, match="FORGE_CONTROL_KEY"):
            await client.ingest_trust(
                project_id="P1",
                content_ref="web://example",
                content="external content",
                source=SourceDescriptor(kind="web"),
            )


@pytest.mark.asyncio
async def test_latest_capsule_returns_none_on_404() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404, json={"detail": "missing"}))
    ) as http:
        client = ForgeAssuranceClient("http://forge.invalid", client=http)
        assert await client.latest_capsule("missing") is None
