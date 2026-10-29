# Phase 3: Open Data Explorer and automated DuckDB ingestion

Date: 2026-10-29. Branch: `feature/databridge-mvp`. Builds on accepted Phase 2
`c1448cb`, Phase 1 `02b821c`, Phase 0 audit/publication decisions, the approved
design package and existing deployment guides. The owner's `design/` package is
unchanged. **Phase 4 has not begun.**

**Result: the authorized Phase 3 fixture gate passes (71 acceptance checks).**

## Acceptance scope

The owner explicitly directed: **"No key configured; use fixtures for acceptance."**
The required sequence is implemented through DataBridge and verified with its real
API, background worker, persistent registry, isolated parser and MCP services:

**Search catalog → inspect dataset → validate/preview → import → observe processing
→ query published dataset through MCP → inspect provenance.**

The catalog and publisher in this demonstration are synthetic HTTPS services shaped
like the official Data.gov v4 API. No input is manually placed in staging, no
command-line ingestion creates the demonstration databases, and no external
connection registration is required. The tests invoke the application's Import
action; the worker downloads, parses, publishes, registers and queries the result.
The browser host was unavailable, so this is API/worker/MCP integration evidence
plus frontend component tests, **not browser E2E or live Data.gov certification**.

## Implemented

- `open_notebook/databridge/ingestion/`: direct v4 catalog client and snapshot cache,
  importability assessment, public-only bounded downloader, isolated format parser,
  durable import/recovery state machine and active-notebook dataset context.
- `commands/databridge_commands.py`: real `surreal-commands` import job, loaded by
  the existing worker. Migration 27 adds catalog/resource/cache/import records.
- `api/routers/databridge_catalog.py`: protected search, detail, preflight, import,
  status, cancellation, recovery and dataset discovery endpoints. Clients provide
  record IDs, notebook selection and an idempotency key, not arbitrary URLs/paths.
- `frontend/.../Explorer.tsx` and `/explorer`: search/browse, agency/keyword filters,
  cursor pagination, metadata/rights, resource selection, preview/schema mappings,
  import confirmation, processing/recovery, dataset catalog, provenance and scoped
  handoff to the existing MCP query-review UI. Locale keys exist in all 14 locales.
- `compose.databridge-ingestion.yml`: opt-in overlay, backend-only Data.gov key,
  reviewed publisher hosts and scoped existing DuckDB credential. No new server,
  port, database technology, Python dependency or uv lock change.

CSV, flat JSON/JSONL, scalar Parquet and one-data-member ZIP are supported. Actual
bounded transfer and parse must succeed before Import is enabled. The worker
downloads again and checks the preview checksum. Identifier strings retain leading
zeros; column mappings, count/profile, raw/archive/database/schema hashes, URLs,
catalog metadata, timestamps, stages and MCP health evidence are persisted.

The accepted Phase 2 publisher remains unchanged: checkpoint/close, schema and file
validation, quotas, locking, hashes and immutable publication still apply. Imports
are automatically registered only on the bundled DuckDB broker, for the selected
notebook and manifest schema, with the release-reviewed capability fingerprint.
A real Phase 2 `COUNT(*)` query must match the parser count before `ready`.
Administrator connection changes/revocation cannot be overwritten by recovery.

Successful jobs attach a deterministic schema/provenance Source to the notebook.
Real acceptance confirms the association and zero embedding chunks. Raw records
stay in DuckDB; they are not embedded as notebook documentation. The context API
returns dataset/version/connection/schema identifiers and explicitly reports
`conversational_analysis: false`.

## Security and reliability evidence

The downloader enforces exact operator-approved HTTPS hosts, port 443, public DNS
answers and pinned IP connections with original Host/SNI. Every redirect is
revalidated; local/private/multicast/reserved/transition addresses, credential URLs,
proxy inheritance and compressed HTTP are rejected. API keys never reach publisher
requests. Transfer sizes, timeouts and length mismatch are enforced.

Parsing uses a credential-free subprocess with CPU/memory/file/time limits and
DuckDB extensions/external access disabled except the exact local source path.
Archive limits reject traversal, links, encryption, nested/multiple data members
and decompression bombs. Malformed/duplicate-key/nested JSON, ragged CSV, HTML
masquerading as CSV and invalid Parquet fail validation. Full limits are in the
[deployment guide](../../deployment/databridge/ingestion/README.md).

Real failure tests exercised changed bytes after preview, running-download
cancellation, a stopped DuckDB broker, revoked connection permissions, and a
SIGKILL during worker download. After restart the interrupted state persisted;
the test advanced the lease timestamp instead of waiting 15 minutes, then used
the normal recovery endpoint and worker. Registration retry reused the existing
manifest/download provenance. Cross-process locking prevents concurrent writers.

