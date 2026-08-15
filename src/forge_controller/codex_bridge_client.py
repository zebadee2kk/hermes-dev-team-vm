from __future__ import annotations

import base64
import json
import os
import socket
import sys
import threading

_SOCKET_PATH = "/run/forge-codex/codex.sock"


def _write_frame(stream, payload: dict[str, object]) -> None:
    stream.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
    stream.flush()


def _pump_stdin(stream) -> None:
    try:
        while chunk := sys.stdin.buffer.read(65536):
            _write_frame(stream, {"type": "stdin", "data": base64.b64encode(chunk).decode("ascii")})
        _write_frame(stream, {"type": "stdin_eof"})
    except (BrokenPipeError, OSError):
        return


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(_SOCKET_PATH)
    except OSError as exc:
        print(f"Forge Codex bridge unavailable: {exc}", file=sys.stderr)
        return 127

    reader = sock.makefile("rb")
    writer = sock.makefile("wb")
    try:
        _write_frame(writer, {"cwd": os.getcwd(), "args": args})
        ready_line = reader.readline()
        if not ready_line:
            print("Forge Codex bridge closed before launch", file=sys.stderr)
            return 126
        ready = json.loads(ready_line)
        if ready.get("type") == "error":
            print(f"Forge Codex bridge rejected launch: {ready.get('message')}", file=sys.stderr)
            return 126
        if ready.get("type") != "ready":
            print("Forge Codex bridge returned an invalid launch response", file=sys.stderr)
            return 126

        input_thread = threading.Thread(target=_pump_stdin, args=(writer,), daemon=True)
        input_thread.start()

        for line in reader:
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                print("Forge Codex bridge returned invalid JSON", file=sys.stderr)
                return 126
            kind = frame.get("type")
            if kind in {"stdout", "stderr"} and isinstance(frame.get("data"), str):
                payload = base64.b64decode(frame["data"], validate=True)
                destination = sys.stdout.buffer if kind == "stdout" else sys.stderr.buffer
                destination.write(payload)
                destination.flush()
                continue
            if kind == "exit":
                returncode = frame.get("returncode")
                return int(returncode) if isinstance(returncode, int) else 126
            if kind == "error":
                print(f"Forge Codex bridge error: {frame.get('message')}", file=sys.stderr)
                return 126
        print("Forge Codex bridge closed without an exit status", file=sys.stderr)
        return 126
    finally:
        try:
            writer.close()
        finally:
            reader.close()
            sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
