-- City of Pixelvyne - pgvector Initialization Script
-- Enables vector extension and sets up municipal chunks schema

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS municipal_knowledge_chunks (
    id VARCHAR(64) PRIMARY KEY,
    department_id VARCHAR(64) NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    category VARCHAR(128),
    chunk_index INT,
    content TEXT NOT NULL,
    word_count INT,
    embedding vector(128),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_dept ON municipal_knowledge_chunks(department_id);
CREATE INDEX IF NOT EXISTS idx_chunks_url ON municipal_knowledge_chunks(url);

-- HNSW cosine distance index for high-speed similarity search
CREATE INDEX IF NOT EXISTS idx_chunks_hnsw 
ON municipal_knowledge_chunks 
USING hnsw (embedding vector_cosine_ops);
