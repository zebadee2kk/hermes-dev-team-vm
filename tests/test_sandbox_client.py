import httpx
import pytest

from forge_controller.sandbox import SandboxLaunchRequest
from forge_controller.sandbox_client import SandboxBrokerClient, SandboxBrokerClientError

DIGEST = "sha256:" + "d" * 64
IMAGE = f"ghcr.io/example/forge-worker@{DIGEST}"


def request() -> SandboxLaunchRequest:
    return SandboxLaunchRequest(
        request_id="12345678-1234-5678-1234-567812345678",
        project_id="P1",
        task_id="T1",
        image=IMAGE,
        command=["true"],
        workspace_path="/workspaces/P1/T1",
    )


@pytest.mark.asyncio
async def test_client_sends_only_broker_protocol_and_bearer_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(incoming: httpx.Request) -> httpx.Response:
        seen.append(incoming)
        assert incoming.url.path == "/v1/sandboxes/plan"
        assert incoming.headers["Authorization"] == "Bearer broker-secret"
        payload = __import__("json").loads(incoming.content)
        assert "docker_socket" not in payload
        assert "runtime_socket" not in payload
        return httpx.Response(
            200,
            json={
                "request_id": payload["request_id"],
                "runtime": "runsc",
                "image": payload["image"],
                "command": payload["command"],
                "container_name": "forge-t1-123456781234",
                "workspace_source": payload["workspace_path"],
                "workspace_destination": "/workspace",
                "user": "65532:65532",
                "network_mode": "none",
                "read_only_rootfs": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=512m,mode=1777"},
                "limits": payload["limits"],
                "environment": {},
                "capability_grant_refs": [],
                "secret_refs": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SandboxBrokerClient(broker_key="broker-secret", client=http)
        plan = await client.plan(request())

    assert plan.network_mode == "none"
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_client_fails_closed_on_broker_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda incoming: httpx.Response(403, json={"detail": "workspace escapes root"})
        )
    ) as http:
        client = SandboxBrokerClient(broker_key="broker-secret", client=http)
        with pytest.raises(SandboxBrokerClientError, match="HTTP 403"):
            await client.plan(request())


def test_client_requires_broker_key() -> None:
    with pytest.raises(ValueError):
        SandboxBrokerClient(broker_key="")
