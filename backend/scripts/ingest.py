"""
URL Scraper & Vector Indexer for Pixelvyne Smart Assistant
Iterates over all department knowledge_links.json, retrieves or parses content,
chunks into semantic segments, and creates vector embeddings in the local SQLite vector store.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from typing import List, Dict

# Add backend to sys.path so it can be run from anywhere
current_file = Path(__file__).resolve()
backend_root = current_file.parent.parent
sys.path.insert(0, str(backend_root))

from app.config import DEPARTMENTS_DIR, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS
from app.vector_store import SQLiteVectorStore
from bs4 import BeautifulSoup
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

def fetch_url_content(url: str, fallback_content: str = "", try_live: bool = False, timeout: float = 1.0) -> str:
    """
    Fetches live URL text using requests & BeautifulSoup if try_live is True and accessible.
    Default prioritizes fast, grounded ingestion from the client's provided authoritative link content.
    """
    if try_live and not ("pixelvyne.gov" in url):
        try:
            headers = {"User-Agent": "Pixelvyne-CivicIQ-Crawler/1.0 (+https://pixelvyne.gov/bot)"}
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for s in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                    s.decompose()
                text = soup.get_text(separator="\n")
                cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
                cleaned_text = "\n".join(cleaned_lines)
                if len(cleaned_text.split()) > 30:
                    logger.info(f"Successfully scraped live URL: {url} ({len(cleaned_text.split())} words)")
                    return cleaned_text
        except Exception as e:
            logger.debug(f"Live fetch not available for {url} ({e}); using authoritative cached content.")

    return fallback_content

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> List[str]:
    """Splits text into chunks of roughly chunk_size words with overlap."""
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start += (chunk_size - overlap)

    return chunks

def ingest_department_links(dept_id: str, dept_dir: Path, vector_store: SQLiteVectorStore) -> int:
    links_file = dept_dir / "knowledge_links.json"
    if not links_file.exists():
        logger.warning(f"No knowledge_links.json found for department: {dept_id}")
        return 0

    with open(links_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    links = data.get("links", [])
    total_chunks = 0
    dept_chunks_to_add = []

    for link_entry in links:
        url = link_entry.get("url", "")
        title = link_entry.get("title", "Untitled Document")
        category = link_entry.get("category", "General")
        fallback_content = link_entry.get("content", "") or link_entry.get("summary", "")

        logger.info(f"[{dept_id.upper()}] Processing link: {title} ({url})")
        full_text = fetch_url_content(url, fallback_content=fallback_content)

        if not full_text.strip():
            logger.warning(f"No content found for {url}, skipping.")
            continue

        chunks = chunk_text(full_text)
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{dept_id}_{url_hash}_{idx}"
            dept_chunks_to_add.append({
                "id": chunk_id,
                "department_id": dept_id,
                "url": url,
                "title": title,
                "category": category,
                "chunk_index": idx,
                "content": chunk,
                "word_count": len(chunk.split())
            })
            total_chunks += 1

    if dept_chunks_to_add:
        # Clear existing chunks for this dept then add new
        vector_store.clear(department_id=dept_id)
        vector_store.add_chunks(dept_chunks_to_add)

    return total_chunks

def run_ingestion(target_dept: str = "all", clear_all: bool = False):
    vector_store = SQLiteVectorStore()
    if clear_all:
        logger.info("Clearing entire vector database...")
        vector_store.clear()

    total_indexed = 0
    departments_processed = []

    for entry in os.scandir(DEPARTMENTS_DIR):
        if entry.is_dir():
            dept_id = entry.name
            if target_dept != "all" and dept_id != target_dept:
                continue

            count = ingest_department_links(dept_id, Path(entry.path), vector_store)
            total_indexed += count
            departments_processed.append((dept_id, count))

    stats = vector_store.get_stats()
    print("\n" + "="*60)
    print("MUNICIPAL KNOWLEDGE BASE INGESTION COMPLETE")
    print("="*60)
    for dept_id, count in departments_processed:
        print(f" • Department: {dept_id:15} | Indexed Chunks: {count}")
    print(f"\nTotal Chunks in Vector Store : {stats['total_chunks']}")
    print(f"Total Unique URLs Indexed    : {stats['url_count']}")
    print(f"Departments Covered          : {stats['department_count']}")
    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest municipal links into vector store")
    parser.add_argument("--dept", default="all", help="Target department ID or 'all'")
    parser.add_argument("--clear", action="store_true", help="Clear all vectors before ingesting")
    args = parser.parse_args()

    run_ingestion(target_dept=args.dept, clear_all=args.clear)
