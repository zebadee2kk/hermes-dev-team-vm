from __future__ import annotations

from dataclasses import dataclass

import httpx

from .models import Capability, QuotaObservation, RouteRequest, Sensitivity
from .placement import WaitingForCompute, observe, place
from .repository import AssuranceRepository

MODEL_ALIASES: dict[str, Capability] = {
    "forge/fast": Capability.FAST,
    "forge/reasoning": Capability.REASONING,
    "forge/coding": Capability.CODING,
    "forge/review": Capability.REVIEW,
    "forge/research": Capability.RESEARCH,
    "forge/documentation": Capability.DOCUMENTATION,
    "forge/tool-use": Capability.TOOL_USE,
}
_RETRYABLE_UPSTREAM = {429, 502, 503, 504}


class UnknownForgeModel(ValueError):
    pass


class ModelGatewayUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelGatewayResponse:
    status_code: int
    content: bytes
    headers: dict[str, str]
    deployment_id: str


def capability_for_model(model: str) -> Capability:
    try:
        return MODEL_ALIASES[model]
    except KeyError as exc:
        raise UnknownForgeModel(f"unknown Forge model alias: {model!r}") from exc


def model_catalogue() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"id": alias, "object": "model", "owned_by": "forge"}
            for alias in MODEL_ALIASES
        ],
    }


async def forward_chat_completion(
    repository: AssuranceRepository,
    payload: dict[str, object],
    *,
    litellm_base_url: str,
    litellm_master_key: str,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    client: httpx.AsyncClient | None = None,
    max_attempts: int = 2,
) -> ModelGatewayResponse:
    model = payload.get("model")
    if not isinstance(model, str):
        raise UnknownForgeModel("request model must be a Forge model alias string")
    capability = capability_for_model(model)
    route_request = RouteRequest(capability=capability, sensitivity=sensitivity)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=300)
    try:
        for attempt in range(max_attempts):
            candidate = await place(repository, route_request)
            forwarded = {**payload, "model": _litellm_alias(candidate.id)}
            try:
                response = await http.post(
                    f"{litellm_base_url.rstrip('/')}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {litellm_master_key}"},
                    json=forwarded,
                )
            except httpx.TransportError as exc:
                raise ModelGatewayUnavailable("LiteLLM execution gateway is unreachable") from exc

            if response.status_code in _RETRYABLE_UPSTREAM:
                observation = QuotaObservation(
                    provider=candidate.provider,
                    model=candidate.model,
                    deployment_id=candidate.id,
                    status_code=response.status_code,
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
                await observe(repository, candidate.id, observation)
                if attempt + 1 < max_attempts:
                    continue

            return ModelGatewayResponse(
                status_code=response.status_code,
                content=response.content,
                headers={key.lower(): value for key, value in response.headers.items()},
                deployment_id=candidate.id,
            )
    finally:
        if owns_client:
            await http.aclose()

    raise WaitingForCompute(None)


def _litellm_alias(deployment_id: str) -> str:
    return f"forge/deployment/{deployment_id}"
