"""
PDF Text Extraction & Scanned PDF OCR Support for CivicIQ.
Extracts text page-by-page using pypdf so chunk provenance preserves pdf_page_number.
Detects scanned (image-only) PDFs and runs optional OCR via pytesseract when available.
"""

import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

from pypdf import PdfReader

logger = logging.getLogger("crawler.pdf_extractor")


@dataclass
class PdfExtractionResult:
    pages: List[Tuple[int, str]] = field(default_factory=list)  # (1-based page_number, text)
    total_pages: int = 0
    extraction_status: str = "extracted"  # extracted | ocr_extracted | scanned_pdf_needs_ocr | malformed_pdf
    needs_ocr: bool = False
    ocr_attempted: bool = False
    error: Optional[str] = None

    @property
    def full_text(self) -> str:
        return "\n\n".join(text for _, text in self.pages if text.strip())

    @property
    def total_chars(self) -> int:
        return sum(len(text.strip()) for _, text in self.pages)


def _try_ocr_pdf(pdf_bytes: bytes) -> Optional[List[Tuple[int, str]]]:
    """
    Attempts OCR using pytesseract + pdf2image when both Python libraries
    and the Tesseract binary are installed on the host.
    Returns list of (page_number, text) or None if OCR is unavailable.
    """
    if shutil.which("tesseract") is None:
        return None
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return None

    try:
        images = convert_from_bytes(pdf_bytes)
        ocr_pages: List[Tuple[int, str]] = []
        for idx, img in enumerate(images, start=1):
            text = (pytesseract.image_to_string(img) or "").strip()
            if text:
                ocr_pages.append((idx, text))
        return ocr_pages
    except Exception as exc:
        logger.warning(f"OCR extraction failed: {exc}")
        return None


def extract_pdf_pages(
    source: Union[Path, str, bytes],
    min_chars_total: int = 30,
    enable_ocr: bool = True,
) -> PdfExtractionResult:
    """
    Extracts text page-by-page from a PDF file path or raw bytes.
    Detects scanned PDFs and falls back to OCR when available.
    Handles malformed PDFs gracefully without raising.
    """
    try:
        if isinstance(source, (Path, str)):
            raw_bytes = Path(source).read_bytes()
        else:
            raw_bytes = source
    except Exception as exc:
        return PdfExtractionResult(
            extraction_status="malformed_pdf",
            error=f"Unable to read PDF bytes: {exc}",
        )

    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        total_pages = len(reader.pages)
        pages: List[Tuple[int, str]] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                txt = (page.extract_text() or "").strip()
            except Exception:
                txt = ""
            if txt:
                pages.append((idx, txt))
    except Exception as exc:
        return PdfExtractionResult(
            extraction_status="malformed_pdf",
            error=f"Malformed PDF: {exc}",
        )

    total_chars = sum(len(t) for _, t in pages)
    if total_chars >= min_chars_total:
        return PdfExtractionResult(
            pages=pages,
            total_pages=total_pages,
            extraction_status="extracted",
            needs_ocr=False,
            ocr_attempted=False,
        )

    # Detected scanned/image-based PDF
    if enable_ocr:
        ocr_pages = _try_ocr_pdf(raw_bytes)
        if ocr_pages and sum(len(t) for _, t in ocr_pages) >= min_chars_total:
            return PdfExtractionResult(
                pages=ocr_pages,
                total_pages=total_pages,
                extraction_status="ocr_extracted",
                needs_ocr=False,
                ocr_attempted=True,
            )

    return PdfExtractionResult(
        pages=pages,
        total_pages=total_pages,
        extraction_status="scanned_pdf_needs_ocr",
        needs_ocr=True,
        ocr_attempted=enable_ocr,
    )
