"""
Configurable Official Website Crawler for CivicIQ.
Starts from a client-configured root URL, follows relevant HTML links,
discovers linked PDFs (including external-domain PDFs linked from trusted pages),
enforces SSRF protection, rate limiting, file size limits, conditional HTTP headers,
and preserves full document provenance.
"""

import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .pdf_extractor import extract_pdf_pages
from .ssrf_guard import (
    PinnedIPAdapter,
    UnsafeURLError,
    canonicalize_url_for_dedup,
    normalize_url,
    resolve_and_validate_url,
    validate_safe_url,
)

logger = logging.getLogger("crawler.web_crawler")


@dataclass
class CrawlerConfig:
    root_url: str
    department_id: str = "engineering"
    client_id: str = "default"
    allowed_domains: List[str] = field(default_factory=list)
    follow_external_pdfs: bool = True
    max_depth: int = 2
    max_pages: int = 80
    delay_seconds: float = 0.5
    timeout_seconds: int = 15
    max_retries: int = 2
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_html_bytes: int = 5 * 1024 * 1024
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    enable_ocr: bool = True
    user_agent: str = "CivicIQ-Municipal-Crawler/1.0 (+official-document-sync)"

    def __post_init__(self):
        if not self.allowed_domains and self.root_url:
            host = (urlparse(self.root_url).hostname or "").lower()
            if host:
                self.allowed_domains = [host]
                if host.startswith("www."):
                    self.allowed_domains.append(host[4:])


@dataclass
class DiscoveredDocument:
    document_id: str
    url: str
    canonical_url: str
    referring_url: str
    title: str
    content_type: str
    source_type: str  # "html" | "pdf"
    retrieval_date: str
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    content_hash: str = ""
    pages: List[Tuple[int, str]] = field(default_factory=list)  # (page_num or None/1, text)
    extraction_status: str = "extracted"
    needs_ocr: bool = False
    status_code: int = 200
    unchanged: bool = False


@dataclass
class FailedFetch:
    url: str
    canonical_url: str
    referring_url: str
    status_code: Optional[int]
    error: str
    is_permanent_not_found: bool = False


@dataclass
class CrawlResult:
    root_url: str
    crawl_healthy: bool
    pages_discovered: int = 0
    pdfs_discovered: int = 0
    documents: List[DiscoveredDocument] = field(default_factory=list)
    unchanged_urls: List[str] = field(default_factory=list)
    failed_fetches: List[FailedFetch] = field(default_factory=list)
    skipped_urls: List[Tuple[str, str]] = field(default_factory=list)
    seen_canonical_urls: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)


