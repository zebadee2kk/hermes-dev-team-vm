from __future__ import annotations

import errno
import json
import os
import socket
import subprocess
from pathlib import Path

SECRET_ENV_FRAGMENTS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "DATABASE_URL",
    "PRIVATE_KEY",
    "CREDENTIAL",
)


def _record(checks: dict[str, dict[str, object]], name: str, ok: bool, detail: object) -> None:
    checks[name] = {"ok": bool(ok), "detail": detail}


def _workspace_write_probe() -> tuple[bool, str]:
    path = Path("/workspace/.forge-write-probe")
    try:
        path.write_text("ok")
        observed = path.read_text()
        path.unlink()
        return observed == "ok", "workspace write/read/delete succeeded"
    except OSError as exc:
        return False, f"workspace write failed: {exc}"


def _rootfs_write_probe() -> tuple[bool, str]:
    path = Path("/.forge-root-write-probe")
    try:
        path.write_text("unexpected")
    except OSError as exc:
        return True, f"rootfs write denied: errno={exc.errno}"
    else:
        try:
            path.unlink()
        except OSError:
            pass
        return False, "rootfs unexpectedly writable"


def _tmp_exec_probe() -> tuple[bool, str]:
    path = Path("/tmp/forge-exec-probe")
    try:
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o700)
        subprocess.run([str(path)], check=False, capture_output=True, timeout=3)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EPERM}:
            return True, f"tmp execution denied: errno={exc.errno}"
        return False, f"unexpected tmp execution error: {exc}"
    except subprocess.TimeoutExpired:
        return False, "tmp execution timed out"
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    return False, "tmp executable unexpectedly launched"


def _network_probe(host: str, port: int = 443) -> tuple[bool, str]:
    try:
        connection = socket.create_connection((host, port), timeout=1.5)
    except OSError as exc:
        return True, f"connection denied: {exc.__class__.__name__}"
    else:
        connection.close()
        return False, f"unexpected connection succeeded to {host}:{port}"


def main() -> int:
    checks: dict[str, dict[str, object]] = {}

    _record(checks, "non_root_uid", os.geteuid() != 0, f"euid={os.geteuid()}")
    _record(
        checks,
        "docker_socket_absent",
        not Path("/var/run/docker.sock").exists(),
        "/var/run/docker.sock",
    )
    _record(
        checks,
        "containerd_socket_absent",
        not Path("/run/containerd/containerd.sock").exists(),
        "/run/containerd/containerd.sock",
    )

    ok, detail = _workspace_write_probe()
    _record(checks, "workspace_writable", ok, detail)
    ok, detail = _rootfs_write_probe()
    _record(checks, "rootfs_read_only", ok, detail)
    ok, detail = _tmp_exec_probe()
    _record(checks, "tmp_noexec", ok, detail)

    secret_names = sorted(
        name
        for name in os.environ
        if any(fragment in name.upper() for fragment in SECRET_ENV_FRAGMENTS)
    )
    _record(checks, "no_secret_like_environment", not secret_names, secret_names)

    ok, detail = _network_probe("169.254.169.254", 80)
    _record(checks, "cloud_metadata_unreachable", ok, detail)
    ok, detail = _network_probe("1.1.1.1", 443)
    _record(checks, "public_internet_unreachable", ok, detail)

    passed = all(bool(check["ok"]) for check in checks.values())
    report = {
        "kind": "forge-hand-security-probe",
        "passed": passed,
        "pid": os.getpid(),
        "checks": checks,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
