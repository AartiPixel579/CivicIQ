import os
import sqlite3
import pickle
import logging
from contextlib import closing
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import (
    VECTOR_DB_PATH, SIMILARITY_THRESHOLD, TOP_K_RESULTS,
    DATABASE_URL, VECTOR_STORE_PROVIDER, IS_PRODUCTION, ENVIRONMENT
)
from .models import RagCitation
from .pgvector_store import PgVectorStore, mask_db_url

logger = logging.getLogger("vector_store")

class SQLiteVectorStore:
    def __init__(self, db_path: Path = VECTOR_DB_PATH):
        self.db_path = Path(db_path)
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.chunk_ids: List[str] = []
        self._loaded_mtime: float = 0.0
        self._init_db()
        self._load_index()

    def _get_connection(self):
        return closing(sqlite3.connect(str(self.db_path)))

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    client_id TEXT DEFAULT 'default',
                    department_id TEXT NOT NULL,
                    document_id TEXT,
                    url TEXT NOT NULL,
                    referring_url TEXT,
                    title TEXT NOT NULL,
                    category TEXT,
                    content_type TEXT,
                    source_type TEXT DEFAULT 'pdf',
                    pdf_page_number INTEGER,
                    chunk_index INTEGER,
                    content TEXT NOT NULL,
                    word_count INTEGER,
                    retrieval_date TEXT,
                    last_modified TEXT,
                    etag TEXT,
                    content_hash TEXT,
                    is_active INTEGER DEFAULT 1,
                    version_id INTEGER DEFAULT 1,
                    visibility TEXT DEFAULT 'public',
                    document_type TEXT DEFAULT 'guideline',
                    service TEXT,
                    verification_status TEXT DEFAULT 'verified',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("PRAGMA table_info(chunks)")
            cols = [col[1] for col in cursor.fetchall()]
            for c_name, c_def in [
                ("client_id", "TEXT DEFAULT 'default'"),
                ("document_id", "TEXT"),
                ("referring_url", "TEXT"),
                ("content_type", "TEXT"),
                ("source_type", "TEXT DEFAULT 'pdf'"),
                ("pdf_page_number", "INTEGER"),
                ("retrieval_date", "TEXT"),
                ("last_modified", "TEXT"),
                ("etag", "TEXT"),
                ("content_hash", "TEXT"),
                ("is_active", "INTEGER DEFAULT 1"),
                ("version_id", "INTEGER DEFAULT 1"),
                ("visibility", "TEXT DEFAULT 'public'"),
                ("document_type", "TEXT DEFAULT 'guideline'"),
                ("service", "TEXT"),
                ("verification_status", "TEXT DEFAULT 'verified'")
            ]:
                if c_name not in cols:
                    cursor.execute(f"ALTER TABLE chunks ADD COLUMN {c_name} {c_def}")

            cursor.execute("UPDATE chunks SET is_active = 1 WHERE is_active IS NULL")
            cursor.execute("UPDATE chunks SET version_id = 1 WHERE version_id IS NULL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value BLOB
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dept ON chunks(department_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON chunks(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_active ON chunks(department_id, is_active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_ver ON chunks(document_id, version_id)")
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
                    (id, client_id, department_id, document_id, url, referring_url, title, category,
                     content_type, source_type, pdf_page_number, chunk_index, content, word_count,
                     retrieval_date, last_modified, etag, content_hash, is_active, version_id,
                     visibility, document_type, service, verification_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ch["id"],
                    ch.get("client_id", "default"),
                    ch["department_id"],
                    ch.get("document_id"),
                    ch["url"],
                    ch.get("referring_url"),
                    ch["title"],
                    ch.get("category", "General"),
                    ch.get("content_type"),
                    ch.get("source_type", "pdf"),
                    ch.get("pdf_page_number"),
                    ch.get("chunk_index", 0),
                    ch["content"],
                    len(ch["content"].split()),
                    ch.get("retrieval_date"),
                    ch.get("last_modified"),
                    ch.get("etag"),
                    ch.get("content_hash"),
                    1 if ch.get("is_active", True) else 0,
                    int(ch.get("version_id", 1)),
                    ch.get("visibility", "public"),
                    ch.get("document_type", "guideline"),
                    ch.get("service"),
                    ch.get("verification_status", "verified")
                ))
            conn.commit()

        self._rebuild_vector_index()

    def stage_and_activate_document_chunks(
        self,
        department_id: str,
        document_id: str,
        chunks: List[Dict],
        new_version_id: int
    ) -> bool:
        """
        Safely stages new chunks as inactive (is_active=0), validates insertion,
        and atomically activates the new version while deactivating older versions.
        """
        if not chunks:
            return False

        with self._get_connection() as conn:
            try:
                cursor = conn.cursor()
                for ch in chunks:
                    cursor.execute("""
                        INSERT OR REPLACE INTO chunks
                        (id, client_id, department_id, document_id, url, referring_url, title, category,
                         content_type, source_type, pdf_page_number, chunk_index, content, word_count,
                         retrieval_date, last_modified, etag, content_hash, is_active, version_id,
                         visibility, document_type, service, verification_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """, (
                        ch["id"],
                        ch.get("client_id", "default"),
                        department_id,
                        document_id,
                        ch["url"],
                        ch.get("referring_url"),
                        ch["title"],
                        ch.get("category", "General"),
                        ch.get("content_type"),
                        ch.get("source_type", "pdf"),
                        ch.get("pdf_page_number"),
                        ch.get("chunk_index", 0),
                        ch["content"],
                        len(ch["content"].split()),
                        ch.get("retrieval_date"),
                        ch.get("last_modified"),
                        ch.get("etag"),
                        ch.get("content_hash"),
                        int(new_version_id),
                        ch.get("visibility", "public"),
                        ch.get("document_type", "guideline"),
                        ch.get("service"),
                        ch.get("verification_status", "verified")
                    ))

                cursor.execute(
                    "SELECT count(*) FROM chunks WHERE department_id = ? AND document_id = ? AND version_id = ?",
                    (department_id, document_id, int(new_version_id))
                )
                staged_count = cursor.fetchone()[0]
                if staged_count < len(chunks):
                    raise RuntimeError(f"SQLite staging validation failed: expected {len(chunks)}, got {staged_count}")

                doc_urls = list({ch["url"] for ch in chunks if ch.get("url")})
                cursor.execute(
                    "UPDATE chunks SET is_active = 0 WHERE department_id = ? AND document_id = ? AND version_id <> ?",
                    (department_id, document_id, int(new_version_id))
                )
                if doc_urls:
                    url_ph = ",".join("?" for _ in doc_urls)
                    cursor.execute(
                        f"UPDATE chunks SET is_active = 0 WHERE department_id = ? AND document_id IS NULL AND url IN ({url_ph})",
                        [department_id] + doc_urls
                    )
                cursor.execute(
                    "UPDATE chunks SET is_active = 1 WHERE department_id = ? AND document_id = ? AND version_id = ?",
                    (department_id, document_id, int(new_version_id))
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        self._rebuild_vector_index()
        return True

    def deactivate_document(self, department_id: str, document_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chunks SET is_active = 0 WHERE department_id = ? AND document_id = ?",
                (department_id, document_id)
            )
            conn.commit()
        self._rebuild_vector_index()

    def get_active_document_versions(self, department_id: str) -> Dict[str, Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT document_id, MAX(version_id), MAX(content_hash), MAX(etag), MAX(last_modified), MAX(url)
                FROM chunks
                WHERE department_id = ? AND (is_active IS NULL OR is_active = 1) AND document_id IS NOT NULL
                GROUP BY document_id
            """, (department_id,))
            rows = cursor.fetchall()
        return {
            r[0]: {
                "version_id": r[1] or 1,
                "content_hash": r[2],
                "etag": r[3],
                "last_modified": r[4],
                "url": r[5],
            }
            for r in rows if r[0]
        }

    def _rebuild_vector_index(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content FROM chunks WHERE is_active IS NULL OR is_active = 1 ORDER BY id")
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
        try:
            self._loaded_mtime = self.db_path.stat().st_mtime
        except OSError:
            pass
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
                    try:
                        self._loaded_mtime = self.db_path.stat().st_mtime
                    except OSError:
                        pass
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
        try:
            current_mtime = self.db_path.stat().st_mtime
            if current_mtime != self._loaded_mtime:
                self._load_index()
        except OSError:
            pass

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
            SELECT id, client_id, department_id, document_id, url, referring_url, title, category,
                   content_type, source_type, pdf_page_number, retrieval_date, last_modified, etag,
                   content_hash, is_active, version_id, visibility, document_type, service,
                   verification_status, content
            FROM chunks
            WHERE id IN ({placeholders})
              AND (is_active IS NULL OR is_active = 1)
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
            (
                chunk_id, client_id, dept_id, document_id, url, referring_url, title, category,
                content_type, source_type, pdf_page_number, retrieval_date, last_modified, etag,
                content_hash, is_active, version_id, visibility, doc_type, srv, ver_status, content
            ) = r
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
                excerpt=excerpt,
                client_id=client_id,
                document_id=document_id,
                referring_url=referring_url,
                content_type=content_type,
                source_type=source_type,
                pdf_page_number=pdf_page_number,
                retrieval_date=retrieval_date,
                last_modified=last_modified,
                etag=etag,
                content_hash=content_hash,
                is_active=bool(is_active if is_active is not None else 1),
                version_id=int(version_id or 1),
                visibility=visibility or "public",
                document_type=doc_type or "guideline",
                service=srv,
                verification_status=ver_status or "verified"
            ))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:top_k]

    def get_stats(self) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*), count(distinct department_id), count(distinct url) FROM chunks WHERE is_active IS NULL OR is_active = 1")
            row = cursor.fetchone()
            total_chunks = row[0] if row else 0
            dept_count = row[1] if row else 0
            url_count = row[2] if row else 0

            cursor.execute("SELECT department_id, count(*) FROM chunks WHERE is_active IS NULL OR is_active = 1 GROUP BY department_id")
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
    Unified Vector Store that prioritizes pgvector (PostgreSQL/Supabase).
    In development/testing (IS_PRODUCTION=False), provides seamless local resilience to built-in SQLite.
    In production (IS_PRODUCTION=True), enforces PostgreSQL/pgvector and strictly rejects silent SQLite fallback.
    """
    def __init__(self):
        self.sqlite_store = SQLiteVectorStore()
        self.pg_store = PgVectorStore(DATABASE_URL)
        self._use_pg = False
        self._production_db_error: Optional[str] = None
        self._check_and_init()

    def _check_and_init(self):
        provider = os.getenv("VECTOR_STORE_PROVIDER", VECTOR_STORE_PROVIDER).lower().strip()
        db_url = os.getenv("DATABASE_URL", self.pg_store.db_url).strip()
        self.pg_store.db_url = db_url

        if IS_PRODUCTION:
            if not db_url:
                self._use_pg = False
                self._production_db_error = "DATABASE_URL is not set in production. Production mandates PostgreSQL/pgvector."
                logger.error(f"❌ [pgvector] {self._production_db_error}")
                return

            if self.pg_store.check_connection():
                if self.pg_store.init_db():
                    self._use_pg = True
                    self._production_db_error = None
                    logger.info("⚡ [pgvector] Active! Operating on PostgreSQL/Supabase with native vector extension.")
                    return
                else:
                    self._use_pg = False
                    self._production_db_error = f"Database schema initialization failed for {mask_db_url(db_url)}"
                    logger.error(f"❌ [pgvector] {self._production_db_error}")
                    return
            else:
                self._use_pg = False
                self._production_db_error = f"Connection failed to PostgreSQL/pgvector at {mask_db_url(db_url)}"
                logger.error(f"❌ [pgvector] {self._production_db_error}")
                return

        if provider == "pgvector" and db_url:
            if self.pg_store.check_connection():
                if self.pg_store.init_db():
                    self._use_pg = True
                    logger.info("⚡ [pgvector] Active! Operating on PostgreSQL/Supabase with native vector extension.")
                    return
            masked_target = mask_db_url(db_url)
            logger.info(f"ℹ️ [pgvector] Target PostgreSQL ({masked_target}) is unreachable or initializing. Active backend: SQLite Vector Store (Local fallback).")
        else:
            logger.info("ℹ️ [pgvector] DATABASE_URL not set. Active backend: SQLite Vector Store (Local fallback).")

    def get_active_backend_name(self) -> str:
        if IS_PRODUCTION:
            return "pgvector (PostgreSQL)" if self._use_pg else "pgvector (unhealthy/disconnected)"
        return "pgvector (PostgreSQL)" if self._use_pg else "SQLite Vector Store (Local fallback)"

    def is_pgvector_active(self) -> bool:
        return self._use_pg

    def is_healthy(self) -> bool:
        if IS_PRODUCTION:
            return bool(self._use_pg and self.pg_store.check_connection())
        return True

    def add_chunks(self, chunks: List[Dict]):
        if IS_PRODUCTION:
            if not self._use_pg:
                self._check_and_init()
            if not self._use_pg:
                raise RuntimeError(
                    f"Cannot ingest chunks into production: PostgreSQL/pgvector is unavailable. "
                    f"Details: {self._production_db_error}"
                )
            try:
                self.pg_store.add_chunks(chunks)
            except Exception as e:
                self._use_pg = False
                self._production_db_error = f"pgvector add_chunks error: {mask_db_url(str(e))}"
                logger.error(f"❌ [pgvector] Ingestion error in production: {self._production_db_error}")
                raise RuntimeError(f"Production pgvector ingestion failed: {self._production_db_error}") from e
            return

        # Development fallback logic
        self.sqlite_store.add_chunks(chunks)
        try:
            if self.pg_store.check_connection():
                if self.pg_store.init_db():
                    self.pg_store.add_chunks(chunks)
                    self._use_pg = True
        except Exception as e:
            logger.warning(f"pgvector add_chunks notice: {mask_db_url(str(e))}; chunks saved in local SQLite.")

    def stage_and_activate_document_chunks(
        self,
        department_id: str,
        document_id: str,
        chunks: List[Dict],
        new_version_id: int
    ) -> bool:
        if IS_PRODUCTION:
            if not self._use_pg:
                self._check_and_init()
            if not self._use_pg:
                raise RuntimeError(
                    f"Cannot stage/activate chunks in production: PostgreSQL/pgvector is unavailable. "
                    f"Details: {self._production_db_error}"
                )
            return self.pg_store.stage_and_activate_document_chunks(department_id, document_id, chunks, new_version_id)

        ok = self.sqlite_store.stage_and_activate_document_chunks(department_id, document_id, chunks, new_version_id)
        if self._use_pg:
            try:
                if self.pg_store.check_connection() and self.pg_store.init_db():
                    self.pg_store.stage_and_activate_document_chunks(department_id, document_id, chunks, new_version_id)
            except Exception as e:
                logger.warning(f"pgvector stage_and_activate notice: {mask_db_url(str(e))}")
        return ok

    def deactivate_document(self, department_id: str, document_id: str):
        if IS_PRODUCTION:
            if not self._use_pg:
                raise RuntimeError("Cannot deactivate document in production: PostgreSQL/pgvector is unavailable.")
            self.pg_store.deactivate_document(department_id, document_id)
            return
        self.sqlite_store.deactivate_document(department_id, document_id)
        if self._use_pg:
            try:
                self.pg_store.deactivate_document(department_id, document_id)
            except Exception as e:
                logger.warning(f"pgvector deactivate_document notice: {mask_db_url(str(e))}")

    def get_active_document_versions(self, department_id: str) -> Dict[str, Dict]:
        if IS_PRODUCTION:
            if not self._use_pg:
                raise RuntimeError("Cannot read document versions in production: PostgreSQL/pgvector is unavailable.")
            return self.pg_store.get_active_document_versions(department_id)
        if self._use_pg:
            try:
                return self.pg_store.get_active_document_versions(department_id)
            except Exception as e:
                logger.warning(f"pgvector get_active_document_versions notice: {mask_db_url(str(e))}")
        return self.sqlite_store.get_active_document_versions(department_id)

    def clear(self, department_id: Optional[str] = None):
        if IS_PRODUCTION:
            if not self._use_pg:
                raise RuntimeError("Cannot clear production database: PostgreSQL/pgvector is unavailable.")
            try:
                self.pg_store.clear(department_id)
            except Exception as e:
                self._use_pg = False
                self._production_db_error = f"pgvector clear error: {mask_db_url(str(e))}"
                raise RuntimeError(f"Production pgvector clear failed: {self._production_db_error}") from e
            return

        self.sqlite_store.clear(department_id)
        if self._use_pg:
            try:
                self.pg_store.clear(department_id)
            except Exception as e:
                logger.warning(f"pgvector clear notice: {mask_db_url(str(e))}")

    def search(
        self,
        query: str,
        department_id: Optional[str] = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD
    ) -> List[RagCitation]:
        if IS_PRODUCTION:
            if not self._use_pg:
                raise RuntimeError(
                    f"Production vector store query failed: PostgreSQL/pgvector is unavailable. "
                    f"Details: {self._production_db_error or 'Connection offline'}. "
                    "Silent fallback to SQLite is strictly disabled in production."
                )
            try:
                return self.pg_store.search(query, department_id, top_k, threshold)
            except Exception as e:
                self._use_pg = False
                self._production_db_error = f"pgvector query error: {mask_db_url(str(e))}"
                logger.error(f"❌ [pgvector] Runtime error in production: {self._production_db_error}")
                raise RuntimeError(
                    f"Production PostgreSQL/pgvector search failed: {self._production_db_error}. "
                    "Silent fallback to SQLite is strictly disabled in production."
                ) from e

        # Development fallback logic
        if self._use_pg:
            try:
                return self.pg_store.search(query, department_id, top_k, threshold)
            except Exception as e:
                logger.warning(f"pgvector search runtime notice: {mask_db_url(str(e))}; falling back seamlessly to SQLite.")
                self._use_pg = False
        return self.sqlite_store.search(query, department_id, top_k, threshold)

    def get_stats(self) -> Dict:
        if IS_PRODUCTION:
            if not self._use_pg:
                return {
                    "backend": "pgvector (unhealthy/disconnected)",
                    "total_chunks": 0,
                    "error": self._production_db_error or "PostgreSQL/pgvector disconnected in production"
                }
            try:
                stats = self.pg_store.get_stats()
                stats["backend"] = "pgvector (PostgreSQL)"
                return stats
            except Exception as e:
                self._use_pg = False
                self._production_db_error = mask_db_url(str(e))
                return {
                    "backend": "pgvector (unhealthy/disconnected)",
                    "total_chunks": 0,
                    "error": self._production_db_error
                }

        # Development mode stats
        if self._use_pg:
            try:
                stats = self.pg_store.get_stats()
                stats["backend"] = "pgvector (PostgreSQL)"
                return stats
            except Exception as e:
                logger.warning(f"pgvector get_stats notice: {mask_db_url(str(e))}; falling back to SQLite stats.")
                self._use_pg = False
        stats = self.sqlite_store.get_stats()
        stats["backend"] = "SQLite Vector Store (Local fallback)"
        return stats

vector_store = UnifiedVectorStore()
