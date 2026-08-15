import json

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
