from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class PublishResult:
    path: Path
    digest: str
    changed: bool


def render_yaml(config: dict[str, object]) -> bytes:
    return yaml.safe_dump(config, sort_keys=False).encode("utf-8")


def publish_config(
    path: str | Path,
    config: dict[str, object],
    *,
    mode: int = 0o600,
) -> PublishResult:
    """Atomically publish a generated LiteLLM config and report content changes."""
    target = Path(path)
    content = render_yaml(config)
    digest = sha256(content).hexdigest()

    try:
        existing = target.read_bytes()
    except FileNotFoundError:
        existing = None
    if existing == content:
        return PublishResult(path=target, digest=digest, changed=False)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary.name, mode)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
        _fsync_directory(target.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return PublishResult(path=target, digest=digest, changed=True)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
