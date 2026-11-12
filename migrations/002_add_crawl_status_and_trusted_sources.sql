-- Migration 002: Trusted Source Registry and Incremental Crawl Run Audit Tables
-- Safe to run multiple times on existing Supabase / PostgreSQL deployments.

CREATE TABLE IF NOT EXISTS trusted_sources (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(64) DEFAULT 'default',
    department_id VARCHAR(64) NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_domain VARCHAR(255),
    referring_url TEXT,
    source_type VARCHAR(32) DEFAULT 'html',
    discovered_via VARCHAR(64) DEFAULT 'admin_config',
    is_approved BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    consecutive_misses INT DEFAULT 0,
    last_checked_at TIMESTAMP,
    last_status_code INT,
    etag TEXT,
    last_modified TEXT,
    content_hash VARCHAR(64),
    active_version_id INT DEFAULT 1,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(department_id, canonical_url)
);

CREATE INDEX IF NOT EXISTS idx_trusted_dept_active ON trusted_sources(department_id, is_active, is_approved);
CREATE INDEX IF NOT EXISTS idx_trusted_canonical ON trusted_sources(canonical_url);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(64) DEFAULT 'default',
    department_id VARCHAR(64) NOT NULL,
    root_url TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(32) NOT NULL,
    pages_discovered INT DEFAULT 0,
    pdfs_discovered INT DEFAULT 0,
    new_docs INT DEFAULT 0,
    updated_docs INT DEFAULT 0,
    unchanged_docs INT DEFAULT 0,
    inactive_docs INT DEFAULT 0,
    failed_docs INT DEFAULT 0,
    error_summary JSONB
);

CREATE INDEX IF NOT EXISTS idx_crawl_runs_dept_time ON crawl_runs(department_id, started_at DESC);
