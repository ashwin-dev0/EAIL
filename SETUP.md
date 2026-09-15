# Setup — Ubuntu / EC2 / ShaktiDB / Ollama

## 1. Keep the working project

Extract this package as a NEW `~/eail` directory. Do not overwrite or delete `~/pdf-rag`, its `.env`, source documents, or `ragdb`. This package uses separate EAIL table names. See `MIGRATION.md` before importing old documents.

Commands below assume you are user `ubuntu`, project path `/home/ubuntu/eail`, and Python 3.11/3.12.

```bash
cd ~/eail
sudo apt update
sudo apt install -y python3-venv python3-pip tesseract-ocr postgresql-client fonts-dejavu-core
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
mkdir -p data logs models documents
chmod 700 data logs documents
```

Installation/model provisioning may use a connected administrative staging host. Copy approved packages and weights into the private environment. Runtime document embedding and LLM inference do not download models or send enterprise content to public services.

## 2. Database choice

### Isolated SQLite demo

Leave `DATABASE_URL` unset. The default is `data/eail.db`. Initialize explicitly:

```bash
python scripts/init_db.py
```

SQLite is useful for development and sequential demonstrations, not high-concurrency enterprise deployment.

### Dedicated ShaktiDB database

Use your existing ShaktiDB administrator to create a dedicated database named `eaildb`. The included schema uses ordinary tables and JSON stored as text; it does not depend on a vector extension.

```bash
psql -h 127.0.0.1 -p 15234 -U postgres -d postgres
```

Inside the administrator session:

```sql
CREATE DATABASE eaildb;
\connect eaildb
\i /home/ubuntu/eail/sql/schema.sql
\i /home/ubuntu/eail/sql/bootstrap_roles.sql
\password eail_runtime
```

The bootstrap role script requires PostgreSQL-compatible `DO`, roles and grants. Validate those features against your ShaktiDB build. Adapt the client command/path if ShaktiDB supplies a different `psql` client. The package has not been executed against your live ShaktiDB instance.

Set `.env` using that application's password, URL-encoded when necessary:

```dotenv
DATABASE_URL=postgresql://eail_runtime:URL_ENCODED_PASSWORD@127.0.0.1:15234/eaildb
```

Do not run schema initialization as the runtime role. The API and CLI only verify tables. They do not create or alter schemas at startup. The runtime role is not a superuser, database creator, schema owner, or role administrator.

Remote private databases require `sslmode=verify-full` and an enterprise CA. Do not put database URLs containing passwords in shell command history.

## 3. Provision local MiniLM

The default directory is `~/eail/models/all-MiniLM-L6-v2`. Runtime strictly uses `local_files_only=True`.

If the existing RAG host already has a cached MiniLM model:

```bash
python scripts/provision_embeddings.py
```

Or copy an approved local model through the helper:

```bash
python scripts/provision_embeddings.py --source /path/to/approved/all-MiniLM-L6-v2
```

On a connected provisioning host ONLY, explicitly permit public model-weight download:

```bash
python scripts/provision_embeddings.py --allow-download
```

Transfer the resulting `models/` directory to the private host. Keep its contents immutable for an indexed release; after changing weights, restart the processes and reingest every document. The explicit `lexical_demo` mode supports no-network tests but does not provide semantic understanding.

## 4. Local Ollama

Keep the Ollama API bound to `127.0.0.1:11434`. Install approved local model weights:

```bash
ollama pull llama3.2:3b
ollama pull qwen2.5:1.5b
ollama list
```

The application only permits loopback HTTP Ollama and rejects model tags containing `cloud`. Also restrict host egress and configure the Ollama installation for local-only operation: application checks alone do not prove platform-wide sovereignty.

On the existing approximately 8-GB host, defaults unload the generator before independent judging and unload the judge afterward. This avoids keeping both models resident simultaneously, at the cost of reload latency. Leave `UNLOAD_BEFORE_JUDGE=true` until memory measurements justify changing it. Use one API worker; no GPU/production concurrency claim is made.

## 5. Users and role grants

Provision real server-owned identities. The examples below illustrate capabilities, not automatic executive access to confidential HR data.

```bash
python scripts/manage_users.py demo-admin --role Admin --departments Finance IT Administration Innovation HR Procurement Compliance --clearance 3 --ingest
python scripts/manage_users.py demo-cfo --role CFO --departments Finance Procurement --clearance 2
python scripts/manage_users.py demo-approver --role FinanceManager --departments Finance Procurement --clearance 2 --approve
python scripts/manage_users.py demo-employee --role Employee --departments HR --clearance 1
```

Each command prints a strong random token ONCE. Store it privately. Only SHA-256 token hashes are stored in `config/users.json`, mode `600`. Re-running a command rotates the user's token and increments policy version. Use `--disable` with the same provisioning arguments to revoke the user.

