from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .sandbox import SandboxLimits, SandboxPolicyError

_IMAGE_REFERENCE = re.compile(r"^(?:sha256:[0-9a-f]{64}|.+@sha256:[0-9a-f]{64})$")
_DOCKER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DEFAULT_CONFIG = Path("/etc/forge/codex-runtime.env")
_ALLOWED_KEYS = {
    "FORGE_CODEX_AUTH_VOLUME",
    "FORGE_CODEX_IMAGE",
    "FORGE_CODEX_NETWORK",
    "FORGE_CODEX_PROXY_URL",
    "FORGE_CODEX_WORKSPACE",
}


@dataclass(frozen=True, slots=True)
class CodexRuntimeConfig:
    workspace: Path
    image: str
    network: str
    auth_volume: str
    proxy_url: str
    limits: SandboxLimits = field(default_factory=SandboxLimits)

    @classmethod
    def load(cls, path: str | Path = _DEFAULT_CONFIG) -> "CodexRuntimeConfig":
        source = Path(path)
        values = _read_root_config(source)
        missing = sorted(set(_ALLOWED_KEYS).difference(values))
        if missing:
            raise SandboxPolicyError("missing Codex runtime settings: " + ", ".join(missing))
        image = values["FORGE_CODEX_IMAGE"]
        if not _IMAGE_REFERENCE.fullmatch(image):
            raise SandboxPolicyError("FORGE_CODEX_IMAGE must be content-addressed")
        network = _docker_name(values["FORGE_CODEX_NETWORK"], "network")
        auth_volume = _docker_name(values["FORGE_CODEX_AUTH_VOLUME"], "auth volume")
        proxy_url = values["FORGE_CODEX_PROXY_URL"]
        if not proxy_url.startswith("http://") or "@" in proxy_url:
            raise SandboxPolicyError("FORGE_CODEX_PROXY_URL must be a credential-free internal HTTP proxy")
        workspace = Path(values["FORGE_CODEX_WORKSPACE"]).resolve()
        if workspace == Path("/") or not workspace.is_dir():
            raise SandboxPolicyError("FORGE_CODEX_WORKSPACE must be an existing non-root directory")
        return cls(
            workspace=workspace,
            image=image,
            network=network,
            auth_volume=auth_volume,
            proxy_url=proxy_url,
        )


@dataclass(frozen=True, slots=True)
class CodexRuntimePlan:
    container_name: str
    command: list[str]


def validate_codex_args(args: list[str], workspace: Path) -> list[str]:
    """Permit only the Codex shapes needed by Hermes' app-server runtime and probation preflight."""
    if args == ["--version"]:
        return list(args)
    if args in (["app-server"], ["app-server", "--stdio"]):
        return list(args)
    if (
        len(args) == 4
        and args[0] == "app-server"
        and args[1] in {"generate-json-schema", "generate-ts"}
        and args[2] == "--out"
    ):
        destination = Path(args[3]).resolve()
        _require_under(destination, workspace, label="schema output")
        return list(args)
    raise SandboxPolicyError("Codex sandbox shim rejected unsupported command: " + shlex.join(args))


def validate_cwd(cwd: str | Path, workspace: str | Path) -> Path:
    allowed = Path(workspace).resolve()
    current = Path(cwd).resolve()
    _require_under(current, allowed, label="working directory")
    return current


def docker_codex_plan(
    config: CodexRuntimeConfig,
    *,
    cwd: str | Path,
    codex_args: list[str],
) -> CodexRuntimePlan:
    task_workspace = config.workspace.resolve()
    current = validate_cwd(cwd, task_workspace)
    validated_args = validate_codex_args(codex_args, task_workspace)
    container_name = _container_name(task_workspace)
    proxy_env = {
        "CODEX_HOME": "/codex-home",
        "HOME": "/tmp/home",
        "HTTP_PROXY": config.proxy_url,
        "HTTPS_PROXY": config.proxy_url,
        "http_proxy": config.proxy_url,
        "https_proxy": config.proxy_url,
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
    }
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--runtime",
        "runsc",
        "--name",
        container_name,
        "--network",
        config.network,
        "--ipc",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(config.limits.pids),
        "--memory",
        f"{config.limits.memory_mb}m",
        "--cpus",
        str(config.limits.cpus),
        "--user",
        "65532:65532",
        "--workdir",
        str(current),
        "--mount",
        f"type=bind,src={task_workspace},dst={task_workspace},rw",
        "--mount",
        f"type=volume,src={config.auth_volume},dst=/codex-home,rw",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={config.limits.tmpfs_mb}m,mode=1777",
    ]
    for name, value in sorted(proxy_env.items()):
        command.extend(["--env", f"{name}={value}"])
    command.extend([config.image, "codex", *validated_args])
    return CodexRuntimePlan(container_name=container_name, command=command)


def docker_codex_command(
    config: CodexRuntimeConfig,
    *,
    cwd: str | Path,
    codex_args: list[str],
) -> list[str]:
    return docker_codex_plan(config, cwd=cwd, codex_args=codex_args).command


def _read_root_config(path: Path) -> dict[str, str]:
    try:
        stat = path.stat()
    except FileNotFoundError as exc:
        raise SandboxPolicyError(f"Codex runtime config not found: {path}") from exc
    if stat.st_uid != 0:
        raise SandboxPolicyError("Codex runtime config must be owned by root")
    if stat.st_mode & 0o022:
        raise SandboxPolicyError("Codex runtime config must not be group/world writable")
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SandboxPolicyError(f"invalid Codex runtime config line: {raw_line!r}")
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name not in _ALLOWED_KEYS:
            raise SandboxPolicyError(f"unsupported Codex runtime setting: {name}")
        values[name] = value
    return values


def _require_under(path: Path, root: Path, *, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SandboxPolicyError(f"{label} {path} escapes probation workspace {root}") from exc


def _docker_name(value: str, label: str) -> str:
    if not _DOCKER_NAME.fullmatch(value):
        raise SandboxPolicyError(f"invalid Docker {label} name")
    return value


def _container_name(workspace: Path) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "-", "-".join(workspace.parts[-2:])).strip("-.")
    return f"forge-codex-{suffix[:48]}-{uuid4().hex[:12]}".lower()
