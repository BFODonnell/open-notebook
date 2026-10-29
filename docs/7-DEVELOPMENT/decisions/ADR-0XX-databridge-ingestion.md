# ADR: bounded public acquisition and immutable notebook dataset imports

Date: 2026-10-29. Status: implemented for Phase 3 demonstration acceptance.
Extends the accepted [publication](ADR-0XX-databridge-duckdb-publication.md) and
[MCP boundaries](ADR-0XX-databridge-mcp-boundaries.md) decisions; neither is replaced.

## Decision

Use the official Data.gov v4 Catalog API directly from FastAPI. Search returns
DCAT snapshots; detail uses those snapshots or the fixed transformed-harvest
endpoint. The backend holds the personal API key. No CKAN fallback, scraper,
FastMCP wrapper, user-entered download URL or generalized HTTP proxy is introduced.
The [official catalog documentation](https://resources.data.gov/catalog-api/)
requires a personal key for automated requests. The owner authorized fixtures
for acceptance because no key is configured.

Catalog format labels are candidates, not permission to import. Require public
access, absent rights or the exact `public` declaration (including `["public"]`),
an approved HTTPS publisher, then a complete bounded transfer and parse. Unknown
rights, connectors, authentication, unsupported formats and oversized data fail
closed. A successful preview expires after 15 minutes. Import downloads again and
requires the same raw checksum; changed bytes require a new preview/import.

The downloader checks every redirect, resolves all DNS answers, rejects nonpublic
and transition addresses, and connects to a validated IP with the original TLS
SNI/Host. TLS verification remains enabled. It ignores environment proxies,
disallows credential-bearing URLs and compressed HTTP, and bounds transfer time
and bytes. An operator may add a trusted CA file; this never disables validation
or private-address rejection. Catalog credentials cannot follow publisher hops.

Use the existing `surreal-commands` worker. Migration 27 persists snapshots,
preview assessments and import state. An idempotency key identifies a request;
a UUID identifies its immutable version. Stages and provenance are durable.
Retry is explicit, including recovery after the running lease expires. A process
claim plus a Linux filesystem lock serialize ingestion/previews across API and
worker processes. No DuckDB file has simultaneous writers/readers. This is a
single-host Docker-volume implementation, not a distributed lock service.

Native parsing runs in a short-lived subprocess with no inherited service
credentials, Linux parent-death SIGKILL protection, bounded CPU/address space/file
descriptors/file size, DuckDB working
memory and spill limits, one thread, and no extensions/network readers. Only the
downloaded local file is allowlisted to the parser. CSV and flat JSON/JSONL share
conservative inference; Parquet must have scalar columns. ZIP supports one data
member, with path/type/encryption/ratio/count/expanded-size checks. Every import
creates one table `data`. Original names, mapped columns, schema, row count,
profile, checksums, retrieval time and archive-member identity are retained.

Call Phase 2's existing `publish_version` after checkpoint/close. Its validation,
hashes, immutable file/manifest publication and storage quotas remain authoritative.
Interrupted publication is reconciled through that same interface. Published
files are never edited or silently replaced; temporary raw/staging files are
removed. A failed registration can leave an immutable orphan for safe retry.

## Scoped automatic registration

Enabling the ingestion overlay is **operator standing authorization** to register
the imported version on the bundled DuckDB endpoint, for the selected notebook
and the exact published schema. The importer approves only the release-reviewed
broker capability fingerprint, stored as a constant; a changed signature fails.
This is the narrowly scoped automation needed for the authorized Import action.
It does not grant arbitrary MCP registration or bypass Phase 2 query policy.

A fixed `COUNT(*)` health query goes through Phase 2 plan, one-use approval and
execute, recording normal query evidence. Only a matching row count allows
`ready`. User queries still require separate review/execution. Existing connection
changes or revocation block recovery; recovery cannot overwrite administrator
scope. Dedicated broker credentials are encrypted with the existing encryption
service. No LiteLLM/provider/SQL-server credentials reach the parser or publishers.

Associate a deterministic Source record and notebook reference containing dataset
schema/provenance documentation, never raw data rows. No automatic embeddings or
new chat workflow. The notebook dataset context endpoint exposes version/schema/
connection identities with `conversational_analysis: false` for future DB-DATA-02.

## Consequences and limits

The conservative limits intentionally reject large nationwide exports, complex
JSON, XLSX, multi-member ZIPs and unknown licensing. Exact bounds and recovery
procedures are in the [deployment guide](../../../deployment/databridge/ingestion/README.md).
CSV empty fields use SQL NULL; mixed numeric representations may remain text.
Identifier strings retain leading zeros; numeric Parquet identifiers cannot
recover zeros absent from the source. Semantic units/geography need human review.

Existing shared-password identity and notebook scoping are preserved; this does
not provide multi-tenant ownership. There is no automatic retention/deletion of
registry records or published versions. Phase 2's single-table SQL limitation
blocks future NTD/Census/NOAA joins until an independently reviewed extension.
The six-engine certification roadmap, MotherDuck isolation, Esperanto/LangGraph,
SurrealDB and LiteLLM accounting are unchanged.
