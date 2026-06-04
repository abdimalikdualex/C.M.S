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


def _on_render() -> bool:
    return bool(os.environ.get("RENDER", "").strip())


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


def _bare_render_pg_host(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("dpg-") and "." not in host:
        return host
    return None


def resolve_render_postgres_url(url: str) -> str:
    """
    Bare Render internal hosts (dpg-…-a) sometimes fail DNS.
    Expand to the public FQDN (dpg-…-a.<region>-postgres.render.com).
    """
    if not url:
        return url
    bare = _bare_render_pg_host(url)
    if not bare:
        return url

    # On Render, use configured region or default — do not rely on DNS at import time.
    if _on_render():
        region = os.environ.get("RENDER_POSTGRES_REGION", "oregon").strip().lower()
        return _replace_hostname(url, f"{bare}.{region}-postgres.render.com")

    region = os.environ.get("RENDER_POSTGRES_REGION", "").strip().lower()
    regions = (region,) if region else _RENDER_PG_REGIONS
    for reg in regions:
        if not reg:
            continue
        fqdn = f"{bare}.{reg}-postgres.render.com"
        if _host_resolves(fqdn):
            return _replace_hostname(url, fqdn)
    return url


def postgres_sslmode_for_host(hostname: str) -> str:
    """Render external hosts need SSL; bare internal slugs use prefer on private network."""
    host = (hostname or "").lower()
    if host.endswith(".postgres.render.com"):
        return "require"
    if host.startswith("dpg-") and "." not in host:
        return "prefer"
    if _on_render() and host.startswith("dpg-"):
        return "require"
    return "prefer"
