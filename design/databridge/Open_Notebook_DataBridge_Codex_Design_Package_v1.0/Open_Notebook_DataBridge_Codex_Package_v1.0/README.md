# Open Notebook DataBridge — Codex Design & Implementation Package

**Version:** 1.0  
**Date:** October 29, 2026  
**Status:** Approved requirements; implementation not yet started  
**Audience:** Codex working in a fork of [`lfnovo/open-notebook`](https://github.com/lfnovo/open-notebook)  
**Project context:** U.S. DOT MCP / AI Agent Hackathon; all demonstrations use synthetic or approved public data.

## Purpose

Extend Open Notebook into a multi-source analytical research workspace where a user can **find public datasets, import them into local DuckDB, and immediately analyze them in chat**, alongside read-only relational databases and existing notebook documents. The resulting answer includes reviewable SQL, charts, evidence, source metadata, and a reproducible query trail.

**Golden path:** `Find → Preview → Check importability → Click Import → DuckDB → Chat → Verify → Save`.

## Start here

1. **Give Codex [`CODEX_START_HERE.md`](CODEX_START_HERE.md)** as its initial task and place this folder in the cloned repository (suggested: `design/databridge/`).
2. Codex MUST first inspect the checked-out upstream repository, current `AGENTS.md` files, actual versions, and existing tests. The proposed paths and interfaces in this package are implementation targets, **not claims that code already exists**.
3. Implement in phases; each phase has its own acceptance gate. Do not claim completion on mocked or skipped tests.
4. Use the official Data.gov v4 catalog API; no manual browser download or external ingestion scripts for the user.
5. Do not add Trino, MCP Alchemy, Teradata, or additional MCP backends to the MVP. They are recorded as future considerations.

## Package map

| Location | What Codex should read |
|---|---|
| `CODEX_START_HERE.md` | Master engineering brief and execution rules |
| `docs/01_PRODUCT_SCOPE.md` | Product narrative, users, explicit scope and non-goals |
| `docs/02_ARCHITECTURE.md` | Components, data flows, code integration points, concurrency issue |
| `docs/03_REQUIREMENTS.md` | Traceable functional/nonfunctional requirements and acceptance criteria |
| `docs/04_OPEN_DATA_INGESTION.md` | Data.gov v4 search, importability, adapters, ingest jobs |
| `docs/05_MCP_DATABASE_INTEGRATION.md` | DBHub, Google Toolbox, DuckDB MCP, client registry, query safety |
| `docs/06_LLM_LITELLM_COSTS.md` | LiteLLM Proxy, provider config, model defaults, token/cost UI |
| `docs/07_SECURITY.md` | Threat model, guardrails, federal deployment cautions |
| `docs/08_UI_AND_API.md` | Frontend flows and suggested REST contracts |
| `docs/09_PROVENANCE_DATA_MODEL.md` | Metadata, evidence, source and data lineage |
| `docs/10_DOT_DEMO.md` | NTD + Census + NOAA use case, deterministic demonstration |
| `docs/11_TEST_PLAN.md` | Unit/integration/e2e/security test matrix |
| `docs/12_ROADMAP.md` | Ordered Codex phases, PR plan and gates |
| `docs/13_ADRS_AND_QUESTIONS.md` | Decisions, deferrals, investigations |
| `docs/14_REFERENCES.md` | Official source documentation, checked Oct. 29, 2026 |
| `spec/openapi.yaml` | Proposed API contract (design, **not an existing implemented API**) |
| `spec/schemas/` | JSON Schema contracts for important payloads |
| `config/.env.example` | Deployment variables — fake placeholders only |
| `config/litellm-config.template.yaml` | LiteLLM config reference; verify against pinned image |
| `config/compose-extension.reference.yaml` | Illustrative Compose topology, not a drop-in file |
| `diagrams/*.mmd` | Mermaid architecture and ingestion sequences |
| `assets/` | Previously created architecture and tech-stack infographics; conceptual only |
| `fixtures/` | Clearly synthetic DOT-like fixtures, safe offline demo |
| `tests/test_fixture_baseline.py` | Standalone fixture invariant test (stdlib unittest) |
| `tools/validate_package.py` | Self-check for this **design package** (not app tests) |

## Approved decisions

- **Base:** Fork Open Notebook, retain existing Next.js/React, FastAPI, Python, LangGraph, SurrealDB and background-worker patterns.
- **Database MCP:** DBHub (SQL Server, PostgreSQL, MySQL, MariaDB, SQLite, Oracle); a DuckDB MCP server; and Google MCP Toolbox for Databases, with curated rather than unrestricted tools.
- **Python dependency management:** `uv` with committed lock file, target Python 3.12 if compatible with pinned upstream.
- **LLM:** LiteLLM Proxy, OpenAI-compatible API-key endpoint, model defined in `.env`, default **GPT-6 Astra** (`gpt-6-astra`), automatic model/proxy bootstrap through Open Notebook's existing provider abstraction.
- **Metering:** Input/output/cached tokens, request counts, cost by request/session/notebook/user/model, per-research-task totals; visible application dashboard; accuracy and missing-price indications.
- **Open data:** Data.gov Catalog API v4 first, with direct HTTP ingestion managed inside the app; optional selected FastMCP ingestion tools after the main path is stable.
- **Storage:** DuckDB is the default local analytical store, SurrealDB remains for notebook domain data, a separate PostgreSQL service backs LiteLLM spend logging.
- **Demo:** FTA 2022–2025 NTD Annual Data, Census population and NOAA weather; synthetic offline fixtures ensure the demo never depends on outside service availability.
- **Security:** Public/approved synthetic data only initially; read-only query tools and credentials; allowlists, query validation, query approval, bounded results, provenance; restricted download egress.

## Definition of success

In a fresh, documented Docker Compose deployment, a user can search Data.gov, preview an eligible dataset, click Import, see progress and a schema, then ask the same notebook chat a quantitative question whose answer links to its source dataset, SQL, execution snapshot, and refresh timestamp. A demo with DOT, Census and NOAA datasets should show the cross-source capability and its limitations. Cost/tokens should be visible for the session.

**This ZIP is a design and Codex instruction package. It is not a built or tested DataBridge application.**
