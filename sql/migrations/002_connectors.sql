
CREATE TABLE IF NOT EXISTS eail_sync_state (
 dataset_id TEXT NOT NULL, scope TEXT NOT NULL, generation TEXT NOT NULL,
 catalog_hash TEXT NOT NULL, synced_at TEXT NOT NULL, last_error TEXT NOT NULL,
 PRIMARY KEY(dataset_id,scope)
);
CREATE TABLE IF NOT EXISTS eail_sync_runs (
 id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, scope TEXT NOT NULL,
 status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eail_source_records (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, dataset_id TEXT NOT NULL, scope TEXT NOT NULL,
 source_record_id TEXT NOT NULL, payload TEXT NOT NULL, metadata TEXT NOT NULL,
 source_updated_at TEXT NOT NULL, synced_at TEXT NOT NULL, generation TEXT NOT NULL,
 UNIQUE(dataset_id,scope,source_record_id)
);
CREATE INDEX IF NOT EXISTS eail_source_dataset_idx ON eail_source_records(dataset_id,scope);
