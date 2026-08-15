from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

from .contracts import RealityAnchor, TaskCapsule

mcp = FastMCP(
    "Forge Assurance",
    instructions=(
        "Narrow trusted facade for Hermes workers. Task lifecycle remains in Hermes Kanban; "
        "these tools only checkpoint Task Capsules and record executable Reality Anchors."
    ),
)


class ForgeAssuranceClient:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def checkpoint_capsule(self, capsule: TaskCapsule) -> dict[str, object]:
        response = await self._request(
            "POST",
            "/v1/capsules",
            json=capsule.model_dump(mode="json"),
        )
        return _mapping(response.json())

    async def latest_capsule(self, task_id: str) -> dict[str, object] | None:
        response = await self._request(
            "GET",
            f"/v1/capsules/{quote(task_id, safe='')}",
            allow_not_found=True,
        )
        if response.status_code == 404:
            return None
        return _mapping(response.json())

    async def record_reality_anchor(self, anchor: RealityAnchor) -> dict[str, object]:
        response = await self._request(
            "POST",
            "/v1/anchors",
            json=anchor.model_dump(mode="json"),
        )
        return _mapping(response.json())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=30)
        try:
            response = await client.request(method, f"{self.base_url}{path}", json=json)
            if allow_not_found and response.status_code == 404:
                return response
            response.raise_for_status()
            return response
        finally:
            if owns_client:
                await client.aclose()


def _client() -> ForgeAssuranceClient:
    return ForgeAssuranceClient(os.environ.get("FORGE_INTERNAL_URL", "http://127.0.0.1:8080"))


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("Forge assurance response must be a JSON object")
    return {str(key): item for key, item in value.items()}


@mcp.tool()
async def checkpoint_capsule(capsule: TaskCapsule) -> dict[str, object]:
    """Checkpoint a Task Capsule without changing Hermes task lifecycle."""
    return await _client().checkpoint_capsule(capsule)


@mcp.tool()
async def latest_capsule(task_id: str) -> dict[str, object] | None:
    """Read the latest Task Capsule snapshot for one Hermes task."""
    return await _client().latest_capsule(task_id)


@mcp.tool()
async def record_reality_anchor(anchor: RealityAnchor) -> dict[str, object]:
    """Record independent executable evidence for a task claim."""
    return await _client().record_reality_anchor(anchor)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
