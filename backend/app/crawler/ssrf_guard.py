"""
SSRF Protection & URL Normalization Utilities for CivicIQ Crawler.
Blocks localhost, loopback, private RFC1918 ranges, link-local / cloud metadata endpoints,
and unsafe non-HTTP(S) schemes before any network connection is made.
"""

import ipaddress
import socket
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import urllib3.connection
from requests.adapters import HTTPAdapter


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF or scheme safety validation."""


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata",
}

BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".arpa")


def _is_unsafe_ip(ip_str: str) -> bool:
    """Returns True if the IP address is private, loopback, link-local, multicast, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str.split("%")[0])
    except ValueError:
        return True

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # Explicitly block AWS/GCP/Azure metadata IP 169.254.169.254
    if str(ip) == "169.254.169.254":
        return True

    return False


def _default_resolver(hostname: str, port: int) -> List[str]:
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos if info and len(info) > 4 and info[4]]


def resolve_and_validate_url(
    url: str,
    resolver: Optional[Callable[[str, int], Iterable[str]]] = None,
) -> Tuple[str, str]:
    """
    Validates that `url` is a safe external HTTP/HTTPS URL (anti-SSRF) and returns
    `(cleaned_url, validated_ip)` so callers can pin the outbound TCP socket to the
    exact validated IP and prevent DNS rebinding TOCTOU attacks.
    Raises UnsafeURLError if unsafe.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("Empty or invalid URL.")

    cleaned = url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")

    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs with embedded credentials are not allowed.")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise UnsafeURLError("URL missing hostname.")

    if hostname in BLOCKED_HOSTNAMES or any(hostname.endswith(sfx) for sfx in BLOCKED_SUFFIXES):
        raise UnsafeURLError(f"Blocked internal/local hostname: {hostname}")

    # Direct IP literal check
    try:
        ipaddress.ip_address(hostname)
        if _is_unsafe_ip(hostname):
            raise UnsafeURLError(f"Blocked unsafe IP literal: {hostname}")
        return cleaned, hostname
    except ValueError:
        pass

    # DNS resolution check to prevent DNS rebinding / internal resolution
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    resolve_fn = resolver or _default_resolver
    try:
        ips = list(resolve_fn(hostname, port))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"DNS resolution failed for {hostname}: {exc}") from exc

    if not ips:
        raise UnsafeURLError(f"No IP addresses resolved for {hostname}")

    for ip in ips:
        if _is_unsafe_ip(ip):
            raise UnsafeURLError(f"Hostname {hostname} resolved to unsafe IP {ip}")

    return cleaned, ips[0]


def validate_safe_url(
    url: str,
    resolver: Optional[Callable[[str, int], Iterable[str]]] = None,
) -> str:
    """
    Validates that `url` is a safe external HTTP/HTTPS URL (anti-SSRF).
    Raises UnsafeURLError if unsafe. Returns the cleaned URL string if safe.
    """
    cleaned, _ = resolve_and_validate_url(url, resolver=resolver)
    return cleaned


class PinnedIPAdapter(HTTPAdapter):
    """
    Requests HTTPAdapter that pins outbound TCP connections to the exact IP address
    already validated by `resolve_and_validate_url`, eliminating DNS rebinding TOCTOU
    while preserving TLS SNI, X.509 certificate hostname verification, and HTTP Host headers.
    """

    def __init__(self, pinned_ips: Optional[Dict[str, str]] = None, **kwargs):
        self.pinned_ips: Dict[str, str] = pinned_ips if pinned_ips is not None else {}
        super().__init__(**kwargs)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        pool = super().get_connection_with_tls_context(request, verify, proxies=proxies, cert=cert)
        pinned_map = self.pinned_ips

        class _PinnedHTTPConnection(urllib3.connection.HTTPConnection):
            def _new_conn(self):
                ip = pinned_map.get((self.host or "").lower())
                if ip:
                    self._dns_host = ip
                return super()._new_conn()

        class _PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
            def _new_conn(self):
                ip = pinned_map.get((self.host or "").lower())
                if ip:
                    self._dns_host = ip
                return super()._new_conn()

        if pool.scheme == "https":
            pool.ConnectionCls = _PinnedHTTPSConnection
        else:
            pool.ConnectionCls = _PinnedHTTPConnection
        return pool


def normalize_url(url: str, strip_params: Optional[Tuple[str, ...]] = None) -> str:
    """
    Normalizes URL scheme/host casing, strips fragment, removes default ports,
    and optionally removes specified query parameters.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port

    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443) or port is None:
        netloc = host
    else:
        netloc = f"{host}:{port}"

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        # Preserve directory trailing slash only for root; trim redundant trailing slashes on subpaths
        path = path.rstrip("/")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if strip_params:
        strip_set = {p.lower() for p in strip_params}
        query_pairs = [(k, v) for k, v in query_pairs if k.lower() not in strip_set]
    query = urlencode(sorted(query_pairs))

    return urlunparse((scheme, netloc, path, "", query, ""))


def canonicalize_url_for_dedup(url: str) -> str:
    """
    Canonicalizes a URL for deduplication and trust matching,
    stripping common timestamp cache-busters (e.g. ?t=202409111411240, utm_*).
    """
    return normalize_url(
        url,
        strip_params=("t", "v", "_", "cb", "utm_source", "utm_medium", "utm_campaign"),
    )
