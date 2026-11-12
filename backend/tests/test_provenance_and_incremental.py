"""
Tests for Document Provenance, Safe Staged Versioning, Incremental Updates,
Temporary Failure Resilience, Safe Removal Reconciliation, and Admin Crawl Endpoints.
"""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.config import ADMIN_API_KEY
from backend.app.crawler import ConfigurableWebCrawler, CrawlerConfig, TrustedSourceRegistry
from backend.app.main import get_admin_crawl_status, list_admin_trusted_sources
from backend.app.vector_store import SQLiteVectorStore
from backend.scripts.incremental_ingest import run_incremental_ingestion


def _make_pdf_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(50, 740, text)
    c.showPage()
    c.save()
    return buf.getvalue()


class _FakeResp:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}

    def iter_content(self, chunk_size=65536):
        yield self._content

    def close(self):
        pass


class _IsolatedStoreAdapter:
    """Adapter wrapping SQLiteVectorStore for isolated incremental_ingest tests."""
    def __init__(self, db_path: Path):
        self.sqlite = SQLiteVectorStore(db_path=db_path)

    def get_active_document_versions(self, department_id: str):
        return self.sqlite.get_active_document_versions(department_id)

    def stage_and_activate_document_chunks(self, department_id, document_id, chunks, new_version_id):
        return self.sqlite.stage_and_activate_document_chunks(department_id, document_id, chunks, new_version_id)

    def deactivate_document(self, department_id, document_id):
        self.sqlite.deactivate_document(department_id, document_id)

    def get_active_backend_name(self):
        return "SQLite Test Store"

    def search(self, query, department_id="engineering", top_k=5, threshold=0.05):
        return self.sqlite.search(query, department_id=department_id, top_k=top_k, threshold=threshold)


