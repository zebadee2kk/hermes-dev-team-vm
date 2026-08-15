from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class KnowledgeError(RuntimeError):
    pass


class ClaimOrigin(StrEnum):
    ASSERTED = "asserted"
    INFERRED = "inferred"


class WikiPageStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    REVIEW_DUE = "review_due"
    SUPERSEDED = "superseded"


class CandidateKind(StrEnum):
    PRIMITIVE = "primitive"
    PROTOCOL = "protocol"
    PATTERN = "pattern"
    FRAMEWORK = "framework"
    WRAPPER = "wrapper"
    SECURITY_SIGNAL = "security_signal"


class CandidateStatus(StrEnum):
    OBSERVED = "observed"
    TRIAGED = "triaged"
    SANDBOX_TESTED = "sandbox_tested"
    PROBATION = "probation"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class EvaluationOutcome(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class SignalTier(StrEnum):
    IGNORE = "ignore"
    WATCH = "watch"
    TEST = "test"


class CandidateSignalInput(BaseModel):
    primary_source: bool = False
    concrete_artifact: bool = False
    reproducible: bool = False
    production_evidence: bool = False
    measurable_results: bool = False
    postmortem_or_failure_analysis: bool = False
    independent_corroboration: bool = False
    security_advisory_or_research: bool = False
    rumor_only: bool = False
    marketing_only: bool = False


class CandidateSignalAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    tier: SignalTier
    reasons: list[str]


def assess_candidate_signal(signals: CandidateSignalInput) -> CandidateSignalAssessment:
    """Evidence-weighted triage that intentionally ignores social engagement metrics."""

    score = 0
    reasons: list[str] = []
    positive = [
        (signals.primary_source, 20, "primary source"),
        (signals.concrete_artifact, 20, "concrete artifact"),
        (signals.reproducible, 15, "reproducible"),
        (signals.production_evidence, 20, "production evidence"),
        (signals.measurable_results, 10, "measurable results"),
        (signals.postmortem_or_failure_analysis, 10, "postmortem/failure analysis"),
        (signals.independent_corroboration, 10, "independent corroboration"),
        (signals.security_advisory_or_research, 10, "security research/advisory"),
    ]
    for present, points, reason in positive:
        if present:
            score += points
            reasons.append(f"+{points} {reason}")
    if signals.rumor_only:
        score -= 50
        reasons.append("-50 rumor only")
    if signals.marketing_only:
        score -= 30
        reasons.append("-30 marketing only")
    if not signals.concrete_artifact:
        score -= 15
        reasons.append("-15 no concrete artifact")
    score = max(0, min(100, score))
    tier = SignalTier.TEST if score >= 70 else SignalTier.WATCH if score >= 40 else SignalTier.IGNORE
    return CandidateSignalAssessment(score=score, tier=tier, reasons=reasons)


class RawSourceManifest(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9._:-]+$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    relative_path: str
    media_type: str = "text/markdown"
    source_url: str | None = None
    trust_envelope_ref: str
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WikiClaim(BaseModel):
    claim_id: str = Field(pattern=r"^[A-Za-z0-9._:-]+$")
    text: str = Field(min_length=1)
    origin: ClaimOrigin
    source_refs: list[str] = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("source_refs")
    @classmethod
    def raw_sources_only(cls, refs: list[str]) -> list[str]:
        if any(not ref.startswith("raw:") for ref in refs):
            raise ValueError("wiki claims may only be grounded by raw: source references")
        return refs


class WikiPage(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9/_-]*$")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    about: list[str] = Field(min_length=1)
    status: WikiPageStatus = WikiPageStatus.DRAFT
    claims: list[WikiClaim] = Field(min_length=1)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("links")
    @classmethod
    def links_are_slugs(cls, links: list[str]) -> list[str]:
        pattern = re.compile(r"^[a-z0-9][a-z0-9/_-]*$")
        if any(not pattern.fullmatch(link) for link in links):
            raise ValueError("wiki links must be canonical page slugs")
        return links


class CandidateEvaluation(BaseModel):
    evaluation_id: str
    candidate_id: str
    task_id: str
    outcome: EvaluationOutcome
    real_workload: bool = False
    anchor_refs: list[str] = Field(default_factory=list)
    notes: str = ""
    cost: dict[str, object] = Field(default_factory=dict)
    latency: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def passing_results_need_evidence(self) -> CandidateEvaluation:
        if self.outcome == EvaluationOutcome.PASS and not self.anchor_refs:
            raise ValueError("passing candidate evaluations require Reality Anchor references")
        return self


class TechnologyCandidate(BaseModel):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str
    kind: CandidateKind
    status: CandidateStatus = CandidateStatus.OBSERVED
    problem: str
    proposed_value: str
    evidence_refs: list[str] = Field(min_length=1)
    signal_assessment: CandidateSignalAssessment | None = None
    replacement_scope: list[str] = Field(default_factory=list)
    integration_seam: str
    test_plan: list[str] = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    probation_started_at: datetime | None = None
    promoted_at: datetime | None = None
    rollback: str | None = None


class PromotionPolicy(BaseModel):
    min_probation_days: int = Field(default=14, ge=0)
    min_real_workload_passes: int = Field(default=2, ge=1)
    min_anchor_count: int = Field(default=2, ge=1)


class PromotionDecision(BaseModel):
    eligible: bool
    reasons: list[str]


def evaluate_promotion(
    candidate: TechnologyCandidate,
    evaluations: Iterable[CandidateEvaluation],
    *,
    policy: PromotionPolicy | None = None,
    now: datetime | None = None,
) -> PromotionDecision:
    policy = policy or PromotionPolicy()
    now = now or datetime.now(UTC)
    reasons: list[str] = []
    if candidate.status != CandidateStatus.PROBATION:
        reasons.append("candidate is not in probation")
    if candidate.signal_assessment and candidate.signal_assessment.tier != SignalTier.TEST:
        reasons.append("candidate did not pass high-signal intake triage")
    if candidate.probation_started_at is None:
        reasons.append("probation start is not recorded")
    elif now - candidate.probation_started_at < timedelta(days=policy.min_probation_days):
        reasons.append("minimum probation period has not elapsed")

    candidate_evals = [item for item in evaluations if item.candidate_id == candidate.candidate_id]
    real_passes = [
        item
        for item in candidate_evals
        if item.real_workload and item.outcome == EvaluationOutcome.PASS
    ]
    if len(real_passes) < policy.min_real_workload_passes:
        reasons.append("insufficient passing real-workload evaluations")
    anchor_count = len({ref for item in real_passes for ref in item.anchor_refs})
    if anchor_count < policy.min_anchor_count:
        reasons.append("insufficient independent Reality Anchor evidence")
    if any(item.outcome == EvaluationOutcome.FAIL for item in candidate_evals):
        reasons.append("candidate has unresolved failing evaluations")
    if not candidate.rollback:
        reasons.append("rollback path is not documented")
    return PromotionDecision(eligible=not reasons, reasons=reasons)


class KnowledgeLintReport(BaseModel):
    orphan_pages: list[str] = Field(default_factory=list)
    broken_links: list[str] = Field(default_factory=list)
    unknown_source_refs: list[str] = Field(default_factory=list)


class KnowledgeStore:
    """Plain-file compiled knowledge store with immutable raw sources.

    Markdown is the human-inspectable compiled artifact. Raw source manifests are append-only
    and every claim in an active page must resolve to one of those manifests.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.manifest_dir = self.raw_dir / "_manifest"
        self.wiki_dir = self.root / "wiki"
        self.candidates_dir = self.root / "candidates"
        self.evals_dir = self.root / "evals"
        for path in (self.manifest_dir, self.wiki_dir, self.candidates_dir, self.evals_dir):
            path.mkdir(parents=True, exist_ok=True)

    def add_raw_source(
        self,
        *,
        source_id: str,
        content: bytes,
        trust_envelope_ref: str,
        suffix: str = ".md",
        media_type: str = "text/markdown",
        source_url: str | None = None,
    ) -> RawSourceManifest:
        digest = hashlib.sha256(content).hexdigest()
        safe_suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9._-]+", suffix) else ".bin"
        relative = Path(digest[:2]) / f"{digest}{safe_suffix}"
        data_path = self.raw_dir / relative
        manifest_path = self.manifest_dir / f"{source_id}.yaml"
        if manifest_path.exists():
            existing = RawSourceManifest.model_validate(yaml.safe_load(manifest_path.read_text()))
            if existing.sha256 != digest:
                raise KnowledgeError("raw source ids are immutable and cannot be repointed")
            return existing
        data_path.parent.mkdir(parents=True, exist_ok=True)
        if not data_path.exists():
            data_path.write_bytes(content)
        manifest = RawSourceManifest(
            source_id=source_id,
            sha256=digest,
            relative_path=str(relative),
            media_type=media_type,
            source_url=source_url,
            trust_envelope_ref=trust_envelope_ref,
        )
        manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=True))
        return manifest

    def compile_page(self, page: WikiPage) -> Path:
        unknown = sorted(set(self._page_source_ids(page)) - set(self.source_ids()))
        if unknown:
            raise KnowledgeError(f"wiki page references unknown raw sources: {', '.join(unknown)}")
        destination = self.wiki_dir / f"{page.slug}.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "title": page.title,
            "status": page.status.value,
            "about": page.about,
            "tags": page.tags,
            "updated_at": page.updated_at.isoformat(),
            "derived_from": sorted({ref for claim in page.claims for ref in claim.source_refs}),
        }
        lines = [
            "---",
            yaml.safe_dump(frontmatter, sort_keys=True).strip(),
            "---",
            "",
            f"# {page.title}",
            "",
            page.summary,
            "",
        ]
        for claim in page.claims:
            refs = ", ".join(claim.source_refs)
            lines.extend(
                [
                    f"## Claim: {claim.claim_id}",
                    "",
                    claim.text,
                    "",
                    f"- origin: `{claim.origin.value}`",
                    f"- confidence: `{claim.confidence:.2f}`",
                    f"- sources: {refs}",
                    "",
                ]
            )
        if page.links:
            lines.extend(["## Related", "", *[f"- [[{link}]]" for link in page.links], ""])
        destination.write_text("\n".join(lines))
        self._rewrite_index()
        self._append_log("compile", page.slug)
        return destination

    def source_ids(self) -> list[str]:
        result: list[str] = []
        for path in sorted(self.manifest_dir.glob("*.yaml")):
            manifest = RawSourceManifest.model_validate(yaml.safe_load(path.read_text()))
            result.append(manifest.source_id)
        return result

    def search(self, query: str, *, limit: int = 10) -> list[str]:
        terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_-]+", query) if term]
        scored: list[tuple[int, str]] = []
        for path in self._page_paths():
            text = path.read_text().lower()
            score = sum(text.count(term) for term in terms)
            if score:
                scored.append((score, self._slug_for(path)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [slug for _, slug in scored[:limit]]

    def read_page(self, slug: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9/_-]*", slug):
            raise KnowledgeError("invalid wiki page slug")
        path = (self.wiki_dir / f"{slug}.md").resolve()
        if not path.is_relative_to(self.wiki_dir.resolve()) or not path.exists():
            raise KnowledgeError("wiki page not found")
        return path.read_text()

    def lint(self) -> KnowledgeLintReport:
        slugs = {self._slug_for(path) for path in self._page_paths()}
        inbound = {slug: 0 for slug in slugs}
        broken: list[str] = []
        unknown_sources: list[str] = []
        known_sources = set(self.source_ids())
        for path in self._page_paths():
            slug = self._slug_for(path)
            text = path.read_text()
            for link in re.findall(r"\[\[([a-z0-9/_-]+)\]\]", text):
                if link in inbound:
                    inbound[link] += 1
                else:
                    broken.append(f"{slug}->{link}")
            for source_ref in re.findall(r"raw:([A-Za-z0-9._:-]+)", text):
                if source_ref not in known_sources:
                    unknown_sources.append(f"{slug}->raw:{source_ref}")
        return KnowledgeLintReport(
            orphan_pages=sorted(
                slug for slug, count in inbound.items() if count == 0 and slug != "index"
            ),
            broken_links=sorted(set(broken)),
            unknown_source_refs=sorted(set(unknown_sources)),
        )

    def save_candidate(self, candidate: TechnologyCandidate) -> Path:
        path = self.candidates_dir / f"{candidate.candidate_id}.yaml"
        path.write_text(yaml.safe_dump(candidate.model_dump(mode="json"), sort_keys=True))
        return path

    def save_evaluation(self, evaluation: CandidateEvaluation) -> Path:
        path = self.evals_dir / f"{evaluation.evaluation_id}.yaml"
        path.write_text(yaml.safe_dump(evaluation.model_dump(mode="json"), sort_keys=True))
        return path

    def _page_paths(self) -> list[Path]:
        return [
            path
            for path in sorted(self.wiki_dir.rglob("*.md"))
            if path.name not in {"index.md", "log.md"}
        ]

    def _slug_for(self, path: Path) -> str:
        return str(path.relative_to(self.wiki_dir).with_suffix("")).replace("\\", "/")

    def _page_source_ids(self, page: WikiPage) -> list[str]:
        return [ref.removeprefix("raw:") for claim in page.claims for ref in claim.source_refs]

    def _rewrite_index(self) -> None:
        lines = ["# Knowledge Index", "", "Generated from compiled wiki pages.", ""]
        for path in self._page_paths():
            slug = self._slug_for(path)
            title_match = re.search(r"^# (.+)$", path.read_text(), flags=re.MULTILINE)
            title = title_match.group(1) if title_match else slug
            lines.append(f"- [[{slug}]] — {title}")
        (self.wiki_dir / "index.md").write_text("\n".join(lines) + "\n")

    def _append_log(self, operation: str, subject: str) -> None:
        stamp = datetime.now(UTC).isoformat()
        with (self.wiki_dir / "log.md").open("a", encoding="utf-8") as handle:
            handle.write(f"## [{stamp}] {operation} | {subject}\n\n")
