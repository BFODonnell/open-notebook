# Phase 3 Open Data Explorer

Retain the [Phase 1](../README.md) and [Phase 2](../mcp/README.md) configurations.
Use Linux Docker containers and `uv sync --extra databridge` for Python dependencies.
No new Python package or MCP server is required for ingestion.

## Enable

Add a personal `DATAGOV_API_KEY` to the protected `.env.databridge` file. Keep it
out of frontend variables, Git and container build contexts. Keep the existing
scoped `DATABRIDGE_DUCKDB_TOKEN`. The overlay opts into automatic registration of
imports only on the bundled, signature-pinned DuckDB broker. Review the
[authorization decision](../../../docs/7-DEVELOPMENT/decisions/ADR-0XX-databridge-ingestion.md).

```powershell
docker compose --env-file .env.databridge -f compose.databridge.yml -f compose.databridge-mcp.yml -f compose.databridge-ingestion.yml up -d --build --wait
```

The official [Catalog API](https://resources.data.gov/catalog-api/) uses a personal
key in `X-Api-Key`; automated `DEMO_KEY` use is deliberately rejected. Direct
backend deployments also support `DATAGOV_API_KEY_FILE`. The supplied Compose
overlay passes the environment value; use a reviewed secret-file override when
deploying with container secrets. API and worker must receive identical settings.

`DATABRIDGE_DOWNLOAD_HOSTS` defaults to exact hosts `data.transportation.gov`,
`transit.dot.gov`, `www.transit.dot.gov`. Additional publishers/redirect hosts need
operator review and an environment change/recreation. Wildcards are not supported.
Private IPs remain blocked even on the allowlist. `DATABRIDGE_DOWNLOAD_CA_FILE`
optionally adds a mounted PEM CA to system trust; it is not an insecure-TLS switch.
The downloader ignores proxy environment variables to preserve DNS/IP enforcement.

## In-app demonstration

1. Sign in, create/select a notebook, then open **Open Data Explorer** in the sidebar.
2. Search Data.gov. Empty search browses the catalog; agency slug and exact keyword
   narrow results. Use **Next results** for cursor pagination.
3. **Inspect dataset** and expand catalog metadata/rights. Select a resource and
   **Validate and preview**. This checks availability, actual file size, parser
   compatibility and schema. Only a fresh successful validation enables Import.
4. Choose the destination notebook, click **Import**, then **Confirm import**.
   Processing continues in the existing background worker after the page closes.
5. Observe stages under **Notebook datasets and imports**. `Ready` means publication,
   registration, a real MCP row-count query and notebook attachment succeeded.
6. Click **Query dataset through MCP**. Review the canonical SQL, then separately
   approve execution. The initial query counts rows in the selected version.
7. Expand **Inspect provenance and processing history** for catalog snapshot,
   resource URL, byte count, raw SHA-256, retrieval time, schema mappings, database
   and schema hashes, version identity and stage history. Open notebook documentation
   for the associated schema Source. Explicit query results have Phase 2 evidence.

No manual download, file path, command-line import, database creation or external
connection registration is required. The fixture acceptance runner exercises the
same API actions and real worker/MCP path; it is not a live Data.gov certification.
The [NTD preparation note](../../../docs/databridge/NTD_CROSS_SOURCE_PREPARATION.md)
explains current formats and later cross-source dependencies.

## Limits and recovery

| Boundary | Limit |
|---|---|
| Catalog response / record / resource count | 2 MiB / 128 KiB / 30 |
| Catalog cache / validation lifetime | 5 / 15 minutes |
| Download | 32 MiB, HTTPS 443, 3 redirects, 90 seconds total, 8 seconds connect, 15 seconds read |
| ZIP | 10 entries, exactly one supported data file, 64 MiB expanded, 100:1 maximum ratio |
| Dataset | 250,000 rows, 100 columns, 256-character headers, scalar values |
| Preview | 5 rows, 256 characters per cell |
| Parser | 60 seconds wall time, 45 CPU seconds, 2 GiB virtual address space, 256 MB DuckDB memory, 128 MB spill, one thread |
| Publication | Existing Phase 2 256 MiB/version, 50 published/pending files, 2 GiB total; immutable |
| Jobs | 20 active-record admission threshold, one active ingestion workspace, 120-second lock wait; explicit retry |
| Recovery lease | Queued 60 seconds; running 15 minutes |
| Notebook catalog | Latest 100 imports; no automatic retention deletion |

The queue admission count is an overload guard, not an atomic multi-client quota;
the cross-process work lock and publication quotas enforce the resource bounds.

CSV must be UTF-8, rectangular, comma-delimited with headers. JSON must be a flat
array of consistent objects (or JSON Lines); duplicate keys and nested structures
are rejected. Parquet must contain supported scalar columns. ZIP directories are
permitted, but links, traversal, encrypted/nested/multiple data files are rejected.
XLSX, XML, API-only and authenticated resources remain adapter-required/unavailable.
Unknown rights require review; there is no browser bypass. Raw files are temporary;
download and archive-member checksums remain in provenance. Empty CSV fields become
NULL and conservative inference may keep mixed numeric values as text.

Cancellation takes effect at safe checkpoints before publication. A cancelled
download may finish its bounded transfer before stopping. Once publication begins,
use status/retry rather than cancelling atomic publication. Errors expose codes and
job correlation IDs, not provider bodies or credentials. Check API/worker logs for
the stage and exception class. `SOURCE_CHANGED_RECHECK_REQUIRED` requires a new
preview and a new import. Old validated jobs retain the old checksum intentionally.

After power loss, restart the stack with the same volumes. Use **Retry or recover
import** after its lease expires; this submits a real background job. Partial work
directories and the job's unpublished staging/WAL are cleaned while holding the
lock. Existing manifest/hash validation reconciles completed publication, including
broker outages. Scope changes/revocation require administrator review and are never
automatically reversed. Do not delete published files to clear a failed job.

Back up SurrealDB, the DataBridge volume (files and manifests together), notebook
data/checkpoints, LiteLLM PostgreSQL and the protected secret configuration. Disable
ingestion by removing the overlay and recreating the app; existing registry/source/
version/evidence records remain. Migration 27 runs on startup. Its down migration
deletes ingestion records and is **not** routine feature-disable or recovery.

DB-DATA-01 is available for this bounded format subset. The context endpoint
`GET /api/databridge/notebooks/{id}/datasets/context` prepares DB-DATA-02; chat does
not yet discover, plan, query and synthesize answers automatically. Existing SQL
policy permits one table and explicit approval. Do not advertise cross-source joins.

Repeatable tests: [Phase 3 acceptance](../../../scripts/databridge_p3/README.md).
