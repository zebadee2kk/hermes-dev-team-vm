from datetime import UTC, datetime

from fastapi.testclient import TestClient

from forge_controller.api import create_app
from forge_controller.contracts import InferenceDeployment, TaskCapsule
from forge_controller.models import Capability, CostClass, Sensitivity


def test_durable_api_and_capsule_revision_guard(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    app = create_app(database_url=url, auto_create_schema=True)

    capsule = TaskCapsule(
        capsule_id="C1",
        revision=1,
        project_id="P1",
        task_id="T1",
        objective="build feature",
        acceptance=["test passes"],
    )
    deployment = InferenceDeployment(
        deployment_id="fake/free/model",
        provider="fake",
        model="model",
        tier="free",
        endpoint="https://fake.invalid/v1",
        enabled=True,
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.9},
    )

    with TestClient(app) as client:
        assert client.post("/v1/projects", json={"project_id": "P1", "name": "demo"}).status_code == 200
        assert client.post("/v1/capsules", json=capsule.model_dump(mode="json")).status_code == 200
        # Exact retry is idempotent.
        assert client.post("/v1/capsules", json=capsule.model_dump(mode="json")).status_code == 200

        conflicting = capsule.model_copy(update={"capsule_id": "C2", "objective": "different"})
        response = client.post("/v1/capsules", json=conflicting.model_dump(mode="json"))
        assert response.status_code == 409

        assert client.put("/v1/deployments", json=deployment.model_dump(mode="json")).status_code == 200
        route = client.post("/v1/route", json={"capability": "coding", "sensitivity": "PUBLIC"})
        assert route.status_code == 200
        assert route.json()["id"] == deployment.deployment_id

        observation = {
            "provider": "fake",
            "model": "model",
            "deployment_id": deployment.deployment_id,
            "status_code": 429,
            "headers": {
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "2h",
            },
            "observed_at": datetime(2026, 8, 15, 10, 0, tzinfo=UTC).isoformat(),
        }
        assert (
            client.post(
                f"/v1/deployments/{deployment.deployment_id}/observations", json=observation
            ).status_code
            == 200
        )

    # A new app/controller process over the same DB recovers the durable capsule and deployment state.
    restarted = create_app(database_url=url, auto_create_schema=True)
    with TestClient(restarted) as client:
        restored = client.get("/v1/capsules/T1")
        assert restored.status_code == 200
        assert restored.json()["capsule_id"] == "C1"
        blocked = client.post("/v1/route", json={"capability": "coding", "sensitivity": "PUBLIC"})
        assert blocked.status_code == 503
        assert blocked.json()["detail"]["state"] == "WAITING_COMPUTE"


def test_capsule_keeps_identity_across_monotonic_revisions(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'revisions.db'}"
    app = create_app(database_url=url, auto_create_schema=True)
    first = TaskCapsule(
        capsule_id="C1",
        revision=1,
        project_id="P1",
        task_id="T1",
        kanban_task_id="t_1",
        objective="fix the failing test",
        acceptance=["test passes"],
    )
    second = first.model_copy(update={"revision": 2, "open_questions": ["reviewed?"]})
    skipped = first.model_copy(update={"revision": 4})
    rewritten = second.model_copy(update={"objective": "something else"})

    with TestClient(app) as client:
        assert client.post("/v1/capsules", json=first.model_dump(mode="json")).status_code == 200
        # Same capsule_id, next revision: the normal checkpoint path must succeed.
        assert client.post("/v1/capsules", json=second.model_dump(mode="json")).status_code == 200
        # Exact replay of the latest revision stays idempotent.
        assert client.post("/v1/capsules", json=second.model_dump(mode="json")).status_code == 200
        # Rewriting an existing revision or skipping a revision is still refused.
        assert client.post("/v1/capsules", json=rewritten.model_dump(mode="json")).status_code == 409
        assert client.post("/v1/capsules", json=skipped.model_dump(mode="json")).status_code == 409

        latest = client.get("/v1/capsules/T1")
        assert latest.status_code == 200
        assert latest.json()["capsule_id"] == "C1"
        assert latest.json()["revision"] == 2


