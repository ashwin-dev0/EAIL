# Enterprise Agentic Intelligence Layer (EAIL)

A complete runnable backend reference implementation extending the hardened multi-format RAG project with enterprise access policies, departmental MCP tools, structured analytics, local inference, decision support, and approved follow-up tasks.

**Release: 0.1.0.** This package provides implemented features, executable tests, and deployment examples. It is not a claim that a production enterprise installation, existing EC2 integration, or security certification has already been completed.

The existing CLI is retained. FastAPI provides an authenticated API and interactive API documentation at `http://127.0.0.1:8000/docs`. There is no separate React portal in this backend release. Existing applications remain systems of record.

Read these files in order:

1. `SETUP.md` — Ubuntu/EC2 setup and exact commands.
2. `HOW_IT_WORKS.md` — component responsibilities and request flow.
3. `MIGRATION.md` — preserve your existing `~/pdf-rag` and ShaktiDB records.
4. `SECURITY.md` — implemented security boundaries and rollout requirements.
5. `FEATURES.md` — feature preservation, implementation status, and limits.
6. `TEST_REPORT.md` — checks actually performed.

## Included code

| Path | Purpose |
|---|---|
| `src/config.py` | Configuration, local-only AI policy, resource limits |
| `src/database.py` | Parameterized SQLite / ShaktiDB-compatible PostgreSQL access |
| `src/auth.py` | Server-owned roles/ACLs; opaque tokens and optional offline private-SSO JWT verification |
| `src/file_safety.py` | Bounded regular files, signatures, archive checks, explicit ACL sidecars |
| `src/extractors/multiformat.py` | Text, PDF, scanned PDF, images/OCR, Office, OpenDocument extraction |
| `src/chunking.py`, `src/embeddings.py` | Existing chunk defaults and local MiniLM embeddings |
| `src/ingest.py` | Snapshot ingestion and transactional chunk replacement |
| `src/watcher.py` | Background automatic ingestion / deletion reconciliation |
| `src/ingestion_status.py` | Ingestion history |
| `src/search.py` | ACL-filtered hybrid retrieval and source freshness checks |
| `src/guardrails/checks.py` | Input/context injection checks and numeric support |
| `src/ollama_client.py` | Local Ollama structured chat and inference timings |
| `src/evaluation/judge.py` | Independent judge, metrics and acceptance threshold |
| `src/orchestrator.py` | Bounded natural-language plans, tool calls, grounded synthesis |
| `src/analytics.py` | Budget variance, department summaries, scenarios, baseline forecasts |
| `src/mcp_server.py`, `src/mcp_gateway.py` | Genuine MCP JSON-RPC over local stdio |
| `src/workflows.py` | Approval and idempotent local task execution |
| `src/api.py` | Authenticated API, request limits, safe errors |
| `src/ask.py` | Interactive terminal interface |
| `src/health.py` | DB, model, OCR and dependency health |
| `sql/` | Separate EAIL tables and least-privilege role example |
| `scripts/` | Setup, source export/import, users, provisioning, backup and checks |
| `examples/` | All seven departments' synthetic structured records and RAG documents |
| `deploy/` | Hardened API and watcher systemd units |
| `tests/` | Acceptance, security, parser, API, SSO and MCP checks |

## Defaults preserved

`TOP_K=10`, similarity threshold `0.30`, chunk size `1000`, overlap `200`, local `all-MiniLM-L6-v2`, generator `llama3.2:3b`, separate judge `qwen2.5:1.5b`, and four rotating metadata-only JSONL logs.

The newer tested generator selection in some earlier terminal sessions differed. Both generator and judge remain configurable; this consolidated default follows the hardened RAG specification and enforces separate model tags.

## Quick offline demonstration

From this project's root, with Python 3.11/3.12:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
chmod 600 .env
# Change EMBEDDING_BACKEND to lexical_demo for the explicit no-model demo only.
nano .env
python scripts/init_db.py
python scripts/manage_users.py demo-cfo --role CFO --departments Finance Procurement --clearance 2
python scripts/import_facts.py examples/facts.json
python -m src.ask
```

Paste the newly generated token at the private prompt, then ask `Finance budget variance 2026-08`. The query uses actual MCP transport and deterministic arithmetic; this example does not require Ollama. For real document reasoning, use MiniLM and install the two local Ollama models as described in `SETUP.md`.
