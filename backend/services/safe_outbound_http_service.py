"""Pinned, redirect-aware HTTP fetching for attacker-controlled public URLs."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp

from backend.utils.public_urls import PublicUrlValidationError, normalize_public_url

SAFE_FETCH_USER_AGENT = "PapersWithCode-SafeFetch/1.0"
SUPPORTED_PORTS = frozenset({80, 443})


class SafeOutboundHttpError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        origin_status_code: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.origin_status_code = origin_status_code


@dataclass(frozen=True)
class SafeFetchResult:
    url: str
    status_code: int
    content_type: str
    body: bytes


def _address_is_public(value: str) -> bool:
    address = ip_address(value)
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_global
    return address.is_global


def _validated_url(value: str) -> str:
    try:
        normalized = normalize_public_url(value)
        parsed = urlsplit(normalized)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except PublicUrlValidationError as exc:
        raise SafeOutboundHttpError(422, "The outbound URL is invalid") from exc
    if parsed.fragment:
        normalized = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
        )
    if port not in SUPPORTED_PORTS:
        raise SafeOutboundHttpError(422, "The outbound URL port is not supported")
    host = parsed.hostname or ""
    try:
        literal = ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _address_is_public(host):
        raise SafeOutboundHttpError(403, "The outbound destination is not public")
    if literal is None and ("." not in host or host.isdigit()):
        raise SafeOutboundHttpError(422, "The outbound hostname is ambiguous")
    return normalized


async def resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror:
        raise SafeOutboundHttpError(
            502, "The outbound hostname could not be resolved"
        ) from None
    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not _address_is_public(value) for value in addresses):
        raise SafeOutboundHttpError(403, "The outbound destination is not public")
    return addresses


class PinnedResolver(aiohttp.abc.AbstractResolver):
    """Resolve exactly one validated hostname to its already-checked addresses."""

    def __init__(self, host: str, addresses: tuple[str, ...]):
        self.host = host
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        if host.rstrip(".").lower() != self.host.rstrip(".").lower():
            raise OSError("Unexpected outbound hostname")
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": socket.IPPROTO_TCP,
                "flags": socket.AI_NUMERICHOST,
            }
            for address in self.addresses
        ]

    async def close(self) -> None:
        return None


async def _fetch_one_hop(
    url: str,
    *,
    allowed_content_types: frozenset[str],
    max_bytes: int,
    timeout: aiohttp.ClientTimeout,
) -> tuple[int, str, bytes, str | None]:
    parsed = urlsplit(url)
    host = parsed.hostname
    assert host is not None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await resolve_public_addresses(host, port)
    connector = aiohttp.TCPConnector(
        resolver=PinnedResolver(host, addresses),
        ttl_dns_cache=0,
        use_dns_cache=False,
    )
    try:
        async with (
            aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                auto_decompress=True,
                headers={"User-Agent": SAFE_FETCH_USER_AGENT},
            ) as client,
            client.get(url, allow_redirects=False) as response,
        ):
            location = response.headers.get("Location")
            if 300 <= response.status < 400:
                return response.status, "", b"", location
            if not 200 <= response.status < 300:
                raise SafeOutboundHttpError(
                    502,
                    "The outbound origin returned an error",
                    origin_status_code=response.status,
                )
            content_type = (
                response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            )
            if content_type not in allowed_content_types:
                raise SafeOutboundHttpError(
                    415, "The outbound content type is not allowed"
                )
            body = bytearray()
            while True:
                remaining = max_bytes + 1 - len(body)
                chunk = await response.content.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise SafeOutboundHttpError(
                        413, "The outbound response is too large"
                    )
            return response.status, content_type, bytes(body), None
    except SafeOutboundHttpError:
        raise
    except (TimeoutError, aiohttp.ClientError):
        raise SafeOutboundHttpError(502, "The outbound request failed") from None


async def fetch_public_resource(
    url: str,
    *,
    allowed_content_types: frozenset[str],
    max_bytes: int,
    timeout_seconds: float,
    max_redirects: int = 3,
    allowed_hosts: frozenset[str] | None = None,
) -> SafeFetchResult:
    if max_bytes <= 0 or timeout_seconds <= 0 or max_redirects < 0:
        raise ValueError("Safe fetch bounds must be positive")
    current = _validated_url(url)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    for redirects in range(max_redirects + 1):
        host = urlsplit(current).hostname
        if allowed_hosts is not None and host not in allowed_hosts:
            raise SafeOutboundHttpError(403, "The outbound hostname is not approved")
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise SafeOutboundHttpError(502, "The outbound request timed out")
        status_code, content_type, body, location = await _fetch_one_hop(
            current,
            allowed_content_types=allowed_content_types,
            max_bytes=max_bytes,
            timeout=aiohttp.ClientTimeout(total=remaining),
        )
        if location is None:
            return SafeFetchResult(current, status_code, content_type, body)
        if redirects == max_redirects:
            raise SafeOutboundHttpError(409, "The outbound redirect limit was exceeded")
        current = _validated_url(urljoin(current, location))
    raise AssertionError("unreachable")
