# 09 — Persistence, Dataset Lineage and Evidence Model

## Systems of record

- **SurrealDB:** keep Open Notebook's notebooks/sources/notes/credentials and attach DataBridge-specific metadata via appropriate `ObjectModel`/`RecordModel` and migrations.
- **DuckDB:** local analytical tables/data versions only, stored on durable Docker volume, not a generic app metadata store.
- **LiteLLM PostgreSQL:** gateway credentials, spend logs, request cost and budgets; not a place for notebook content.
- **Upstream LangGraph checkpoint SQLite:** leave ownership to existing Open Notebook; do not create duplicate chat history.
- **Restricted volumes:** bounded temporary downloads + published version files; strong retention/cleanup and access policy.

## Proposed domain entities

| Entity | Identity and important fields | Relationships |
|---|---|---|
| `DataCatalogRecord` | `catalog_record_id`, remote identifier, publisher, `dcat` metadata, catalog URL, harvested/modified timestamps, resource refs | Has resources |
| `DataResource` | `resource_id`, parent record, format, download URL, access rights, checksum if known, adapter kind, importability and reason | Has import jobs |
| `DataImportJob` | UUID, user, notebook, resource, request idempotency key, stage/status/progress/bytes/rows, errors and trace ID | Produces dataset version |
| `DataDataset` | Stable internal dataset ID, name, owner/scope, source, table logical identity, schema summary | Has immutable versions, attached to notebook |
| `DataDatasetVersion` | Version UUID, raw hash SHA-256, schema fingerprint, rows, source/publisher modified date, retrieved-at, physical DuckDB location/approved alias, validation result | Referenced by query evidence |
| `MCPServer` | Endpoint type/transport, encrypted credential ref, scope, enabled health state, approved toolset/schema version | Serves connection aliases |
| `DatabaseConnection` | Alias, engine/dialect, catalog/schema, backend/server ref, read-only profile, allowlists, auth scopes | Referenced by plans and runs |
| `QueryPlan` | Notebook, question, SQL, dialect, parameter spec, allowlist decision, approval state/expiry, model metadata | Can produce run |
| `QueryRun` | SQL + bound params safely encoded, connection/catalog, request/user IDs, query policy version, started/completed/status, rows/bytes/time | Produces evidence |
| `QueryEvidence` | Evidence ID, result hash, bounded result snapshot/URI, referenced dataset version IDs, tables/columns, timestamp, SQL, transformation/quality caveats | Referenced from notebook report |
| `UsageLink` (optional) | IDs linking notebook/chat/task/run to LiteLLM spend log IDs; never duplicate spend accounting | Used in usage dashboard |

Persist source and result identifiers as typed opaque IDs (not user-controlled file paths). Prefer links/edges consistent with upstream `reference`, `artifact`, `refers_to` relationships.

## Provenance contract per numerical claim

A quantitative claim in a saved report needs:

1. **Source identity:** catalog/provider, title, publisher, original landing/download resource, license/rights, model/data source classification.
2. **Version:** retrieval timestamp, publisher modification timestamp, payload checksum, schema hash, DuckDB dataset version and query-time data freshness.
3. **Execution:** exact SQL or canonical query plan, safe parameters, dialect, allowed tables, query/agent version, execution timestamp, row count, result hash, and bounded immutable result snapshot.
4. **Presentation:** chart mapping/aggregation, units and denominator, missing-data treatment, geospatial/time join assumptions, caveats and model synthesis attribution.

Document citations and database citations must be distinguishable in the UI. Avoid claiming that a table SQL query proves a policy recommendation or causation.

## Example evidence JSON (illustrative)

```json
{
  "evidence_id": "ev-demo-0001",
  "notebook_id": "nb-demo",
  "query_run_id": "qr-demo-0001",
  "connection_id": "duckdb:dataset-v1",
  "dialect": "duckdb",
  "sql": "SELECT year, SUM(unlinked_trips) AS trips FROM ntd_demo GROUP BY year ORDER BY year",
  "parameters": {},
  "executed_at": "2026-10-29T13:00:00Z",
  "result_row_count": 4,
  "result_sha256": "<hash-computed-at-runtime>",
  "source_versions": ["ntd-demo-v1"],
  "result_preview": [{"year": 2022, "trips": 1000}],
  "warnings": ["Illustrative synthetic data — not real NTD values"]
}
```

## Refresh and immutability

Never silently replace the data underneath existing reports. New ingestions produce new immutable versions (or explicit version snapshots) and optional `latest` alias; prior evidence always references its exact version. Retain failed import job audit metadata but safely purge temporary raw files.

## Cost linkage

Store only LiteLLM spend-log references and optional nonauthoritative cached aggregates in SurrealDB; use LiteLLM's PostgreSQL spend log as the accounting system of record. Distinguish model-only cost from Docker runtime/storage and data API expenses.
