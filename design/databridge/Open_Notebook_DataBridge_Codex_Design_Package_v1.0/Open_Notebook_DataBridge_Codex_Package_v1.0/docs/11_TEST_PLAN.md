# 11 — Verification Strategy and Test Matrix

## Test layers

| Layer | What it covers | Required evidence |
|---|---|---|
| Unit | Data.gov payload parser, adapters, SQL AST policy, metadata and import state, evidence hash, cost aggregation | `pytest` + synthetic fixtures, >90% on policy and importability modules where feasible |
| Contract | Pydantic/OpenAPI route schemas, MCP tool adapter response/argument normalization | Schema validation; error envelopes and versioned tests |
| Component integration | FastAPI ↔ SurrealDB, ingestion worker ↔ DuckDB, LiteLLM ↔ PostgreSQL, MCP registry ↔ each server | Docker Compose test profile, health and persistence |
| Engine integration | DBHub and Google Toolbox to real approved demo databases; DuckDB MCP read | Record engines actually tested, SQL returned, enforcement proven |
| E2E browser | Data.gov search, resource preflight, click import, wait Ready, same notebook chat, query approval, chart/evidence, usage | Playwright screenshots and pass/fail logs |
| Security | SSRF, archive bombs, SQL exfil/unsafe statements, tool injection, unauthorized access, secrets | Automated negative test suite and threat mapping |
| Performance | Typical fixture import size, concurrent chat/import, row/time/bytes and budget limits | Measured run logs, not assumed numbers |
| Regression | Existing Open Notebook notebook, source, provider, chat and document flow | Upstream smoke tests |

## Acceptance scenarios (Given / When / Then)

### E2E-DATA-01 — Full in-app acquisition

**Given** an authorized analyst in a notebook with a Data.gov catalog fixture listing a downloadable public CSV, **when** they search, preview, select the resource and click Import, **then** background job stages complete, DuckDB row/schema values match fixture, provenance exists, and imported table is immediately accessible to the current chat **without** leaving the app or manually registering an MCP connection.

### E2E-DATA-02 — Importability explanations

**Given** a catalog record with CSV/unsupported XML/restricted-resource distributions, **when** the analyst opens it, **then** statuses are Ready/Connector Required/Unavailable as appropriate, with accessible human-readable reasons and disabled unsafe actions.

### E2E-AI-01 — SQL review and audit

**Given** a registered DuckDB dataset, **when** user asks for a yearly grouped total, **then** SQL plan displays, requires approval if enabled, executes bounded read-only query through policy+MCP, returns exact expected fixture totals, and stores immutable evidence.

### E2E-AI-02 — Cross-source restraint

**Given** NTD, Census and NOAA example sources with intentionally missing geography/time coverage, **when** user requests “per-capita ridership and weather causality,” **then** system warns about invalid denominator/geography or insufficient coverage, refuses to present misleading per-capita/causal figures, and offers defensible alternatives.

### E2E-COST-01 — Usage records

**Given** LiteLLM with PostgreSQL spend logs and a mocked OpenAI-compatible model, **when** user runs a chat task, **then** genuine proxy token counts/price status display and persist across restart. Unknown pricing renders as **unpriced**, not zero.

### SEC-01 — Query and connector isolation

**Given** a low-privilege user and read-only database role, **when** a malicious prompt or direct API request tries SQL `DROP`, `COPY`, file reads, writes, unapproved catalog or MCP URL, **then** backend denies action before execution and database/server still independently rejects it.

### SEC-02 — External data fetch

**Given** catalog metadata containing a URL that resolves or redirects to a private address, **when** preflight/import runs, **then** no request to target is made, user receives `DOWNLOAD_BLOCKED`, and audit logs show a sanitized reason.

### OPS-01 — Fresh deploy

**Given** a clean branch, only `.env` derived from example and documented prerequisites, **when** user invokes tested Compose command, **then** app, MCP, LiteLLM, PostgreSQL and SurrealDB health checks are green; restart preserves data and spend logs.

## Suggested CI commands (adapt to actual repo)

```bash
uv sync --frozen
uv run pytest tests/databridge -q
uv run ruff check open_notebook api commands tests
cd frontend && npm ci && npm run lint && npm run typecheck
# Pseudocode: adapt to upstream Compose filenames and test profiles:
docker compose -f docker-compose.yml -f compose.databridge.yml --profile demo up --build -d
# Run integration tests and capture exit status + docker logs
```

Do not blindly assume upstream has `npm run typecheck` or exact file names: verify during P0 and modify commands.

## Test and evidence artifact policy

For each P phase report actual commands, exit codes, test counts, screenshots, failed/unrun cases and rollback commands. Mock responses can certify **contracts**, not live Data.gov or live provider availability. No synthetic fixture labeled a real federal result.
