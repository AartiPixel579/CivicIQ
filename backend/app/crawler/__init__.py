"""
Configurable Official Website Crawler & Provenance Package for CivicIQ.
"""

from .ssrf_guard import (
    validate_safe_url,
    resolve_and_validate_url,
    PinnedIPAdapter,
    normalize_url,
    canonicalize_url_for_dedup,
    UnsafeURLError,
)
from .pdf_extractor import extract_pdf_pages, PdfExtractionResult
from .trusted_source_registry import TrustedSourceRegistry, trusted_source_registry
from .web_crawler import ConfigurableWebCrawler, CrawlerConfig, DiscoveredDocument, CrawlResult

__all__ = [
    "validate_safe_url",
    "resolve_and_validate_url",
    "PinnedIPAdapter",
    "normalize_url",
    "canonicalize_url_for_dedup",
    "UnsafeURLError",
    "extract_pdf_pages",
    "PdfExtractionResult",
    "TrustedSourceRegistry",
    "trusted_source_registry",
    "ConfigurableWebCrawler",
    "CrawlerConfig",
    "DiscoveredDocument",
    "CrawlResult",
]
