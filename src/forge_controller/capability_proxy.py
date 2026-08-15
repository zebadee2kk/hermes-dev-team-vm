from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import socket
import sys
from dataclasses import dataclass

_DEFAULT_ALLOWED_HOSTS = frozenset({"auth.openai.com", "chatgpt.com"})
_MAX_HEADER_BYTES = 65536


@dataclass(frozen=True, slots=True)
class ProxyTarget:
    host: str
    port: int


class CapabilityProxyPolicy:
    """Fail-closed CONNECT policy for a service-bound HTTPS capability."""

    def __init__(self, allowed_hosts: set[str] | frozenset[str]) -> None:
        normalized = {_normalize_host(host) for host in allowed_hosts}
        if not normalized:
            raise ValueError("at least one allowed host is required")
        self.allowed_hosts = frozenset(normalized)

    def parse_target(self, authority: str) -> ProxyTarget:
        if "@" in authority:
            raise ValueError("userinfo is not allowed in CONNECT authority")
        if authority.startswith("["):
            closing = authority.find("]")
            if closing < 0 or closing + 1 >= len(authority) or authority[closing + 1] != ":":
                raise ValueError("invalid CONNECT authority")
            host = authority[1:closing]
            port_text = authority[closing + 2 :]
        else:
            if ":" not in authority:
                raise ValueError("CONNECT authority must include port")
            host, port_text = authority.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("invalid CONNECT port") from exc
        normalized = _normalize_host(host)
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            pass
        else:
            raise ValueError("IP-literal CONNECT targets are not allowed")
        if normalized not in self.allowed_hosts or port != 443:
            raise PermissionError("CONNECT target is outside the granted service capability")
        return ProxyTarget(host=normalized, port=port)

    @staticmethod
    def validate_resolved_ip(value: str) -> str:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise PermissionError("resolved target is not globally routable")
        return str(address)


class CapabilityConnectProxy:
    def __init__(self, policy: CapabilityProxyPolicy, *, connect_timeout: float = 10.0) -> None:
        self.policy = policy
        self.connect_timeout = connect_timeout

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        target: ProxyTarget | None = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10.0)
            if len(header) > _MAX_HEADER_BYTES:
                raise ValueError("proxy request headers too large")
            request_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
            parts = request_line.split()
            if len(parts) != 3 or parts[0].upper() != "CONNECT":
                await _respond(writer, 405, "CONNECT required")
                return
            target = self.policy.parse_target(parts[1])
            upstream_reader, upstream_writer = await self._connect(target)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(
                _relay(reader, upstream_writer),
                _relay(upstream_reader, writer),
            )
        except asyncio.IncompleteReadError:
            pass
        except (asyncio.LimitOverrunError, UnicodeDecodeError, ValueError):
            await _respond(writer, 400, "Bad Request")
        except PermissionError:
            await _respond(writer, 403, "Forbidden")
        except (OSError, TimeoutError, asyncio.TimeoutError):
            await _respond(writer, 502, "Bad Gateway")
        finally:
            _audit(peer, target)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _connect(
        self, target: ProxyTarget
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        loop = asyncio.get_running_loop()
        resolved = await loop.getaddrinfo(
            target.host,
            target.port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        candidates: list[tuple[int, str]] = []
        for family, _socktype, _proto, _canonname, sockaddr in resolved:
            try:
                ip = self.policy.validate_resolved_ip(sockaddr[0])
            except PermissionError:
                continue
            candidate = (family, ip)
            if candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            raise PermissionError("allowed hostname resolved only to blocked addresses")

        last_error: OSError | None = None
        for family, ip in candidates:
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(ip, target.port, family=family),
                    timeout=self.connect_timeout,
                )
            except OSError as exc:
                last_error = exc
        raise last_error or OSError("no routable target address")


async def _relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.write_eof()
            await writer.drain()
        except (AttributeError, ConnectionError, OSError):
            pass


async def _respond(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    if writer.is_closing():
        return
    body = f"{status} {reason}\n".encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
    )
    try:
        await writer.drain()
    except (ConnectionError, OSError):
        pass


def _normalize_host(value: str) -> str:
    normalized = value.strip().rstrip(".").lower()
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("invalid hostname")
    return normalized


def _audit(peer: object, target: ProxyTarget | None) -> None:
    event = {
        "event": "capability_proxy_connect",
        "peer": str(peer),
        "target": f"{target.host}:{target.port}" if target else None,
    }
    print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-capability-proxy")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3128)
    parser.add_argument(
        "--allowed-hosts",
        default=os.getenv("FORGE_PROXY_ALLOWED_HOSTS", ",".join(sorted(_DEFAULT_ALLOWED_HOSTS))),
    )
    return parser


async def _serve(args: argparse.Namespace) -> None:
    allowed_hosts = {host for host in args.allowed_hosts.split(",") if host.strip()}
    proxy = CapabilityConnectProxy(CapabilityProxyPolicy(allowed_hosts))
    server = await asyncio.start_server(proxy.handle, args.host, args.port, limit=_MAX_HEADER_BYTES)
    async with server:
        await server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(_serve(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