A separate Linux test kills only the parser's parent and confirms native-child
termination through parent-death SIGKILL protection. Completed-import polling also
invalidates notebook source and MCP caches; a hook test checks this completion-time
refresh instead of relying on invalidation when the job was merely queued.

All persistent services were stopped/restarted without deleting volumes. Published
data and provenance remained queryable. P1 spend/budget/conversation state and P2
registry/version/query evidence also survived. Existing Esperanto, LangGraph,
SurrealDB, LiteLLM and frontend paths remain in place.

## Executed checks

Exact reproduction commands: [P3 acceptance README](../../scripts/databridge_p3/README.md),
with the unchanged [P1](../../scripts/databridge_p1/README.md) and
[P2](../../scripts/databridge_p2/README.md) regression runners applied to the P3 stack.
Sanitized per-check results: [phase3-acceptance.json](evidence/phase3-acceptance.json).

| Check | Result |
|---|---|
| P3 catalog/import/real worker/MCP/provenance seed | 51 passed |
| P3 changed source, cancel, outage/recover, SIGKILL/recover, revocation | 11 passed |
| P3 restart persistence/query/context | 9 passed |
| Full backend, DataBridge dependency profile | 1,220 passed, 2 existing deprecation warnings |
| Base backend without optional DataBridge dependencies | 1,070 passed, 23 skipped, 2 existing deprecation warnings |
| Frontend coverage suite | 200 passed in 39 files |
| P2 real protocol seed/outage/drift/restart | 75 passed |
| Isolated MotherDuck engine/child defenses | 6 passed |
| PostgreSQL role/read-only/column/catalog denials | 4 expected failures, all denied |
| P1 seed/restart/unavailable-pricing | 26 passed |
| Upstream real-worker smoke | 7 passed |
| Ruff, formatting, mypy | Passed; 193 Python files |
| Frontend lint | Passed; 0 errors, 7 existing warnings |
| Source-built Docker app / frontend production build | Passed |
| Browser | Not executed: browser access host unavailable |
| Live Data.gov/NTD and GPT-6 Astra | Not executed; no live credentials |

The initial integration runs found and fixed a reserved SurrealQL claim variable,
UUID record-name update incompatibility (generated Source/connection IDs now use
UUID hex), cached missing-null cursor normalization, and parser virtual-address
pressure. The subprocess now uses a 2 GiB virtual ceiling, bounded native memory
and `MALLOC_ARENA_MAX=2`. The staging-cleanup assertion was scoped to importer-owned
versions so it does not mistake Phase 2's separate fixtures for leaked import files.
No remaining fixture acceptance failure is waived.

One LiteLLM recreation briefly failed its startup health dependency under build
load; the service subsequently became healthy and ordinary Compose startup/restart
completed. No accepted Phase 1 configuration or database was reset to recover.

## Decisions, deviations and limitations

The [ingestion ADR](../7-DEVELOPMENT/decisions/ADR-0XX-databridge-ingestion.md)
records the narrow standing authorization for automatic registration and health
queries. User SQL still requires explicit review and one-use execution approval.
The live catalog uses the current official v4 API, replacing the design package's
older CKAN assumption; the [official documentation](https://resources.data.gov/catalog-api/)
instructs new integrations to use v4 and personal keys for automation. No FastMCP
wrapper or additional specialized MCP server was justified.

This is a single-host Linux volume implementation. The active-job count is an
admission guard, not an atomic distributed quota. Work is serialized, catalog
responses are bounded, and P2 publication quotas remain hard limits. Data retention
and catalog cleanup are manual operator concerns; the UI lists the latest 100
imports. Unknown rights and authenticated/unsupported/oversized resources fail
closed. CSV empty fields become NULL; inference is conservative. XLSX and complex
or multi-file resources require future adapters. Existing shared-password identity
does not become multi-tenant authorization.

The [NTD/Census/NOAA preparation note](NTD_CROSS_SOURCE_PREPARATION.md) identifies
the official 2022-2025 FTA candidate and documents the unverified live byte/schema
gate, reporting grain, geography, time and unit checks. No comparisons are produced
from synthetic values. Census/NOAA adapter contracts are documented, not implemented.
The existing single-table SQL policy is an explicit dependency for later joins.
The six-database DBHub certification roadmap is unchanged and is not claimed complete.

**DB-DATA-01:** implemented and verified for the approved fixture/format scope.
**DB-DATA-02:** discovery interface prepared; conversational database analysis is
not implemented or claimed. Browser verification, live Data.gov/NTD, live GPT-6
Astra and human translations remain on the revised
[cross-phase tracker](ACCEPTANCE_TRACKER.md). Complete those outstanding checks
when their environments are available; obtain phase authorization before Phase 4.
