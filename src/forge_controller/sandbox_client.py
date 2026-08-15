from __future__ import annotations

from pathlib import Path

import httpx

from .sandbox import SandboxLaunchRequest, SandboxPlan
from .sandbox_broker import SandboxExecutionResponse


class SandboxBrokerClientError(RuntimeError):
    pass


class SandboxBrokerClient:
    """Controller-side broker client. It never talks to Docker/containerd directly."""

    def __init__(
        self,
        *,
        broker_key: str,
        uds_path: str | Path | None = None,
        base_url: str = "http://sandbox-broker",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not broker_key:
            raise ValueError("sandbox broker key is required")
        self.broker_key = broker_key
        self.uds_path = str(uds_path) if uds_path is not None else None
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def plan(self, request: SandboxLaunchRequest) -> SandboxPlan:
        response = await self._request("/v1/sandboxes/plan", request)
        return SandboxPlan.model_validate(response.json())

    async def run(self, request: SandboxLaunchRequest) -> SandboxExecutionResponse:
        response = await self._request("/v1/sandboxes/run", request)
        return SandboxExecutionResponse.model_validate(response.json())

    async def _request(
        self,
        path: str,
        request: SandboxLaunchRequest,
    ) -> httpx.Response:
        owns_client = self.client is None
        client = self.client
        if client is None:
            transport = (
                httpx.AsyncHTTPTransport(uds=self.uds_path)
                if self.uds_path is not None
                else None
            )
            client = httpx.AsyncClient(
                transport=transport,
                timeout=300,
            )
        try:
            try:
                response = await client.post(
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {self.broker_key}"},
                    json=request.model_dump(mode="json"),
                )
            except httpx.TransportError as exc:
                raise SandboxBrokerClientError("sandbox broker is unreachable") from exc
            if response.is_error:
                detail = response.text[:1000]
                raise SandboxBrokerClientError(
                    f"sandbox broker returned HTTP {response.status_code}: {detail}"
                )
            return response
        finally:
            if owns_client:
                await client.aclose()