class TestProvenanceAndIncrementalUpdates(unittest.TestCase):
    def test_01_incremental_staging_versioning_and_safe_removal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "test_prov.db"
            dept_dir = tmp / "departments"
            (dept_dir / "engineering").mkdir(parents=True)
            root_url = "https://city.example.gov/docs/index.html"
            pdf_url = "https://city.example.gov/docs/culvert_policy.pdf"

            (dept_dir / "engineering" / "config.json").write_text(
                f'{{"trusted_sources": {{"client_id": "test_city", "root_url": "{root_url}", "allowed_domains": ["city.example.gov"], "crawl_depth": 2, "delay_seconds": 0}}}}',
                encoding="utf-8",
            )

            store = _IsolatedStoreAdapter(db_path)
            reg = TrustedSourceRegistry(db_path=db_path)

            # --- Run 1: Initial crawl discovers root + PDF ---
            pdf_v1 = _make_pdf_bytes("Culvert Permit Fee is 50 dollars version one municipal policy.")
            html_v1 = f'<html><head><title>Docs</title></head><body><p>Engineering index page.</p><a href="{pdf_url}">Culvert Policy</a></body></html>'.encode()

            def make_crawler_run1(cfg):
                sess = MagicMock()
                def fake_get(url, headers=None, **kw):
                    if url == root_url:
                        return _FakeResp(200, html_v1, {"Content-Type": "text/html", "ETag": '"r1"'})
                    if url == pdf_url:
                        return _FakeResp(200, pdf_v1, {"Content-Type": "application/pdf", "ETag": '"p1"'})
                    return _FakeResp(404, b"", {})
                sess.get.side_effect = fake_get
                return ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)

            r1 = run_incremental_ingestion(
                department_id="engineering",
                departments_dir=dept_dir,
                store=store,
                registry=reg,
                crawler_factory=make_crawler_run1,
                miss_threshold=2,
            )
            self.assertEqual(r1["status"], "completed")
            self.assertEqual(r1["new_docs"], 2)

            cits = store.search("Culvert Permit Fee", department_id="engineering", threshold=0.05)
            self.assertGreater(len(cits), 0)
            pdf_cit = next(c for c in cits if c.url == pdf_url)
            self.assertEqual(pdf_cit.version_id, 1)
            self.assertEqual(pdf_cit.pdf_page_number, 1)
            self.assertEqual(pdf_cit.referring_url, root_url)
            self.assertEqual(pdf_cit.source_type, "pdf")
            self.assertIsNotNone(pdf_cit.content_hash)

            # --- Run 2: Unchanged (304 Not Modified) -> skipped, version remains 1 ---
            def make_crawler_run2(cfg):
                sess = MagicMock()
                def fake_get(url, headers=None, **kw):
                    if url == root_url:
                        return _FakeResp(304, b"", {})
                    if url == pdf_url and headers and headers.get("If-None-Match") == '"p1"':
                        return _FakeResp(304, b"", {})
                    return _FakeResp(404, b"", {})
                sess.get.side_effect = fake_get
                return ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)

            r2 = run_incremental_ingestion(
                department_id="engineering",
                departments_dir=dept_dir,
                store=store,
                registry=reg,
                crawler_factory=make_crawler_run2,
                miss_threshold=2,
            )
            self.assertEqual(r2["new_docs"], 0)
            self.assertEqual(r2["updated_docs"], 0)
            self.assertGreaterEqual(r2["unchanged_docs"], 2)

            # --- Run 3: PDF content changes -> v2 activated, v1 deactivated & never returned ---
            pdf_v2 = _make_pdf_bytes("Culvert Permit Fee updated to 75 dollars version two municipal policy.")
            def make_crawler_run3(cfg):
                sess = MagicMock()
                def fake_get(url, headers=None, **kw):
                    if url == root_url:
                        return _FakeResp(200, html_v1, {"Content-Type": "text/html"})
                    if url == pdf_url:
                        return _FakeResp(200, pdf_v2, {"Content-Type": "application/pdf", "ETag": '"p2"'})
                    return _FakeResp(404, b"", {})
                sess.get.side_effect = fake_get
                return ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)

            r3 = run_incremental_ingestion(
                department_id="engineering",
                departments_dir=dept_dir,
                store=store,
                registry=reg,
                crawler_factory=make_crawler_run3,
                miss_threshold=2,
            )
            self.assertEqual(r3["updated_docs"], 1)
            cits_v2 = store.search("Culvert Permit Fee dollars", department_id="engineering", threshold=0.05)
            pdf_cits_v2 = [c for c in cits_v2 if c.url == pdf_url]
            self.assertTrue(all(c.version_id == 2 for c in pdf_cits_v2))
            self.assertTrue(any("75 dollars" in c.excerpt for c in pdf_cits_v2))
            self.assertFalse(any("50 dollars" in c.excerpt for c in pdf_cits_v2))

            # --- Run 4: Temporary 503 outage on PDF -> existing v2 preserved! ---
            def make_crawler_run4(cfg):
                sess = MagicMock()
                def fake_get(url, headers=None, **kw):
                    if url == root_url:
                        return _FakeResp(200, html_v1, {"Content-Type": "text/html"})
                    return _FakeResp(503, b"Service Unavailable", {})
                sess.get.side_effect = fake_get
                return ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)

            r4 = run_incremental_ingestion(
                department_id="engineering",
                departments_dir=dept_dir,
                store=store,
                registry=reg,
                crawler_factory=make_crawler_run4,
                miss_threshold=2,
            )
            self.assertEqual(r4["inactive_docs"], 0)
            self.assertGreater(len([c for c in store.search("Culvert Permit Fee", threshold=0.05) if c.url == pdf_url]), 0)

            # --- Run 5 & 6: Permanent 404 for 2 consecutive healthy crawls -> safely deactivated ---
            def make_crawler_404(cfg):
                sess = MagicMock()
                def fake_get(url, headers=None, **kw):
                    if url == root_url:
                        return _FakeResp(200, b"<html><head><title>Docs</title></head><body><p>Updated root without culvert link.</p></body></html>", {"Content-Type": "text/html"})
                    return _FakeResp(404, b"", {})
                sess.get.side_effect = fake_get
                return ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)

            r5 = run_incremental_ingestion(
                department_id="engineering", departments_dir=dept_dir, store=store, registry=reg,
                crawler_factory=make_crawler_404, miss_threshold=2,
            )
            self.assertEqual(r5["inactive_docs"], 0)  # 1 miss < threshold 2

            r6 = run_incremental_ingestion(
                department_id="engineering", departments_dir=dept_dir, store=store, registry=reg,
                crawler_factory=make_crawler_404, miss_threshold=2,
            )
            self.assertEqual(r6["inactive_docs"], 1)  # 2 misses >= threshold 2 -> deactivated
            remaining_pdf = [c for c in store.search("Culvert Permit Fee 75 dollars", threshold=0.05) if c.url == pdf_url]
            self.assertEqual(len(remaining_pdf), 0)

    def test_02_admin_crawl_status_endpoint_auth_and_payload(self):
        with self.assertRaises(HTTPException) as cm:
            get_admin_crawl_status(x_admin_key="wrong-key")
        self.assertEqual(cm.exception.status_code, 403)

        status_res = get_admin_crawl_status(x_admin_key=ADMIN_API_KEY)
        self.assertIn("crawl_status", status_res)
        self.assertIn("vector_stats", status_res)

        sources_res = list_admin_trusted_sources(x_admin_key=ADMIN_API_KEY)
        self.assertEqual(sources_res["department_id"], "engineering")
        self.assertGreaterEqual(sources_res["total"], 1)

    def test_03_postgres_trusted_source_registry_and_production_enforcement(self):
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "prod_test.db"
            # In production without DATABASE_URL, must fail fast (no silent SQLite fallback)
            with patch.dict(os.environ, {"ENVIRONMENT": "production", "DATABASE_URL": ""}, clear=False):
                reg = TrustedSourceRegistry(db_path=db_path, db_url="")
                with self.assertRaises(RuntimeError):
                    reg.seed_from_config("engineering", "https://city.example.gov/docs")

            # With mocked psycopg2 connection, verify PG persistence queries are executed and committed
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = [1]

            with patch.dict(os.environ, {"ENVIRONMENT": "production", "DATABASE_URL": "postgresql://u:p@db.example.com:5432/db"}, clear=False):
                with patch("psycopg2.connect", return_value=mock_conn):
                    reg_pg = TrustedSourceRegistry(db_path=db_path, db_url="postgresql://u:p@db.example.com:5432/db")
                    reg_pg.seed_from_config("engineering", "https://city.example.gov/docs", client_id="city")
                    run_id = reg_pg.record_crawl_run(
                        department_id="engineering",
                        root_url="https://city.example.gov/docs",
                        started_at="2026-11-12T00:00:00+00:00",
                        completed_at="2026-11-12T00:01:00+00:00",
                        status="completed",
                        new_docs=1,
                    )
                    self.assertEqual(run_id, 1)
                    self.assertGreaterEqual(mock_conn.commit.call_count, 3)

    def test_04_rate_limiting_and_concurrent_crawl_lock(self):
        from backend.app.rate_limiter import PersistentRateLimiter
        from backend.app.main import trigger_admin_crawl

        with tempfile.TemporaryDirectory() as tmpdir:
            rl = PersistentRateLimiter(db_path=Path(tmpdir) / "rl.db", force_sqlite=True)
            for i in range(3):
                ok, cnt = rl.check_rate_limit("chat:1.2.3.4:s1", max_requests=3, window_seconds=60)
                self.assertTrue(ok)
            ok_over, cnt_over = rl.check_rate_limit("chat:1.2.3.4:s1", max_requests=3, window_seconds=60)
            self.assertFalse(ok_over)
            self.assertEqual(cnt_over, 4)

            self.assertTrue(rl.acquire_crawl_lock("crawl_engineering", owner="worker1", ttl_seconds=60))
            self.assertFalse(rl.acquire_crawl_lock("crawl_engineering", owner="worker2", ttl_seconds=60))
            rl.release_crawl_lock("crawl_engineering")
            self.assertTrue(rl.acquire_crawl_lock("crawl_engineering", owner="worker2", ttl_seconds=60))

            # Verify /api/admin/crawl returns 409 when lock is held
            from unittest.mock import patch
            with patch("backend.app.main.rate_limiter.acquire_crawl_lock", return_value=False):
                with self.assertRaises(HTTPException) as cm:
                    trigger_admin_crawl(department_id="engineering", x_admin_key=ADMIN_API_KEY)
                self.assertEqual(cm.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
