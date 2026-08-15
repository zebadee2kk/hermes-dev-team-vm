from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path

from .deployment_reader import load_deployments
from .litellm_config import build_litellm_config
from .litellm_publish import PublishResult, publish_config


async def render_database_config(
    *,
    database_url: str,
    path: str | Path,
    credential_env: Mapping[str, str],
    include_development: bool = False,
) -> PublishResult:
    deployments = await load_deployments(database_url)
    config = build_litellm_config(
        deployments,
        credential_env=credential_env,
        include_development=include_development,
    )
    return publish_config(path, config)


def credential_env_from_json(value: str) -> dict[str, str]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("credential mapping must be a JSON object")
    mapping: dict[str, str] = {}
    for binding, env_name in payload.items():
        if not isinstance(binding, str) or not isinstance(env_name, str):
            raise ValueError("credential mapping keys and values must be strings")
        if not env_name or not env_name.replace("_", "").isalnum():
            raise ValueError(f"invalid environment-variable name: {env_name!r}")
        mapping[binding] = env_name
    return mapping


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render Forge-approved LiteLLM config from the durable deployment registry"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy async database URL; defaults to DATABASE_URL",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("LITELLM_RUNTIME_CONFIG_PATH", "/runtime/litellm/config.yaml"),
    )
    parser.add_argument(
        "--credential-env-json",
        default=os.environ.get("FORGE_CREDENTIAL_ENV_JSON", "{}"),
        help="JSON map of credential binding to environment-variable name; never secret values",
    )
    parser.add_argument("--include-development", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    result = await render_database_config(
        database_url=args.database_url,
        path=args.output,
        credential_env=credential_env_from_json(args.credential_env_json),
        include_development=args.include_development,
    )
    print(
        json.dumps(
            {
                "path": str(result.path),
                "sha256": result.digest,
                "changed": result.changed,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
