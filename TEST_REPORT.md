# Verification report — EAIL 0.1.0

Verified on 15 September 2026 with Python 3.12 in a Linux test environment.

## Executed checks

- **68 tests passed, zero failures and zero skips.**
- Full Python syntax compilation passed.
- Multi-format ingestion: JSON, CSV, XML, HTML, DOCX, PPTX, XLSX, PDF text, scanned PDF OCR, PNG/JPEG/TIFF/BMP/WEBP OCR, ODT, ODS, ODP, and plain-text document flows.
- File safety: traversal, symlinks, signature mismatch, archive traversal/expansion and XML external-entity rejection.
- Source integrity: versioned replacement, unchanged-content skip, failed-update chunk preservation, deletion and immediate ACL/source-change suppression.
- Identity/policy: credentials, disabled users, credential-file modes, department, user-specific and classification restrictions.
- SSO: actual RS256 signature/audience checks, server-owned role precedence, local-token rejection under SSO-only mode.
- MCP: gateway/server calls and interoperability with the independently installed standard MCP Python SDK 2.2.0 client.
- Structured intelligence: budget totals/variance, mixed-currency refusal, scenario arithmetic, six-month forecast baseline/backtest and source-ACL revocation.
- Workflows: separate approver, self-approval refusal, idempotency conflicts and duplicate-task prevention.
- API: missing-token rejection, authenticated query, body-size bound and no-store responses.
- Grounded generation: loopback Ollama API stub exercised generator, independent judge, citations and acceptance path.
- Metadata-only application logs checked for raw-content/token leakage.

## Test boundaries

Tests used temporary SQLite data and the explicitly labeled lexical_demo embedding backend. There was no live ShaktiDB server, MiniLM/torch installation, live Ollama model inference, enterprise source application or production load test available in this build environment. The loopback model stub verifies protocol/control flow, not actual model quality.

Real-host acceptance must check ShaktiDB compatibility and least-privilege roles, approved MiniLM weights, actual generator/judge responses, small-host RAM/latency, original documents, authoritative department reports, enterprise SSO, service units and backup restoration. Freeze target-environment dependencies after those pass.

## Reproduce

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
python -m compileall -q src scripts tests
python -m unittest discover -s tests -v
```

The test suite creates and removes isolated temporary files and does not ingest into your configured live database.
