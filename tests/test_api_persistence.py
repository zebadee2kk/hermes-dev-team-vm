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
