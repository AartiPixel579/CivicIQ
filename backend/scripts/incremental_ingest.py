"""
Safe, Non-Destructive Incremental Website Ingestion Pipeline for CivicIQ.
- Discovers pages & PDFs from administrator-configured trusted root URL
- Checks ETag, Last-Modified, and SHA-256 content hashes to skip unchanged docs
- Stages new document versions (is_active=False), validates, and atomically activates
- Preserves existing knowledge on temporary outages
- Marks removed URLs inactive only after confirmed consecutive misses on healthy crawls
- Records full crawl audit history in crawl_runs
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.app.config import (
    CHUNK_OVERLAP_WORDS,
    CHUNK_SIZE_WORDS,
    CRAWL_DELAY_SECONDS,
    CRAWL_MAX_DEPTH,
    CRAWL_MAX_HTML_MB,
    CRAWL_MAX_PAGES,
    CRAWL_MAX_PDF_MB,
    CRAWL_MAX_RETRIES,
    CRAWL_MISS_THRESHOLD,
    CRAWL_TIMEOUT_SECONDS,
    DEPARTMENTS_DIR,
    TRUSTED_ROOT_URL,
)
from backend.app.crawler import (
    ConfigurableWebCrawler,
    CrawlerConfig,
    CrawlResult,
    DiscoveredDocument,
    TrustedSourceRegistry,
    canonicalize_url_for_dedup,
    trusted_source_registry,
)
from backend.app.vector_store import UnifiedVectorStore, vector_store as shared_vector_store

logger = logging.getLogger("incremental_ingest")


def _chunk_words(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> List[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words)]
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += max(1, chunk_size - overlap)
    return chunks


def build_chunks_for_document(
    doc: DiscoveredDocument,
    department_id: str,
    client_id: str,
    version_id: int,
) -> List[Dict[str, Any]]:
    """
    Converts a DiscoveredDocument (with page-level text) into provenance-rich chunk dicts.
    """
    chunks: List[Dict[str, Any]] = []
    canon_hash = hashlib.md5(doc.canonical_url.encode("utf-8")).hexdigest()[:8]
    global_idx = 0

    for page_num, page_text in doc.pages:
        clean_text = (page_text or "").strip()
        if not clean_text:
            continue
        header_prefix = f"DOCUMENT: {doc.title}\nOFFICIAL URL: {doc.url}\n"
        if doc.source_type == "pdf" and page_num:
            header_prefix += f"PDF PAGE: {page_num}\n"
        page_chunks = _chunk_words(clean_text)
        for p_chunk in page_chunks:
            content = f"{header_prefix}\n{p_chunk}" if global_idx == 0 or doc.source_type == "pdf" else p_chunk
            chunk_id = f"{department_id}_{canon_hash}_v{version_id}_{global_idx}"
            chunks.append({
                "id": chunk_id,
                "client_id": client_id,
                "department_id": department_id,
                "document_id": doc.document_id,
                "url": doc.url,
                "referring_url": doc.referring_url,
                "title": doc.title,
                "category": "Official PDF" if doc.source_type == "pdf" else "Official Web Page",
                "content_type": doc.content_type,
                "source_type": doc.source_type,
                "pdf_page_number": page_num if doc.source_type == "pdf" else None,
                "chunk_index": global_idx,
                "content": content,
                "word_count": len(content.split()),
                "retrieval_date": doc.retrieval_date,
                "last_modified": doc.last_modified,
                "etag": doc.etag,
                "content_hash": doc.content_hash,
                "is_active": True,
                "version_id": version_id,
                "visibility": "public",
                "document_type": "official_document" if doc.source_type == "pdf" else "guideline",
                "service": None,
                "verification_status": "needs_ocr" if doc.needs_ocr else "verified",
            })
            global_idx += 1

    return chunks


def load_crawler_config_for_department(
    department_id: str = "engineering",
    departments_dir: Path = DEPARTMENTS_DIR,
    root_url_override: Optional[str] = None,
) -> CrawlerConfig:
    config_path = Path(departments_dir) / department_id / "config.json"
    ts_cfg: Dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            ts_cfg = raw.get("trusted_sources", {}) or {}
        except Exception as exc:
            logger.warning(f"Could not parse {config_path}: {exc}")

    root_url = root_url_override or ts_cfg.get("root_url") or TRUSTED_ROOT_URL
    return CrawlerConfig(
        root_url=root_url,
        department_id=department_id,
        client_id=ts_cfg.get("client_id", "default"),
        allowed_domains=ts_cfg.get("allowed_domains", []),
        follow_external_pdfs=bool(ts_cfg.get("follow_external_pdfs", True)),
        max_depth=int(ts_cfg.get("crawl_depth", CRAWL_MAX_DEPTH)),
        max_pages=int(ts_cfg.get("max_pages", CRAWL_MAX_PAGES)),
        delay_seconds=float(ts_cfg.get("delay_seconds", CRAWL_DELAY_SECONDS)),
        timeout_seconds=int(ts_cfg.get("timeout_seconds", CRAWL_TIMEOUT_SECONDS)),
        max_retries=int(ts_cfg.get("max_retries", CRAWL_MAX_RETRIES)),
        max_pdf_bytes=int(ts_cfg.get("max_pdf_mb", CRAWL_MAX_PDF_MB)) * 1024 * 1024,
        max_html_bytes=int(ts_cfg.get("max_html_mb", CRAWL_MAX_HTML_MB)) * 1024 * 1024,
        include_patterns=ts_cfg.get("include_patterns", []),
        exclude_patterns=ts_cfg.get("exclude_patterns", []),
    )


def run_incremental_ingestion(
    department_id: str = "engineering",
    departments_dir: Path = DEPARTMENTS_DIR,
    store: Optional[UnifiedVectorStore] = None,
    registry: Optional[TrustedSourceRegistry] = None,
    crawler_factory: Optional[Callable[[CrawlerConfig], ConfigurableWebCrawler]] = None,
    root_url_override: Optional[str] = None,
    miss_threshold: int = CRAWL_MISS_THRESHOLD,
) -> Dict[str, Any]:
    """
    Runs a complete incremental website crawl and safe staged index update.
    Guarantees existing active knowledge remains intact if crawl or indexing fails.
    """
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    vec_store = store or shared_vector_store
    src_registry = registry or trusted_source_registry
    cfg = load_crawler_config_for_department(
        department_id=department_id,
        departments_dir=departments_dir,
        root_url_override=root_url_override,
    )

    # Seed admin-configured root URL
    src_registry.seed_from_config(
        department_id=department_id,
        root_url=cfg.root_url,
        client_id=cfg.client_id,
    )

    known_sources = src_registry.get_known_sources(department_id, active_only=True)
    known_meta = {
        s["canonical_url"]: {
            "url": s["url"],
            "referring_url": s["referring_url"],
            "etag": s["etag"],
            "last_modified": s["last_modified"],
            "content_hash": s["content_hash"],
            "discovered_via": s["discovered_via"],
        }
        for s in known_sources
    }

    crawler = crawler_factory(cfg) if crawler_factory else ConfigurableWebCrawler(cfg)
    crawl_res: CrawlResult = crawler.crawl(known_metadata=known_meta)

    active_versions = vec_store.get_active_document_versions(department_id)

    new_docs = 0
    updated_docs = 0
    unchanged_docs = len(crawl_res.unchanged_urls)
    inactive_docs = 0
    failed_docs = len(crawl_res.failed_fetches)
    errors = list(crawl_res.errors)

    # 1. Process discovered/updated documents via safe staging + atomic activation
    for doc in crawl_res.documents:
        prev_info = active_versions.get(doc.document_id)
        if prev_info and prev_info.get("content_hash") == doc.content_hash:
            unchanged_docs += 1
            src_registry.record_discovered_source(
                department_id=department_id,
                url=doc.url,
                source_type=doc.source_type,
                referring_url=doc.referring_url,
                discovered_via="crawler",
                client_id=cfg.client_id,
                last_status_code=doc.status_code,
                etag=doc.etag,
                last_modified=doc.last_modified,
                content_hash=doc.content_hash,
                active_version_id=prev_info.get("version_id", 1),
            )
            continue

        new_ver = (prev_info.get("version_id", 0) + 1) if prev_info else 1
        doc_chunks = build_chunks_for_document(
            doc=doc,
            department_id=department_id,
            client_id=cfg.client_id,
            version_id=new_ver,
        )

        # Register trusted source even for scanned PDFs needing OCR
        if not doc_chunks:
            # Scanned PDF or empty page text: preserve source metadata without wiping active chunks
            src_registry.record_discovered_source(
                department_id=department_id,
                url=doc.url,
                source_type=doc.source_type,
                referring_url=doc.referring_url,
                discovered_via="crawler",
                client_id=cfg.client_id,
                last_status_code=doc.status_code,
                etag=doc.etag,
                last_modified=doc.last_modified,
                content_hash=doc.content_hash,
                active_version_id=prev_info.get("version_id", 1) if prev_info else 1,
                last_error="No extractable text (scanned PDF or empty)" if doc.needs_ocr else None,
            )
            continue

        try:
            activated = vec_store.stage_and_activate_document_chunks(
                department_id=department_id,
                document_id=doc.document_id,
                chunks=doc_chunks,
                new_version_id=new_ver,
            )
            if activated:
                if prev_info:
                    updated_docs += 1
                else:
                    new_docs += 1
                src_registry.record_discovered_source(
                    department_id=department_id,
                    url=doc.url,
                    source_type=doc.source_type,
                    referring_url=doc.referring_url,
                    discovered_via="crawler",
                    client_id=cfg.client_id,
                    last_status_code=doc.status_code,
                    etag=doc.etag,
                    last_modified=doc.last_modified,
                    content_hash=doc.content_hash,
                    active_version_id=new_ver,
                )
        except Exception as exc:
            failed_docs += 1
            errors.append(f"Staging failed for {doc.url}: {exc}")

    # Refresh unchanged source timestamps
    for u_url in crawl_res.unchanged_urls:
        src_registry.record_discovered_source(
            department_id=department_id,
            url=u_url,
            source_type="pdf" if u_url.lower().endswith(".pdf") else "html",
            discovered_via="crawler",
            client_id=cfg.client_id,
            last_status_code=304,
        )

    # 2. Handle failed fetches & safe reconciliation
    for fail in crawl_res.failed_fetches:
        if fail.is_permanent_not_found and crawl_res.crawl_healthy:
            should_deactivate = src_registry.increment_miss_and_check_deactivation(
                department_id=department_id,
                url=fail.url,
                miss_threshold=miss_threshold,
            )
            if should_deactivate:
                doc_id = f"{department_id}_{hashlib.sha256(fail.canonical_url.encode('utf-8')).hexdigest()[:16]}"
                vec_store.deactivate_document(department_id, doc_id)
                inactive_docs += 1
        else:
            # Temporary error -> NEVER delete existing knowledge
            src_registry.record_temporary_failure(
                department_id=department_id,
                url=fail.url,
                status_code=fail.status_code,
                error=fail.error,
            )

    # 3. Check previously crawled sources that disappeared completely from a healthy crawl
    if crawl_res.crawl_healthy:
        failed_canons = {f.canonical_url for f in crawl_res.failed_fetches}
        for s in known_sources:
            if s.get("discovered_via") != "crawler":
                continue
            canon = s["canonical_url"]
            if canon == canonicalize_url_for_dedup(cfg.root_url):
                continue
            if canon not in crawl_res.seen_canonical_urls and canon not in failed_canons:
                should_deactivate = src_registry.increment_miss_and_check_deactivation(
                    department_id=department_id,
                    url=s["url"],
                    miss_threshold=miss_threshold,
                )
                if should_deactivate:
                    doc_id = f"{department_id}_{hashlib.sha256(canon.encode('utf-8')).hexdigest()[:16]}"
                    vec_store.deactivate_document(department_id, doc_id)
                    inactive_docs += 1

    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status = "completed" if crawl_res.crawl_healthy else "failed"

    run_id = src_registry.record_crawl_run(
        department_id=department_id,
        root_url=cfg.root_url,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        pages_discovered=crawl_res.pages_discovered,
        pdfs_discovered=crawl_res.pdfs_discovered,
        new_docs=new_docs,
        updated_docs=updated_docs,
        unchanged_docs=unchanged_docs,
        inactive_docs=inactive_docs,
        failed_docs=failed_docs,
        error_summary=errors[:20],
        client_id=cfg.client_id,
    )

    return {
        "run_id": run_id,
        "status": status,
        "department_id": department_id,
        "root_url": cfg.root_url,
        "crawl_healthy": crawl_res.crawl_healthy,
        "pages_discovered": crawl_res.pages_discovered,
        "pdfs_discovered": crawl_res.pdfs_discovered,
        "new_docs": new_docs,
        "updated_docs": updated_docs,
        "unchanged_docs": unchanged_docs,
        "inactive_docs": inactive_docs,
        "failed_docs": failed_docs,
        "errors": errors[:20],
        "vector_backend": vec_store.get_active_backend_name(),
    }
