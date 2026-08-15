from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Sensitivity

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")


class CapabilityPolicyError(RuntimeError):
    pass


class CapabilityDenied(CapabilityPolicyError):
    pass


class CapabilityTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str
    operations: frozenset[str]
    resource_scope_required: bool = False
    branch_scope_required: bool = False
    credential_binding: str | None = None
    max_ttl_minutes: int | None = Field(default=None, gt=0)
    deny_default_branch_write: bool = False
    allow_force_push: bool = False
    pr_base_must_equal_default: bool = False
    credential_exposure: str = "never"


class CapabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deny_unmatched: bool = True
    preserve_audit: bool = True
    max_ttl_minutes: int = Field(default=60, gt=0)
    templates: dict[str, CapabilityTemplate]

    @classmethod
    def load(cls, path: str | Path) -> "CapabilityPolicy":
        source = Path(path)
        raw = yaml.safe_load(source.read_text())
        if not isinstance(raw, dict):
            raise CapabilityPolicyError("capability policy must be a mapping")
        defaults = raw.get("defaults")
        templates = raw.get("capability_templates")
        if not isinstance(defaults, dict) or not isinstance(templates, dict):
            raise CapabilityPolicyError("capability policy requires defaults and capability_templates")
        return cls(
            deny_unmatched=bool(defaults.get("deny_unmatched", True)),
            preserve_audit=bool(defaults.get("preserve_audit", True)),
            max_ttl_minutes=int(defaults.get("max_ttl_minutes", 60)),
            templates=templates,
        )


