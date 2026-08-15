from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import TrustEnvelope
from .models import Sensitivity

_MAX_CONTENT_BYTES = 2 * 1024 * 1024


class TrustGatewayError(RuntimeError):
    pass


class TrustClass(StrEnum):
    TRUSTED_OWNER = "trusted_owner"
    TRUSTED_CONTROL_PLANE = "trusted_control_plane"
    AGENT_GENERATED = "agent_generated"
    VERIFIED_EXTERNAL = "verified_external"
    UNTRUSTED_EXTERNAL = "untrusted_external"
    SUSPICIOUS = "suspicious"
    BLOCKED = "blocked"


_TRUST_RISK = {
    TrustClass.TRUSTED_OWNER: 0,
    TrustClass.TRUSTED_CONTROL_PLANE: 0,
    TrustClass.AGENT_GENERATED: 2,
    TrustClass.VERIFIED_EXTERNAL: 2,
    TrustClass.UNTRUSTED_EXTERNAL: 3,
    TrustClass.SUSPICIOUS: 4,
    TrustClass.BLOCKED: 5,
}

_SENSITIVITY_RISK = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.CONFIDENTIAL: 2,
    Sensitivity.RESTRICTED: 3,
}

_EXTERNAL_SOURCE_KINDS = {
    "browser",
    "email",
    "github",
    "github_connector",
    "mcp_external",
    "package_metadata",
    "web",
    "webhook",
}

_ALLOWED_SOURCE_KEYS = {
    "kind",
    "locator",
    "connector",
    "agent_id",
    "deployment_id",
    "repository",
    "url",
    "message_id",
}


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=128)
    locator: str | None = Field(default=None, max_length=4096)
    connector: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    deployment_id: str | None = Field(default=None, max_length=256)
    repository: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=4096)
    message_id: str | None = Field(default=None, max_length=512)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        return value.strip().lower()


class InjectionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    severity: str
    category: str


class InjectionProbe(Protocol):
    def inspect(self, content: str, source: SourceDescriptor) -> list[InjectionFinding]: ...


class HeuristicInjectionProbe:
    """Cheap deterministic suspicion hook. Findings restrict trust; they never prove safety."""

    _RULES = (
        (
            "ignore-instructions",
            "high",
            "instruction_override",
            re.compile(r"\b(ignore|disregard|override)\b.{0,60}\b(previous|prior|system|developer)\b", re.I | re.S),
        ),
        (
            "system-prompt-request",
            "high",
            "secret_or_policy_extraction",
            re.compile(r"\b(system prompt|developer message|hidden instructions?)\b", re.I),
        ),
        (
            "secret-exfiltration",
            "high",
            "credential_exfiltration",
            re.compile(
                r"\b(reveal|print|send|upload|exfiltrate|return)\b.{0,80}\b(secret|token|password|api[-_ ]?key|credential)\b",
                re.I | re.S,
            ),
        ),
        (
            "tool-coercion",
            "medium",
            "tool_instruction",
            re.compile(r"\b(run|execute|call)\b.{0,50}\b(shell|terminal|tool|curl|powershell|bash)\b", re.I | re.S),
        ),
        (
            "concealment",
            "medium",
            "concealment",
            re.compile(r"\b(do not|don't|never)\b.{0,40}\b(tell|show|mention|inform)\b.{0,40}\b(user|owner|reviewer)\b", re.I | re.S),
        ),
    )

    def inspect(self, content: str, source: SourceDescriptor) -> list[InjectionFinding]:
        del source
        return [
            InjectionFinding(rule_id=rule_id, severity=severity, category=category)
            for rule_id, severity, category, pattern in self._RULES
            if pattern.search(content)
        ]


