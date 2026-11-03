import os
import sqlite3
import pickle
import logging
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import (
    VECTOR_DB_PATH, SIMILARITY_THRESHOLD, TOP_K_RESULTS,
    DATABASE_URL, VECTOR_STORE_PROVIDER
)
from .models import RagCitation
from .pgvector_store import PgVectorStore

logger = logging.getLogger("vector_store")

class SQLiteVectorStore:
    def __init__(self, db_path: Path = VECTOR_DB_PATH):
        self.db_path = Path(db_path)
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.chunk_ids: List[str] = []
        self._init_db()
        self._load_index()

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    department_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT,
                    chunk_index INTEGER,
                    content TEXT NOT NULL,
                    word_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value BLOB
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dept ON chunks(department_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON chunks(url)")
            conn.commit()

    def clear(self, department_id: Optional[str] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if department_id:
                cursor.execute("DELETE FROM chunks WHERE department_id = ?", (department_id,))
            else:
                cursor.execute("DELETE FROM chunks")
                cursor.execute("DELETE FROM index_metadata")
            conn.commit()
        self._rebuild_vector_index()

    def add_chunks(self, chunks: List[Dict]):
        if not chunks:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for ch in chunks:
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks 
                    (id, department_id, url, title, category, chunk_index, content, word_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ch["id"],
                    ch["department_id"],
                    ch["url"],
                    ch["title"],
                    ch.get("category", "General"),
                    ch.get("chunk_index", 0),
                    ch["content"],
                    len(ch["content"].split())
                ))
            conn.commit()

        self._rebuild_vector_index()

    def _rebuild_vector_index(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content FROM chunks ORDER BY id")
            rows = cursor.fetchall()

        if not rows:
            self.vectorizer = None
            self.tfidf_matrix = None
            self.chunk_ids = []
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM index_metadata WHERE key = 'tfidf_model'")
                conn.commit()
            return

        self.chunk_ids = [r[0] for r in rows]
        corpus = [r[1] for r in rows]

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words='english',
            sublinear_tf=True
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

        serialized = pickle.dumps({
            "vectorizer": self.vectorizer,
            "tfidf_matrix": self.tfidf_matrix,
            "chunk_ids": self.chunk_ids
        })

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO index_metadata (key, value)
                VALUES ('tfidf_model', ?)
            """, (sqlite3.Binary(serialized),))
            conn.commit()
        logger.info(f"Rebuilt SQLite vector index with {len(self.chunk_ids)} chunks.")

    def _load_index(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM index_metadata WHERE key = 'tfidf_model'")
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    data = pickle.loads(row[0])
                    self.vectorizer = data.get("vectorizer")
                    self.tfidf_matrix = data.get("tfidf_matrix")
                    self.chunk_ids = data.get("chunk_ids", [])
                except Exception as e:
                    self._rebuild_vector_index()
            else:
                self._rebuild_vector_index()

    def search(
        self,
        query: str,
        department_id: Optional[str] = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD
    ) -> List[RagCitation]:
        if not self.vectorizer or self.tfidf_matrix is None or not self.chunk_ids:
            return []

        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        candidates = []
        for idx, score in enumerate(scores):
            if score >= threshold:
                candidates.append((self.chunk_ids[idx], float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        if not candidates:
            return []

        top_ids = [c[0] for c in candidates[:top_k * 3]]
        id_score_map = dict(candidates)

        placeholders = ",".join("?" for _ in top_ids)
        query_sql = f"""
            SELECT id, department_id, url, title, category, content
            FROM chunks
            WHERE id IN ({placeholders})
        """
        params = list(top_ids)
        if department_id:
            query_sql += " AND department_id = ?"
            params.append(department_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()

        results = []
        for r in rows:
            chunk_id, dept_id, url, title, category, content = r
            score = id_score_map.get(chunk_id, 0.0)
            excerpt = content.strip().replace("\n", " ")
            if len(excerpt) > 500:
                excerpt = excerpt[:497] + "..."

            results.append(RagCitation(
                url=url,
                title=title,
                category=category or "General",
                department_id=dept_id,
                relevance_score=round(score, 3),
                excerpt=excerpt
            ))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:top_k]

    def get_stats(self) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*), count(distinct department_id), count(distinct url) FROM chunks")
            row = cursor.fetchone()
            total_chunks = row[0] if row else 0
            dept_count = row[1] if row else 0
            url_count = row[2] if row else 0

            cursor.execute("SELECT department_id, count(*) FROM chunks GROUP BY department_id")
            by_dept = dict(cursor.fetchall())

        return {
            "backend": "sqlite (local fallback)",
            "total_chunks": total_chunks,
            "department_count": dept_count,
            "url_count": url_count,
            "chunks_by_department": by_dept
        }


class UnifiedVectorStore:
    """
    Unified Vector Store that prioritizes pgvector (PostgreSQL) when available,
    with seamless local resilience if PostgreSQL has not yet been started.
    """
    def __init__(self):
        self.sqlite_store = SQLiteVectorStore()
        self.pg_store = PgVectorStore(DATABASE_URL)
        self._use_pg = False
        self._check_and_init()

    def _check_and_init(self):
        if VECTOR_STORE_PROVIDER == "pgvector":
            if self.pg_store.check_connection():
                if self.pg_store.init_db():
                    self._use_pg = True
                    logger.info("⚡ [pgvector] Active! Operating on PostgreSQL with native vector extension.")
                    return
            logger.info("ℹ️ [pgvector] PostgreSQL is not currently running at localhost:5432. Active backend: SQLite Vector Store.")

    def get_active_backend_name(self) -> str:
        return "pgvector (PostgreSQL)" if self._use_pg else "SQLite Vector Store (Local fallback)"

    def is_pgvector_active(self) -> bool:
        return self._use_pg

    def add_chunks(self, chunks: List[Dict]):
        # Always update sqlite as local cache
        self.sqlite_store.add_chunks(chunks)
        # If pgvector is reachable, also write to pgvector
        if self.pg_store.check_connection():
            self.pg_store.init_db()
            self.pg_store.add_chunks(chunks)
            self._use_pg = True

    def clear(self, department_id: Optional[str] = None):
        self.sqlite_store.clear(department_id)
        if self._use_pg or self.pg_store.check_connection():
            self.pg_store.clear(department_id)

    def search(
        self,
        query: str,
        department_id: Optional[str] = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD
    ) -> List[RagCitation]:
        if self._use_pg or self.pg_store.check_connection():
            self._use_pg = True
            return self.pg_store.search(query, department_id, top_k, threshold)
        return self.sqlite_store.search(query, department_id, top_k, threshold)

    def get_stats(self) -> Dict:
        if self._use_pg or self.pg_store.check_connection():
            stats = self.pg_store.get_stats()
            stats["backend"] = "pgvector (PostgreSQL)"
            return stats
        stats = self.sqlite_store.get_stats()
        stats["backend"] = "SQLite Vector Store (Local fallback)"
        return stats

vector_store = UnifiedVectorStore()
