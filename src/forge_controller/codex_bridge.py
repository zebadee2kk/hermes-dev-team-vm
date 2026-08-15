from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
from pathlib import Path

from .codex_runtime import CodexRuntimeConfig, docker_codex_plan
from .sandbox import SandboxPolicyError

_SOCKET_PATH = Path("/run/forge-codex/codex.sock")
_MAX_FRAME_BYTES = 1024 * 1024


class CodexBridgeServer:
    """Trusted local stdio bridge from Hermes to one policy-pinned gVisor Codex Hand."""

    def __init__(self, config: CodexRuntimeConfig) -> None:
        self.config = config

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        process: asyncio.subprocess.Process | None = None
        container_name: str | None = None
        send_lock = asyncio.Lock()
        try:
            launch = await _read_json_line(reader)
            cwd = launch.get("cwd")
            args = launch.get("args")
            if not isinstance(cwd, str) or not isinstance(args, list) or not all(
                isinstance(value, str) for value in args
            ):
                raise SandboxPolicyError("invalid Codex bridge launch request")
            plan = docker_codex_plan(self.config, cwd=cwd, codex_args=list(args))
            container_name = plan.container_name
            process = await asyncio.create_subprocess_exec(
                *plan.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await _send_json(writer, {"type": "ready", "container": container_name}, send_lock)

            stdin_task = asyncio.create_task(_feed_stdin(reader, process))
            stdout_task = asyncio.create_task(
                _pump_output(process.stdout, writer, "stdout", send_lock)
            )
            stderr_task = asyncio.create_task(
                _pump_output(process.stderr, writer, "stderr", send_lock)
            )
            returncode = await process.wait()
            stdin_task.cancel()
            await asyncio.gather(stdin_task, return_exceptions=True)
            await asyncio.gather(stdout_task, stderr_task)
            await _send_json(writer, {"type": "exit", "returncode": returncode}, send_lock)
        except (SandboxPolicyError, ValueError, json.JSONDecodeError) as exc:
            await _send_json(writer, {"type": "error", "message": str(exc)}, send_lock)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            if container_name:
                await _force_remove(container_name)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


async def _feed_stdin(
    reader: asyncio.StreamReader, process: asyncio.subprocess.Process
) -> None:
    assert process.stdin is not None
    while True:
        frame = await _read_json_line(reader)
        kind = frame.get("type")
        if kind == "stdin_eof":
            process.stdin.close()
            return
        if kind != "stdin" or not isinstance(frame.get("data"), str):
            raise ValueError("invalid Codex bridge stdin frame")
        payload = base64.b64decode(frame["data"], validate=True)
        process.stdin.write(payload)
        await process.stdin.drain()


async def _pump_output(
    source: asyncio.StreamReader | None,
    writer: asyncio.StreamWriter,
    kind: str,
    lock: asyncio.Lock,
) -> None:
    if source is None:
        return
    while payload := await source.read(65536):
        await _send_json(
            writer,
            {"type": kind, "data": base64.b64encode(payload).decode("ascii")},
            lock,
        )


async def _read_json_line(reader: asyncio.StreamReader) -> dict[str, object]:
    line = await reader.readline()
    if not line:
        raise asyncio.IncompleteReadError(partial=b"", expected=1)
    if len(line) > _MAX_FRAME_BYTES:
        raise ValueError("Codex bridge frame too large")
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("Codex bridge frame must be a JSON object")
    return payload


async def _send_json(
    writer: asyncio.StreamWriter,
    payload: dict[str, object],
    lock: asyncio.Lock,
) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
    async with lock:
        writer.write(data)
        await writer.drain()


async def _force_remove(container_name: str) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=10)
    except (FileNotFoundError, OSError, asyncio.TimeoutError):
        pass


def _prepare_socket(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_socket():
        info = path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise RuntimeError(f"refusing to replace unexpected Codex bridge path: {path}")
        path.unlink()


async def _serve() -> None:
    config = CodexRuntimeConfig.load()
    _prepare_socket(_SOCKET_PATH)
    previous_umask = os.umask(0o007)
    try:
        bridge = CodexBridgeServer(config)
        server = await asyncio.start_unix_server(
            bridge.handle,
            path=str(_SOCKET_PATH),
            limit=_MAX_FRAME_BYTES,
        )
    finally:
        os.umask(previous_umask)
    os.chmod(_SOCKET_PATH, 0o660)
    async with server:
        await server.serve_forever()


def main() -> int:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
