from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .assurance import (
    CapabilityScoreRecord,
    DecisionRecord,
    LearningCandidate,
    SemanticEdge,
    SemanticNode,
)
from .contracts import InferenceDeployment, RealityAnchor, TaskCapsule, TrustEnvelope
from .models import (
    Availability,
    Capability,
    ModelCandidate,
    QuotaObservation,
    RouteRequest,
    Sensitivity,
)
from .persistence import (
    CapabilityScoreRow,
    DecisionRow,
    EventRow,
    InferenceDeploymentRow,
    LearningCandidateRow,
    ProjectRow,
    QuotaObservationRow,
    RealityAnchorRow,
    SemanticEdgeRow,
    SemanticNodeRow,
    TaskCapsuleRow,
    TrustEnvelopeRow,
    ensure_utc,
    utcnow,
)


class AssuranceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create_project(self, project_id: str, name: str) -> None:
        async with self.sessions.begin() as session:
            if await session.get(ProjectRow, project_id) is None:
                session.add(ProjectRow(project_id=project_id, name=name))

    async def save_capsule(self, capsule: TaskCapsule) -> None:
        async with self.sessions.begin() as session:
            session.add(
                TaskCapsuleRow(
                    capsule_id=capsule.capsule_id,
                    project_id=capsule.project_id,
                    task_id=capsule.task_id,
                    kanban_task_id=(
                        str(capsule.kanban_task_id) if capsule.kanban_task_id is not None else None
                    ),
                    revision=capsule.revision,
                    payload=capsule.model_dump(mode="json"),
                )
            )
            session.add(
                self._event(
                    "capsule.checkpointed",
                    project_id=capsule.project_id,
                    task_id=capsule.task_id,
                    payload={"capsule_id": capsule.capsule_id, "revision": capsule.revision},
                )
            )

    async def latest_capsule(self, task_id: str) -> TaskCapsule | None:
        async with self.sessions() as session:
            stmt = (
                select(TaskCapsuleRow)
                .where(TaskCapsuleRow.task_id == task_id)
                .order_by(TaskCapsuleRow.revision.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return TaskCapsule.model_validate(row.payload) if row else None

    async def upsert_semantic_node(self, node: SemanticNode) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(SemanticNodeRow, node.node_id)
            values = {
                "project_id": node.project_id,
                "kind": node.kind.value,
                "external_ref": node.external_ref,
                "label": node.label,
                "data": node.data,
                "stale": node.stale,
                "updated_at": utcnow(),
            }
            if row is None:
                session.add(SemanticNodeRow(node_id=node.node_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    async def add_semantic_edge(self, edge: SemanticEdge) -> None:
        async with self.sessions.begin() as session:
            if await session.get(SemanticEdgeRow, edge.edge_id) is None:
                session.add(
                    SemanticEdgeRow(
                        edge_id=edge.edge_id,
                        project_id=edge.project_id,
                        source_id=edge.source_id,
                        relationship=edge.relationship,
                        target_id=edge.target_id,
                        metadata_json=edge.metadata,
                    )
                )

    async def record_anchor(self, anchor: RealityAnchor) -> None:
        async with self.sessions.begin() as session:
            session.add(
                RealityAnchorRow(
                    anchor_id=anchor.anchor_id,
                    project_id=anchor.project_id,
                    task_id=anchor.task_id,
                    anchor_type=anchor.type,
                    claim_ref=anchor.claim_ref,
                    payload=anchor.model_dump(mode="json"),
                    observed_at=anchor.observed_at,
                    stale=anchor.stale,
                )
            )
            session.add(
                self._event(
                    "anchor.recorded",
                    project_id=anchor.project_id,
                    task_id=anchor.task_id,
                    payload={"anchor_id": anchor.anchor_id, "type": anchor.type},
                )
            )

    async def record_trust_envelope(self, envelope: TrustEnvelope) -> None:
        async with self.sessions.begin() as session:
            session.add(
                TrustEnvelopeRow(
                    envelope_id=envelope.envelope_id,
                    project_id=envelope.project_id,
                    task_id=envelope.task_id,
                    content_ref=envelope.content_ref,
                    trust=envelope.trust,
                    payload=envelope.model_dump(mode="json"),
                    acquired_at=envelope.acquired_at,
                )
            )

    async def save_decision(self, decision: DecisionRecord) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(DecisionRow, decision.decision_id)
            values = {
                "project_id": decision.project_id,
                "task_id": decision.task_id,
                "authority": decision.authority.value,
                "status": decision.status.value,
                "payload": decision.model_dump(mode="json"),
                "created_at": decision.created_at,
                "resolved_at": decision.resolved_at,
            }
            if row is None:
                session.add(DecisionRow(decision_id=decision.decision_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    async def record_capability_score(self, score: CapabilityScoreRecord) -> None:
        async with self.sessions.begin() as session:
            session.add(
                CapabilityScoreRow(
                    score_id=score.score_id,
                    deployment_id=score.deployment_id,
                    capability=score.capability.value,
                    score=score.score,
                    sample_count=score.sample_count,
                    uncertainty=score.uncertainty,
                    source=score.source,
                    observed_at=score.observed_at,
                    payload=score.model_dump(mode="json"),
                )
            )

    async def save_learning_candidate(self, candidate: LearningCandidate) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(LearningCandidateRow, candidate.candidate_id)
            values = {
                "project_id": candidate.project_id,
                "lesson_type": candidate.lesson_type,
                "status": candidate.status.value,
                "payload": candidate.model_dump(mode="json"),
                "created_at": candidate.created_at,
                "updated_at": candidate.updated_at,
            }
            if row is None:
                session.add(LearningCandidateRow(candidate_id=candidate.candidate_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    async def upsert_deployment(self, deployment: InferenceDeployment) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(InferenceDeploymentRow, deployment.deployment_id)
            values = self._deployment_values(deployment)
            if row is None:
                session.add(InferenceDeploymentRow(deployment_id=deployment.deployment_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    async def list_candidates(self) -> list[ModelCandidate]:
        async with self.sessions() as session:
            rows = (await session.execute(select(InferenceDeploymentRow))).scalars().all()
        return [self._candidate(row) for row in rows]

    async def record_availability(
        self,
        deployment_id: str,
        observation: QuotaObservation,
        availability: Availability,
    ) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(InferenceDeploymentRow, deployment_id)
            if row is None:
                raise KeyError(f"unknown inference deployment: {deployment_id}")
            row.state = availability.state.value
            row.retry_at = availability.retry_at
            row.updated_at = utcnow()
            session.add(
                QuotaObservationRow(
                    deployment_id=deployment_id,
                    observed_at=observation.observed_at,
                    state=availability.state.value,
                    retry_at=availability.retry_at,
                    reason=availability.reason,
                    confidence=availability.confidence,
                    raw=observation.model_dump(mode="json"),
                )
            )
            session.add(
                self._event(
                    "compute.availability_observed",
                    payload={
                        "deployment_id": deployment_id,
                        "state": availability.state.value,
                        "retry_at": (
                            availability.retry_at.isoformat() if availability.retry_at else None
                        ),
                        "confidence": availability.confidence,
                    },
                )
            )

    async def next_retry_at(self, request: RouteRequest, now: datetime) -> datetime | None:
        candidates = await self.list_candidates()
        retry_times: list[datetime] = []
        for candidate in candidates:
            if not candidate.enabled:
                continue
            if request.sensitivity not in candidate.accepted_sensitivity:
                continue
            if candidate.cost_class.value == "paid" and not request.allow_paid:
                continue
            if candidate.capability_scores.get(request.capability, 0) <= 0:
                continue
            retry_at = ensure_utc(candidate.retry_at)
            if retry_at and retry_at > now:
                retry_times.append(retry_at)
        return min(retry_times) if retry_times else None

    async def append_event(
        self,
        event_type: str,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        async with self.sessions.begin() as session:
            if idempotency_key:
                stmt = select(EventRow).where(EventRow.idempotency_key == idempotency_key)
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    return existing.event_id
            event = self._event(
                event_type,
                project_id=project_id,
                task_id=task_id,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            session.add(event)
            return event.event_id

    async def list_events(self) -> list[dict[str, object]]:
        async with self.sessions() as session:
            rows = (await session.execute(select(EventRow).order_by(EventRow.created_at))).scalars().all()
            return [
                {
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "project_id": row.project_id,
                    "task_id": row.task_id,
                    "payload": row.payload,
                }
                for row in rows
            ]

    @staticmethod
    def _event(
        event_type: str,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> EventRow:
        return EventRow(
            event_id=str(uuid4()),
            event_type=event_type,
            project_id=project_id,
            task_id=task_id,
            payload=payload or {},
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _deployment_values(deployment: InferenceDeployment) -> dict[str, object]:
        return {
            "provider": deployment.provider,
            "model": deployment.model,
            "account_ref": deployment.account_ref,
            "tier": deployment.tier,
            "endpoint": deployment.endpoint,
            "credential_binding": deployment.credential_binding,
            "enabled": deployment.enabled,
            "state": deployment.state.value,
            "retry_at": deployment.retry_at,
            "cost_class": deployment.cost_class.value,
            "accepted_sensitivity": [item.value for item in deployment.accepted_sensitivity],
            "capability_scores": {
                key.value: value for key, value in deployment.capability_scores.items()
            },
            "reliability": deployment.reliability,
            "latency_score": deployment.latency_score,
            "development_only": deployment.development_only,
            "terms_evidence_ref": deployment.terms_evidence_ref,
            "metadata_json": deployment.metadata,
            "updated_at": utcnow(),
        }

    @staticmethod
    def _candidate(row: InferenceDeploymentRow) -> ModelCandidate:
        return ModelCandidate(
            id=row.deployment_id,
            provider=row.provider,
            model=row.model,
            enabled=row.enabled,
            state=row.state,
            retry_at=ensure_utc(row.retry_at),
            cost_class=row.cost_class,
            accepted_sensitivity={Sensitivity(item) for item in row.accepted_sensitivity},
            capability_scores={Capability(key): value for key, value in row.capability_scores.items()},
            reliability=row.reliability,
            latency_score=row.latency_score,
        )
