"""
Tests for Configurable Website Crawler, SSRF Protection, URL Normalization,
External Linked PDF Discovery, Conditional Headers, and Scanned/Malformed PDFs.
"""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.crawler import (
    ConfigurableWebCrawler,
    CrawlerConfig,
    UnsafeURLError,
    canonicalize_url_for_dedup,
    extract_pdf_pages,
    normalize_url,
    validate_safe_url,
)


def _make_text_pdf_bytes(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_blank_pdf_bytes():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.showPage()
    c.save()
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def close(self):
        pass


class TestCrawlerAndSSRF(unittest.TestCase):
    def test_01_ssrf_blocks_unsafe_urls_and_ips(self):
        unsafe_urls = [
            "http://localhost/admin",
            "http://127.0.0.1:8000/secret",
            "http://10.0.0.5/internal",
            "http://172.16.0.10/metadata",
            "http://192.168.1.1/router",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/loopback",
            "file:///etc/passwd",
            "ftp://example.com/file.pdf",
            "https://user:pass@example.com/doc.pdf",
            "http://myhost.internal/api",
        ]
        for u in unsafe_urls:
            with self.assertRaises(UnsafeURLError, msg=f"Expected UnsafeURLError for {u}"):
                validate_safe_url(u)

        # DNS resolving to private IP must also be blocked
        with self.assertRaises(UnsafeURLError):
            validate_safe_url("https://rebind.example.com/doc", resolver=lambda h, p: ["10.20.30.40"])

        # Public IP resolution passes
        safe = validate_safe_url("https://www.municipality.gov/docs", resolver=lambda h, p: ["93.184.216.34"])
        self.assertEqual(safe, "https://www.municipality.gov/docs")

    def test_02_url_normalization_and_dedup(self):
        u1 = "HTTPS://WWW.EdisonNJ.org:443/document_center/Tree.pdf?t=20240911#section1"
        u2 = "https://www.edisonnj.org/document_center/Tree.pdf"
        self.assertEqual(canonicalize_url_for_dedup(u1), canonicalize_url_for_dedup(u2))
        self.assertEqual(normalize_url("http://Example.com:80/a/b/#top"), "http://example.com/a/b")

    def test_03_crawler_discovers_html_and_external_linked_pdfs(self):
        root_url = "https://city.example.gov/engineering/index.html"
        sub_url = "https://city.example.gov/engineering/permits.html"
        excluded_url = "https://city.example.gov/health/restaurant.html"
        ext_pdf_url = "https://cdn-forms.externalhost.org/files/grading_checklist.pdf"

        pdf_bytes = _make_text_pdf_bytes([
            "City Engineering Grading Checklist",
            "Submit signed survey and stormwater drywell plan.",
        ])

        html_root = f"""
        <html><head><title>Engineering Docs</title></head>
        <body>
          <a href="/engineering/permits.html">Permits</a>
          <a href="/health/restaurant.html">Health</a>
        </body></html>
        """.encode("utf-8")

        html_permits = f"""
        <html><head><title>Engineering Permits</title></head>
        <body>
          <p>Official grading permit instructions for City Engineering.</p>
          <a href="{ext_pdf_url}">Grading Checklist PDF</a>
          <a href="{root_url}">Back to Root</a>
        </body></html>
        """.encode("utf-8")

        session = MagicMock()
        def fake_get(url, headers=None, timeout=15, allow_redirects=False, stream=True):
            if url == root_url:
                return _FakeResponse(200, html_root, {"Content-Type": "text/html", "ETag": '"etag-root"'})
            if url == sub_url:
                return _FakeResponse(200, html_permits, {"Content-Type": "text/html"})
            if url == ext_pdf_url:
                return _FakeResponse(200, pdf_bytes, {"Content-Type": "application/pdf", "ETag": '"etag-pdf-1"'})
            raise AssertionError(f"Unexpected crawl URL: {url}")

        session.get.side_effect = fake_get

        cfg = CrawlerConfig(
            root_url=root_url,
            department_id="engineering",
            allowed_domains=["city.example.gov"],
            follow_external_pdfs=True,
            max_depth=2,
            max_pages=20,
            delay_seconds=0.0,
            include_patterns=["engineering", "permit", "grading"],
            exclude_patterns=["health"],
        )
        crawler = ConfigurableWebCrawler(cfg, session=session, url_validator=lambda u: u)
        res = crawler.crawl()

        self.assertTrue(res.crawl_healthy)
        self.assertEqual(res.pages_discovered, 2)
        self.assertEqual(res.pdfs_discovered, 1)
        urls = [d.url for d in res.documents]
        self.assertIn(sub_url, urls)
        self.assertIn(ext_pdf_url, urls)
        self.assertNotIn(excluded_url, urls)

        pdf_doc = next(d for d in res.documents if d.url == ext_pdf_url)
        self.assertEqual(pdf_doc.referring_url, sub_url)
        self.assertEqual(pdf_doc.source_type, "pdf")
        self.assertEqual(pdf_doc.etag, '"etag-pdf-1"')
        self.assertEqual(pdf_doc.pages[0][0], 1)
        self.assertIn("Grading Checklist", pdf_doc.pages[0][1])

    def test_04_crawler_blocks_ssrf_redirect_and_handles_304(self):
        root_url = "https://city.example.gov/index.html"
        session = MagicMock()

        def fake_get(url, headers=None, timeout=15, allow_redirects=False, stream=True):
            if headers and headers.get("If-None-Match") == '"etag-1"':
                return _FakeResponse(304, b"", {})
            return _FakeResponse(302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"})

        session.get.side_effect = fake_get
        cfg = CrawlerConfig(root_url=root_url, delay_seconds=0.0, max_retries=0)
        def offline_validator(u):
            return validate_safe_url(
                u,
                resolver=lambda h, p: ["93.184.216.34"] if h == "city.example.gov" else ["169.254.169.254"],
            )
        crawler = ConfigurableWebCrawler(cfg, session=session, url_validator=offline_validator)

        # Conditional 304 check
        res_304 = crawler.crawl(known_metadata={
            canonicalize_url_for_dedup(root_url): {"url": root_url, "etag": '"etag-1"'}
        })
        self.assertTrue(res_304.crawl_healthy)
        self.assertIn(root_url, res_304.unchanged_urls)

        # Redirect to metadata IP must fail SSRF
        res_ssrf = crawler.crawl()
        self.assertFalse(res_ssrf.crawl_healthy)
        self.assertEqual(len(res_ssrf.failed_fetches), 1)
        self.assertIn("SSRF blocked", res_ssrf.failed_fetches[0].error)

    def test_05_pdf_extractor_scanned_and_malformed_handling(self):
        blank_pdf = _make_blank_pdf_bytes()
        scanned_res = extract_pdf_pages(blank_pdf, enable_ocr=False)
        self.assertEqual(scanned_res.extraction_status, "scanned_pdf_needs_ocr")
        self.assertTrue(scanned_res.needs_ocr)

        malformed_res = extract_pdf_pages(b"not-a-pdf-bytes", enable_ocr=False)
        self.assertEqual(malformed_res.extraction_status, "malformed_pdf")

    def test_06_external_pdf_scope_excludes_unrelated_township_docs(self):
        root_url = "https://www.city.example.gov/document_center/index.php"
        eng_ext_pdf = "https://cms2.revize.com/revize/city/document_center/Tree_Permit.pdf"
        bingo_ext_pdf = "https://cms2.revize.com/revize/city/document_center/Bingoapp.pdf"
        voter_ext_pdf = "https://cms2.revize.com/revize/city/document_center/Voterregistration.pdf"

        pdf_bytes = _make_text_pdf_bytes(["City Engineering Tree Permit Application"])
        html_root = f"""
        <html><head><title>Document Center</title></head>
        <body>
          <a href="{eng_ext_pdf}">Tree Removal Permit Application</a>
          <a href="{bingo_ext_pdf}">Bingo Application</a>
          <a href="{voter_ext_pdf}">Voter Registration Form</a>
        </body></html>
        """.encode("utf-8")

        sess = MagicMock()
        sess.get.side_effect = lambda u, **kw: (
            _FakeResponse(200, html_root, {"Content-Type": "text/html"})
            if u == root_url
            else _FakeResponse(200, pdf_bytes, {"Content-Type": "application/pdf"})
        )

        cfg = CrawlerConfig(
            root_url=root_url,
            department_id="engineering",
            allowed_domains=["www.city.example.gov"],
            follow_external_pdfs=True,
            max_depth=2,
            delay_seconds=0.0,
            include_patterns=["tree", "soil", "engineering", "permit"],
            exclude_patterns=["bingo", "voter", "raffle", "landlord"],
        )
        crawler = ConfigurableWebCrawler(cfg, session=sess, url_validator=lambda u: u)
        res = crawler.crawl()

        urls = [d.url for d in res.documents]
        self.assertIn(eng_ext_pdf, urls)
        self.assertNotIn(bingo_ext_pdf, urls)
        self.assertNotIn(voter_ext_pdf, urls)
        skipped_urls = {u for u, _ in res.skipped_urls}
        self.assertIn(bingo_ext_pdf, skipped_urls)
        self.assertIn(voter_ext_pdf, skipped_urls)

    def test_07_dns_rebinding_ip_pinning_adapter(self):
        from backend.app.crawler import PinnedIPAdapter, resolve_and_validate_url

        cleaned, ip = resolve_and_validate_url(
            "https://city.example.gov/docs/a.pdf",
            resolver=lambda h, p: ["93.184.216.34"],
        )
        self.assertEqual(cleaned, "https://city.example.gov/docs/a.pdf")
        self.assertEqual(ip, "93.184.216.34")

        adapter = PinnedIPAdapter({"city.example.gov": ip})
        self.assertEqual(adapter.pinned_ips["city.example.gov"], "93.184.216.34")


if __name__ == "__main__":
    unittest.main()
