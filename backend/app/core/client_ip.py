"""Client IP resolution that trusts forwarded headers only from known proxies."""

from __future__ import annotations

import ipaddress


def parse_trusted_networks(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            if "/" not in token:
                address = ipaddress.ip_address(token)
                token = f"{address}/{32 if address.version == 4 else 128}"
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _normalize_ip(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().strip('"')
    if not token:
        return None
    if token.startswith("[") and "]" in token:
        token = token[1:token.index("]")]
    elif token.count(":") == 1 and "." in token:
        token = token.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(token))
    except ValueError:
        return None


def _is_trusted(host: str | None, networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]) -> bool:
    normalized = _normalize_ip(host)
    if not normalized:
        return False
    address = ipaddress.ip_address(normalized)
    return any(address in network for network in networks)


def resolve_client_ip(
    peer: str | None,
    forwarded_for: str | None,
    real_ip: str | None,
    trusted_proxies: str,
) -> str:
    """Return the visitor IP.

    Forwarded headers are ignored unless the TCP peer is a trusted proxy.
    ``X-Forwarded-For`` is read from the right so a client-supplied prefix
    cannot hide the address the trusted proxy appended.
    """
    peer_host = (peer or "").strip() or "unknown"
    networks = parse_trusted_networks(trusted_proxies)
    if not _is_trusted(peer_host, networks):
        return peer_host

    if forwarded_for:
        hops = [hop for raw in forwarded_for.split(",") if (hop := _normalize_ip(raw))]
        for hop in reversed(hops):
            if not _is_trusted(hop, networks):
                return hop
        if hops:
            return hops[0]

    real = _normalize_ip(real_ip)
    if real:
        return real
    return peer_host


def client_ip_budget_applies(client_ip: str, trusted_proxies: str) -> bool:
    """Per-IP budgets are unsafe when every visitor still looks like the proxy."""
    return not _is_trusted(client_ip, parse_trusted_networks(trusted_proxies))
