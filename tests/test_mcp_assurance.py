import json

import httpx
import pytest

from forge_controller.contracts import RealityAnchor, TaskCapsule, TrustEnvelope
from forge_controller.mcp_server import ForgeAssuranceClient
from forge_controller.models import DecisionRequest


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
    envelope = TrustEnvelope(
        project_id="P1",
        task_id="T1",
        content_ref="web://example",
        source={"kind": "web", "url": "https://example.invalid"},
        trust="untrusted",
        taint=["external_content"],
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
        client = ForgeAssuranceClient("http://forge.invalid", client=http)
        assert (await client.checkpoint_capsule(capsule))["capsule_id"] == "C1"
        assert (await client.latest_capsule("T1"))["task_id"] == "T1"
        assert (await client.record_reality_anchor(anchor))["type"] == "test"
        assert (await client.record_trust_envelope(envelope))["trust"] == "untrusted"
        assert (await client.classify_decision(decision))["authority"] == "L1"

    assert seen == [
        ("POST", "/v1/capsules"),
        ("GET", "/v1/capsules/T1"),
        ("POST", "/v1/anchors"),
        ("POST", "/v1/trust-envelopes"),
        ("POST", "/v1/decisions/classify"),
    ]


@pytest.mark.asyncio
async def test_latest_capsule_returns_none_on_404() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404, json={"detail": "missing"}))
    ) as http:
        client = ForgeAssuranceClient("http://forge.invalid", client=http)
        assert await client.latest_capsule("missing") is None
