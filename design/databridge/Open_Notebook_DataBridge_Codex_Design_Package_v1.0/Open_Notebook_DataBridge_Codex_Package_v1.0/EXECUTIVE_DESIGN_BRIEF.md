# Open Notebook DataBridge — Executive Design Brief

**MCP-powered research and analytics for public and approved relational data**  
*U.S. DOT MCP / AI Agent Hackathon — October 29, 2026 — Proposed Design v1.0*

## The problem

Analysts frequently work across relational databases, agency-maintained public datasets, and supporting documents. Retrieving a dataset from Data.gov often leads to an agency download page; joining it with demographic or weather information requires extra data-engineering work. Text-to-SQL assistants alone do not preserve a defensible chain of evidence.

## The solution

**DataBridge extends Open Notebook into one research environment.** Analysts use a built-in Data.gov Explorer to find data, see whether an individual resource is importable, and click Import. DataBridge itself downloads and validates eligible resources, publishes them to a local DuckDB analytical store, and makes the result available in the same notebook chat. The AI agent can also query permitted read-only enterprise databases through MCP, consult research documents, produce a chart, and cite the SQL/data version behind each quantitative claim.

**Product promise:** `Find → Import → Chat → Verify → Save` — without manual external downloads or standalone data preparation scripts for the user.

## Full stack at a glance

| Layer | Technology / approach |
|---|---|
| Research UX | Existing Next.js/React/TypeScript Open Notebook frontend with Data.gov Explorer, query review, evidence and cost panels |
| App services | Existing FastAPI/Python (target 3.12, subject to upstream), `uv`, background worker jobs, Pydantic schemas |
| Agent workflow | LangGraph with schema selection, SQL planning, policy/approval, execution, deterministic verification and report synthesis |
| Model gateway | Upstream Esperanto model abstraction → OpenAI-Compatible provider → LiteLLM Proxy → configured endpoint; `.env` default `gpt-6-astra` |
| Structured-data MCP | DBHub, read-only DuckDB MCP, curated Google MCP Toolbox; FastMCP as conditional client choice |
| Ingestion | Data.gov Catalog API v4, safe publisher downloader, format adapters and queued import jobs |
| Storage | Local versioned DuckDB for analytics; SurrealDB for notebooks/metadata/evidence; PostgreSQL for LiteLLM spend and key logs |
| Deployment | Docker Compose, persistent volumes, approved internal networks, pinning and health checks |
| Trust | Read-only DB roles, SQLGlot + strict policy, query approval, download SSRF controls, bounded execution, immutable provenance |

## User experience: Data.gov datasets

1. Search/browse Data.gov in DataBridge; server calls the **official v4 Catalog API** with its configured API key.
2. Examine dataset title, publisher, metadata and individual distribution resources.
3. See per-resource statuses: **Ready**, **Additional connector required**, **Unavailable** (and **Checking** while preflight runs).
4. Select a Ready resource and click Import. The backend downloads/parses it and publishes a versioned DuckDB table.
5. Imported schema/metadata are automatically attached to the currently selected Open Notebook notebook and available in its existing chat—**no manual MCP registration**.
6. Chat runs bounded, reviewed read-only SQL through MCP and saves SQL, checksum, source version, result snapshot and citations.

These implement explicitly approved **DB-DATA-01** and **DB-DATA-02**.

## Demonstration

Use the Federal Transit Administration's **2022–2025 NTD Annual Data — Service by Mode and Time Period** (public catalog record) as the anchor. Add U.S. Census population estimates and NOAA NCEI weather/climate data through approved in-app adapters; join only when calendar and geography mapping are valid. The model should explain that weather/ridership correlation is not causation and refuse misleading per-capita rates when service-area and Census denominators cannot be matched.

A deterministic, explicitly synthetic offline fixture pack is included so the judging demonstration is not dependent on a live data portal or an available model key.

## Model choice and spending

The deployment's `.env` defines `LLM_MODEL=gpt-6-astra` and an OpenAI-compatible API base URL/API key. LiteLLM Proxy routes requests and persists per-request spend to its dedicated PostgreSQL store. The in-app dashboard shows request count, input/output/cached tokens, cost estimates by session/notebook/model/task, and warnings when pricing is unknown.

## Scope and delivery

**MVP:** Upstream-preserving Docker integration; LiteLLM usage; DBHub/DuckDB MCP/Google Toolbox connections; Data.gov search/preview/import; reliable read-only query path; immediate notebook access; SQL approval/evidence; one chart; complete DOT demonstration and tests.

**After MVP:** Data.gov import tools exposed through FastMCP, incremental refresh, improved query federation and specialist data sources.

**Deferred:** Trino, MCP Alchemy, specialized Teradata/AWS/Databricks/MongoDB/graph servers, broad arbitrary internet crawling, database writeback, and restricted internal agency data.

## Critical engineering considerations

- The original Open Notebook uses **Esperanto** as its model abstraction; integrate LiteLLM by supported provider registration, not by rewriting all agents.
- DuckDB requires an explicitly tested process/locking/versioning strategy before placing an importer and an independent MCP server against the same file.
- Data.gov is primarily a **catalog**; the actual resource is generally held by a publisher. DataBridge must safely retrieve publisher URLs and handle unsupported resources honestly.
- A read-only MCP server is **not by itself a sandbox**, especially for local DuckDB functions capable of filesystem access. Use network, file and database privilege isolation.
- This is a hackathon design for **public/synthetic** data; DOT production use requires security and privacy review and authorized LLM endpoints.

## Codex handoff

Begin with [`CODEX_START_HERE.md`](CODEX_START_HERE.md). The ZIP contains 14 detailed design chapters, 17 proposed API routes, four JSON Schema contracts, deployment templates, Mermaid diagrams, synthetic fixtures, tests, and a phase-by-phase roadmap. **It is a specification package, not an already implemented application.**
