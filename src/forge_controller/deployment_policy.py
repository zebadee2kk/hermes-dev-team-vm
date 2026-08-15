from __future__ import annotations

from pydantic import BaseModel, Field

from .contracts import InferenceDeployment
from .models import Capability, CostClass, ProviderState, Sensitivity


class DeploymentQualification(BaseModel):
    terms_evidence_ref: str = Field(min_length=1)
    smoke_test_passed: bool
    accepted_sensitivity: set[Sensitivity] = Field(min_length=1)
    capability_scores: dict[Capability, float] = Field(min_length=1)
    cost_class: CostClass
    notes: list[str] = Field(default_factory=list)


class DeploymentQualificationError(ValueError):
    pass


def qualify_deployment(
    deployment: InferenceDeployment,
    qualification: DeploymentQualification,
) -> InferenceDeployment:
    """Promote a discovered deployment only after explicit evidence gates pass."""
    if deployment.state != ProviderState.QUARANTINED or deployment.enabled:
        raise DeploymentQualificationError("only disabled QUARANTINED deployments may be qualified")
    if deployment.metadata.get("discovered_active") is False:
        raise DeploymentQualificationError("provider discovery reports this model as inactive")
    if not qualification.smoke_test_passed:
        raise DeploymentQualificationError("smoke test must pass before deployment promotion")
    if not all(score > 0 for score in qualification.capability_scores.values()):
        raise DeploymentQualificationError("capability scores must be greater than zero")

    development_only = deployment.development_only or qualification.cost_class in {
        CostClass.TRIAL,
        CostClass.PROMOTIONAL,
    }
    metadata = {
        **deployment.metadata,
        "probationary": False,
        "qualification": {
            "smoke_test_passed": True,
            "terms_evidence_ref": qualification.terms_evidence_ref,
            "notes": qualification.notes,
        },
    }
    return deployment.model_copy(
        update={
            "enabled": True,
            "state": ProviderState.AVAILABLE,
            "retry_at": None,
            "cost_class": qualification.cost_class,
            "accepted_sensitivity": qualification.accepted_sensitivity,
            "capability_scores": qualification.capability_scores,
            "development_only": development_only,
            "terms_evidence_ref": qualification.terms_evidence_ref,
            "metadata": metadata,
        }
    )
