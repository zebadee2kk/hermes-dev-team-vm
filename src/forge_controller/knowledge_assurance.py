from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import Field, field_validator

from .knowledge import KnowledgeLintReport, KnowledgeStore, WikiClaim, WikiPage, WikiPageStatus


class FactRelation(StrEnum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"


class StructuredWikiClaim(WikiClaim):
    """Wiki claim plus machine-useful fact identity and explicit claim relations."""

    fact_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:/-]+$")
    contradicts: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)

    @field_validator("contradicts", "supersedes")
    @classmethod
    def claim_refs_only(cls, refs: list[str]) -> list[str]:
        for ref in refs:
            if not ref.startswith("wiki:") or "#" not in ref:
                raise ValueError("claim relations must use wiki:<slug>#<claim-id> references")
        return refs


class StructuredWikiPage(WikiPage):
    claims: list[StructuredWikiClaim] = Field(min_length=1)
    review_after: datetime | None = None


class CompiledKnowledgeLintReport(KnowledgeLintReport):
    contradictions: list[str] = Field(default_factory=list)
    stale_pages: list[str] = Field(default_factory=list)
    superseded_claims: list[str] = Field(default_factory=list)


class CompiledKnowledgeAssurance:
    """Adds inspectable machine metadata and lifecycle lint to the Markdown wiki.

    The Markdown page remains the human-readable derivative artifact. The metadata sidecar is
    strictly a projection of the structured compiler input; it never becomes raw grounding.
    """

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self.meta_dir = store.wiki_dir / "_meta"
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def compile_page(self, page: StructuredWikiPage) -> Path:
        path = self.store.compile_page(page)
        meta_path = self.meta_dir / f"{page.slug}.yaml"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(yaml.safe_dump(page.model_dump(mode="json"), sort_keys=True))
        return path

    def read_metadata(self, slug: str) -> StructuredWikiPage:
        path = (self.meta_dir / f"{slug}.yaml").resolve()
        if not path.is_relative_to(self.meta_dir.resolve()) or not path.exists():
            raise FileNotFoundError(f"compiled page metadata not found: {slug}")
        return StructuredWikiPage.model_validate(yaml.safe_load(path.read_text()))

    def pages(self) -> list[StructuredWikiPage]:
        pages: list[StructuredWikiPage] = []
        for path in sorted(self.meta_dir.rglob("*.yaml")):
            pages.append(StructuredWikiPage.model_validate(yaml.safe_load(path.read_text())))
        return pages

    def lint(self, *, now: datetime | None = None) -> CompiledKnowledgeLintReport:
        now = now or datetime.now(UTC)
        base = self.store.lint()
        contradictions: set[str] = set()
        stale_pages: set[str] = set()
        superseded: set[str] = set()
        facts: dict[str, list[tuple[str, StructuredWikiClaim]]] = {}

        for page in self.pages():
            if page.status in {WikiPageStatus.REVIEW_DUE, WikiPageStatus.SUPERSEDED}:
                stale_pages.add(page.slug)
            if page.review_after and page.review_after <= now:
                stale_pages.add(page.slug)
            for claim in page.claims:
                claim_ref = f"wiki:{page.slug}#{claim.claim_id}"
                if claim.fact_key:
                    facts.setdefault(claim.fact_key, []).append((claim_ref, claim))
                for target in claim.contradicts:
                    contradictions.add(self._relation_key(claim_ref, target))
                for target in claim.supersedes:
                    superseded.add(target)

        for fact_key, entries in facts.items():
            active = [(ref, claim) for ref, claim in entries if ref not in superseded]
            normalized = {self._normalize_fact(claim.text) for _, claim in active}
            if len(active) > 1 and len(normalized) > 1:
                refs = ",".join(sorted(ref for ref, _ in active))
                contradictions.add(f"fact:{fact_key}:{refs}")

        return CompiledKnowledgeLintReport(
            orphan_pages=base.orphan_pages,
            broken_links=base.broken_links,
            unknown_source_refs=base.unknown_source_refs,
            contradictions=sorted(contradictions),
            stale_pages=sorted(stale_pages),
            superseded_claims=sorted(superseded),
        )

    @staticmethod
    def _relation_key(left: str, right: str) -> str:
        first, second = sorted((left, right))
        return f"explicit:{first}<->{second}"

    @staticmethod
    def _normalize_fact(value: str) -> str:
        return " ".join(value.casefold().split())
