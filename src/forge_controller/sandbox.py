from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

_IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_ENV_FRAGMENTS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "DATABASE_URL",
    "PRIVATE_KEY",
    "CREDENTIAL",
)


class SandboxPolicyError(ValueError):
    pass


class SandboxLimits(BaseModel):
    cpus: float = Field(default=2.0, gt=0, le=8)
    memory_mb: int = Field(default=4096, ge=256, le=32768)
    pids: int = Field(default=256, ge=32, le=2048)
    tmpfs_mb: int = Field(default=512, ge=64, le=4096)
    timeout_seconds: int = Field(default=1800, ge=30, le=14400)


class SandboxLaunchRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    task_id: str
    image: str
    command: list[str] = Field(min_length=1)
    workspace_path: str
    profile: str = "normal"
    environment: dict[str, str] = Field(default_factory=dict)
    capability_grant_refs: list[str] = Field(default_factory=list)
    secret_refs: list[str] = Field(default_factory=list)
    limits: SandboxLimits = Field(default_factory=SandboxLimits)

    @field_validator("image")
    @classmethod
    def image_must_be_digest_pinned(cls, value: str) -> str:
        if not _IMAGE_DIGEST.fullmatch(value):
            raise ValueError("sandbox image must be pinned by sha256 digest")
        return value

    @field_validator("environment")
    @classmethod
    def environment_must_be_non_secret(cls, value: dict[str, str]) -> dict[str, str]:
        for name in value:
            if not _ENV_NAME.fullmatch(name):
                raise ValueError(f"invalid environment variable name: {name!r}")
            upper = name.upper()
            if any(fragment in upper for fragment in _SECRET_ENV_FRAGMENTS):
                raise ValueError(
                    f"secret-like environment variable {name!r} must be a brokered secret reference"
                )
        return value


class SandboxPlan(BaseModel):
    request_id: str
    runtime: str = "runsc"
    image: str
    command: list[str]
    container_name: str
    workspace_source: str
    workspace_destination: str = "/workspace"
    user: str = "65532:65532"
    network_mode: str = "none"
    read_only_rootfs: bool = True
    cap_drop: list[str] = Field(default_factory=lambda: ["ALL"])
    security_opt: list[str] = Field(default_factory=lambda: ["no-new-privileges:true"])
    tmpfs: dict[str, str]
    limits: SandboxLimits
    environment: dict[str, str] = Field(default_factory=dict)
    capability_grant_refs: list[str] = Field(default_factory=list)
    secret_refs: list[str] = Field(default_factory=list)


class SandboxPlanner:
    """Trusted control-plane planner. It never executes inside a worker Hand."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        runtime_name: str = "runsc",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.runtime_name = runtime_name

    def plan(self, request: SandboxLaunchRequest) -> SandboxPlan:
        if request.profile != "normal":
            raise SandboxPolicyError(
                f"profile {request.profile!r} is not implemented by the gVisor normal backend"
            )
        workspace = self._workspace(request.workspace_path)
        return SandboxPlan(
            request_id=request.request_id,
            runtime=self.runtime_name,
            image=request.image,
            command=request.command,
            container_name=_container_name(request.task_id, request.request_id),
            workspace_source=str(workspace),
            tmpfs={
                "/tmp": (
                    f"rw,noexec,nosuid,nodev,size={request.limits.tmpfs_mb}m,mode=1777"
                )
            },
            limits=request.limits,
            environment=request.environment,
            capability_grant_refs=request.capability_grant_refs,
            secret_refs=request.secret_refs,
        )

    def _workspace(self, requested: str) -> Path:
        workspace = Path(requested).resolve()
        try:
            workspace.relative_to(self.workspace_root)
        except ValueError as exc:
            raise SandboxPolicyError(
                f"workspace {workspace} escapes allowed root {self.workspace_root}"
            ) from exc
        if workspace == self.workspace_root:
            raise SandboxPolicyError("workspace must be a task-scoped child of the workspace root")
        return workspace


def docker_run_command(plan: SandboxPlan) -> list[str]:
    """Materialise the normal profile as a locked-down Docker+runsc invocation."""
    command = [
        "docker",
        "run",
        "--rm",
        "--runtime",
        plan.runtime,
        "--name",
        plan.container_name,
        "--network",
        plan.network_mode,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(plan.limits.pids),
        "--memory",
        f"{plan.limits.memory_mb}m",
        "--cpus",
        str(plan.limits.cpus),
        "--user",
        plan.user,
        "--workdir",
        plan.workspace_destination,
        "--mount",
        (
            "type=bind,src="
            f"{plan.workspace_source},dst={plan.workspace_destination},rw"
        ),
    ]
    for destination, options in sorted(plan.tmpfs.items()):
        command.extend(["--tmpfs", f"{destination}:{options}"])
    for name, value in sorted(plan.environment.items()):
        command.extend(["--env", f"{name}={value}"])
    command.append(plan.image)
    command.extend(plan.command)
    return command


def _container_name(task_id: str, request_id: str) -> str:
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "-", task_id).strip("-.") or "task"
    safe_request = re.sub(r"[^A-Za-z0-9]+", "", request_id)[:12] or "request"
    return f"forge-{safe_task[:40]}-{safe_request}".lower()
