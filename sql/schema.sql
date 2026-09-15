CREATE TABLE IF NOT EXISTS eail_documents (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, content_hash TEXT NOT NULL,
 version INTEGER NOT NULL, metadata TEXT NOT NULL, embedding_id TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eail_chunks (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES eail_documents(id) ON DELETE CASCADE,
 section TEXT NOT NULL, chunk_index INTEGER NOT NULL, content TEXT NOT NULL,
 embedding TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eail_chunks_document_idx ON eail_chunks(document_id);
CREATE TABLE IF NOT EXISTS eail_ingestion (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eail_facts (
 id TEXT PRIMARY KEY, department TEXT NOT NULL, kind TEXT NOT NULL, period TEXT NOT NULL,
 payload TEXT NOT NULL, metadata TEXT NOT NULL, updated_at TEXT NOT NULL, source_updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS eail_facts_scope_idx ON eail_facts(department,kind,period);
CREATE TABLE IF NOT EXISTS eail_actions (
 id TEXT PRIMARY KEY, requester TEXT NOT NULL, department TEXT NOT NULL,
 title TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
 approver TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eail_tasks (
 id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE REFERENCES eail_actions(id),
 department TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL
);
