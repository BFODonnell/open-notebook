# 08 — Application UX and REST API Design

## UX principle

The analyst needs **one application**. The system never instructs them to visit a catalog, manually download a resource, run Python, or register an MCP table after a supported import.

## Navigation additions

- **Open Data Explorer**: search, filters, results list/cards; dataset details, resources, importability; preview columns/records with bounded sample.
- **My Data / Datasets**: imported datasets with row count, version, origin, refresh timestamp, quality warnings, attached notebook(s), and `Chat with this dataset` action.
- **Database Connections** (admin): DBHub/Google Toolbox/DuckDB MCP registry, available toolsets/engine, scope, test/health, read-only status.
- **Chat & Research**: existing Open Notebook conversation with dataset badges, plan/query approval drawer, result table/chart, source/evidence drawer and save-to-notebook action.
- **AI Usage**: compact token/cost indicator and full usage dashboard by model/request/session/notebook/user/task, with estimated/unpriced signals.

## User journey

1. Open Data Explorer; search **NTD transit service** and optionally DOT agency filter.
2. Dataset cards show publisher and freshness. Open dataset to see distribution choices (e.g., CSV, JSON, XML).
3. Each resource has a status: `Ready to import`, `Additional connector required`, or `Unavailable for direct import` (and `Checking` during preflight). The status is **not** assumed from the label alone.
4. Click Import; choose destination notebook and permitted options (e.g. sheet selection when XLSX); confirm estimated size.
5. See async progress with rows/bytes and safe recoverable errors. On successful `registering` stage, app displays table/schema/quality summary.
6. Without leaving the notebook, ask a question. Chat panel shows SQL plan and optional **Approve query** action; after execution, displays table/chart and linked evidence record.
7. User saves report as notebook note/source insight with cited data and SQL lineage. Token/cost header updates.

## New FastAPI resources (proposed; do not collide with upstream)

All live under `/api/databridge/*`; conform to `spec/openapi.yaml` and existing upstream auth and error conventions.

| Method | Route | Intended behavior / auth |
|---|---|---|
| GET | `/catalog/search` | `q`, `org_slug`, `per_page`, `after`; returns dataset cards and next cursor; authorized analyst |
| GET | `/catalog/datasets/{dataset_ref}` | Our **internal cached** metadata record and resource list; does **not** assume Data.gov has a dataset detail route |
| POST | `/catalog/resources/{resource_ref}/preflight` | Perform approved safe availability/format checks; return status, reason, adapter, preview estimate |
| POST | `/imports` | Launch async job for catalog resource + notebook; typed options and idempotency key |
| GET | `/imports/{job_id}` | Stage, progress, warnings, published dataset/version reference |
| POST | `/imports/{job_id}/cancel` | Best-effort cancellation with cleanup |
| GET | `/datasets` | Visible/authorized imported dataset versions |
| GET | `/datasets/{dataset_id}` | Metadata, schema, quality, provenance, attached notebooks |
| POST | `/datasets/{dataset_id}/attach` | Add existing authorized dataset to another notebook; admin/analyst within scope |
| GET/POST | `/mcp/servers` | List/register approved MCP servers; POST admin only |
| POST | `/mcp/servers/{server_id}/test` | Admin connection test, sanitized result |
| POST | `/mcp/servers/{server_id}/discover` | Admin-approved tool list and signatures |
| POST | `/query/plans` | Generate **unexecuted** read-only query plan; existing chat workflow can call service internally |
| POST | `/query/plans/{plan_id}/execute` | Server-side approval token and policy validation, execute bounded query |
| GET | `/evidence/{evidence_id}` | Access-controlled executed query metadata/result snapshot |
| GET | `/usage` | Authentic aggregates, date/model/notebook filters; cost-estimate status |
| GET | `/health` | Restricted aggregated readiness (no credential details) |

**Keep existing Open Notebook chat endpoint and history.** The query-plan endpoints are optional internal services for the current chat path, not a mandate to build a second chat product.

## Error standards

Return a consistent Pydantic envelope: `code` (e.g. `SOURCE_RESTRICTED`, `UNSUPPORTED_FORMAT`, `DOWNLOAD_BLOCKED`, `LIMIT_EXCEEDED`, `QUERY_DENIED`, `MCP_UNAVAILABLE`, `MODEL_UNAVAILABLE`, `COST_UNPRICED`), `message` safe for UI, `correlation_id`, `retryable`, and optional `details` (redacted). Never return DB passwords or raw model prompts.

## Accessibility and UX polish

Keyboard-accessible Import/Approve buttons, explicit text besides color coding, progress/live announcements, pagination, non-blocking error states, readable SQL with copy action, and consistent mobile/tablet fallback. Preserve existing Open Notebook localization patterns and UI style.

## Key screens to capture for hackathon

1. Data.gov search and NTD dataset metadata with per-resource statuses.
2. Import progress and final DuckDB table schema.
3. Research chat with SQL approval, NTD/Census/NOAA context, chart, and evidence citation.
4. LiteLLM token/cost dashboard showing genuine usage.
5. Database connection registry including DBHub, Google Toolbox and DuckDB.
