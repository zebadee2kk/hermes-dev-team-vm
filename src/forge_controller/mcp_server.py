from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote

import httpx
from mcp.server import MCPServer

from .contracts import RealityAnchor, TaskCapsule
from .knowledge import KnowledgeError, KnowledgeStore
from .knowledge_assurance import CompiledKnowledgeAssurance
from .models import DecisionRequest, Sensitivity
from .trust_gateway import SourceDescriptor

mcp = MCPServer(
    "Forge Assurance",
    instructions=(
        "Narrow trusted facade for Hermes workers. Task lifecycle remains in Hermes Kanban; "
        "these tools checkpoint Task Capsules, record evidence/provenance, classify decisions, "
        "and provide read-only access to the compiled knowledge wiki."
    ),
)


class ForgeAssuranceClient:
    def __init__(
        self,
        base_url: str,
        *,
        control_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.control_key = control_key
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

    async def ingest_trust(
        self,
        *,
        project_id: str,
        content_ref: str,
        content: str,
        source: SourceDescriptor,
        task_id: str | None = None,
        sensitivity: Sensitivity = Sensitivity.PUBLIC,
        parent_envelope_ids: list[str] | None = None,
    ) -> dict[str, object]:
        response = await self._request(
            "POST",
            "/v1/governance/trust/ingest",
            json={
                "project_id": project_id,
                "task_id": task_id,
                "content_ref": content_ref,
                "content": content,
                "source": source.model_dump(mode="json", exclude_none=True),
                "sensitivity": sensitivity.value,
                "parent_envelope_ids": parent_envelope_ids or [],
            },
            require_control=True,
        )
        return _mapping(response.json())

    async def classify_decision(self, decision: DecisionRequest) -> dict[str, object]:
        response = await self._request(
            "POST",
            "/v1/decisions/classify",
            json=decision.model_dump(mode="json"),
        )
        return _mapping(response.json())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        allow_not_found: bool = False,
        require_control: bool = False,
    ) -> httpx.Response:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=30)
        headers: dict[str, str] = {}
        if require_control:
            if not self.control_key:
                raise RuntimeError("FORGE_CONTROL_KEY is required for governed trust ingestion")
            headers["Authorization"] = f"Bearer {self.control_key}"
        try:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                headers=headers,
            )
            if allow_not_found and response.status_code == 404:
                return response
            response.raise_for_status()
            return response
        finally:
            if owns_client:
                await client.aclose()


def _client() -> ForgeAssuranceClient:
    return ForgeAssuranceClient(
        os.environ.get("FORGE_INTERNAL_URL", "http://127.0.0.1:8080"),
        control_key=os.environ.get("FORGE_CONTROL_KEY"),
    )


def _knowledge_store() -> KnowledgeStore:
    root = os.environ.get("FORGE_KNOWLEDGE_ROOT")
    if not root:
        raise RuntimeError("FORGE_KNOWLEDGE_ROOT is not configured")
    return KnowledgeStore(root)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Forge assurance response must be a JSON object")
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


@mcp.tool()
async def ingest_trust(
    project_id: str,
    content_ref: str,
    content: str,
    source: SourceDescriptor,
    task_id: str | None = None,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    parent_envelope_ids: list[str] | None = None,
) -> dict[str, object]:
    """Derive provenance, taint and trust for external/subagent content; callers cannot set trust."""
    return await _client().ingest_trust(
        project_id=project_id,
        task_id=task_id,
        content_ref=content_ref,
        content=content,
        source=source,
        sensitivity=sensitivity,
        parent_envelope_ids=parent_envelope_ids,
    )


@mcp.tool()
async def classify_decision(decision: DecisionRequest) -> dict[str, object]:
    """Classify whether a proposed decision is autonomous or needs owner authority."""
    return await _client().classify_decision(decision)


@mcp.tool()
async def knowledge_search(query: str, limit: int = 10) -> list[str]:
    """Search active compiled wiki files. This does not search or execute raw sources."""
    return _knowledge_store().search(query, limit=max(1, min(limit, 25)))


@mcp.tool()
async def knowledge_read_page(slug: str) -> str:
    """Read one compiled wiki page by canonical slug."""
    try:
        return _knowledge_store().read_page(slug)
    except KnowledgeError as exc:
        return f"knowledge page unavailable: {exc}"


@mcp.tool()
async def knowledge_lint() -> dict[str, object]:
    """Report structural, contradiction and staleness findings without modifying knowledge."""
    assurance = CompiledKnowledgeAssurance(_knowledge_store())
    return assurance.lint().model_dump(mode="json")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
