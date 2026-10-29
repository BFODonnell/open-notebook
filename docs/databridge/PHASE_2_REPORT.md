# Phase 2 — MCP registry and authorized read-only database access

Date: 2026-10-29. Branch: `feature/databridge-mvp`. Builds on accepted Phase 1
commit `02b821c` and the accepted Phase 0 audit/publication decision. The supplied
design package remains untouched. **Phase 3 has not started.**

## Implemented scope

The existing FastAPI application now owns a connection manager and SurrealDB
registry using official MCP Python SDK 1.28.1. Migration 26 adds connection,
immutable dataset-version, query-plan and query-run records. Existing credentials,
Esperanto, model defaults, LiteLLM accounting, LangGraph and worker paths are retained.
The optional feature is disabled without the Phase 2 environment configuration.

The [Compose overlay](../../compose.databridge-mcp.yml) adds pinned DBHub 1.5.0,
Google Toolbox 1.15.0, an authenticated Toolbox gateway and a bounded DuckDB broker.
No MCP/database ports are published. Reviewed service configs contain independent
least-privilege database credentials; app-held MCP bearer values use upstream
encryption. Browser administration selects only operator-approved endpoint
references, never URLs, DSNs, paths or subprocess commands. Every exchange uses
a fresh authenticated SDK session and revalidates discovered capability signatures.
Operator configs live outside the build context or in `.databridge-private/`,
explicitly excluded from both Git and Docker, so upstream `COPY .` cannot bundle
those database credentials into the application image.

The Settings panel provides notebook selection, connection registration/editing/
disable, health, explicit capability review/approval, filtered schema inspection,
SQL or curated-tool review, explicit execution, result previews and historical
evidence. New text keys are present in all 14 locales (English pending translation).
The administrator key is held only in page memory; existing secret values are
never returned to the browser. The database-role credentials never enter the app.

Database execution has independent boundaries:

- Existing app authentication plus a separate administrator key for configuration;
  notebook scope for plans, execution and evidence. This preserves single-user
  semantics; it does not invent tenant/user identity.
- A small exact SQLGlot AST allowlist: one SELECT, one approved unqualified base
  table, approved columns, selected scalar/aggregate functions and bounded LIMIT.
  No comments, DDL/DML, joins/CTEs/subqueries, unsafe functions, external files,
  extensions, settings changes or other catalogs. Quoted canonical SQL is shown
  before approval. Scalar SQL parameters are escaped AST literals; Toolbox uses
  fixed prepared statements and validated scalar parameters.
- Separately reviewed database roles, column grants, query deadlines, connection
  and transport limits. MCP read-only hints are not treated as authorization.
  Toolbox authorization is the approved fixed tool set and database grants;
  its schema metadata is additionally filtered to the connection allowlist.
- An atomic, five-minute, one-use approval bound to connection revision,
  notebook, policy and dataset version. Concurrent/replayed/stale/invalid approvals
  cannot execute twice. Each execution rediscovers tools before calling one.
- Bounded result snapshots, canonical SQL/tool arguments, timestamps, version and
  content hashes persist in SurrealDB. Denied SQL stores a request hash rather
  than raw rejected text. Failed queries have no fabricated rows, no automatic
  retries, and sanitized API errors. Invalid/stale approval attempts are audited.

## Immutable DuckDB implementation

The accepted architecture is retained: a closed/checkpointed staging database is
published under a unique immutable UUID, and queries remain pinned to that version.
The Linux publisher serializes quotas/publication with an OS lock, holds the
source's DuckDB read lock during copy, checks schema/WAL/symlinks, fsyncs and uses
no-overwrite hard links for the final database and manifest. Registry writes follow
manifest completion. Repeating a completed publication safely repairs interrupted
registration; it cannot reassign a version to another dataset or overwrite it.

