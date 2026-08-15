from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import Protocol

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from .capabilities import CapabilityDenied, CapabilityPolicy, CapabilityPolicyError
from .capability_envelope import CapabilityGrantEnvelope
from .github_broker import (
    GitHubAppConfig,
    GitHubAppTokenProvider,
    GitHubBroker,
    GitHubBrokerError,
    GitHubPullRequestRequest,
    GitHubPullRequestResult,
    GitHubPushRequest,
    GitHubPushResult,
    SubprocessGitExecutor,
    TrustedWorkspace,
)

_DEFAULT_POLICY = Path("/etc/forge/capability-policy.yaml")
_DEFAULT_REGISTRY = Path("/etc/forge/github-workspaces.json")
_DEFAULT_WORKSPACE_ROOT = Path("/var/lib/forge/workspaces")
_DEFAULT_SOCKET = Path("/run/forge-github/broker.sock")
_MAX_REGISTRY_BYTES = 1024 * 1024


class GitHubBrokerDispatcher(Protocol):
    def push_task_branch(
        self, envelope: CapabilityGrantEnvelope, request: GitHubPushRequest
    ) -> GitHubPushResult: ...

    def create_pull_request(
        self, envelope: CapabilityGrantEnvelope, request: GitHubPullRequestRequest
    ) -> GitHubPullRequestResult: ...


class GitHubPushEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    envelope: CapabilityGrantEnvelope
    request: GitHubPushRequest


class GitHubPullEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    envelope: CapabilityGrantEnvelope
    request: GitHubPullRequestRequest


@dataclass(frozen=True, slots=True)
class WorkspaceRegistryEntry:
    project_id: str
    task_id: str
    resource: str
    workspace: TrustedWorkspace


