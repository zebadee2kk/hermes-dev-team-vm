from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .capabilities import (
    CapabilityGrant,
    CapabilityPolicy,
    CapabilityUse,
    authorize,
    preauthorize,
)
from .capability_envelope import CapabilityGrantEnvelope, open_grant

_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_DANGEROUS_GIT_CONFIG = re.compile(
    r"^(?:include|url\.|credential\.|http\.|protocol\.|core\.sshcommand|core\.hookspath|"
    r"remote\..*\.proxy)",
    re.IGNORECASE,
)
_GITHUB_API_VERSION = "2026-03-10"


class GitHubBrokerError(RuntimeError):
    pass


@dataclass(slots=True)
class InstallationToken:
    value: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TrustedWorkspace:
    path: Path
    git_common_dir: Path


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    head_sha: str
    clean: bool
    top_level: Path
    git_common_dir: Path
    dangerous_config_keys: tuple[str, ...] = ()


class GitHubTokenProvider(Protocol):
    def mint(self, resource: str, permissions: Mapping[str, str]) -> InstallationToken: ...

    def revoke(self, token: InstallationToken) -> None: ...


class GitExecutor(Protocol):
    def inspect(self, workspace: TrustedWorkspace) -> WorkspaceState: ...

    def push(
        self,
        workspace: TrustedWorkspace,
        *,
        resource: str,
        branch: str,
        token: InstallationToken,
    ) -> None: ...


class GitHubPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    task_id: str
    subject_id: str
    resource: str
    branch: str
    expected_head: str = Field(pattern=r"^[0-9a-f]{40,64}$")


class GitHubPullRequestRequest(GitHubPushRequest):
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=16384)
    draft: bool = True


class GitHubPushResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    branch: str
    head_sha: str
    remote_verified: bool


class GitHubPullRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    number: int = Field(gt=0)
    url: str
    head_branch: str
    head_sha: str
    base_branch: str
    draft: bool


class GitHubAppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    app_id: str = Field(min_length=1)
    installation_id: int = Field(gt=0)
    installation_owner: str = Field(min_length=1)
    private_key_file: Path
    require_root_owned_key: bool = True

    @field_validator("private_key_file")
    @classmethod
    def absolute_key_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("GitHub App private key path must be absolute")
        return value