MotherDuck 1.1.0 remains in its accepted isolated uv environment with FastMCP 4.1.4,
MCP SDK 2.3.0 and DuckDB 1.5.6. The official-SDK 1.28.1 broker launches at most two
active child processes, each for one query/version, then tears it down. No child
receives the broker/app secrets or a database-switch capability. It reads a
read-only volume with external access/extension loading disabled, settings locked,
one thread, 256 MB memory and a native three-second query timeout. It verifies the
file hash; application evidence verifies the returned version/hash against the plan.

This is a publication interface for prepared files, not a Data.gov importer. There
is no mutable current-file pointer, process-pool eviction, automatic deletion or
ingestion UI. Retaining every published version protects current evidence refs;
publication stops at the documented quotas. Incomplete files remain unqueryable.
See the [implementation ADR](../7-DEVELOPMENT/decisions/ADR-0XX-databridge-mcp-boundaries.md)
and [deployment/recovery guide](../../deployment/databridge/mcp/README.md).

## Executed validation

All database fixtures contain synthetic values. MCP initialization, tools/list,
tools/call, PostgreSQL queries, MotherDuck stdio processes, HTTP transports,
SurrealDB, LiteLLM, worker and persistence are real. Only the external language
provider is the accepted deterministic HTTP fixture. No private data or paid
provider calls were used. Reproduction commands are in the
[P2 test runbook](../../scripts/databridge_p2/README.md); structured results are in
[phase2-acceptance.json](evidence/phase2-acceptance.json).

| Validation | Executed result |
|---|---|
| Backend suite, uv-managed Linux environment | **1,145 passed**, two dependency deprecation warnings; includes 128 new policy/lifecycle cases |
| Base installation compatibility | **1,017 passed**, optional MCP test module skipped without the DataBridge dependencies; CI now runs both base and DataBridge profiles |
| Frontend suite and coverage | **193 passed / 37 files**, including six new connection-control tests and locale parity |
| Frontend lint and production build | Passed; seven existing lint warnings, zero errors; full Docker frontend build passed |
| Python tracked-source lint/format/mypy | Passed for **180 files**; owner-supplied untracked design examples excluded, not modified |
| Full source-built Compose environment | API, worker/frontend, migration 26, existing gateway and all MCP services booted; Settings HTTP route returned 200 |
| P2 API/MCP seed | **65 checks passed**: all three services, schema, correct totals, permissions, encrypted tokens, approvals, SQL denial, limits and immutable versions |
| Real DBHub outage and capability drift | **1 + 1 passed**: stopped service and changed tools/list both yield durable failed runs with no rows |
| Full service restart without volume deletion | **8 passed**: all three queries and canonical evidence/version hashes survive API, SurrealDB, broker/MCP/database restarts |
| Native isolated MotherDuck defenses via official MCP | **6 passed**: child credential isolation/no switch tool; write, file read, extension install and config change denial; native query timeout |
| Direct PostgreSQL role probes | **4 expected denials**: DELETE; DELETE after turning read-only mode off; SELECT on restricted `secret` column; CONNECT to hidden database |
| Unchanged P1 accounting acceptance | **26 checks passed** across initial usage/budget/provider-error checks, durable restart and unpriced model/default change |
| Unchanged upstream API/real-worker smoke | **7 checks passed**: notebook CRUD, async text/document processing, original download, context/chat CRUD, cleanup |

The P2 application acceptance count is **75** across seed/outage/drift/restart;
six native engine checks and four PostgreSQL permission denials provide additional
evidence. The test does not infer permission safety from advertised server flags.
Old/new immutable DuckDB fixtures returned totals **6 / 21** with distinct file
hashes and the same schema hash, while the original connection retained total 6.
DBHub represents PostgreSQL aggregate integers as strings; evidence preserves that
native representation and numeric assertions verify its value without coercing
the stored snapshot. DBHub/PostgreSQL, Toolbox/PostgreSQL and local DuckDB are
**integration tested**, not claims of organizational production approval.

