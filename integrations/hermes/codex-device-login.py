from __future__ import annotations

import json
import subprocess
import sys


def _send(process: subprocess.Popen[str], payload: dict[str, object]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _messages(process: subprocess.Popen[str]):
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            yield message


def main() -> int:
    process = subprocess.Popen(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    try:
        _send(
            process,
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "hermes_forge_probation",
                        "title": "Hermes Forge Probation",
                        "version": "1",
                    }
                },
            },
        )
        initialized = False
        login_id: str | None = None
        for message in _messages(process):
            if message.get("id") == 0 and "result" in message:
                initialized = True
                break
            if message.get("id") == 0 and "error" in message:
                print(json.dumps({"ok": False, "stage": "initialize", "error": message["error"]}))
                return 2
        if not initialized:
            print(json.dumps({"ok": False, "stage": "initialize", "error": "app-server exited"}))
            return 2

        _send(process, {"method": "initialized", "params": {}})
        _send(
            process,
            {
                "method": "account/login/start",
                "id": 1,
                "params": {"type": "chatgptDeviceCode"},
            },
        )
        for message in _messages(process):
            if message.get("id") == 1 and "error" in message:
                print(json.dumps({"ok": False, "stage": "login_start", "error": message["error"]}))
                return 2
            if message.get("id") == 1 and isinstance(message.get("result"), dict):
                result = message["result"]
                if result.get("type") != "chatgptDeviceCode":
                    print(json.dumps({"ok": False, "stage": "login_start", "error": result}))
                    return 2
                login_id = str(result["loginId"])
                print(
                    json.dumps(
                        {
                            "action": "complete_device_login",
                            "verification_url": result.get("verificationUrl"),
                            "user_code": result.get("userCode"),
                        }
                    ),
                    flush=True,
                )
                continue
            if message.get("method") == "account/login/completed":
                params = message.get("params")
                if not isinstance(params, dict) or str(params.get("loginId")) != login_id:
                    continue
                success = params.get("success") is True
                print(
                    json.dumps(
                        {
                            "ok": success,
                            "stage": "completed",
                            "error": params.get("error"),
                        }
                    ),
                    flush=True,
                )
                return 0 if success else 2
        print(json.dumps({"ok": False, "stage": "login", "error": "app-server exited"}))
        return 2
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
