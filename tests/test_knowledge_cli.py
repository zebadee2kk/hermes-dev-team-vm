import json
from pathlib import Path

import yaml

from forge_controller.knowledge_cli import main


def test_signal_cli_scores_reproducible_primary_artifact(tmp_path, capsys) -> None:
    result = main(
        [
            "--root",
            str(tmp_path / "knowledge"),
            "signal",
            "--primary-source",
            "--concrete-artifact",
            "--reproducible",
            "--production-evidence",
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tier"] == "test"


def test_ingest_cli_creates_content_addressed_source_manifest(tmp_path, capsys) -> None:
    source = tmp_path / "source.md"
    source.write_text("primary source")
    root = tmp_path / "knowledge"
    result = main(
        [
            "--root",
            str(root),
            "ingest",
            "--source-id",
            "source-1",
            "--file",
            str(source),
            "--trust-envelope-ref",
            "TE-1",
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == "source-1"
    assert (root / "raw/_manifest/source-1.yaml").exists()


def test_promote_cli_uses_controlled_promotion_gate(tmp_path, capsys) -> None:
    root = tmp_path / "knowledge"
    candidate_path = tmp_path / "candidate.yaml"
    eval_dir = tmp_path / "evals"
    eval_dir.mkdir()
    candidate_path.write_text(
        yaml.safe_dump(
            {
                "candidate_id": "candidate-1",
                "name": "Candidate 1",
                "kind": "primitive",
                "status": "probation",
                "problem": "Test controlled adoption",
                "proposed_value": "Prove evidence gate",
                "evidence_refs": ["raw:primary-docs"],
                "signal_assessment": {
                    "score": 75,
                    "tier": "test",
                    "reasons": ["primary source", "artifact", "reproducible"],
                },
                "integration_seam": "test seam",
                "test_plan": ["real workload A", "real workload B"],
                "acceptance": ["both workloads pass"],
                "probation_started_at": "2026-08-01T00:00:00Z",
                "rollback": "remove candidate adapter",
            }
        )
    )
    for index in (1, 2):
        (eval_dir / f"e{index}.yaml").write_text(
            yaml.safe_dump(
                {
                    "evaluation_id": f"E{index}",
                    "candidate_id": "candidate-1",
                    "task_id": f"T{index}",
                    "outcome": "pass",
                    "real_workload": True,
                    "anchor_refs": [f"RA-{index}"],
                }
            )
        )

    result = main(
        [
            "--root",
            str(root),
            "promote",
            "--candidate",
            str(candidate_path),
            "--eval-dir",
            str(eval_dir),
            "--min-probation-days",
            "0",
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promoted"] is True
    assert payload["candidate"]["status"] == "promoted"
    stored = yaml.safe_load((Path(root) / "candidates/candidate-1.yaml").read_text())
    assert stored["status"] == "promoted"