class ConfigurableWebCrawler:
    """
    Reusable, SSRF-hardened municipal website crawler.
    """

    def __init__(
        self,
        config: CrawlerConfig,
        session: Optional[requests.Session] = None,
        url_validator: Optional[Callable[[str], str]] = None,
    ):
        self.config = config
        self._pinned_ips: Dict[str, str] = {}
        self.session = session or requests.Session()
        if isinstance(self.session, requests.Session):
            adapter = PinnedIPAdapter(pinned_ips=self._pinned_ips)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": self.config.user_agent})
        self._custom_validator = url_validator
        self.validate_url = url_validator or validate_safe_url

    def _is_domain_allowed(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == d.lower() or host.endswith("." + d.lower()) for d in self.config.allowed_domains)

    def _matches_scope(
        self,
        url: str,
        depth: int,
        link_text: str = "",
        referring_url: str = "",
    ) -> Tuple[bool, str]:
        if depth == 0:
            return True, "root_url"
        combined = f"{url} {link_text}".lower()
        for pat in self.config.exclude_patterns:
            if pat.lower() in combined:
                return False, f"excluded by pattern '{pat}'"

        if self.config.include_patterns:
            if any(pat.lower() in combined for pat in self.config.include_patterns):
                return True, "matched include_pattern"
            # If referring_url is a dedicated department subpage (not a generic multi-dept index),
            # allow child PDFs on that department page unless excluded above.
            ref_path = (urlparse(referring_url).path or "").lower()
            if f"/{self.config.department_id}" in ref_path and self._looks_like_pdf(url):
                return True, f"linked from {self.config.department_id} page"
            return False, "outside department include_patterns"
        return True, "no include_patterns filter"

    def _looks_like_pdf(self, url: str, content_type: str = "") -> bool:
        ct = (content_type or "").lower()
        if "application/pdf" in ct:
            return True
        path = (urlparse(url).path or "").lower()
        return path.endswith(".pdf")

    def _fetch_with_ssrf_redirects(
        self,
        url: str,
        known_etag: Optional[str] = None,
        known_last_modified: Optional[str] = None,
        max_redirects: int = 5,
    ) -> Tuple[Optional[requests.Response], str, Optional[str]]:
        """
        Fetches a URL with SSRF validation on the initial URL and every redirect hop,
        with retry support for transient network/5xx errors.
        Returns (response_or_None, final_url, error_or_None).
        """
        current_url = url
        headers: Dict[str, str] = {}
        if known_etag:
            headers["If-None-Match"] = known_etag
        if known_last_modified:
            headers["If-Modified-Since"] = known_last_modified

        for attempt in range(self.config.max_retries + 1):
            try:
                hop_url = current_url
                for _ in range(max_redirects + 1):
                    if self._custom_validator is not None:
                        self._custom_validator(hop_url)
                    else:
                        _, validated_ip = resolve_and_validate_url(hop_url)
                        hop_host = (urlparse(hop_url).hostname or "").strip().lower().rstrip(".")
                        if hop_host and validated_ip:
                            self._pinned_ips[hop_host] = validated_ip
                    resp = self.session.get(
                        hop_url,
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                        allow_redirects=False,
                        stream=True,
                    )
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location")
                        resp.close()
                        if not loc:
                            return None, hop_url, f"Redirect {resp.status_code} missing Location header"
                        hop_url = normalize_url(urljoin(hop_url, loc))
                        continue
                    return resp, hop_url, None
                return None, hop_url, "Exceeded maximum redirect hops"
            except UnsafeURLError as exc:
                return None, current_url, f"SSRF blocked: {exc}"
            except requests.RequestException as exc:
                if attempt < self.config.max_retries:
                    time.sleep(min(1.0 * (attempt + 1), 3.0))
                    continue
                return None, current_url, f"Request failed: {exc}"

        return None, current_url, "Unknown fetch error"

    def _read_bounded_bytes(self, resp: requests.Response, max_bytes: int) -> bytes:
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > max_bytes:
            raise ValueError(f"Content-Length {cl} exceeds limit {max_bytes}")

        chunks: List[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"Response body exceeded max allowed bytes ({max_bytes})")
            chunks.append(chunk)
        return b"".join(chunks)

    def _extract_html(self, html_bytes: bytes, page_url: str) -> Tuple[str, str, List[Tuple[str, str]]]:
        """Returns (title, clean_text, [(link_url, link_text), ...])."""
        soup = BeautifulSoup(html_bytes, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else "") or page_url

        links: List[Tuple[str, str]] = []
        for tag in soup.find_all("a", href=True):
            href = (tag.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_url = normalize_url(urljoin(page_url, href))
            link_text = tag.get_text(" ", strip=True)
            links.append((abs_url, link_text))

        for tag in soup.find_all(["iframe", "embed"], src=True):
            src = (tag.get("src") or "").strip()
            if src:
                abs_url = normalize_url(urljoin(page_url, src))
                links.append((abs_url, ""))

        for noise in soup(["script", "style", "noscript", "svg"]):
            noise.decompose()

        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        return title, text, links

    def crawl(
        self,
        known_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> CrawlResult:
        """
        Executes bounded breadth-first crawl from `config.root_url`.
        `known_metadata` maps canonical_url -> {"etag", "last_modified", "content_hash"}.
        """
        known = known_metadata or {}
        result = CrawlResult(root_url=self.config.root_url, crawl_healthy=False)

        root_norm = normalize_url(self.config.root_url)
        try:
            self.validate_url(root_norm)
        except UnsafeURLError as exc:
            result.errors.append(f"Unsafe root_url: {exc}")
            return result

        # Queue entries: (url, referring_url, depth, is_external_pdf_candidate)
        queue: deque[Tuple[str, str, int, bool]] = deque([(root_norm, root_norm, 0, False)])
        # Also schedule previously known URLs for incremental conditional re-check (ETag / Last-Modified)
        for known_canon, meta in known.items():
            known_url = meta.get("url") or known_canon
            if known_url and canonicalize_url_for_dedup(known_url) != canonicalize_url_for_dedup(root_norm):
                ref_url = meta.get("referring_url") or root_norm
                is_ext = not self._is_domain_allowed(known_url) and self._looks_like_pdf(known_url)
                queue.append((normalize_url(known_url), ref_url, 1, is_ext))

        visited_canon: Set[str] = set()
        pages_fetched = 0

        while queue and pages_fetched < self.config.max_pages:
            url, referring_url, depth, is_ext_pdf = queue.popleft()
            canon = canonicalize_url_for_dedup(url)
            if canon in visited_canon:
                continue
            visited_canon.add(canon)
            result.seen_canonical_urls.add(canon)

            if pages_fetched > 0 and self.config.delay_seconds > 0:
                time.sleep(self.config.delay_seconds)

            prev = known.get(canon, {})
            resp, final_url, err = self._fetch_with_ssrf_redirects(
                url,
                known_etag=prev.get("etag"),
                known_last_modified=prev.get("last_modified"),
            )
            pages_fetched += 1

            if err or resp is None:
                result.failed_fetches.append(
                    FailedFetch(
                        url=url,
                        canonical_url=canon,
                        referring_url=referring_url,
                        status_code=None,
                        error=err or "No response",
                    )
                )
                result.errors.append(f"{url}: {err}")
                continue

            try:
                status = resp.status_code
                now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                final_canon = canonicalize_url_for_dedup(final_url)
                result.seen_canonical_urls.add(final_canon)

                if status == 304:
                    if depth == 0:
                        result.crawl_healthy = True
                    result.unchanged_urls.append(final_url)
                    continue

                if status in (404, 410):
                    result.failed_fetches.append(
                        FailedFetch(
                            url=url,
                            canonical_url=canon,
                            referring_url=referring_url,
                            status_code=status,
                            error=f"HTTP {status}",
                            is_permanent_not_found=True,
                        )
                    )
                    continue

                if status >= 400:
                    result.failed_fetches.append(
                        FailedFetch(
                            url=url,
                            canonical_url=canon,
                            referring_url=referring_url,
                            status_code=status,
                            error=f"HTTP {status}",
                        )
                    )
                    continue

                content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                is_pdf = self._looks_like_pdf(final_url, content_type)
                is_html = content_type in ("text/html", "application/xhtml+xml", "") and not is_pdf

                if not is_pdf and not is_html:
                    logger.debug(f"Skipping unsupported content type {content_type} at {final_url}")
                    continue

                if is_ext_pdf and not is_pdf:
                    # External non-PDF pages are not crawled
                    result.skipped_urls.append((final_url, "external non-PDF blocked"))
                    continue

                if is_html and not self._is_domain_allowed(final_url):
                    # Reject HTML responses whose final redirect destination is outside allowed_domains
                    result.skipped_urls.append((final_url, "redirected outside allowed_domains"))
                    continue

                if is_pdf and not self._is_domain_allowed(final_url) and not self.config.follow_external_pdfs:
                    result.skipped_urls.append((final_url, "external PDF blocked by follow_external_pdfs=False"))
                    continue

                max_bytes = self.config.max_pdf_bytes if is_pdf else self.config.max_html_bytes
                raw_bytes = self._read_bounded_bytes(resp, max_bytes)
                content_hash = hashlib.sha256(raw_bytes).hexdigest()
                etag = resp.headers.get("ETag")
                last_modified = resp.headers.get("Last-Modified")

                if depth == 0:
                    result.crawl_healthy = True

                doc_id = f"{self.config.department_id}_{hashlib.sha256(final_canon.encode('utf-8')).hexdigest()[:16]}"

                if prev.get("content_hash") and prev["content_hash"] == content_hash and not is_html:
                    result.unchanged_urls.append(final_url)
                    continue

                if is_pdf:
                    result.pdfs_discovered += 1
                    pdf_res = extract_pdf_pages(raw_bytes, enable_ocr=self.config.enable_ocr)
                    title = urlparse(final_url).path.rsplit("/", 1)[-1] or final_url
                    result.documents.append(
                        DiscoveredDocument(
                            document_id=doc_id,
                            url=final_url,
                            canonical_url=final_canon,
                            referring_url=referring_url,
                            title=title,
                            content_type=content_type or "application/pdf",
                            source_type="pdf",
                            retrieval_date=now_iso,
                            last_modified=last_modified,
                            etag=etag,
                            content_hash=content_hash,
                            pages=pdf_res.pages,
                            extraction_status=pdf_res.extraction_status,
                            needs_ocr=pdf_res.needs_ocr,
                            status_code=status,
                        )
                    )
                else:
                    result.pages_discovered += 1
                    title, text, links = self._extract_html(raw_bytes, final_url)

                    # Still follow links even if HTML text is unchanged
                    if depth < self.config.max_depth:
                        for link_url, link_text in links:
                            link_canon = canonicalize_url_for_dedup(link_url)
                            if link_canon in visited_canon:
                                continue
                            in_scope, scope_reason = self._matches_scope(
                                link_url,
                                depth + 1,
                                link_text=link_text,
                                referring_url=final_url,
                            )
                            if self._looks_like_pdf(link_url):
                                if self._is_domain_allowed(link_url) or self.config.follow_external_pdfs:
                                    if in_scope:
                                        queue.append((link_url, final_url, depth + 1, not self._is_domain_allowed(link_url)))
                                    else:
                                        result.skipped_urls.append((link_url, scope_reason))
                            elif self._is_domain_allowed(link_url):
                                if in_scope:
                                    queue.append((link_url, final_url, depth + 1, False))
                                else:
                                    result.skipped_urls.append((link_url, scope_reason))

                    if prev.get("content_hash") and prev["content_hash"] == content_hash:
                        result.unchanged_urls.append(final_url)
                        continue

                    if text.strip():
                        result.documents.append(
                            DiscoveredDocument(
                                document_id=doc_id,
                                url=final_url,
                                canonical_url=final_canon,
                                referring_url=referring_url,
                                title=title,
                                content_type=content_type or "text/html",
                                source_type="html",
                                retrieval_date=now_iso,
                                last_modified=last_modified,
                                etag=etag,
                                content_hash=content_hash,
                                pages=[(1, text)],
                                extraction_status="extracted",
                                needs_ocr=False,
                                status_code=status,
                            )
                        )
            except Exception as exc:
                result.failed_fetches.append(
                    FailedFetch(
                        url=url,
                        canonical_url=canon,
                        referring_url=referring_url,
                        status_code=getattr(resp, "status_code", None),
                        error=str(exc),
                    )
                )
                result.errors.append(f"{url}: {exc}")
            finally:
                resp.close()

        return result
