# 01 — Product Scope & User Stories

## Product proposition

**Open Notebook DataBridge** converts separate public datasets, internal approved relational databases and research documents into a unified research experience: *find, import, analyze, verify and share*. Users should not have to manually download files, run data preparation commands or configure an MCP connection after import.

### Personas

- **Transportation analyst:** Discovers an NTD dataset, imports it, calculates mode trends and normalizes results with Census denominators.
- **Research program manager:** Asks a multi-source question, reviews the executed SQL and provenance, saves evidence to a notebook.
- **Data steward / administrator:** Configures approved MCP endpoints and database credentials, controls access and budgets, investigates audit trails.
- **Hackathon evaluator:** Sees a working seven-minute demonstration on public or synthetic data without agency network access.

### Primary user stories

1. As an analyst, I can search Data.gov inside DataBridge and filter by agency/topic/format without leaving the app.
2. As an analyst, I can select a specific resource from a dataset and see **Ready**, **Connector required**, or **Unavailable**, with a reason and next step.
3. As an analyst, I can select **Import**, watch progress, preview inferred schema/quality, and chat about the imported data immediately in the current notebook.
4. As an analyst, I can ask questions spanning imported data, read-only enterprise databases, and notebook documents; answers distinguish numerical evidence from narrative interpretation.
5. As an analyst, I can inspect generated SQL *before* execution when approval mode is on, and inspect executed SQL + source row/result snapshot afterward.
6. As an administrator, I can register, test, disable and assign read-only access to MCP backends, including multiple SQL Server databases on one instance.
7. As a cost-conscious user, I can see the session/request/notebook token and USD cost estimates, plus any unpriced usage warnings.
8. As a reviewer, I can reopen a saved report, see dataset versions/time of extraction, source links, SQL, and chart data, and run refresh deliberately.

## MVP in scope

- Fork upstream and run Docker Compose with existing Open Notebook features retained.
- DBHub (SQL Server, PostgreSQL, MySQL, MariaDB, SQLite, Oracle), DuckDB MCP, Google MCP Toolbox for Databases **as configured options**; stage actual integration certification engine by engine.
- Data.gov Catalog API v4 search and metadata view; importability triage; backend acquisition of eligible CSV, JSON, Parquet, ZIP, and Excel resources with explicit limits and per-format test coverage.
- DuckDB persistence; source metadata/provenance and immediate notebook chat registration.
- Existing LangGraph workflows extended to structured querying and evidence output; charts from result tables.
- LiteLLM Proxy with persistent spend logs in PostgreSQL; env-based GPT-6 Astra model default and configurable OpenAI-compatible endpoint.
- UI: Open Data Explorer, import wizard/status, database registry/admin, SQL approval/evidence, usage dashboard.
- Deterministic DOT/Census/NOAA demonstration, with fixture fallback.

## Stretch, only after MVP

- Selected FastMCP tools for Data.gov discovery/import requests; full dynamic agent-initiated ingestion with explicit approval.
- Automated dataset refresh, change alerts, and historical snapshots.
- Advanced quality agent and cross-source join suggestions with steward-approved crosswalks.
- Extra specialized APIs/format adapters and multi-user production auth/SSO.

## Out of scope / deferred

- Trino and federated SQL engine deployment; MCP Alchemy and other domain-specific MCP servers; all-write database operations; no broad arbitrary web crawling; no ingestion of restricted content; no unapproved production DOT endpoint connections.
- Full data lake, generic ETL orchestration product, self-managed RDBMS administration, or guarantee that all catalog records can be downloaded.

## Success criteria

A normal user needs no interaction outside the application for any **Ready to Import** dataset; the demo shows that imported data is queryable in chat, with traceable evidence and cost accounting. Unsupported records explain why automated import is not possible.

## Project positioning

This is a hackathon research prototype, not a U.S. DOT-authorized production service. Avoid suggesting government endorsement or suitability for sensitive federal information until agency review and controls are implemented.
