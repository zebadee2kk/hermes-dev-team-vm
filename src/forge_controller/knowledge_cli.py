from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .candidate_promotion import promote_candidate_with_assurance
from .knowledge import (
    CandidateEvaluation,
    CandidateSignalInput,
    KnowledgeError,
    KnowledgeStore,
    PromotionPolicy,
    TechnologyCandidate,
    assess_candidate_signal,
    evaluate_promotion,
)
from .knowledge_assurance import CompiledKnowledgeAssurance, StructuredWikiPage
from .persistence import make_engine, make_session_factory
from .repository import AssuranceRepository


def _add_promotion_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--eval-dir", required=True)
    parser.add_argument("--min-probation-days", type=int, default=14)
    parser.add_argument("--min-real-workload-passes", type=int, default=2)
    parser.add_argument("--min-anchor-count", type=int, default=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-knowledge")
    parser.add_argument("--root", default="knowledge", help="knowledge tree root")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="add one immutable raw source")
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--trust-envelope-ref", required=True)
    ingest.add_argument("--source-url")
    ingest.add_argument("--media-type", default="text/markdown")

    compile_page = commands.add_parser(
        "compile", help="validate and compile one structured WikiPage JSON/YAML"
    )
    compile_page.add_argument("--page", required=True)

    commands.add_parser("lint", help="lint compiled wiki, fact conflicts and staleness")

    signal = commands.add_parser("signal", help="score a technology candidate evidence packet")
    for name in CandidateSignalInput.model_fields:
        signal.add_argument(f"--{name.replace('_', '-')}", action="store_true")

    promotion = commands.add_parser(
        "promotion-check", help="check structural candidate promotion eligibility"
    )
    _add_promotion_arguments(promotion)

    promote = commands.add_parser(
        "promote",
        help="promote only after Forge verifies current Reality Anchors in the assurance database",
    )
    _add_promotion_arguments(promote)
    promote.add_argument("--project-id", required=True)
    promote.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Forge async SQLAlchemy database URL; defaults to DATABASE_URL",
    )

    search = commands.add_parser("search", help="search compiled wiki pages")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    read = commands.add_parser("read", help="read one compiled wiki page")
    read.add_argument("slug")
    return parser


def _load_structured(path: str | Path) -> object:
    file_path = Path(path)
    text = file_path.read_text()
    if file_path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _load_promotion_inputs(
    args: argparse.Namespace,
) -> tuple[TechnologyCandidate, list[CandidateEvaluation], PromotionPolicy]:
    candidate = TechnologyCandidate.model_validate(_load_structured(args.candidate))
    evaluations = [
        CandidateEvaluation.model_validate(_load_structured(path))
        for path in sorted(Path(args.eval_dir).glob("*.yaml"))
    ]
    policy = PromotionPolicy(
        min_probation_days=args.min_probation_days,
        min_real_workload_passes=args.min_real_workload_passes,
        min_anchor_count=args.min_anchor_count,
    )
    return candidate, evaluations, policy


async def _promote_with_database(
    *,
    store: KnowledgeStore,
    database_url: str,
    project_id: str,
    candidate: TechnologyCandidate,
    evaluations: list[CandidateEvaluation],
    policy: PromotionPolicy,
) -> TechnologyCandidate:
    engine = make_engine(database_url)
    try:
        repository = AssuranceRepository(make_session_factory(engine))
        return await promote_candidate_with_assurance(
            store,
            repository,
            candidate,
            evaluations,
            project_id=project_id,
            policy=policy,
        )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = KnowledgeStore(args.root)
    assurance = CompiledKnowledgeAssurance(store)

    if args.command == "ingest":
        file_path = Path(args.file)
        manifest = store.add_raw_source(
            source_id=args.source_id,
            content=file_path.read_bytes(),
            trust_envelope_ref=args.trust_envelope_ref,
            suffix=file_path.suffix or ".bin",
            media_type=args.media_type,
            source_url=args.source_url,
        )
        _print_json(manifest.model_dump(mode="json"))
        return 0

    if args.command == "compile":
        page = StructuredWikiPage.model_validate(_load_structured(args.page))
        print(assurance.compile_page(page))
        return 0

    if args.command == "lint":
        report = assurance.lint()
        _print_json(report.model_dump(mode="json"))
        failures = (
            report.broken_links
            or report.unknown_source_refs
            or report.contradictions
            or report.stale_pages
        )
        return 1 if failures else 0

    if args.command == "signal":
        payload = {name: bool(getattr(args, name)) for name in CandidateSignalInput.model_fields}
        assessment = assess_candidate_signal(CandidateSignalInput(**payload))
        _print_json(assessment.model_dump(mode="json"))
        return 0

    if args.command == "promotion-check":
        candidate, evaluations, policy = _load_promotion_inputs(args)
        decision = evaluate_promotion(
            candidate,
            evaluations,
            policy=policy,
            now=datetime.now(UTC),
        )
        _print_json(decision.model_dump(mode="json"))
        return 0 if decision.eligible else 2

    if args.command == "promote":
        candidate, evaluations, policy = _load_promotion_inputs(args)
        if not args.database_url:
            _print_json(
                {
                    "promoted": False,
                    "reason": "candidate promotion requires --database-url or DATABASE_URL so Reality Anchors can be verified",
                }
            )
            return 2
        try:
            promoted = asyncio.run(
                _promote_with_database(
                    store=store,
                    database_url=args.database_url,
                    project_id=args.project_id,
                    candidate=candidate,
                    evaluations=evaluations,
                    policy=policy,
                )
            )
        except KnowledgeError as exc:
            _print_json({"promoted": False, "reason": str(exc)})
            return 2
        _print_json({"promoted": True, "candidate": promoted.model_dump(mode="json")})
        return 0

    if args.command == "search":
        _print_json(store.search(args.query, limit=args.limit))
        return 0

    if args.command == "read":
        print(store.read_page(args.slug))
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
