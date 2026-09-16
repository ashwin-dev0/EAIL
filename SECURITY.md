# Security and sovereignty boundaries

Implemented: server-owned roles/department grants, optional offline private-SSO verification, explicit record/document ACLs, least-privilege DB examples, bound parameters, no arbitrary model SQL/shell tools, loopback-only AI, format signatures, archive/path/size limits, process-bounded extraction, transactional replacement, injection exclusion, numeric/citation checks, independent judge, separate approval, duplicate-action protection, final source/grant rechecks, metadata-only logs, bounded API bodies, one-worker admission control, and hardened services.

Deploy on private networking. Do not expose port 8000 or Ollama directly to the public internet. For shared enterprise access, use approved HTTPS termination, enterprise identity configuration, network allowlists/segmentation, and shared rate/admission controls. Keep model/dependency provisioning separate from enterprise query processing. Restrict egress at the host/network level.

Application ACLs provide the initial enforcement layer. The supplied DB role is not a proof of database row-level security: administrators and direct DB consumers must be separately governed. Validate ShaktiDB RLS behavior before adding database policies; EAIL does not silently rely on compatibility that has not been checked.

A parser subprocess with address-space/CPU/time limits is not an OS container or malware scanner. Higher-risk ingestion requires an enterprise-approved isolated extraction service and scanning/content-disarm policies. The document tree and credential files must be writable only by authorized administrators. Symlink safety assumes the configured parent tree is administrator-controlled.

SSO signing keys are pinned in a local public-key file. Rotate them through administration; no automatic JWKS refresh is implemented. Configure short token lifetimes and local role revocation. Never trust JWT role claims as application grants.

API-local rate limits are process-local and key off socket peer IP. Reverse-proxy deployments need authenticated user-aware gateway limits. The API has no answer cache and is intended to run one worker on the initial small host.

Audit files rotate and are not cryptographically immutable. Use approved protected centralized collection, retention, time synchronization, and monitoring when audit-grade history is required. Do not enable raw-content access logging in upstream systems unintentionally.

No feature is advertised as unhackable. Live production readiness requires target-environment integration, cross-user authorization testing, business reconciliation, measured load limits, restore tests, and enterprise security review.


## Connector release 0.2.0

See `CONNECTORS.md` for the additive schema migration, read-only source configuration, encrypted OAuth cache, approved fields, snapshot freshness and vendor limitations. Existing RAG ingestion, OCR, retrieval, local models, independent judge, MCP analytics and task approvals remain available. Source systems retain their records; these adapters perform reads only.
