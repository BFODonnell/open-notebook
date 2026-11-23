# 12 — Codex Delivery Roadmap and Phase Gates

## Working agreement

Codex should make incremental, reviewable commits/PRs, work on a feature branch, keep upstream regression tests, and report deviations. The project owner approved the entire target architecture, but **does not require all engines and every optional data format to be certified on day one**. Trade unsupported surfaces for demonstrably working core flow, not hidden mocks.

### P0 — Repository audit and high-risk spikes

**Tasks:** Clone/fork, read upstream `AGENTS.md` hierarchy and current docs; determine exact baseline SHA, supported Python, image/build paths, model/Esperanto provider adapters, commands, existing domain migration and UI conventions. Spike one read/write DuckDB import/query coordination approach and Google Toolbox/DBHub transport/permissions.

**Deliverables:** `UPSTREAM_AUDIT.md`, compatibility matrix, dependency/image versions to pin, concurrency ADR with an executable proof, baseline tests and known risks.

**Gate:** Reproducible upstream boot + tests recorded; chosen local DuckDB concurrency model survives actual read/write contention test.

### P1 — Runtime and LLM plumbing

**Tasks:** Compose + `uv` extras, durable volumes, LiteLLM Proxy and dedicated PostgreSQL, env-driven OpenAI-compatible endpoint and model default `gpt-6-astra`, idempotent upstream model registration, trace/usage correlation, dashboard initial read model.

**Gate:** Test question reaches LiteLLM through existing model adapter; usage/cost and budgets persist after restart. Provider failure shows useful error.

### P2 — MCP registry and read-only query layer

**Tasks:** DBHub, DuckDB MCP and Google MCP Toolbox service options; registry/admin UI and connection tests; normalized schema/search/read SQL capabilities; read-only SQL validation, approval flow, bounded results, auth. FastMCP client library only if documented advantage.

**Gate:** Query a fixture from local DuckDB MCP and one DBHub demo connection; Google Toolbox approved tool is discovered and called; rejected SQL proven denied.

### P3 — Data.gov search and ingestion golden path

**Tasks:** Official v4 search/cursor pagination, cached dataset metadata, per-resource preflight/importability, safe downloader and adapters, async import jobs using upstream worker, staged DuckDB persistence, schema/quality profile, versioned provenance, notebook attachment and immediate chat registration.

**Gate:** Browser E2E `Find → Preview → Import → Ready → Chat` succeeds entirely in app using CSV fixture and (network permitting) real NTD resource. Errors/unsupported resources do not require manual outside steps.

### P4 — Research and evidence engine

**Tasks:** Extend LangGraph planner for appropriate source selection; schema discovery, SQL generation/review, safe MCP execution; combine numeric and document sources, verify calculations, generate simple chart and immutable evidence for notebook report.

**Gate:** Deterministic multi-source question yields correct numbers and honest warnings; exact SQL/result version inspectable after refresh.

### P5 — DOT/Census/NOAA demonstration and UX

**Tasks:** NTD data source, Census/NOAA approved API imports or preloaded public snapshots, geography/time crosswalk validation; polished Explorer/importability UI, usage dashboard, e2e demo script and video/screenshots, offline fixture reset.

**Gate:** Seven-minute demo rehearsed end-to-end; no manual file manipulation; no unverified per-capita or weather causality claims.

### P6 — Hardening and handoff

**Tasks:** Full security negative tests, additional connector tests, dependency/image pinning, Compose clean-room test, perf checks, docs and screenshots, environment setup/rollback, traceability report and limitations.

**Gate:** Required MVP rows of `docs/03_REQUIREMENTS.md` have evidence; upstream notebook regression green; remaining items transparently marked configured/untested/deferred.

## Suggested PR structure

1. `docs: baseline architecture/ADRs + test scaffolding`
2. `feat: litellm gateway + env-default model + usage endpoint`
3. `feat: read-only MCP registry/adapters + SQL policy`
4. `feat: datagov explorer + import pipeline + DuckDB publishing`
5. `feat: research graph + evidence + notebooks integration`
6. `feat: UI/usage dashboard + DOT demo`
7. `test: hardening, docs, release gates`

## Minimum hackathon showstopper criteria

A simple CSV Data.gov result, imported inside app, immediately queryable in current notebook with SQL evidence and a visible genuine model spend entry. If this fails, the project does **not** pass the MVP regardless of the number of connectors listed.

## Optional after MVP

- Expose selected catalog functions via FastMCP tools with explicit user confirmation.
- More specialized MCP servers: MCP Alchemy, Teradata, AWS Labs, Databricks, IBM i/Db2, Neo4j, MongoDB, Elasticsearch, ClickHouse, Snowflake-managed MCP.
- Trino for federated joins (separate complexity/security/performance study).
- Advanced source refresh/lineage diff, query cache, full role-based enterprise SSO and governance certification.