class CapabilityGrant(BaseModel):
    """Serializable authority reference. It deliberately contains no credential material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_id: str = Field(default_factory=lambda: str(uuid4()))
    template: str
    project_id: str
    task_id: str
    subject_id: str
    service: str
    resource: str
    operations: frozenset[str] = Field(min_length=1)
    branch: str | None = None
    credential_binding: str | None = None
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    reason: str | None = None

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: str) -> str:
        if not _REPOSITORY.fullmatch(value):
            raise ValueError("resource must be an exact owner/repository identifier")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is None:
            return value
        _validate_branch(value)
        return value


class CapabilityUse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    task_id: str
    subject_id: str
    service: str
    resource: str
    operation: str
    branch: str | None = None
    default_branch: str | None = None
    force: bool = False
    base_branch: str | None = None

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: str) -> str:
        if not _REPOSITORY.fullmatch(value):
            raise ValueError("resource must be an exact owner/repository identifier")
        return value

    @field_validator("branch", "default_branch", "base_branch")
    @classmethod
    def validate_optional_branch(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_branch(value)
        return value


class AuthorizedCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_id: str
    service: str
    resource: str
    operation: str
    branch: str | None = None
    credential_binding: str | None = None
    expires_at: datetime


def issue_grant(
    policy: CapabilityPolicy,
    *,
    template: str,
    project_id: str,
    task_id: str,
    subject_id: str,
    resource: str,
    operations: set[str] | frozenset[str],
    ttl_minutes: int,
    branch: str | None = None,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    reason: str | None = None,
    now: datetime | None = None,
) -> CapabilityGrant:
    issued_at = _aware(now or datetime.now(UTC), "now")
    selected = _template(policy, template)
    ttl_limit = min(policy.max_ttl_minutes, selected.max_ttl_minutes or policy.max_ttl_minutes)
    if ttl_minutes <= 0 or ttl_minutes > ttl_limit:
        raise CapabilityPolicyError(f"ttl must be between 1 and {ttl_limit} minutes")
    grant = CapabilityGrant(
        template=template,
        project_id=project_id,
        task_id=task_id,
        subject_id=subject_id,
        service=selected.service,
        resource=resource,
        operations=frozenset(operations),
        branch=branch,
        credential_binding=selected.credential_binding,
        sensitivity=sensitivity,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=ttl_minutes),
        reason=reason,
    )
    validate_grant(policy, grant)
    return grant


def validate_grant(policy: CapabilityPolicy, grant: CapabilityGrant) -> None:
    selected = _template(policy, grant.template)
    issued_at = _aware(grant.issued_at, "issued_at")
    expires_at = _aware(grant.expires_at, "expires_at")
    if expires_at <= issued_at:
        raise CapabilityPolicyError("grant expires_at must be after issued_at")
    ttl_limit = min(policy.max_ttl_minutes, selected.max_ttl_minutes or policy.max_ttl_minutes)
    if expires_at - issued_at > timedelta(minutes=ttl_limit):
        raise CapabilityPolicyError(f"grant exceeds {ttl_limit}-minute policy TTL")
    if grant.service != selected.service:
        raise CapabilityPolicyError("grant service does not match its template")
    if not grant.operations.issubset(selected.operations):
        raise CapabilityPolicyError("grant requests operations outside its template")
    if not grant.operations:
        raise CapabilityPolicyError("grant must contain at least one operation")
    if selected.resource_scope_required and not grant.resource:
        raise CapabilityPolicyError("grant requires an exact resource scope")
    if selected.branch_scope_required and not grant.branch:
        raise CapabilityPolicyError("grant requires an exact branch scope")
    if grant.credential_binding != selected.credential_binding:
        raise CapabilityPolicyError("grant credential binding does not match trusted policy")
    if selected.credential_exposure != "never":
        raise CapabilityPolicyError("worker-visible credential exposure is unsupported")


def authorize(
    policy: CapabilityPolicy,
    grant: CapabilityGrant,
    use: CapabilityUse,
    *,
    now: datetime | None = None,
) -> AuthorizedCapability:
    validate_grant(policy, grant)
    selected = _template(policy, grant.template)
    current = _aware(now or datetime.now(UTC), "now")
    if grant.revoked:
        raise CapabilityDenied("grant is revoked")
    if current < _aware(grant.issued_at, "issued_at"):
        raise CapabilityDenied("grant is not active yet")
    if current >= _aware(grant.expires_at, "expires_at"):
        raise CapabilityDenied("grant is expired")

    comparisons = {
        "project": (grant.project_id, use.project_id),
        "task": (grant.task_id, use.task_id),
        "subject": (grant.subject_id, use.subject_id),
        "service": (grant.service, use.service),
        "resource": (grant.resource, use.resource),
    }
    for label, (expected, actual) in comparisons.items():
        if expected != actual:
            raise CapabilityDenied(f"{label} is outside the capability grant")
    if use.operation not in grant.operations or use.operation not in selected.operations:
        raise CapabilityDenied("operation is outside the capability grant")

    if selected.branch_scope_required:
        if not grant.branch or not use.branch or grant.branch != use.branch:
            raise CapabilityDenied("branch is outside the capability grant")
        if not use.default_branch:
            raise CapabilityDenied("default branch context is required for write authorization")
        if selected.deny_default_branch_write and use.branch == use.default_branch:
            raise CapabilityDenied("direct writes to the default branch are forbidden")

    if use.operation == "branch.push" and use.force and not selected.allow_force_push:
        raise CapabilityDenied("force push is forbidden")
    if use.operation == "pr.create" and selected.pr_base_must_equal_default:
        if not use.base_branch or use.base_branch != use.default_branch:
            raise CapabilityDenied("pull request base must be the repository default branch")

    return AuthorizedCapability(
        grant_id=grant.grant_id,
        service=grant.service,
        resource=grant.resource,
        operation=use.operation,
        branch=use.branch,
        credential_binding=grant.credential_binding,
        expires_at=grant.expires_at,
    )


def _template(policy: CapabilityPolicy, name: str) -> CapabilityTemplate:
    selected = policy.templates.get(name)
    if selected is None:
        raise CapabilityPolicyError(f"unknown capability template: {name}")
    return selected


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CapabilityPolicyError(f"{label} must be timezone-aware")
    return value


def _validate_branch(value: str) -> None:
    if (
        not _BRANCH.fullmatch(value)
        or ".." in value
        or "//" in value
        or "@{" in value
        or value.endswith(".lock")
        or value.endswith("/")
        or value.startswith("-")
    ):
        raise ValueError("invalid or ambiguous Git branch name")