def test_capsule_identity_cannot_change_and_historical_replay_is_idempotent(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    app = create_app(database_url=url, auto_create_schema=True)
    first = TaskCapsule(
        capsule_id="C1",
        revision=1,
        project_id="P1",
        task_id="T1",
        objective="fix the failing test",
        acceptance=["test passes"],
    )
    second = first.model_copy(update={"revision": 2})
    renamed = first.model_copy(update={"revision": 2, "capsule_id": "C2"})
    rewritten_history = first.model_copy(update={"objective": "changed later"})

    with TestClient(app) as client:
        assert client.post("/v1/capsules", json=first.model_dump(mode="json")).status_code == 200
        # A later revision must keep the task's capsule identity.
        assert client.post("/v1/capsules", json=renamed.model_dump(mode="json")).status_code == 409
        assert client.post("/v1/capsules", json=second.model_dump(mode="json")).status_code == 200
        # An exact replay of an older revision (retry after timeout) is idempotent...
        assert client.post("/v1/capsules", json=first.model_dump(mode="json")).status_code == 200
        # ...but rewriting history is not.
        response = client.post("/v1/capsules", json=rewritten_history.model_dump(mode="json"))
        assert response.status_code == 409
        latest = client.get("/v1/capsules/T1").json()
        assert (latest["capsule_id"], latest["revision"]) == ("C1", 2)


def test_losing_a_race_to_an_identical_checkpoint_is_idempotent(tmp_path, monkeypatch) -> None:
    """Deterministic race: the pre-insert lookup misses a row another writer just committed."""
    import asyncio

    from forge_controller.persistence import create_schema, make_engine, make_session_factory
    from forge_controller.repository import AssuranceRepository, CapsuleRevisionConflict

    async def scenario():
        engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
        await create_schema(engine)
        repository = AssuranceRepository(make_session_factory(engine))
        first = TaskCapsule(capsule_id="C1", revision=1, project_id="P1", task_id="T1",
                            objective="o", acceptance=["a"])
        second = first.model_copy(update={"revision": 2})
        await repository.save_capsule(first)
        await repository.save_capsule(second)  # the "other writer" wins revision 2

        # The losing transaction read both "recorded?" and "latest" before the winner committed.
        real_recorded = AssuranceRepository._recorded_revision
        real_latest = AssuranceRepository._latest_row
        calls = {"recorded": 0, "latest": 0}

        async def stale_recorded(session, task_id, revision):
            calls["recorded"] += 1
            if calls["recorded"] == 1:
                return None
            return await real_recorded(session, task_id, revision)

        async def stale_latest(session, task_id):
            calls["latest"] += 1
            if calls["latest"] == 1:
                return await real_recorded(session, task_id, 1)  # pre-race latest = revision 1
            return await real_latest(session, task_id)

        monkeypatch.setattr(AssuranceRepository, "_recorded_revision",
                            staticmethod(stale_recorded))
        monkeypatch.setattr(AssuranceRepository, "_latest_row", staticmethod(stale_latest))
        await repository.save_capsule(second)  # identical: the loser must succeed
        calls.update(recorded=0, latest=0)
        conflicting = second.model_copy(update={"objective": "different"})
        try:
            await repository.save_capsule(conflicting)
            outcome = "accepted"
        except CapsuleRevisionConflict:
            outcome = "conflict"
        latest = await repository.latest_capsule("T1")
        await engine.dispose()
        return outcome, latest

    outcome, latest = asyncio.run(scenario())
    assert outcome == "conflict"
    assert (latest.capsule_id, latest.revision, latest.objective) == ("C1", 2, "o")


def test_task_evidence_is_readable(tmp_path, monkeypatch) -> None:
    from forge_controller.contracts import RealityAnchor

    monkeypatch.setenv("FORGE_CONTROL_KEY", "control-key-for-test")
    auth = {"Authorization": "Bearer control-key-for-test"}

    url = f"sqlite+aiosqlite:///{tmp_path / 'evidence.db'}"
    app = create_app(database_url=url, auto_create_schema=True)
    first = TaskCapsule(capsule_id="C1", revision=1, project_id="P1", task_id="T1",
                        objective="o", acceptance=["a"])
    anchors = [
        RealityAnchor(anchor_id=f"A{i}", project_id="P1", task_id="T1", type="TEST_EXECUTION",
                      claim_ref="tests", workspace_revision="a" * 40,
                      observed_at=datetime(2026, 9, 29, 10, i, tzinfo=UTC),
                      result={"passed": i != 0}, executor=f"worker-{i}")
        for i in range(3)
    ]
    other = anchors[0].model_copy(update={"anchor_id": "OTHER", "task_id": "T2"})

    with TestClient(app) as client:
        client.post("/v1/capsules", json=first.model_dump(mode="json"))
        client.post("/v1/capsules", json=first.model_copy(update={"revision": 2}).model_dump(mode="json"))
        for anchor in [anchors[2], anchors[0], anchors[1], other]:
            assert client.post("/v1/anchors", json=anchor.model_dump(mode="json")).status_code == 200

        # Evidence payloads can hold reports and paths: the control credential is required.
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert client.get("/v1/anchors", params={"task_id": "T1"},
                              headers=headers).status_code == 401
            assert client.get("/v1/capsules/T1/history", headers=headers).status_code == 401

        listed = client.get("/v1/anchors", params={"task_id": "T1"}, headers=auth)
        assert listed.status_code == 200
        assert [a["anchor_id"] for a in listed.json()] == ["A0", "A1", "A2"]
        assert [a["result"]["passed"] for a in listed.json()] == [False, True, True]
        assert client.get("/v1/anchors", params={"task_id": "none"}, headers=auth).json() == []
        assert client.get("/v1/anchors", headers=auth).status_code == 422  # task_id required

        history = client.get("/v1/capsules/T1/history", headers=auth)
        assert [c["revision"] for c in history.json()] == [1, 2]
        assert {c["capsule_id"] for c in history.json()} == {"C1"}
        assert client.get("/v1/capsules/none/history", headers=auth).json() == []


def test_evidence_endpoints_refuse_when_no_control_key_is_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FORGE_CONTROL_KEY", raising=False)
    app = create_app(database_url=f"sqlite+aiosqlite:///{tmp_path / 'x.db'}",
                     auto_create_schema=True)
    with TestClient(app) as client:
        assert client.get("/v1/anchors", params={"task_id": "T1"}).status_code == 503
        assert client.get("/v1/capsules/T1/history").status_code == 503
