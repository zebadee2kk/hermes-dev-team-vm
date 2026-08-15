from pathlib import Path

import yaml

from forge_controller.contracts import RiskLevel, TaskCapsule, VerificationPlan
from forge_controller.external_runtime import ExternalRuntimeKind, request_from_capsule

ROOT = Path(__file__).parents[1]


def test_external_runtime_request_is_bounded_and_derived_from_capsule() -> None:
    capsule = TaskCapsule(
        capsule_id="C1",
        revision=4,
        project_id="P1",
        task_id="T1",
        objective="Implement the bounded feature",
        acceptance=["unit tests pass", "review anchor exists"],
        constraints={"no_schema_changes": True},
        verification=VerificationPlan(
            risk_level=RiskLevel.MEDIUM,
            required_anchor_types=["test"],
            independent_review=True,
        ),
    )

    request = request_from_capsule(
        capsule,
        runtime=ExternalRuntimeKind.CODEX,
        workspace_path="/work/T1",
        allowed_paths=["/work/T1"],
        capability_grant_refs=["grant://github/task-branch"],
    )

    assert request.task_id == capsule.task_id
    assert request.capsule_id == capsule.capsule_id
    assert request.capsule_revision == 4
    assert request.acceptance == capsule.acceptance
    assert request.allowed_paths == ["/work/T1"]
    assert request.capability_grant_refs == ["grant://github/task-branch"]
    assert request.verification_requirements == ["test", "independent_review"]
    assert request.result_schema == "schemas/worker-result.schema.json"
    dumped = request.model_dump(mode="json")
    assert "api_key" not in dumped
    assert "database_url" not in dumped
    assert "litellm_master_key" not in dumped


def test_all_external_runtime_adapters_remain_disabled_until_native_path_gate() -> None:
    manifest = yaml.safe_load((ROOT / "config/worker-lanes.yaml").read_text())
    assert manifest["external_runtime_adapters"] == {
        "codex": "disabled",
        "claude_code": "disabled",
        "opencode": "disabled",
        "gemini_cli": "disabled",
    }
    assert manifest["rules"]["external_runtime_is_not_project_manager"] is True
    assert manifest["rules"]["require_task_capsule_for_handoff"] is True
