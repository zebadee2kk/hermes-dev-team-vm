from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest

from forge_controller.assurance import (
    CapabilityScoreRecord,
    DecisionRecord,
    LearningCandidate,
    SemanticEdge,
    SemanticKind,
    SemanticNode,
)
from forge_controller.models import AuthorityLevel, Capability
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.redis_state import RedisStateStore
from forge_controller.repository import AssuranceRepository


@pytest.mark.asyncio
async def test_assurance_records_and_idempotent_events(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'assurance.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.create_project("P1", "assurance")

    requirement = SemanticNode(
        project_id="P1", kind=SemanticKind.REQUIREMENT, label="R1: endpoint responds"
    )
    component = SemanticNode(project_id="P1", kind=SemanticKind.COMPONENT, label="API")
    await repository.upsert_semantic_node(requirement)
    await repository.upsert_semantic_node(component)
    await repository.add_semantic_edge(
        SemanticEdge(
            project_id="P1",
            source_id=requirement.node_id,
            relationship="IMPLEMENTED_BY",
            target_id=component.node_id,
        )
    )

    await repository.save_decision(
        DecisionRecord(
            decision_id="D1",
            project_id="P1",
            question="Use FastAPI?",
            recommendation="yes",
            authority=AuthorityLevel.L1,
        )
    )
    await repository.record_capability_score(
        CapabilityScoreRecord(
            deployment_id="fake/a/free",
            capability=Capability.CODING,
            score=0.8,
            uncertainty=0.5,
        )
    )
    candidate = LearningCandidate(
        project_id="P1",
        lesson_type="architecture_pattern",
        content={"lesson": "prefer the simpler option when outcomes are equivalent"},
    )
    await repository.save_learning_candidate(candidate)
    assert candidate.status.value == "QUARANTINED"

    first = await repository.append_event(
        "test.idempotent", project_id="P1", idempotency_key="request-123"
    )
    second = await repository.append_event(
        "test.idempotent", project_id="P1", idempotency_key="request-123"
    )
    assert first == second
    await engine.dispose()


@pytest.mark.asyncio
async def test_redis_wakes_and_owner_safe_lease() -> None:
    client = fakeredis.aioredis.FakeRedis()
    store = RedisStateStore(client)
    now = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)

    await store.set_task_wake("T2", now + timedelta(minutes=20))
    await store.set_task_wake("T1", now + timedelta(minutes=10))
    assert await store.next_wake() == now + timedelta(minutes=10)
    assert await store.due_tasks(now + timedelta(minutes=11)) == ["T1"]

    assert await store.acquire_lease("scheduler", "worker-a", ttl_seconds=60)
    assert not await store.acquire_lease("scheduler", "worker-b", ttl_seconds=60)
    assert not await store.release_lease("scheduler", "worker-b")
    assert await store.release_lease("scheduler", "worker-a")
    await client.aclose()
