from datetime import UTC, datetime, timedelta

import pytest

from forge_controller.contracts import InferenceDeployment, TaskCapsule, VerificationPlan
from forge_controller.models import (
    Capability,
    CostClass,
    QuotaObservation,
    RouteRequest,
    Sensitivity,
)
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.placement import WaitingForCompute, observe, place
from forge_controller.repository import AssuranceRepository


@pytest.mark.asyncio
async def test_capsule_and_compute_failover_survive_restart(tmp_path) -> None:
    database = tmp_path / "forge.db"
    url = f"sqlite+aiosqlite:///{database}"
    now = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)

    engine = make_engine(url)
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.create_project("P1", "test project")

    capsule = TaskCapsule(
        project_id="P1",
        task_id="T1",
        objective="implement a tested feature",
        acceptance=["feature passes its executable acceptance test"],
        verification=VerificationPlan(required_anchor_types=["TEST_EXECUTION"]),
    )
    await repository.save_capsule(capsule)

    first = InferenceDeployment(
        deployment_id="fake/a/free",
        provider="fake",
        model="a",
        tier="free",
        endpoint="https://fake.invalid/v1",
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.9},
        reliability=0.9,
        latency_score=0.8,
    )
    second = InferenceDeployment(
        deployment_id="fake/b/free",
        provider="fake",
        model="b",
        tier="free",
        endpoint="https://fake.invalid/v1",
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.8},
        reliability=0.8,
        latency_score=0.8,
    )
    await repository.upsert_deployment(first)
    await repository.upsert_deployment(second)

    request = RouteRequest(capability=Capability.CODING)
    assert (await place(repository, request, now=now)).id == first.deployment_id

    await observe(
        repository,
        first.deployment_id,
        QuotaObservation(
            provider="fake",
            model="a",
            deployment_id=first.deployment_id,
            status_code=429,
            headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2h"},
            observed_at=now,
        ),
        now=now,
    )
    assert (await place(repository, request, now=now)).id == second.deployment_id

    await observe(
        repository,
        second.deployment_id,
        QuotaObservation(
            provider="fake",
            model="b",
            deployment_id=second.deployment_id,
            status_code=429,
            headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "1h"},
            observed_at=now,
        ),
        now=now,
    )
    with pytest.raises(WaitingForCompute) as waiting:
        await place(repository, request, now=now)
    assert waiting.value.retry_at == now + timedelta(hours=1)

    await engine.dispose()

    restarted_engine = make_engine(url)
    restarted = AssuranceRepository(make_session_factory(restarted_engine))
    restored_capsule = await restarted.latest_capsule("T1")
    assert restored_capsule is not None
    assert restored_capsule.objective == capsule.objective

    # Re-evaluate the full pool after reset instead of pinning work to the previous deployment.
    later = now + timedelta(hours=1, minutes=1)
    assert (await place(restarted, request, now=later)).id == second.deployment_id

    events = await restarted.list_events()
    assert [event["event_type"] for event in events].count("compute.availability_observed") == 2
    assert any(event["event_type"] == "capsule.checkpointed" for event in events)
    await restarted_engine.dispose()