class RootOwnedWorkspaceRegistry:
    """Authority registry outside worker-writable Task Capsules/workspaces."""

    def __init__(
        self,
        path: str | Path,
        *,
        workspace_root: str | Path = _DEFAULT_WORKSPACE_ROOT,
        required_owner_uid: int = 0,
    ) -> None:
        self.path = Path(path)
        self.workspace_root = Path(workspace_root).resolve()
        self.required_owner_uid = required_owner_uid

    def resolve(self, project_id: str, task_id: str, resource: str) -> TrustedWorkspace:
        entries = self._read_entries()
        matches = [
            entry
            for entry in entries
            if entry.project_id == project_id
            and entry.task_id == task_id
            and entry.resource == resource
        ]
        if len(matches) != 1:
            raise GitHubBrokerError(
                "workspace registry requires exactly one project/task/repository binding"
            )
        return matches[0].workspace

    def _read_entries(self) -> list[WorkspaceRegistryEntry]:
        try:
            info = self.path.stat()
        except FileNotFoundError as exc:
            raise GitHubBrokerError("GitHub workspace registry is missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise GitHubBrokerError("GitHub workspace registry must be a regular file")
        if info.st_uid != self.required_owner_uid:
            raise GitHubBrokerError("GitHub workspace registry has an unexpected owner")
        if info.st_mode & 0o022:
            raise GitHubBrokerError("GitHub workspace registry must not be group/world writable")
        if info.st_size > _MAX_REGISTRY_BYTES:
            raise GitHubBrokerError("GitHub workspace registry is too large")
        try:
            raw = json.loads(self.path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubBrokerError("GitHub workspace registry is not valid JSON") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise GitHubBrokerError("unsupported GitHub workspace registry version")
        raw_entries = raw.get("entries")
        if not isinstance(raw_entries, list):
            raise GitHubBrokerError("GitHub workspace registry entries must be a list")

        entries: list[WorkspaceRegistryEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for item in raw_entries:
            if not isinstance(item, dict) or set(item) != {
                "project_id",
                "task_id",
                "resource",
                "workspace",
                "git_common_dir",
            }:
                raise GitHubBrokerError("invalid GitHub workspace registry entry")
            values = {key: item[key] for key in item}
            if not all(isinstance(value, str) and value for value in values.values()):
                raise GitHubBrokerError("GitHub workspace registry values must be non-empty strings")
            workspace = Path(item["workspace"]).resolve()
            git_common_dir = Path(item["git_common_dir"]).resolve()
            try:
                workspace.relative_to(self.workspace_root)
            except ValueError as exc:
                raise GitHubBrokerError("registered workspace escapes the configured workspace root") from exc
            if workspace == self.workspace_root:
                raise GitHubBrokerError("registry cannot grant the workspace root itself")
            identity = (item["project_id"], item["task_id"], item["resource"])
            if identity in seen:
                raise GitHubBrokerError("duplicate project/task/repository workspace binding")
            seen.add(identity)
            entries.append(
                WorkspaceRegistryEntry(
                    project_id=item["project_id"],
                    task_id=item["task_id"],
                    resource=item["resource"],
                    workspace=TrustedWorkspace(
                        path=workspace,
                        git_common_dir=git_common_dir,
                    ),
                )
            )
        return entries


class RegistryBoundGitHubDispatcher:
    def __init__(
        self,
        *,
        policy: CapabilityPolicy,
        capability_keyring: dict[str, bytes],
        token_provider: GitHubAppTokenProvider,
        registry: RootOwnedWorkspaceRegistry,
        workspace_root: str | Path,
        git_executor: SubprocessGitExecutor,
        revoked_grant_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self.policy = policy
        self.capability_keyring = capability_keyring
        self.token_provider = token_provider
        self.registry = registry
        self.workspace_root = Path(workspace_root).resolve()
        self.git_executor = git_executor
        self.revoked_grant_ids = revoked_grant_ids

    def push_task_branch(
        self, envelope: CapabilityGrantEnvelope, request: GitHubPushRequest
    ) -> GitHubPushResult:
        return self._broker(request).push_task_branch(envelope, request)

    def create_pull_request(
        self, envelope: CapabilityGrantEnvelope, request: GitHubPullRequestRequest
    ) -> GitHubPullRequestResult:
        return self._broker(request).create_pull_request(envelope, request)

    def _broker(self, request: GitHubPushRequest) -> GitHubBroker:
        workspace = self.registry.resolve(
            request.project_id,
            request.task_id,
            request.resource,
        )
        return GitHubBroker(
            policy=self.policy,
            capability_keyring=self.capability_keyring,
            token_provider=self.token_provider,
            workspace_resolver=lambda project_id, task_id: self._resolved_workspace(
                workspace,
                request,
                project_id,
                task_id,
            ),
            workspace_root=self.workspace_root,
            git_executor=self.git_executor,
            revoked_grant_ids=self.revoked_grant_ids,
        )

    @staticmethod
    def _resolved_workspace(
        workspace: TrustedWorkspace,
        request: GitHubPushRequest,
        project_id: str,
        task_id: str,
    ) -> TrustedWorkspace:
        if project_id != request.project_id or task_id != request.task_id:
            raise GitHubBrokerError("broker requested an unexpected workspace identity")
        return workspace


def create_github_broker_app(
    dispatcher: GitHubBrokerDispatcher,
    *,
    transport_key: str,
) -> FastAPI:
    if not transport_key:
        raise ValueError("GitHub broker transport key is required")
    app = FastAPI(title="Forge GitHub Capability Broker", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/github/push", response_model=GitHubPushResult)
    def push(payload: GitHubPushEnvelopeRequest, request: Request) -> GitHubPushResult:
        _authorize_transport(request, transport_key)
        try:
            return dispatcher.push_task_branch(payload.envelope, payload.request)
        except (CapabilityDenied, CapabilityPolicyError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except GitHubBrokerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/github/pulls", response_model=GitHubPullRequestResult)
    def pull(payload: GitHubPullEnvelopeRequest, request: Request) -> GitHubPullRequestResult:
        _authorize_transport(request, transport_key)
        try:
            return dispatcher.create_pull_request(payload.envelope, payload.request)
        except (CapabilityDenied, CapabilityPolicyError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except GitHubBrokerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


def build_production_dispatcher() -> tuple[RegistryBoundGitHubDispatcher, str]:
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_dir:
        raise RuntimeError("CREDENTIALS_DIRECTORY is required; use systemd LoadCredential")
    credentials = Path(credentials_dir)
    transport_key = _read_text_secret(credentials / "broker-api-key")
    capability_key = _read_hex_secret(credentials / "capability-hmac-key", min_bytes=32)
    private_key = credentials / "github-app-private-key"
    _validate_secret_file(private_key)

    key_id = _required_env("FORGE_CAPABILITY_KEY_ID")
    app_id = _required_env("FORGE_GITHUB_APP_ID")
    installation_id = int(_required_env("FORGE_GITHUB_INSTALLATION_ID"))
    installation_owner = _required_env("FORGE_GITHUB_INSTALLATION_OWNER")
    workspace_root = Path(
        os.environ.get("FORGE_GITHUB_WORKSPACE_ROOT", str(_DEFAULT_WORKSPACE_ROOT))
    ).resolve()
    policy_path = Path(os.environ.get("FORGE_GITHUB_CAPABILITY_POLICY", str(_DEFAULT_POLICY)))
    registry_path = Path(
        os.environ.get("FORGE_GITHUB_WORKSPACE_REGISTRY", str(_DEFAULT_REGISTRY))
    )

    policy = CapabilityPolicy.load(policy_path)
    registry = RootOwnedWorkspaceRegistry(registry_path, workspace_root=workspace_root)
    provider = GitHubAppTokenProvider(
        GitHubAppConfig(
            app_id=app_id,
            installation_id=installation_id,
            installation_owner=installation_owner,
            private_key_file=private_key,
            require_root_owned_key=False,
        )
    )
    dispatcher = RegistryBoundGitHubDispatcher(
        policy=policy,
        capability_keyring={key_id: capability_key},
        token_provider=provider,
        registry=registry,
        workspace_root=workspace_root,
        git_executor=SubprocessGitExecutor(),
    )
    return dispatcher, transport_key


def main() -> int:
    dispatcher, transport_key = build_production_dispatcher()
    socket_path = Path(os.environ.get("FORGE_GITHUB_BROKER_SOCKET", str(_DEFAULT_SOCKET)))
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(
        create_github_broker_app(dispatcher, transport_key=transport_key),
        uds=str(socket_path),
        access_log=False,
        server_header=False,
        date_header=False,
    )
    return 0


def _authorize_transport(request: Request, expected: str) -> None:
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid GitHub broker transport credential")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _validate_secret_file(path: Path) -> None:
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"required systemd credential is missing: {path.name}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"systemd credential must be a regular file: {path.name}")
    if info.st_uid not in {0, os.geteuid()}:
        raise RuntimeError(f"systemd credential has an unexpected owner: {path.name}")
    if info.st_mode & 0o077:
        raise RuntimeError(f"systemd credential must not be group/world accessible: {path.name}")


def _read_text_secret(path: Path) -> str:
    _validate_secret_file(path)
    value = path.read_text().strip()
    if len(value) < 32:
        raise RuntimeError(f"credential {path.name} must contain at least 32 characters")
    return value


def _read_hex_secret(path: Path, *, min_bytes: int) -> bytes:
    _validate_secret_file(path)
    try:
        value = bytes.fromhex(path.read_text().strip())
    except ValueError as exc:
        raise RuntimeError(f"credential {path.name} must contain hexadecimal bytes") from exc
    if len(value) < min_bytes:
        raise RuntimeError(f"credential {path.name} must contain at least {min_bytes} bytes")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
