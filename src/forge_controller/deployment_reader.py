from __future__ import annotations

from sqlalchemy import select

from .contracts import InferenceDeployment
from .models import Capability, CostClass, ProviderState, Sensitivity
from .persistence import InferenceDeploymentRow, ensure_utc, make_engine, make_session_factory


async def load_deployments(database_url: str) -> list[InferenceDeployment]:
    """Read full deployment records for trusted control-plane materialization."""
    engine = make_engine(database_url)
    sessions = make_session_factory(engine)
    try:
        async with sessions() as session:
            rows = (
                await session.execute(
                    select(InferenceDeploymentRow).order_by(InferenceDeploymentRow.deployment_id)
                )
            ).scalars().all()
            return [_deployment_from_row(row) for row in rows]
    finally:
        await engine.dispose()


def _deployment_from_row(row: InferenceDeploymentRow) -> InferenceDeployment:
    return InferenceDeployment(
        deployment_id=row.deployment_id,
        provider=row.provider,
        model=row.model,
        account_ref=row.account_ref,
        tier=row.tier,
        endpoint=row.endpoint,
        credential_binding=row.credential_binding,
        enabled=row.enabled,
        state=ProviderState(row.state),
        retry_at=ensure_utc(row.retry_at),
        cost_class=CostClass(row.cost_class),
        accepted_sensitivity={Sensitivity(item) for item in row.accepted_sensitivity},
        capability_scores={Capability(key): value for key, value in row.capability_scores.items()},
        reliability=row.reliability,
        latency_score=row.latency_score,
        development_only=row.development_only,
        terms_evidence_ref=row.terms_evidence_ref,
        metadata=row.metadata_json,
    )
