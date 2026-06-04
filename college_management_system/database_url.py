"""Resolve Render Postgres connection URLs to a reachable hostname."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse, urlunparse

_RENDER_PG_REGIONS = (
    "oregon",
    "frankfurt",
    "singapore",
    "ohio",
    "virginia",
)


def _host_resolves(hostname: str, timeout: float = 1.5) -> bool:
    """Quick DNS check so app startup is not delayed by unreachable regions."""
    prev = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(hostname, None)
        return True
    except OSError:
        return False
    finally:
        socket.setdefaulttimeout(prev)


def _replace_hostname(url: str, new_hostname: str) -> str:
    parsed = urlparse(url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{userinfo}{new_hostname}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def resolve_render_postgres_url(url: str) -> str:
    """
    Bare Render internal hosts (dpg-…-a) sometimes fail DNS during build or
    on misconfigured deploys. When that happens, expand to the public FQDN
    (dpg-…-a.<region>-postgres.render.com) if it resolves.
    """
    if not url:
        return url
    host = (urlparse(url).hostname or "").lower()
    if not host.startswith("dpg-") or "." in host:
        return url

    region = os.environ.get("RENDER_POSTGRES_REGION", "").strip().lower()
    regions = (region,) if region else _RENDER_PG_REGIONS
    for reg in regions:
        if not reg:
            continue
        fqdn = f"{host}.{reg}-postgres.render.com"
        if _host_resolves(fqdn):
            return _replace_hostname(url, fqdn)
    return url
