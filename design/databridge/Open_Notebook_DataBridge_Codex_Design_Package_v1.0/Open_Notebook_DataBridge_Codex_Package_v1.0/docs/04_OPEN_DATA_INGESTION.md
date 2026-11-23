# 04 — Open Data Explorer and In-App Ingestion

## Nonnegotiable experience

The analyst **never leaves DataBridge to download or manipulate an importable dataset**. The browser calls our FastAPI backend; server-side jobs handle publisher endpoints. Import ends with an active notebook source and MCP-queryable local table. The UI must not display a successful state until registration and a real safe `SELECT` health query succeed.

## Data.gov official catalog API

- Base: `https://api.gsa.gov/technology/datagov/v4/`
- Use `X-Api-Key: ${DATAGOV_API_KEY}`. `DEMO_KEY` is only for brief manual exploration and is not an automation credential.
- Search: `GET /search?q=transit&per_page=...&org_slug=...`; use `after` **cursor pagination**, not page-offset assumptions.
- Search results include title, identifier, publisher, distribution titles, often nested `dcat` metadata, and possible `harvest_record` links.
- Metadata: prefer `results[].dcat.distribution` and other DCAT fields; where necessary, retrieve permitted `harvest_record/{uuid}`/`transformed` detail. **Do not invent an undocumented Data.gov detail endpoint.** Cache record securely and key it by source identifier and a stable hash to support our own `/catalog/datasets/{dataset_id}` endpoint.
- Publisher distribution `downloadURL` may differ from `accessURL` and landing page; prefer valid machine-readable `downloadURL` if it passes server-side download policy. Always retain originals in provenance.
- Data.gov *indexes*, but usually does not host, the actual data. The downloader follows approved publisher links, not an assumed Data.gov file endpoint.
- Handle 429 and retry-after, HTTP errors, empty/broken distribution lists, restricted rights, change/deletion and publication date versus catalog-harvest date distinctions.

## Status model

| Status | Rule | UI treatment |
|---|---|---|
| `checking` | Metadata found; preflight pending | Spinner and concise explanation |
| `ready` | Public/authorized, supported adapter, trusted protocol/host, download preflight succeeds or known approved API confirmed, bounds acceptable | **Import** action enabled with size and format estimate |
| `connector_required` | Supported publisher type not yet implemented, unknown format, or an API that requires a new adapter | Show reason and disabled Import; suggest internal request/admin option, not manual work as standard path |
| `unavailable` | Restricted access, link broken, inaccessible authentication, unsafe URL or policy denial | Disabled Import and reason; no silent workaround |

Importability is **per resource**, not simply per catalog dataset. One dataset may offer CSV Ready, XML Connector Required, and a landing page Unavailable. Preflight reports estimate/unknown accurately and revalidates just before download.

## Import state machine

`queued → resolving → downloading → validating → parsing → staging → profiling → publishing → registering → ready`

On failure: `failed` with classified retryability, log correlation ID, safe error message, and no leaked temporary files. Cancellation is best effort during fetch/parse; do not corrupt published datasets. Progress uses percent only when known, otherwise byte/row counts and stage text.

## Adapter interface (conceptual)

```python
from typing import Protocol

class SourceAdapter(Protocol):
    def supports(self, *, media_type: str | None, url: str, hints: dict) -> bool: ...
    async def preflight(self, *, resource: dict) -> dict: ...
    async def acquire(self, *, resource: dict, destination: str) -> dict: ...
    def inspect(self, *, local_path: str) -> dict: ...
    def stage_to_duckdb(self, *, local_path: str, target: str, options: dict) -> dict: ...
```

No adapter gets arbitrary shell access. Validation belongs to a shared downloader and sandbox, not each adapter's bespoke HTTP client. Use Pydantic models for input/output and stable error codes.

### MVP adapters

1. CSV/TSV: stream with byte limit; encoding/delimiter detection and schema inference; don't silently truncate; allow an explicit preview before committed import.
2. JSON: support documented records arrays and JSON Lines; reject deeply nested/unbounded structures or flatten only through an explicit, predictable mapping.
3. Parquet: safe loading from downloaded local object; validate headers and size; no unconstrained remote source reads from DuckDB query service.
4. ZIP: validate central directory, max members/expanded bytes/compression ratio, safe paths and allowed file types; reject symlinks, traversal and nested archives unless approved.
5. XLSX: use trusted parser with row/sheet caps; select worksheets inside the app, never run macros; Excel formula results require clear caveat.
6. Socrata: approved adapter for Data.gov's NTD CSV resource at `data.transportation.gov`, with file export/paged API fallback as needed; follow endpoint publisher limits.

The importer validates `accessLevel`/rights and size/records/timeout. Do not assume an apparently public catalog entry makes a publisher URL safe or available.

## Persisting an import

- Download to a restricted temporary staging path, compute SHA-256 (raw payload) and preserve catalog/publisher metadata.
- Validate format, infer schema, compute row counts, null counts, type warnings, duplicate keys (where defined), time coverage, and geographic fields.
- Create a **versioned local DuckDB dataset** with a sanitized table ID (never direct raw names from URLs). Load into staging, validate checksums/row counts, commit/publish, update dataset version metadata. Keep original source URL, ingestion time and checksum for reproducibility.
- Create a lightweight notebook `Source` reference/metadata summary and searchable schema descriptions using existing upstream source conventions. **No wholesale embedding of raw rows**.
- Register the stable dataset version in the MCP query allowlist scoped to the active notebook/session. Execute a safe test query and then mark Ready.
- Failure during any stage leaves previous version intact and no partial visible table.

## Public catalog vs direct agency APIs

Data.gov is the **first discovery entry point**; the general download adapter retrieves the resources it lists. For the demo, explicit ingestion helpers may use Census's official API and NOAA NCEI Access Data Service, with all authentication and data acquisition still entirely inside the application. These are second-stage first-party publisher adapters, not MCP servers and not a requirement that Data.gov itself host their data.

## Required UX details

Search field, agency/topic filters, cursor pagination, dataset cards, metadata/format/resources panel, per-resource importability icons, preview/schema information, select notebook, import confirmation (including declared size), progress, cancel/retry, import report, `Chat with data` action. The current notebook and existing chat context remain active after import.

## Download and data risks

- Publisher URLs are untrusted; block SSRF, internal IP, localhost, link-local, cloud metadata, DNS rebinding, redirects to blocked networks and non-HTTPS by default.
- Avoid remote URL execution in DuckDB (`read_csv('https://...')`) from LLM-generated SQL. The download job handles network and writes only approved staged files.
- Validate Content-Length and actual streamed bytes; hard timeout and max size; decompression-bomb guards; no storage of raw restricted content in logs/prompts.
- Guarantee cleanup of temporary files and disk quotas. Verify a file hash at publish and when relevant on refresh.

## Acceptance tests

- Search/next-page with fixture responses and `after` cursor.
- NTD CSV direct download (live opt-in) + same path mocked offline; one click creates table, publishes metadata, enables chat.
- Same catalog dataset containing mixed Ready/Unavailable resources shows correct per-resource state.
- Inject 429, 404, non-HTTPS, redirected localhost, HTML masquerading as CSV, corrupt ZIP, 100x compressed ZIP, over-limit file: no import or unsafe fetch.
- Change source after previous successful import: old version still queryable and source citations immutable.
