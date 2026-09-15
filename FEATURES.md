# Feature status and scope

| Feature | Status |
|---|---|
| Existing CLI, ingestion/status commands | Implemented |
| PDF text and scanned PDF OCR | Implemented |
| PNG/JPEG/TIFF/BMP/WEBP OCR | Implemented |
| TXT/MD/CSV/JSON/XML/HTML | Implemented |
| DOCX/PPTX/XLSX and ODT/ODS/ODP | Implemented |
| Top-K 10, 1000/200 chunking, threshold .30 | Preserved configurable defaults |
| Local normalized MiniLM embeddings | Implemented; local weights must be provisioned |
| Automatic add/change/delete watcher | Implemented as bounded polling/reconciliation |
| Transactional replacement and ingestion history | Implemented |
| Injection guards, citations, separate judge/regeneration | Implemented |
| Fast path | Preserved as explicit safe evidence-excerpt mode; overlap-only acceptance removed |
| Four metadata-only rotating logs | Implemented |
| Department/clearance/user/role ACLs | Implemented |
| Private enterprise SSO | Offline RS256 bearer verification implemented; enterprise IdP/login flow external |
| Genuine MCP backend | Internal stdio server/gateway implemented and SDK interoperability tested |
| All seven departments | Synthetic fixtures and scoped generic read tools provided |
| Enterprise source connector | Read-only PostgreSQL-compatible export/normalized import pattern provided; real schemas/API adapters must be supplied |
| Conversational structured analytics | Budget, summaries, explicit-period cross-department queries implemented |
| Decision support | Hypothetical spending scenarios and transparent forecast baseline implemented |
| Agentic behavior | Bounded read-only routing/tool execution; one synthesis flow |
| Approved actions | Local task proposal/approval/execution with idempotency implemented |
| React executive portal | Not included; CLI, authenticated API and API docs are available |
| Arbitrary SQL, autonomous financial/HR changes | Intentionally unavailable |
| Knowledge graph / causal inference | Not implemented; normalized source IDs and approved metric definitions provided |
| Enterprise vector index / distributed queues | Not implemented; small-index scan and single reconciliation worker provided |
| Immutable audit store / shared answer cache | Not implemented |
| On-premise/private deployment | Supported by local-only runtime and deployment examples; host-level controls still required |

## Data/semantic contract

`eail_facts` retains department, source ID, record kind, explicit reporting period, typed payload, ACL metadata and update time. Supported budgets use approved budget and recorded actual; variance equals actual minus budget. Source exports must align fiscal calendars, category definitions, ownership, currency and aggregation grain. Prevent duplicated category totals at the source normalization stage. EAIL cannot establish a single truth if conflicting departmental definitions are imported without reconciliation.

Structured reads use developer-authored queries; no model-authored SQL is executed. Archived source versions and organizational business catalogs can be extended separately. The current version number/hash supports current-document traceability; it does not retain every historical source byte version automatically.

## Freshness timestamps

Structured `updated_at` is the EAIL synchronization timestamp. Optional `source_updated_at` retains a supplied authoritative-source timestamp; an empty string means it was not supplied. Answers must not interpret synchronization time as proof the upstream business record was recently updated. Source adapters should provide timezone-aware source timestamps and preserve stable IDs.
