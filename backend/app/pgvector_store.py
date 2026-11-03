"""
pgvector Store for City of Pixelvyne
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

class PgVectorStore:
    def __init__(self, db_url: str = DATABASE_URL, dim: int = EMBEDDING_DIM):
        self.db_url = db_url
        self.dim = dim
        self._connected = False

    def _get_connection(self):
        conn = psycopg2.connect(self.db_url)
        register_vector(conn)
        return conn

    def check_connection(self) -> bool:
        """Tests if PostgreSQL with pgvector is reachable."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return True
        except Exception as e:
            logger.debug(f"pgvector connection test failed: {e}")
            return False

    def init_db(self):
        """Initializes pgvector extension and creates municipal chunks schema."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Enable pgvector extension
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                    # 2. Create chunks table with vector column
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS municipal_knowledge_chunks (
                            id VARCHAR(64) PRIMARY KEY,
                            department_id VARCHAR(64) NOT NULL,
                            url TEXT NOT NULL,
                            title TEXT NOT NULL,
                            category VARCHAR(128),
                            chunk_index INT,
                            content TEXT NOT NULL,
                            word_count INT,
                            embedding vector({self.dim}),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

                    # 3. Create indices (HNSW cosine index for sub-millisecond retrieval)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_dept ON municipal_knowledge_chunks(department_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_url ON municipal_knowledge_chunks(url);")
                    try:
                        cur.execute("""
                            CREATE INDEX IF NOT EXISTS idx_chunks_hnsw 
                            ON municipal_knowledge_chunks 
                            USING hnsw (embedding vector_cosine_ops);
                        """)
                    except Exception as idx_err:
                        # Fallback to IVFFlat if HNSW is not enabled in older pgvector
                        logger.warning(f"HNSW index creation note: {idx_err}; falling back to IVFFlat index.")
                        cur.execute("""
                            CREATE INDEX IF NOT EXISTS idx_chunks_ivfflat 
                            ON municipal_knowledge_chunks 
                            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
                        """)

                conn.commit()
            self._connected = True
            logger.info("pgvector schema initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize pgvector database: {e}")
            self._connected = False
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
        Embeds chunk contents and upserts them into PostgreSQL with pgvector.
        """
        if not chunks:
            return

        texts = [ch["content"] for ch in chunks]
        embeddings = embedder.embed_batch(texts)

        records = []
        for ch, emb in zip(chunks, embeddings):
            records.append((
                ch["id"],
                ch["department_id"],
                ch["url"],
                ch["title"],
                ch.get("category", "General"),
                ch.get("chunk_index", 0),
                ch["content"],
                len(ch["content"].split()),
                emb.tolist() # pgvector handles list or np.ndarray with register_vector
            ))

        upsert_sql = f"""
            INSERT INTO municipal_knowledge_chunks 
            (id, department_id, url, title, category, chunk_index, content, word_count, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET
                department_id = EXCLUDED.department_id,
                url = EXCLUDED.url,
                title = EXCLUDED.title,
                category = EXCLUDED.category,
                chunk_index = EXCLUDED.chunk_index,
                content = EXCLUDED.content,
                word_count = EXCLUDED.word_count,
                embedding = EXCLUDED.embedding;
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_batch(cur, upsert_sql, records, page_size=100)
            conn.commit()

        logger.info(f"Successfully upserted {len(chunks)} chunks into pgvector.")

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
            SELECT id, department_id, url, title, category, content,
                   (1.0 - (embedding <=> %s::vector)) AS similarity
            FROM municipal_knowledge_chunks
            WHERE (%s IS NULL OR department_id = %s)
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
            chunk_id, dept_id, url, title, category, content, score = r
            excerpt = content.strip().replace("\n", " ")
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "..."

            results.append(RagCitation(
                url=url,
                title=title,
                category=category or "General",
                department_id=dept_id,
                relevance_score=round(float(score), 3),
                excerpt=excerpt
            ))

        return results

    def get_stats(self) -> Dict:
        """Returns statistics from PostgreSQL."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*), count(distinct department_id), count(distinct url) 
                    FROM municipal_knowledge_chunks;
                """)
                row = cur.fetchone()
                total = row[0] if row else 0
                depts = row[1] if row else 0
                urls = row[2] if row else 0

                cur.execute("SELECT department_id, count(*) FROM municipal_knowledge_chunks GROUP BY department_id;")
                by_dept = dict(cur.fetchall())

        return {
            "backend": "pgvector (PostgreSQL)",
            "total_chunks": total,
            "department_count": depts,
            "url_count": urls,
            "chunks_by_department": by_dept
        }
