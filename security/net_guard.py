"""Network Guard — URL validation and SSRF protection for fetch operations.

Blocks requests to loopback, private, link-local, reserved, and cloud
metadata IP ranges by default. Configurable allowlist for LAN access.
"""

import ipaddress
import socket
from typing import List, Optional
from urllib.parse import urlparse

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("jarvis.net_guard")

# RFC reserved / private ranges
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private class A
    ipaddress.ip_network("172.16.0.0/12"),     # private class B
    ipaddress.ip_network("192.168.0.0/16"),    # private class C
    ipaddress.ip_network("169.254.0.0/16"),    # link-local
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),         # "this" network
    ipaddress.ip_network("100.64.0.0/10"),     # carrier-grade NAT
    # Cloud metadata endpoints
    ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure metadata
    ipaddress.ip_network("169.254.169.253/32"),  # GCP metadata alternate
    ipaddress.ip_network("fd00:ec2::254/128"),   # AWS IPv6 metadata
]

# Hostnames that resolve to cloud metadata
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "metadata.google",
    "instance-data",
    "169.254.169.254",
    "169.254.169.253",
})


class SSRFBlocked(Exception):
    """Raised when a URL target is blocked by the network guard."""
    pass


def _get_allowed_networks() -> List[ipaddress.IPv4Network]:
    """Get user-configured allowed private networks from settings."""
    settings = get_settings()
    allowed = []
    for cidr in getattr(settings, "net_allow_private_networks", []):
        try:
            allowed.append(ipaddress.ip_network(cidr))
        except ValueError:
            logger.warning("Invalid CIDR in net_allow_private_networks: %s", cidr)
    return allowed


def _is_ip_blocked(ip_str: str, allowed_networks: List[ipaddress.IPv4Network]) -> bool:
    """Check if an IP address falls in a blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # invalid IP = blocked

    for allowed in allowed_networks:
        if addr in allowed:
            return False

    for blocked in _BLOCKED_NETWORKS:
        if addr in blocked:
            return True

    return False


def validate_url(url: str, allow_redirects: bool = False) -> str:
    """Validate a URL for SSRF safety.

    Checks:
    - Scheme is http or https
    - Hostname is not in blocked list
    - Hostname resolves to a non-blocked IP
    - No credentials in URL
    - Not a cloud metadata endpoint

    Args:
        url: The URL to validate.
        allow_redirects: If True, only validates the initial URL (redirect
            validation must be done per-hop by the caller).

    Returns:
        The validated URL.

    Raises:
        SSRFBlocked: If the URL is blocked.
        ValueError: If the URL is malformed.
    """
    parsed = urlparse(url)

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlocked(f"Blocked URL scheme: {parsed.scheme}")

    # Credentials check
    if parsed.username or parsed.password:
        raise SSRFBlocked("URLs with credentials are not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlocked("URL has no hostname")

    # Blocked hostname check (before DNS resolution)
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise SSRFBlocked(f"Blocked hostname: {hostname}")

    # Block common cloud metadata patterns in hostname
    hostname_lower = hostname.lower()
    if "metadata" in hostname_lower and ("google" in hostname_lower or "azure" in hostname_lower or "aws" in hostname_lower):
        raise SSRFBlocked(f"Cloud metadata hostname blocked: {hostname}")
    if hostname_lower.startswith("instance-data"):
        raise SSRFBlocked(f"Cloud metadata hostname blocked: {hostname}")

    # Resolve DNS
    allowed_networks = _get_allowed_networks()
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise SSRFBlocked(f"DNS resolution failed for: {hostname}")

    for family, _, _, _, sockaddr in infos:
        ip_str = str(sockaddr[0])
        if _is_ip_blocked(ip_str, allowed_networks):
            raise SSRFBlocked(f"Blocked IP {ip_str} for hostname {hostname}")

    return url


def validate_redirect_url(location: str, original_url: str) -> str:
    """Validate a redirect Location header URL.

    Performs the same checks as validate_url on the redirect target.
    """
    return validate_url(location)
