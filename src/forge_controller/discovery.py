from __future__ import annotations

from .contracts import InferenceDeployment
from .models import CostClass, ProviderState, Sensitivity
from .providers.base import DiscoveredModel


def probationary_deployment(
    model: DiscoveredModel,
    *,
    account_ref: str,
    tier: str,
    endpoint: str,
    cost_class: CostClass,
    accepted_sensitivity: set[Sensitivity] | None = None,
) -> InferenceDeployment:
    """Convert provider discovery into a disabled deployment pending policy/evaluation."""
    return InferenceDeployment(
        deployment_id=f"{model.provider}/{account_ref}/{model.model_id}",
        provider=model.provider,
        model=model.model_id,
        account_ref=account_ref,
        tier=tier,
        endpoint=endpoint,
        credential_binding=f"provider:{model.provider}:{account_ref}",
        enabled=False,
        state=ProviderState.QUARANTINED,
        cost_class=cost_class,
        accepted_sensitivity=accepted_sensitivity or {Sensitivity.PUBLIC},
        capability_scores={},
        metadata={
            **model.metadata,
            "discovered_active": model.active,
            "context_window": model.context_window,
            "max_completion_tokens": model.max_completion_tokens,
            "owned_by": model.owned_by,
            "probationary": True,
            "requires": ["terms_classification", "smoke_test", "capability_evaluation"],
        },
    )