For private enterprise SSO, set the `OIDC_*` variables in `.env`, use a trusted local RS256 public key, and provision user IDs matching IdP `sub` values. `OIDC_ONLY=true` disables local opaque-token login. JWT issuer, audience, expiry, signature, issue time and subject are verified offline. Roles/department grants still come from local server storage; token-provided roles are ignored. Obtain tokens through your enterprise IdP; this backend does not implement the IdP login UI or authorization-code flow. Administer signing-key rotation separately.

## 6. Sample data and documents

All records in `examples/facts.json` are synthetic, dated `2026-08`. Do not confuse them with enterprise reports.

```bash
python scripts/import_facts.py examples/facts.json
cp examples/employee.txt examples/employee.txt.meta.json documents/
cp examples/procurement_policy.md examples/procurement_policy.md.meta.json documents/
python scripts/preflight.py
python -m src.ingest
python -m src.ingestion_status
python -m src.health
```

Each source document must have an explicit ACL sidecar named `FILENAME.meta.json`:

```json
{
  "department": "HR",
  "classification": 1,
  "owner": "demo-admin",
  "allowed_users": [],
  "allowed_roles": []
}
```

Classifications: `0` internal general, `1` departmental, `2` confidential, `3` restricted. Public in metadata means available to authenticated users who meet clearance; there is no anonymous document access. Empty ACL lists allow users within the permitted department and clearance. Nonempty lists restrict further to listed users/roles or the named owner. Owner status never bypasses department/clearance checks.

There is intentionally no arbitrary file-upload API. Administrative filesystem ingestion preserves the earlier direct-child/symlink safety boundary. The watcher is privileged to read the configured document tree; users of the question API are not.

## 7. Ask from terminal

```bash
python -m src.ask
```

Paste your token when prompted. Examples:

- `Finance budget variance 2026-08`
- `Finance and Procurement spending variance 2026-08`
- `IT summary 2026-08` (requires IT grants)
- `Why did Procurement spending exceed budget in 2026-08?`
- `What is Rahul Sharma's role?` (requires HR document access)
- `/extract Rahul Sharma` (copies an evidence excerpt; not a reasoned answer)
- `Finance spending forecast 2026-09` (requires six complete preceding monthly periods; the default fixture deliberately has only one)

Specify explicit reporting periods. This release does not silently guess what "last quarter" means. A period missing from the source data yields no authorized data rather than invented values.

## 8. API

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Open `http://127.0.0.1:8000/docs` on the host, or use an SSH tunnel from your desktop:

```bash
ssh -L 8000:127.0.0.1:8000 ubuntu@YOUR_PRIVATE_HOST
```

The API documentation supports bearer-token authorization. Avoid pasting tokens into shared terminals/screenshots. The API has no permissive CORS configuration and responses use `Cache-Control: no-store`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Minimal liveness |
| `GET /health/details` | Administrator operational health |
| `GET /me` | Current server-owned grants |
| `POST /ask` | Query with `{ "question": "...", "mode": "reasoned" }` |
| `GET /ingestion/status` | Scoped history for ingestion administrators |
| `GET /actions` | Requester's actions or approver's scoped queue |
| `POST /actions` | Propose a local task |
| `POST /actions/{id}/approve` | Separate user's approval and transactional local task creation |
| `POST /analytics/scenario` | Deterministic spending-change scenario |

Task proposal body:

```json
{"department":"Finance","title":"Review software overspend","idempotency_key":"review-2026-08-001"}
```

Approval requires a DIFFERENT identity with `approve=true` and department access. Duplicate approvals cannot create duplicate tasks. There is no implemented external payment or HR-write capability.

Scenario body:

```json
{"department":"Finance","period":"2026-08","change_percent":-10}
```

## 9. Background watcher and API

The provided units assume user `ubuntu` and `/home/ubuntu/eail`. Review paths and directives on the host before enabling.

```bash
mkdir -p data logs
sudo cp deploy/eail-api.service deploy/eail-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eail-api eail-watcher
sudo systemctl status eail-api eail-watcher --no-pager
sudo journalctl -u eail-watcher -n 50 --no-pager
```

The watcher polls and reconciles every 15 seconds; it processes one document at a time with bounded extraction timeouts. Temporary failures retry on later scans. It hashes documents, so modifications do not depend only on filesystem timestamps. API retrieval independently checks source/ACL freshness before answering.

## 10. Validate and back up

```bash
pip install -r requirements-dev.txt
python -m compileall -q src scripts tests
python -m unittest discover -s tests -v
python scripts/preflight.py
python -m src.health
python scripts/backup.py
bash scripts/create_lock.sh
```

Tests use temporary data, explicit demo vectors, synthetic records, and a loopback model stub. They do not modify your configured enterprise DB. Freeze dependencies only after the target OS/Python/CPU environment passes actual MiniLM, Ollama and ShaktiDB integration checks.

Backups contain sensitive data. Restrict access, encrypt transfers, keep a copy on separate approved storage, and test restoration. The included DB backup command does not automatically back up documents, role configuration, models, or secrets; back up those under enterprise policy as well.
