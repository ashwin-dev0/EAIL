# Preserve the existing RAG project

This is a new project folder and a new schema namespace. It does not replace the live files previously edited on your EC2 machine, and it does not alter legacy `documents` or `document_chunks` tables.

1. Keep `~/pdf-rag` working. Back up its DB and source documents under your existing procedure.
2. Extract EAIL to `~/eail`. Configure a dedicated `eaildb`, separate runtime role and separate credentials.
3. Provision/copy the existing approved MiniLM weights into EAIL's local model directory. Reuse installed local Ollama models.
4. Create your EAIL user roles before migrating documents.
5. Copy desired source documents to EAIL's `documents/` directory. For every copied document, create an explicit five-field ACL sidecar. Do not bulk-label sensitive records as Public.
6. Run EAIL ingestion. Reembedding is intentional: legacy indexes did not carry the required enterprise ACL/version metadata.
7. Validate representative questions for every format and for allowed/denied users. Test updated, deleted and revoked documents.
8. Compare structured analytics with authoritative departmental reports before broader access.
9. Keep the old watcher running against its OLD document folder during evaluation. The EAIL watcher watches the NEW folder. Do not point two differently governed projects at the same mutable tree during migration.
10. Switch consumers only after target-host acceptance tests and operational recovery checks pass.

The normal CLI remains `python -m src.ask`; ingestion remains `python -m src.ingest`; status remains `python -m src.ingestion_status`. Configuration defaults and log channels are preserved, but EAIL deliberately adds authentication and requires document access metadata.