class GitHubAppTokenProvider:
    """Mints repository/permission-scoped installation tokens and revokes them after use."""

    def __init__(
        self,
        config: GitHubAppConfig,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.client = client or httpx.Client(timeout=15.0)
        self.clock = clock or (lambda: datetime.now(UTC))

    def mint(self, resource: str, permissions: Mapping[str, str]) -> InstallationToken:
        owner, repository = _split_repository(resource)
        if owner.casefold() != self.config.installation_owner.casefold():
            raise GitHubBrokerError("repository owner is outside the configured GitHub App installation")
        allowed = {"read", "write"}
        if not permissions or any(value not in allowed for value in permissions.values()):
            raise GitHubBrokerError("invalid GitHub App permission reduction")
        now = _aware(self.clock(), "clock")
        app_jwt = self._app_jwt(now)
        response = self.client.post(
            f"https://api.github.com/app/installations/{self.config.installation_id}/access_tokens",
            headers=_api_headers(app_jwt),
            json={"repositories": [repository], "permissions": dict(permissions)},
        )
        response.raise_for_status()
        payload = response.json()
        value = payload.get("token") if isinstance(payload, dict) else None
        expires = payload.get("expires_at") if isinstance(payload, dict) else None
        if not isinstance(value, str) or not value or not isinstance(expires, str):
            raise GitHubBrokerError("GitHub returned an invalid installation token response")
        expires_at = _parse_datetime(expires)
        if expires_at <= now:
            raise GitHubBrokerError("GitHub returned an already-expired installation token")
        return InstallationToken(value=value, expires_at=expires_at)

    def revoke(self, token: InstallationToken) -> None:
        response = self.client.delete(
            "https://api.github.com/installation/token",
            headers=_api_headers(token.value),
        )
        if response.status_code != 204:
            raise GitHubBrokerError(
                f"failed to revoke GitHub installation token (HTTP {response.status_code})"
            )

    def _app_jwt(self, now: datetime) -> str:
        key_path = self.config.private_key_file
        try:
            info = key_path.stat()
        except FileNotFoundError as exc:
            raise GitHubBrokerError("GitHub App private key file is missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise GitHubBrokerError("GitHub App private key must be a regular file")
        if self.config.require_root_owned_key and info.st_uid != 0:
            raise GitHubBrokerError("GitHub App private key must be root-owned")
        if info.st_mode & 0o077:
            raise GitHubBrokerError("GitHub App private key must not be group/world accessible")
        key = key_path.read_text()
        payload = {
            "iat": int((now - timedelta(seconds=60)).timestamp()),
            "exp": int((now + timedelta(minutes=9)).timestamp()),
            "iss": self.config.app_id,
        }
        encoded = jwt.encode(payload, key, algorithm="RS256")
        if not isinstance(encoded, str):
            raise GitHubBrokerError("failed to create GitHub App JWT")
        return encoded


class SubprocessGitExecutor:
    """Runs Git only from a control-plane-resolved workspace using a trusted askpass helper."""

    def __init__(
        self,
        *,
        git_binary: str = "/usr/bin/git",
        askpass_path: str = "/opt/forge/github-broker/git-askpass.sh",
        timeout_seconds: int = 120,
    ) -> None:
        if not Path(git_binary).is_absolute() or not Path(askpass_path).is_absolute():
            raise ValueError("git binary and askpass helper must use absolute paths")
        self.git_binary = git_binary
        self.askpass_path = askpass_path
        self.timeout_seconds = timeout_seconds

    def inspect(self, workspace: TrustedWorkspace) -> WorkspaceState:
        top = self._git(workspace.path, "rev-parse", "--show-toplevel").stdout.strip()
        common = self._git(
            workspace.path,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
        head = self._git(workspace.path, "rev-parse", "--verify", "HEAD").stdout.strip().lower()
        if not _SHA.fullmatch(head):
            raise GitHubBrokerError("workspace HEAD is not a valid Git object id")
        status_output = self._git(
            workspace.path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).stdout
        config = self._git_allow_one(
            workspace.path,
            "config",
            "--local",
            "--name-only",
            "--get-regexp",
            ".*",
        )
        dangerous = tuple(
            sorted(
                line.strip()
                for line in config.stdout.splitlines()
                if line.strip() and _DANGEROUS_GIT_CONFIG.search(line.strip())
            )
        )
        return WorkspaceState(
            head_sha=head,
            clean=not bool(status_output.strip()),
            top_level=Path(top).resolve(),
            git_common_dir=Path(common).resolve(),
            dangerous_config_keys=dangerous,
        )

    def push(
        self,
        workspace: TrustedWorkspace,
        *,
        resource: str,
        branch: str,
        token: InstallationToken,
    ) -> None:
        helper = Path(self.askpass_path)
        try:
            info = helper.stat()
        except FileNotFoundError as exc:
            raise GitHubBrokerError("trusted GitHub askpass helper is missing") from exc
        if info.st_uid != 0 or info.st_mode & 0o022 or not os.access(helper, os.X_OK):
            raise GitHubBrokerError("GitHub askpass helper must be root-owned, executable and immutable")
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": self.askpass_path,
            "FORGE_GITHUB_INSTALLATION_TOKEN": token.value,
        }
        command = [
            self.git_binary,
            "-C",
            str(workspace.path),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "credential.helper=",
            "push",
            "--porcelain",
            "--no-verify",
            f"https://github.com/{resource}.git",
            f"HEAD:refs/heads/{branch}",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            env=env,
        )
        if result.returncode != 0:
            sanitized = (result.stderr or result.stdout).replace(token.value, "<redacted>")[-2000:]
            raise GitHubBrokerError(f"GitHub task-branch push failed: {sanitized}")

    def _git(self, workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = self._git_allow_one(workspace, *args)
        if result.returncode != 0:
            raise GitHubBrokerError(f"trusted git inspection failed: {result.stderr[-1000:]}")
        return result

    def _git_allow_one(self, workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.git_binary, "-C", str(workspace), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
            },
        )


class GitHubBroker:
    def __init__(
        self,
        *,
        policy: CapabilityPolicy,
        capability_keyring: Mapping[str, bytes],
        token_provider: GitHubTokenProvider,
        workspace_resolver: Callable[[str, str], TrustedWorkspace],
        workspace_root: Path,
        git_executor: GitExecutor,
        client: httpx.Client | None = None,
        revoked_grant_ids: set[str] | frozenset[str] = frozenset(),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.capability_keyring = capability_keyring
        self.token_provider = token_provider
        self.workspace_resolver = workspace_resolver
        self.workspace_root = workspace_root.resolve()
        self.git_executor = git_executor
        self.client = client or httpx.Client(timeout=15.0)
        self.revoked_grant_ids = revoked_grant_ids
        self.clock = clock or (lambda: datetime.now(UTC))

    def push_task_branch(
        self,
        envelope: CapabilityGrantEnvelope,
        request: GitHubPushRequest,
    ) -> GitHubPushResult:
        grant = self._open(envelope)
        preliminary = CapabilityUse(
            project_id=request.project_id,
            task_id=request.task_id,
            subject_id=request.subject_id,
            service="github",
            resource=request.resource,
            operation="branch.push",
            branch=request.branch,
        )
        preauthorize(self.policy, grant, preliminary, now=self.clock())
        default_branch = self._default_branch(request.resource)
        authorize(
            self.policy,
            grant,
            preliminary.model_copy(update={"default_branch": default_branch}),
            now=self.clock(),
        )
        workspace = self._trusted_workspace(request.project_id, request.task_id)
        state = self.git_executor.inspect(workspace)
        self._validate_workspace_state(workspace, state, request.expected_head)

        token = self.token_provider.mint(request.resource, {"contents": "write"})
        try:
            self.git_executor.push(
                workspace,
                resource=request.resource,
                branch=request.branch,
                token=token,
            )
        finally:
            self.token_provider.revoke(token)
        remote_sha = self._remote_branch_sha(request.resource, request.branch)
        if remote_sha != request.expected_head:
            raise GitHubBrokerError("remote branch verification did not match the authorized HEAD")
        return GitHubPushResult(
            repository=request.resource,
            branch=request.branch,
            head_sha=remote_sha,
            remote_verified=True,
        )

    def create_pull_request(
        self,
        envelope: CapabilityGrantEnvelope,
        request: GitHubPullRequestRequest,
    ) -> GitHubPullRequestResult:
        grant = self._open(envelope)
        preliminary = CapabilityUse(
            project_id=request.project_id,
            task_id=request.task_id,
            subject_id=request.subject_id,
            service="github",
            resource=request.resource,
            operation="pr.create",
            branch=request.branch,
        )
        preauthorize(self.policy, grant, preliminary, now=self.clock())
        default_branch = self._default_branch(request.resource)
        authorize(
            self.policy,
            grant,
            preliminary.model_copy(
                update={"default_branch": default_branch, "base_branch": default_branch}
            ),
            now=self.clock(),
        )
        if self._remote_branch_sha(request.resource, request.branch) != request.expected_head:
            raise GitHubBrokerError("pull request head does not match the authorized remote branch")

        token = self.token_provider.mint(request.resource, {"pull_requests": "write"})
        try:
            response = self.client.post(
                f"https://api.github.com/repos/{request.resource}/pulls",
                headers=_api_headers(token.value),
                json={
                    "title": request.title,
                    "body": request.body,
                    "head": request.branch,
                    "base": default_branch,
                    "draft": request.draft,
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            self.token_provider.revoke(token)
        return _parse_pull_request_result(payload, request.resource, request, default_branch)

    def _open(self, envelope: CapabilityGrantEnvelope) -> CapabilityGrant:
        return open_grant(
            envelope,
            keyring=self.capability_keyring,
            revoked_grant_ids=self.revoked_grant_ids,
        )

    def _default_branch(self, resource: str) -> str:
        token = self.token_provider.mint(resource, {"metadata": "read"})
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{resource}",
                headers=_api_headers(token.value),
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            self.token_provider.revoke(token)
        branch = payload.get("default_branch") if isinstance(payload, dict) else None
        if not isinstance(branch, str) or not branch:
            raise GitHubBrokerError("GitHub repository metadata did not provide a default branch")
        return branch

    def _remote_branch_sha(self, resource: str, branch: str) -> str:
        token = self.token_provider.mint(resource, {"contents": "read"})
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{resource}/git/ref/heads/{quote(branch, safe='')}",
                headers=_api_headers(token.value),
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            self.token_provider.revoke(token)
        obj = payload.get("object") if isinstance(payload, dict) else None
        sha = obj.get("sha") if isinstance(obj, dict) else None
        if not isinstance(sha, str) or not _SHA.fullmatch(sha.lower()):
            raise GitHubBrokerError("GitHub branch verification returned an invalid object id")
        return sha.lower()

    def _trusted_workspace(self, project_id: str, task_id: str) -> TrustedWorkspace:
        workspace = self.workspace_resolver(project_id, task_id)
        path = workspace.path.resolve()
        try:
            path.relative_to(self.workspace_root)
        except ValueError as exc:
            raise GitHubBrokerError("trusted workspace resolver returned a path outside workspace root") from exc
        if path == self.workspace_root or not path.is_dir():
            raise GitHubBrokerError("trusted workspace must be an existing task-scoped directory")
        return TrustedWorkspace(path=path, git_common_dir=workspace.git_common_dir.resolve())

    @staticmethod
    def _validate_workspace_state(
        workspace: TrustedWorkspace,
        state: WorkspaceState,
        expected_head: str,
    ) -> None:
        if state.top_level != workspace.path.resolve():
            raise GitHubBrokerError("git top-level does not match the trusted task workspace")
        if state.git_common_dir != workspace.git_common_dir.resolve():
            raise GitHubBrokerError("git common directory does not match trusted workspace state")
        if state.head_sha != expected_head:
            raise GitHubBrokerError("workspace HEAD changed after the capability request was prepared")
        if not state.clean:
            raise GitHubBrokerError("workspace has uncommitted changes")
        if state.dangerous_config_keys:
            raise GitHubBrokerError(
                "workspace contains broker-dangerous Git config: "
                + ", ".join(state.dangerous_config_keys)
            )


def _parse_pull_request_result(
    payload: object,
    resource: str,
    request: GitHubPullRequestRequest,
    default_branch: str,
) -> GitHubPullRequestResult:
    if not isinstance(payload, dict):
        raise GitHubBrokerError("GitHub returned an invalid pull request response")
    number = payload.get("number")
    url = payload.get("html_url")
    head = payload.get("head")
    base = payload.get("base")
    draft = payload.get("draft", request.draft)
    head_ref = head.get("ref") if isinstance(head, dict) else None
    head_sha = head.get("sha") if isinstance(head, dict) else None
    base_ref = base.get("ref") if isinstance(base, dict) else None
    expected_prefix = f"https://github.com/{resource}/pull/"
    if (
        not isinstance(number, int)
        or not isinstance(url, str)
        or not url.startswith(expected_prefix)
        or head_ref != request.branch
        or head_sha != request.expected_head
        or base_ref != default_branch
        or not isinstance(draft, bool)
    ):
        raise GitHubBrokerError("GitHub pull request acknowledgement did not match authorized scope")
    return GitHubPullRequestResult(
        repository=resource,
        number=number,
        url=url,
        head_branch=head_ref,
        head_sha=head_sha,
        base_branch=base_ref,
        draft=draft,
    )


def _split_repository(resource: str) -> tuple[str, str]:
    parts = resource.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise GitHubBrokerError("GitHub resource must be owner/repository")
    return parts[0], parts[1]


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GitHubBrokerError("GitHub returned an invalid token expiry") from exc
    return _aware(parsed, "token expiry")


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GitHubBrokerError(f"{label} must be timezone-aware")
    return value
