from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .knowledge import (
    CandidateEvaluation,
    CandidateSignalInput,
    KnowledgeStore,
    PromotionPolicy,
    TechnologyCandidate,
    WikiPage,
    assess_candidate_signal,
    evaluate_promotion,
)


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

    compile_page = commands.add_parser("compile", help="validate and compile one WikiPage JSON/YAML")
    compile_page.add_argument("--page", required=True)

    commands.add_parser("lint", help="lint the compiled wiki")

    signal = commands.add_parser("signal", help="score a technology candidate evidence packet")
    for name in CandidateSignalInput.model_fields:
        signal.add_argument(f"--{name.replace('_', '-')}", action="store_true")

    promotion = commands.add_parser("promotion-check", help="check candidate promotion eligibility")
    promotion.add_argument("--candidate", required=True)
    promotion.add_argument("--eval-dir", required=True)
    promotion.add_argument("--min-probation-days", type=int, default=14)
    promotion.add_argument("--min-real-workload-passes", type=int, default=2)
    promotion.add_argument("--min-anchor-count", type=int, default=2)

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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = KnowledgeStore(args.root)

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
        page = WikiPage.model_validate(_load_structured(args.page))
        print(store.compile_page(page))
        return 0

    if args.command == "lint":
        report = store.lint()
        _print_json(report.model_dump(mode="json"))
        return 1 if report.broken_links or report.unknown_source_refs else 0

    if args.command == "signal":
        payload = {
            name: bool(getattr(args, name))
            for name in CandidateSignalInput.model_fields
        }
        _print_json(assess_candidate_signal(CandidateSignalInput(**payload)).model_dump(mode="json"))
        return 0

    if args.command == "promotion-check":
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
        decision = evaluate_promotion(
            candidate,
            evaluations,
            policy=policy,
            now=datetime.now(UTC),
        )
        _print_json(decision.model_dump(mode="json"))
        return 0 if decision.eligible else 2

    if args.command == "search":
        _print_json(store.search(args.query, limit=args.limit))
        return 0

    if args.command == "read":
        print(store.read_page(args.slug))
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