class TrustGateway:
    def __init__(self, probes: list[InjectionProbe] | None = None) -> None:
        self.probes = probes if probes is not None else [HeuristicInjectionProbe()]

    def ingest(
        self,
        *,
        project_id: str,
        content_ref: str,
        content: str | bytes,
        source: SourceDescriptor,
        task_id: str | None = None,
        sensitivity: Sensitivity = Sensitivity.PUBLIC,
        requested_trust: TrustClass | None = None,
        parent_envelopes: list[TrustEnvelope] | None = None,
    ) -> TrustEnvelope:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if len(raw) > _MAX_CONTENT_BYTES:
            raise TrustGatewayError(f"content exceeds {_MAX_CONTENT_BYTES} byte trust-gateway limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrustGatewayError("trust gateway currently requires UTF-8 text content") from exc

        parents = parent_envelopes or []
        for parent in parents:
            if parent.project_id != project_id:
                raise TrustGatewayError("trust cannot be laundered across project boundaries")

        source_trust = _default_source_trust(source.kind)
        desired = requested_trust or source_trust
        effective = _worst_trust([source_trust, desired, *(_trust(parent.trust) for parent in parents)])
        taint = set()
        findings: list[InjectionFinding] = []
        parent_refs: list[str] = []
        effective_sensitivity = sensitivity

        if source.kind in _EXTERNAL_SOURCE_KINDS:
            taint.add("external_content")
        if source.kind == "subagent_output":
            taint.add("agent_generated")
        if parents:
            taint.add("transformed_from_parent")

        for parent in parents:
            parent_refs.append(parent.envelope_id)
            taint.update(parent.taint)
            effective_sensitivity = _max_sensitivity(
                effective_sensitivity,
                parent.data_sensitivity,
            )
            for finding in parent.injection_findings:
                findings.append(InjectionFinding.model_validate(finding))

        for probe in self.probes:
            findings.extend(probe.inspect(text, source))
        findings = _deduplicate_findings(findings)
        if findings:
            taint.add("prompt_injection_suspected")
            effective = _worst_trust([effective, TrustClass.SUSPICIOUS])

        # A derived summary/handoff cannot remove external influence merely because a local agent wrote it.
        if "external_content" in taint and _TRUST_RISK[effective] < _TRUST_RISK[TrustClass.UNTRUSTED_EXTERNAL]:
            effective = TrustClass.UNTRUSTED_EXTERNAL

        return TrustEnvelope(
            project_id=project_id,
            task_id=task_id,
            content_ref=content_ref,
            source=source.model_dump(mode="json", exclude_none=True),
            trust=effective.value,
            taint=sorted(taint),
            data_sensitivity=effective_sensitivity,
            integrity_hash="sha256:" + hashlib.sha256(raw).hexdigest(),
            injection_findings=[finding.model_dump(mode="json") for finding in findings],
            parent_refs=parent_refs,
        )


def content_can_authorize_capability(envelope: TrustEnvelope) -> bool:
    """Trust Envelopes are provenance, never capability/decision authority."""
    del envelope
    return False


def _default_source_trust(kind: str) -> TrustClass:
    normalized = kind.strip().lower()
    if normalized == "owner_input":
        return TrustClass.TRUSTED_OWNER
    if normalized in {"forge_internal", "control_plane"}:
        return TrustClass.TRUSTED_CONTROL_PLANE
    if normalized == "subagent_output":
        return TrustClass.AGENT_GENERATED
    if normalized in _EXTERNAL_SOURCE_KINDS:
        return TrustClass.UNTRUSTED_EXTERNAL
    return TrustClass.UNTRUSTED_EXTERNAL


def _trust(value: str) -> TrustClass:
    try:
        return TrustClass(value)
    except ValueError as exc:
        raise TrustGatewayError(f"unknown trust class on parent envelope: {value}") from exc


def _worst_trust(values: list[TrustClass]) -> TrustClass:
    return max(values, key=lambda value: _TRUST_RISK[value])


def _max_sensitivity(first: Sensitivity, second: Sensitivity) -> Sensitivity:
    return max((first, second), key=lambda value: _SENSITIVITY_RISK[value])


def _deduplicate_findings(findings: list[InjectionFinding]) -> list[InjectionFinding]:
    unique: dict[tuple[str, str, str], InjectionFinding] = {}
    for finding in findings:
        unique[(finding.rule_id, finding.severity, finding.category)] = finding
    return [unique[key] for key in sorted(unique)]
