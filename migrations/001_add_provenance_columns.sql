-- Migration 001: Non-destructive addition of document provenance & versioning columns
-- Safe to run multiple times on existing Supabase / PostgreSQL deployments.

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

UPDATE municipal_knowledge_chunks
SET is_active = TRUE
WHERE is_active IS NULL;

UPDATE municipal_knowledge_chunks
SET version_id = 1
WHERE version_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_active ON municipal_knowledge_chunks(department_id, is_active);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_ver ON municipal_knowledge_chunks(document_id, version_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON municipal_knowledge_chunks(content_hash);
