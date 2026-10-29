"""Public-only HTTPS downloads with per-hop DNS validation and IP pinning.

Deliberately stricter than the upstream self-hosted model URL policy. There is no
private-address/test-mode bypass. Unit tests inject transports; integration tests
use an isolated virtual public-address network and verified fixture TLS.
"""

import asyncio
import hashlib
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx

MAX_DOWNLOAD = 32 * 1024 * 1024
DEFAULT_HOSTS = "data.transportation.gov,transit.dot.gov,www.transit.dot.gov"


class AcquisitionError(ValueError):
    def __init__(self, code: str, retryable: bool = False):
        self.code, self.retryable = code, retryable
        super().__init__(code)


def hosts() -> set[str]:
    return {
        h.strip().lower()
        for h in os.getenv("DATABRIDGE_DOWNLOAD_HOSTS", DEFAULT_HOSTS).split(",")
        if h.strip()
    }


def validate_public_url(url: str, allowed: set[str]):
    try:
        if (
            not isinstance(url, str)
            or len(url) > 4096
            or any(ord(c) < 33 for c in url)
            or "\\" in url
        ):
            raise ValueError()
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError()
        if not parsed.hostname or parsed.hostname.lower() not in allowed:
            raise ValueError()
        if any(
            k.lower()
            in {
                "key",
                "api_key",
                "token",
                "access_token",
                "signature",
                "sig",
                "credential",
                "x-amz-credential",
                "x-amz-signature",
            }
            for k, _ in parse_qsl(parsed.query)
        ):
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise AcquisitionError("DOWNLOAD_BLOCKED") from None


async def resolve(host: str) -> list[str]:
    infos = await asyncio.to_thread(
        socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM
    )
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address) and (
        ip not in ipaddress.IPv6Network("2000::/3") or ip.sixtofour or ip.teredo
    ):
        return False
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


async def pinned_target(url: str, allowed: set[str]) -> tuple[str, dict, dict]:
    parsed = validate_public_url(url, allowed)
    try:
        addresses = await asyncio.wait_for(resolve(parsed.hostname), 5)
        if not addresses or any(not public_ip(a) for a in addresses):
            raise AcquisitionError("DOWNLOAD_BLOCKED")
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError("DNS_UNAVAILABLE", True) from None
    address = next((a for a in addresses if ":" not in a), addresses[0])
    netloc = f"[{address}]" if ":" in address else address
    target = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
    return (
        target,
        {"Host": parsed.hostname, "Accept-Encoding": "identity"},
        {"sni_hostname": parsed.hostname},
    )


@dataclass
class Download:
    sha256: str
    bytes: int
    final_url: str
    content_type: str
    etag: str | None
    last_modified: str | None


async def fetch(
    url: str,
    destination: Path,
    *,
    allowed: set[str] | None = None,
    limit: int = MAX_DOWNLOAD,
    api_key: str | None = None,
) -> Download:
    """One bounded transfer. Catalog keys never follow a redirect to another host."""
    allowed = hosts() if allowed is None else allowed
    initial_host = urlsplit(url).hostname
    context = ssl.create_default_context()
    if ca_file := os.getenv("DATABRIDGE_DOWNLOAD_CA_FILE"):
        context.load_verify_locations(cafile=ca_file)
    try:
        async with asyncio.timeout(90):
            async with httpx.AsyncClient(
                verify=context,
                timeout=httpx.Timeout(15, connect=8),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for hop in range(4):
                    target, headers, extensions = await pinned_target(url, allowed)
                    if api_key:
                        if urlsplit(url).hostname != initial_host:
                            raise AcquisitionError("DOWNLOAD_BLOCKED")
                        headers["X-Api-Key"] = api_key
                    async with client.stream(
                        "GET", target, headers=headers, extensions=extensions
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if hop == 3 or not response.headers.get("location"):
                                raise AcquisitionError("REDIRECT_LIMIT")
                            url = urljoin(url, response.headers["location"])
                            continue
                        if response.status_code == 429:
                            raise AcquisitionError("RATE_LIMITED", True)
                        if response.status_code in {401, 403}:
                            raise AcquisitionError("SOURCE_AUTH_REQUIRED")
                        if response.status_code != 200:
                            raise AcquisitionError(
                                "SOURCE_UNAVAILABLE", response.status_code >= 500
                            )
                        if (
                            response.headers.get("content-encoding", "identity").lower()
                            != "identity"
                        ):
                            raise AcquisitionError("HTTP_COMPRESSION_BLOCKED")
                        declared = response.headers.get("content-length")
                        if declared and (
                            not declared.isdigit() or int(declared) > limit
                        ):
                            raise AcquisitionError("TRANSFER_LIMIT")
                        sha, size = hashlib.sha256(), 0
                        with destination.open("xb") as stream:
                            async for chunk in response.aiter_raw(chunk_size=65536):
                                size += len(chunk)
                                if size > limit:
                                    raise AcquisitionError("TRANSFER_LIMIT")
                                sha.update(chunk)
                                await asyncio.to_thread(stream.write, chunk)
                        if not size or (declared is not None and size != int(declared)):
                            raise AcquisitionError("INCOMPLETE_TRANSFER", True)
                        return Download(
                            sha.hexdigest(),
                            size,
                            url,
                            response.headers.get("content-type", "").split(";")[0],
                            response.headers.get("etag"),
                            response.headers.get("last-modified"),
                        )
    except AcquisitionError:
        raise
    except (httpx.HTTPError, TimeoutError, OSError):
        raise AcquisitionError("TRANSFER_FAILED", True) from None
    raise AcquisitionError("SOURCE_UNAVAILABLE")
