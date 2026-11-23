# 03 — Traceable Requirements and Acceptance Criteria

All **MVP** requirements are mandatory unless a phase gate identifies a documented blocker and the owner approves a reduced scope. Evidence must come from actual automated tests or screenshots; unverified configurations are labeled *configured, not certified*.

| ID | Priority | Requirement | Testable acceptance |
|---|---|---|---|
| CORE-01 | MVP | Extend upstream Open Notebook, preserve notebooks, chat, document ingestion, search and background jobs. | Upstream smoke tests pass; no regression on notebook/document workflow. |
| CORE-02 | MVP | Docker Compose reproducible deployment; Python managed by `uv`. | From clean checkout, documented build/boot and health checks pass; lock file committed; persistent volumes verified. |
| CORE-03 | MVP | Configure, test, enable/disable external DB connections in app. | User can inspect connection health and select authorized catalog; no secret in browser payload. |
| MCP-01 | MVP | Integrate DBHub with SQL Server, PostgreSQL, MySQL, MariaDB, SQLite and Oracle options. | Schema/search and bounded `SELECT` tested on chosen demonstration subset; every other engine marked untested until certified. |
| MCP-02 | MVP | Integrate a DuckDB MCP read-only query service for local imported data. | User asks current notebook chat question that executes a safe query against imported DuckDB data. |
| MCP-03 | MVP | Integrate Google MCP Toolbox with approved toolsets/configured sources. | Toolbox server appears in registry; curated tools discovered and policy-filtered; at least one harmless integration test. |
| MCP-04 | MVP | Support multiple SQL Server catalogs on one instance. | Two approved catalog configurations can be discovered independently using least-privilege connections. |
| MCP-05 | Stretch | Expose selected Data.gov discovery/import requests as MCP tools via FastMCP. | Only preapproved operations are available, user approves import; no arbitrary URL execution. |
| DB-DATA-01 | MVP | **In-app Data.gov dataset acquisition**: search, browse, preview, select, import; no manual external download or setup. | For a Ready resource, all acquisition and staging occur server-side after clicking Import; progress and errors visible in app. |
| DB-DATA-02 | MVP | **Immediate conversational access** after import. | Within same notebook/session, imported dataset metadata and table query are available without manual MCP registration or page reload. |
| DATA-03 | MVP | Data.gov official v4 API with authentication, retries and cursor pagination. | Integration tests against mocked v4 response (`after` pagination); 429 error handled. |
| DATA-04 | MVP | Importability classification: Ready, Connector Required, Unavailable. | Each catalog resource shows reason, supported formats and action; restricted records never marked Ready. |
| DATA-05 | MVP | Data adapters for CSV, JSON, Parquet, ZIP and Excel within configured limits. | Unit fixtures cover valid/invalid file type, encoding, schema, corrupt archive, row/file size, and rejection reason. |
| DATA-06 | MVP | DuckDB is default local analytical store. | Imported tables persist after Compose restart, correct row counts and schema, staged failure rolls back. |
| DATA-07 | MVP | Import job progress, cancellation when safe, and dedup/version semantics. | UI shows queued/download/validate/import/profile/register/ready/failed, retry not duplicating published version. |
| DATA-08 | MVP | Include authoritative metadata (publisher, URL, access/rights, retrieved time, checksum, row count, column profile). | Source details show these fields; exported evidence links dataset version. |
| LLM-01 | MVP | LiteLLM Proxy unified LLM gateway, retain Open Notebook's model provider integration. | Default chat uses LiteLLM, original notebook tasks remain functional. |
| LLM-02 | MVP | OpenAI-compatible base URL and API-key authentication. | Integration test with mock compatible endpoint and real provider opt-in; keys never returned to client. |
| LLM-03 | MVP | Model defined by `.env`, default `gpt-6-astra`. | Fresh deployment registers and uses configured model; changing env + restart changes deployment default deterministically. |
| LLM-04 | MVP | Token usage and cost displayed in app. | Dashboard shows authentic input/output tokens, request count, USD estimated cost, session and aggregate views; missing pricing flagged. |
| LLM-05 | MVP | Persistent spend logs and budget/limit controls. | LiteLLM PostgreSQL-backed usage survives restart; configured test budget can halt new requests. |
| AI-01 | MVP | Natural-language query planning and bounded read-only SQL execution. | User can preview/approve SQL; executed query has table allowlist, time/row limits; output matches deterministic fixture. |
| AI-02 | MVP | Synthesize database and notebook-document evidence. | One test answer combines a query result and a document excerpt, each cited distinctly. |
| AI-03 | MVP | Refuse unsupported or misleading inferences (e.g. weather causing transit changes). | Test checks data-join coverage/missing denominators/correlation-vs-causation warning. |
| EVID-01 | MVP | Save SQL text, parameters, dataset/version references, timestamp, result checksum and limited result snapshot. | Notebook report can show underlying evidence even when source data changes. |
| EVID-02 | MVP | Verify numeric aggregates using deterministic calculations before rendering. | Regression test catches intentionally incorrect model claims. |
| UI-01 | MVP | Open Data Explorer in Open Notebook navigation with detail/importability/import status. | Browser E2E finishes the golden path without navigating to Data.gov. |
| UI-02 | MVP | Query review and evidence viewer; notebook report and at least one chart. | Analyst can inspect SQL and source description and save findings. |
| SEC-01 | MVP | Read-only DB roles and server-side SQL validation; SQLGlot is not the only security control. | DDL/DML, multi-statement, `COPY`, filesystem/network functions and unauthorized objects blocked; read-only DB role enforces denial. |
| SEC-02 | MVP | Safe external download handling (SSRF, DNS rebinding/redirects, file-size/time/format limits). | Security test suite blocks loopback/private/metadata endpoints, protocol switches, ZIP bombs and arbitrary paths. |
| SEC-03 | MVP | Minimum agency safe default: approved public/synthetic data, documented restricted data limitations. | No agency credentials or private data in fixtures; deployment docs warn against unapproved sensitive use. |
| SEC-04 | MVP | Authn/authz for dataset and connection management, no client secret exposure. | Unauthorized users cannot register connections or view other tenants' sources; secret-leak checks. |
| PERF-01 | MVP | Bounded response time and meaningful async progress under ordinary fixture load. | Define baselines from measured environment; import and SQL timeout states visible and recoverable. |
| OPS-01 | MVP | Dependency version pinning, health checks, robust startup, logs, rollback/restart. | Clean reproducible demo and failure-injection tests pass. |

## Release gate summary

1. **Golden-path E2E:** Search `transit`, preview approved NTD resource/fixture, click Import, see Ready, query in current chat, inspect evidence, save report.
2. **Cross-source analysis:** NTD + Census + NOAA with documented join geography/time semantics and at least one validated chart.
3. **Safety:** Query approval/denial, SSRF/ZIP-bomb test, read-only role test, no keys in frontend/logs.
4. **LLM accounting:** Proxy-backed token/cost logs persist and appear in UI, with accurate unpriced-status behavior.
5. **Operational:** `docker compose up --build`, reset demo and rerun offline; upstream notebook basics work.

## Certification wording

- `Advertised by upstream`: documentation says connector supports engine.
- `Configured`: connector is in UI/Compose and startup health passes.
- `Integration tested`: actual database engine + MCP call + query return verified.
- `Approved`: internal organizational use authorized by owner/security processes. **Do not equate any earlier status with Approved.**