Issues found and corrected during validation: publication manifest tuples/list
inconsistency; incorrect handling of SurrealDB's single-record result on publication
retry; incomplete Toolbox schema fixture metadata; initial harness assumptions
about DBHub aggregate types and plain-text MCP error results. None is left as a
known failing acceptance test. Unit, component and real integration tests were
rerun on the corrected paths.

## Decisions, deviations and limitations

- The root uv lock adds DuckDB 1.5.6 and SQLGlot 30.25.0; jsonschema 4.26.0 is
  explicitly part of the DataBridge extra. Existing dependency versions, including
  Esperanto 2.28.0 and MCP 1.28.1, remain unchanged. The accepted MotherDuck lock
  is unchanged. No FastMCP orchestration/client dependency was added to the app;
  the broker's server helper comes from the official SDK.
- DBHub execution is certified and enabled for PostgreSQL only. MySQL, MariaDB,
  SQLite, Oracle and SQL Server/multiple SQL Server catalogs are not certified by
  P2 and are rejected by this execution path. This follows the roadmap's explicit
  demonstration-subset gate, not a claim that all advertised connectors work.
- SQL is intentionally narrower than general SELECT. New constructs require
  policy review and negative tests. Toolbox statements remain operator-reviewed
  configuration: a SQL-body change hidden behind an unchanged tool signature
  cannot be detected by tools/list fingerprinting. Operators must review and
  reapprove such changes, and maintain independent least-privilege database roles.
- Connection administration uses a separate shared operator key and notebook
  scopes, preserving upstream auth. It is not multi-tenant security. Reviewed
  config/network changes are required for external databases; no general network
  route or arbitrary target access was added to the MCP services.
- Boundaries are deliberately local: 256 MiB/file, 50 versions/pending files,
  2 GiB published storage, up to 1,000 result rows, 256 KiB snapshots, 512 KiB
  wire responses and 30-second app deadlines. They are documented operational
  caps, not a large-database performance certification. Per-query process startup
  adds latency; no pooled-reader optimization is claimed.
- Linux publication is supported; native Windows backend OpenSSL retains the
  Phase 0 environment problem. Tests and deployment ran successfully in Linux.
  There is no automatic orphan GC, staging cleanup, retention UI or expired-plan
  pruning. Completed manifests reconcile on retry; incomplete files count against
  quota until operator review. A crash after execution claim leaves an indeterminate
  running audit and consumes the approval; it is never silently replayed.
- Audit/evidence snapshots contain selected data and SQL literals. They are bounded
  and protected by upstream storage/auth, but are not an externally signed,
  tamper-proof audit ledger or a sensitive-data governance solution.
- Browser E2E and live GPT-6 Astra/provider billing validation remain **outstanding
  cross-phase acceptance items**, explicitly tracked in
  [ACCEPTANCE_TRACKER.md](ACCEPTANCE_TRACKER.md). No browser screenshots, live
  model access, live embedding/podcast provider certification or translations are
  claimed by component tests and fixture usage.
- Data.gov ingestion, automatic notebook dataset attachment, natural-language
  SQL planning, report synthesis and charts remain their planned subsequent
  phases. No Trino or additional specialized MCP server was introduced.

## Exit and next steps

The automated Phase 2 gate is satisfied for the approved demonstration subset:
real local DuckDB and DBHub queries, a real approved Toolbox call, and demonstrated
SQL denial. No implementation blocker remains within that tested scope. The
cross-phase validation items above remain open; they are not silently waived.

After owner acceptance, the proposed next phase is P3's safe Data.gov discovery
and ingestion path, reusing this publication interface and the upstream worker.
Before broader deployment, complete browser/live-provider validation, translated
UI review and any needed additional-engine certification. Phase 3 has not begun.

After evidence capture, only the disposable `databridge-p2-test` containers,
networks and named volumes were removed. The project, existing user data and
owner-supplied untracked `design/` package were preserved. Build images remain
cached for reproduction.
