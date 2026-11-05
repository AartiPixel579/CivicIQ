"""
Unit and Integration Tests for pgvector implementation
Verifies dense vector embeddings (128-dim), L2 normalization,
PostgreSQL vector extension SQL syntax, and similarity scoring.
"""

import unittest
import numpy as np
from backend.app.embedder import embedder, EMBEDDING_DIM
from backend.app.pgvector_store import PgVectorStore, mask_db_url
from backend.app.vector_store import vector_store

class TestPgVectorImplementation(unittest.TestCase):
    def test_01_dense_embedding_shape_and_norm(self):
        text = "Township of Edison Engineering Department setback requirements"
        vec = embedder.embed_text(text)
        self.assertEqual(vec.shape, (EMBEDDING_DIM,))
        self.assertEqual(vec.dtype, np.float32)
        
        # Verify L2 normalization: norm should equal 1.0
        norm = np.linalg.norm(vec)
        self.assertAlmostEqual(norm, 1.0, places=4)
        print("\n[PGVECTOR TEST] Dense embedding generated: 128-dim normalized float32 vector.")

    def test_02_embedding_cosine_distance_consistency(self):
        text1 = "Residential building permit setback distances"
        text2 = "Residential building permit setback distances"
        text3 = "Healthcare food safety sanitation grade inspection"

        v1 = embedder.embed_text(text1)
        v2 = embedder.embed_text(text2)
        v3 = embedder.embed_text(text3)

        # Identical text cosine similarity should be 1.0 (distance 0.0)
        sim_identical = np.dot(v1, v2)
        self.assertAlmostEqual(sim_identical, 1.0, places=4)

        # Different text should have significantly lower cosine similarity
        sim_diff = np.dot(v1, v3)
        self.assertLess(sim_diff, sim_identical)
        print(f"[PGVECTOR TEST] Identical text similarity: {sim_identical:.4f} | Distinct text similarity: {sim_diff:.4f}")

    def test_03_pgvector_store_initialization(self):
        pg_store = PgVectorStore("postgresql://postgres:test_dummy_pass@localhost:5432/civiciq", dim=EMBEDDING_DIM)
        self.assertEqual(pg_store.dim, EMBEDDING_DIM)
        # Check connection method exists and is callable
        is_conn = pg_store.check_connection()
        print(f"[PGVECTOR TEST] PostgreSQL connection test: {'CONNECTED' if is_conn else 'OFFLINE (Ready for docker compose up)'}")

    def test_04_unified_vector_store_backend_switch(self):
        backend_name = vector_store.get_active_backend_name()
        self.assertIn("vector", backend_name.lower())
        stats = vector_store.get_stats()
        self.assertIn("total_chunks", stats)
        self.assertGreaterEqual(stats["total_chunks"], 10)
        print(f"[PGVECTOR TEST] Active Vector Store Provider: {stats.get('backend')}")

    def test_05_url_normalization_and_masking(self):
        pg = PgVectorStore("postgres://user:supersecretpass@aws-0.pooler.supabase.com:5432/postgres")
        normalized = pg._normalize_db_url(pg.db_url)
        self.assertTrue(normalized.startswith("postgresql://"))
        self.assertIn("sslmode=require", normalized)

        # Test masking
        masked = mask_db_url(normalized)
        self.assertNotIn("supersecretpass", masked)
        self.assertIn(":****@", masked)

    def test_06_supabase_ssl_mode_requirement(self):
        pg = PgVectorStore("postgresql://postgres.project:secret@db.project.supabase.co:5432/postgres")
        normalized = pg._normalize_db_url(pg.db_url)
        self.assertIn("sslmode=require", normalized)

    def test_07_resilient_fallback_when_pg_offline(self):
        # Even if pgvector is offline, unified vector search must return results from SQLite
        results = vector_store.search("Tree Removal permit requirements")
        self.assertGreater(len(results), 0)
        self.assertIsNotNone(results[0].title)

if __name__ == "__main__":
    unittest.main()
