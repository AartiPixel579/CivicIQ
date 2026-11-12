"""
pgvector Store for Township of Edison (CivicIQ)
PostgreSQL vector database store utilizing the pgvector extension for native vector similarity search.
"""

import os
import logging
from typing import List, Dict, Optional
import numpy as np
import psycopg2
from psycopg2.extras import execute_batch
from pgvector.psycopg2 import register_vector

from .config import (
    DATABASE_URL, SIMILARITY_THRESHOLD, TOP_K_RESULTS
)
from .models import RagCitation
from .embedder import embedder, EMBEDDING_DIM

logger = logging.getLogger("pgvector_store")

def mask_db_url(text: str) -> str:
    """Masks database passwords in connection strings or error messages for safe logging."""
    if not text:
        return ""
    import re
    # Mask password in URI pattern (e.g. postgresql://user:password@host:port/db)
    text = re.sub(r":([^:@\s]+)@([^\s:]+)", r":****@\2", text)
    # Mask password in DSN format (e.g. password=xyz)
    text = re.sub(r"password=([^\s]+)", r"password=****", text, flags=re.IGNORECASE)
    return text

class PgVectorStore:
    def __init__(self, db_url: str = DATABASE_URL, dim: int = EMBEDDING_DIM):
        self.db_url = db_url
        self.dim = dim
        self._connected = False
        self._init_error: Optional[str] = None

    def _normalize_db_url(self, raw_url: str) -> str:
        """
        Normalizes database URL for Supabase / PostgreSQL:
        - Converts postgres:// to postgresql://
        - Automatically appends sslmode=require for remote hosts (e.g. Supabase, Render, Neon)
        """
        url = (raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if "sslmode=" not in url.lower():
            is_local = any(h in url.lower() for h in ["localhost", "127.0.0.1", "host.docker.internal"])
            if not is_local:
                delimiter = "&" if "?" in url else "?"
                url = f"{url}{delimiter}sslmode=require"
        return url

    def _get_connection(self):
        active_url = self._normalize_db_url(self.db_url or os.getenv("DATABASE_URL", ""))
        if not active_url:
            raise ValueError("DATABASE_URL is not configured.")
        conn = psycopg2.connect(active_url, connect_timeout=10)
        register_vector(conn)
        return conn

    def check_connection(self) -> bool:
        """Tests if PostgreSQL with pgvector is reachable."""
        active_url = self._normalize_db_url(self.db_url or os.getenv("DATABASE_URL", ""))
        if not active_url:
            return False
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return True
        except Exception as e:
            logger.debug(f"pgvector connection test note: {mask_db_url(str(e))}")
            return False

    def init_db(self) -> bool:
        """Initializes pgvector extension and creates municipal chunks schema."""
        active_url = self._normalize_db_url(self.db_url or os.getenv("DATABASE_URL", ""))
        if not active_url:
            self._init_error = "DATABASE_URL is not configured."
            return False
        try:
            # Transaction 1: Schema creation (extension, table, base indexes)
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS municipal_knowledge_chunks (
                            id VARCHAR(64) PRIMARY KEY,
                            client_id VARCHAR(64) DEFAULT 'default',
                            department_id VARCHAR(64) NOT NULL,
                            document_id VARCHAR(128),
                            url TEXT NOT NULL,
                            referring_url TEXT,
                            title TEXT NOT NULL,
                            category VARCHAR(128),
                            content_type VARCHAR(128),
                            source_type VARCHAR(32) DEFAULT 'pdf',
                            pdf_page_number INT,
                            chunk_index INT,
                            content TEXT NOT NULL,
                            word_count INT,
                            retrieval_date TIMESTAMP,
                            last_modified TEXT,
                            etag TEXT,
                            content_hash VARCHAR(64),
                            is_active BOOLEAN DEFAULT TRUE,
                            version_id INT DEFAULT 1,
                            visibility VARCHAR(32) DEFAULT 'public',
                            document_type VARCHAR(64) DEFAULT 'guideline',
                            service VARCHAR(128),
                            verification_status VARCHAR(32) DEFAULT 'verified',
                            embedding vector({self.dim}),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    # Non-destructive migration for existing deployments
                    cur.execute("""
                        ALTER TABLE municipal_knowledge_chunks
                            ADD COLUMN IF NOT EXISTS client_id VARCHAR(64) DEFAULT 'default',
                            ADD COLUMN IF NOT EXISTS document_id VARCHAR(128),
                            ADD COLUMN IF NOT EXISTS referring_url TEXT,
                            ADD COLUMN IF NOT EXISTS content_type VARCHAR(128),
                            ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) DEFAULT 'pdf',
                            ADD COLUMN IF NOT EXISTS pdf_page_number INT,
                            ADD COLUMN IF NOT EXISTS retrieval_date TIMESTAMP,
                            ADD COLUMN IF NOT EXISTS last_modified TEXT,
                            ADD COLUMN IF NOT EXISTS etag TEXT,
                            ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
                            ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
                            ADD COLUMN IF NOT EXISTS version_id INT DEFAULT 1,
                            ADD COLUMN IF NOT EXISTS visibility VARCHAR(32) DEFAULT 'public',
                            ADD COLUMN IF NOT EXISTS document_type VARCHAR(64) DEFAULT 'guideline',
                            ADD COLUMN IF NOT EXISTS service VARCHAR(128),
                            ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32) DEFAULT 'verified';
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_dept ON municipal_knowledge_chunks(department_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_url ON municipal_knowledge_chunks(url);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_active ON municipal_knowledge_chunks(department_id, is_active);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_ver ON municipal_knowledge_chunks(document_id, version_id);")
                conn.commit()

            # Transaction 2: Vector index creation (HNSW with graceful IVFFlat fallback)
            # Table is safely committed above, so an HNSW rollback will never drop the table.
            with self._get_connection() as conn:
                hnsw_succeeded = False
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            CREATE INDEX IF NOT EXISTS idx_chunks_hnsw 
                            ON municipal_knowledge_chunks 
                            USING hnsw (embedding vector_cosine_ops);
                        """)
                    conn.commit()
                    hnsw_succeeded = True
                    logger.info("⚡ [pgvector] Native HNSW vector index verified.")
                except Exception as hnsw_err:
                    conn.rollback()
                    logger.warning(f"ℹ️ [pgvector] HNSW index creation note ({mask_db_url(str(hnsw_err))}); falling back to IVFFlat index.")

                if not hnsw_succeeded:
                    try:
                        with conn.cursor() as cur_fallback:
                            cur_fallback.execute("""
                                CREATE INDEX IF NOT EXISTS idx_chunks_ivfflat 
                                ON municipal_knowledge_chunks 
                                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
                            """)
                        conn.commit()
                        logger.info("⚡ [pgvector] IVFFlat vector index verified as fallback.")
                    except Exception as ivf_err:
                        conn.rollback()
                        logger.warning(f"⚠️ [pgvector] IVFFlat index creation note ({mask_db_url(str(ivf_err))}); exact k-NN vector scan remains operational.")

            self._connected = True
            self._init_error = None
            logger.info("pgvector schema and vector extension verified successfully.")
            return True
        except Exception as e:
            err_msg = f"Failed to initialize pgvector database: {mask_db_url(str(e))}"
            logger.error(err_msg)
            self._connected = False
            self._init_error = err_msg
            return False

    def clear(self, department_id: Optional[str] = None):
        """Deletes chunks from PostgreSQL."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if department_id:
                    cur.execute("DELETE FROM municipal_knowledge_chunks WHERE department_id = %s;", (department_id,))
                else:
                    cur.execute("DELETE FROM municipal_knowledge_chunks;")
            conn.commit()
        logger.info(f"pgvector store cleared (dept: {department_id or 'all'}).")

    def add_chunks(self, chunks: List[Dict]):
        """
        Embeds chunk contents and upserts them into PostgreSQL with pgvector,
        preserving full document provenance and versioning metadata.
        """
        if not chunks:
            return

        texts = [ch["content"] for ch in chunks]
        embeddings = embedder.embed_batch(texts)

        records = []
        for ch, emb in zip(chunks, embeddings):
            records.append((
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
                bool(ch.get("is_active", True)),
                int(ch.get("version_id", 1)),
                ch.get("visibility", "public"),
                ch.get("document_type", "guideline"),
                ch.get("service"),
                ch.get("verification_status", "verified"),
                emb.tolist() # pgvector handles list or np.ndarray with register_vector
            ))

        upsert_sql = """
            INSERT INTO municipal_knowledge_chunks
            (id, client_id, department_id, document_id, url, referring_url, title, category,
             content_type, source_type, pdf_page_number, chunk_index, content, word_count,
             retrieval_date, last_modified, etag, content_hash, is_active, version_id,
             visibility, document_type, service, verification_status, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                department_id = EXCLUDED.department_id,
                document_id = EXCLUDED.document_id,
                url = EXCLUDED.url,
                referring_url = EXCLUDED.referring_url,
                title = EXCLUDED.title,
                category = EXCLUDED.category,
                content_type = EXCLUDED.content_type,
                source_type = EXCLUDED.source_type,
                pdf_page_number = EXCLUDED.pdf_page_number,
                chunk_index = EXCLUDED.chunk_index,
                content = EXCLUDED.content,
                word_count = EXCLUDED.word_count,
                retrieval_date = EXCLUDED.retrieval_date,
                last_modified = EXCLUDED.last_modified,
                etag = EXCLUDED.etag,
                content_hash = EXCLUDED.content_hash,
                is_active = EXCLUDED.is_active,
                version_id = EXCLUDED.version_id,
                visibility = EXCLUDED.visibility,
                document_type = EXCLUDED.document_type,
                service = EXCLUDED.service,
                verification_status = EXCLUDED.verification_status,
                embedding = EXCLUDED.embedding;
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_batch(cur, upsert_sql, records, page_size=100)
            conn.commit()

        logger.info(f"Successfully upserted {len(chunks)} chunks into pgvector.")

    def stage_and_activate_document_chunks(
        self,
        department_id: str,
        document_id: str,
        chunks: List[Dict],
        new_version_id: int
    ) -> bool:
        """
        Safely stages new chunks for a document (is_active=FALSE), validates insertion,
        then atomically activates the new version and deactivates prior versions in one transaction.
        """
        if not chunks:
            return False

        texts = [ch["content"] for ch in chunks]
        embeddings = embedder.embed_batch(texts)

        records = []
        for ch, emb in zip(chunks, embeddings):
            records.append((
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
                False,  # staged inactive first
                int(new_version_id),
                ch.get("visibility", "public"),
                ch.get("document_type", "guideline"),
                ch.get("service"),
                ch.get("verification_status", "verified"),
                emb.tolist()
            ))

        upsert_sql = """
            INSERT INTO municipal_knowledge_chunks
            (id, client_id, department_id, document_id, url, referring_url, title, category,
             content_type, source_type, pdf_page_number, chunk_index, content, word_count,
             retrieval_date, last_modified, etag, content_hash, is_active, version_id,
             visibility, document_type, service, verification_status, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET
                content = EXCLUDED.content,
                word_count = EXCLUDED.word_count,
                retrieval_date = EXCLUDED.retrieval_date,
                last_modified = EXCLUDED.last_modified,
                etag = EXCLUDED.etag,
                content_hash = EXCLUDED.content_hash,
                is_active = EXCLUDED.is_active,
                version_id = EXCLUDED.version_id,
                embedding = EXCLUDED.embedding;
        """

        with self._get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    execute_batch(cur, upsert_sql, records, page_size=100)
                    cur.execute(
                        "SELECT count(*) FROM municipal_knowledge_chunks WHERE department_id = %s AND document_id = %s AND version_id = %s;",
                        (department_id, document_id, int(new_version_id))
                    )
                    staged_count = cur.fetchone()[0]
                    if staged_count < len(records):
                        raise RuntimeError(f"Staging validation failed: expected {len(records)}, got {staged_count}")

                    # Atomically deactivate older versions (and any legacy unversioned chunks for this URL) and activate new version
                    doc_urls = list({ch["url"] for ch in chunks if ch.get("url")})
                    cur.execute(
                        "UPDATE municipal_knowledge_chunks SET is_active = FALSE WHERE department_id = %s AND document_id = %s AND version_id <> %s;",
                        (department_id, document_id, int(new_version_id))
                    )
                    if doc_urls:
                        cur.execute(
                            "UPDATE municipal_knowledge_chunks SET is_active = FALSE WHERE department_id = %s AND document_id IS NULL AND url = ANY(%s);",
                            (department_id, doc_urls)
                        )
                    cur.execute(
                        "UPDATE municipal_knowledge_chunks SET is_active = TRUE WHERE department_id = %s AND document_id = %s AND version_id = %s;",
                        (department_id, document_id, int(new_version_id))
                    )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def deactivate_document(self, department_id: str, document_id: str):
        """Marks all chunks for a removed document inactive without deleting historical metadata."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE municipal_knowledge_chunks SET is_active = FALSE WHERE department_id = %s AND document_id = %s;",
                    (department_id, document_id)
                )
            conn.commit()

    def get_active_document_versions(self, department_id: str) -> Dict[str, Dict]:
        """Returns active document metadata keyed by document_id."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT document_id, MAX(version_id), MAX(content_hash), MAX(etag), MAX(last_modified), MAX(url)
                    FROM municipal_knowledge_chunks
                    WHERE department_id = %s AND is_active = TRUE AND document_id IS NOT NULL
                    GROUP BY document_id;
                """, (department_id,))
                rows = cur.fetchall()
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

    def search(
        self,
        query: str,
        department_id: Optional[str] = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD
    ) -> List[RagCitation]:
        """
        Executes vector cosine similarity search in PostgreSQL using the <=> operator.
        Cosine similarity = 1 - cosine_distance.
        """
        query_vec = embedder.embed_text(query).tolist()

        # Cosine distance in pgvector is <=> (0 = identical, 2 = opposite)
        # Similarity = 1 - (embedding <=> query_vec)
        sql = """
            SELECT id, client_id, department_id, document_id, url, referring_url, title, category,
                   content_type, source_type, pdf_page_number, retrieval_date, last_modified, etag,
                   content_hash, is_active, version_id, visibility, document_type, service,
                   verification_status, content,
                   (1.0 - (embedding <=> %s::vector)) AS similarity
            FROM municipal_knowledge_chunks
            WHERE (%s IS NULL OR department_id = %s)
              AND (is_active IS NULL OR is_active = TRUE)
              AND (1.0 - (embedding <=> %s::vector)) >= %s
            ORDER BY (embedding <=> %s::vector) ASC
            LIMIT %s;
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    query_vec,
                    department_id,
                    department_id,
                    query_vec,
                    threshold,
                    query_vec,
                    top_k
                ))
                rows = cur.fetchall()

        results = []
        for r in rows:
            (
                chunk_id, client_id, dept_id, document_id, url, referring_url, title, category,
                content_type, source_type, pdf_page_number, retrieval_date, last_modified, etag,
                content_hash, is_active, version_id, visibility, doc_type, srv, ver_status,
                content, score
            ) = r
            excerpt = content.strip().replace("\n", " ")
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "..."

            results.append(RagCitation(
                url=url,
                title=title,
                category=category or "General",
                department_id=dept_id,
                relevance_score=round(float(score), 3),
                excerpt=excerpt,
                client_id=client_id,
                document_id=document_id,
                referring_url=referring_url,
                content_type=content_type,
                source_type=source_type,
                pdf_page_number=pdf_page_number,
                retrieval_date=str(retrieval_date) if retrieval_date else None,
                last_modified=last_modified,
                etag=etag,
                content_hash=content_hash,
                is_active=bool(is_active if is_active is not None else True),
                version_id=int(version_id or 1),
                visibility=visibility or "public",
                document_type=doc_type or "guideline",
                service=srv,
                verification_status=ver_status or "verified"
            ))

        return results

    def get_stats(self) -> Dict:
        """Returns active chunk statistics from PostgreSQL."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*), count(distinct department_id), count(distinct url)
                    FROM municipal_knowledge_chunks
                    WHERE is_active IS NULL OR is_active = TRUE;
                """)
                row = cur.fetchone()
                total = row[0] if row else 0
                depts = row[1] if row else 0
                urls = row[2] if row else 0

                cur.execute("""
                    SELECT department_id, count(*)
                    FROM municipal_knowledge_chunks
                    WHERE is_active IS NULL OR is_active = TRUE
                    GROUP BY department_id;
                """)
                by_dept = dict(cur.fetchall())

        return {
            "backend": "pgvector (PostgreSQL)",
            "total_chunks": total,
            "department_count": depts,
            "url_count": urls,
            "chunks_by_department": by_dept
        }
