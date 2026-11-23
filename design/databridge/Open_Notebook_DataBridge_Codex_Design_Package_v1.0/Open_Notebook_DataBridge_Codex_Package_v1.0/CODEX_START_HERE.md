# Instructions to Codex: Implement Open Notebook DataBridge

You are implementing a production-minded hackathon MVP as a maintainable fork of https://github.com/lfnovo/open-notebook. Requirements and decisions in this directory were approved by the project owner. Follow this package exactly where explicit, but adapt to the **actual pinned upstream code**, which is the integration source of truth.

## Mandatory first actions (Phase 0)

1. Inspect `git status`, remote, current commit SHA, runtime and package versions. **Do not overwrite a dirty user working tree.**
2. Read `AGENTS.md`, `open_notebook/AGENTS.md`, `frontend/AGENTS.md`, upstream docs on architecture, credentials, content processing, and change playbooks. Follow their instructions in addition to this addendum.
3. Identify the real models/credential flow (upstream routes models through Esperanto), existing `Source`/Notebook abstractions, `commands/` background-worker submission pattern, frontend API client/hooks, migrations, testing conventions, and Docker Compose setup.
4. Compare upstream against `docs/02_ARCHITECTURE.md`; write `docs/databridge/UPSTREAM_AUDIT.md` with confirmed paths, risky areas, and deviations. Identify any runtime incompatibilities BEFORE adding dependencies.
5. Create a feature branch `feature/databridge-mvp`, unless that would conflict with existing user work. Record the upstream baseline.
6. Run/record baseline tests before modifying features. No claims of success without actual execution.

## Engineering approach

- Implement the approved **golden path** in small vertical slices, preserving notebook/chat/document functions. Favor extension over rewriting upstream.
- Use `uv add` or the upstream-compatible dependency workflow; keep `uv.lock` committed. Use Python 3.12 unless upstream constraints require another supported version.
- **Keep LiteLLM Proxy behind existing Open Notebook provider/Esperanto integration** by registering a compatible endpoint. The `.env` model variable must be the authoritative deployment default. Do not bypass all existing model infrastructure or break its credentials UI.
- For spending history/budget controls, run LiteLLM with a dedicated PostgreSQL database; do not pretend memory-only or no-db LiteLLM yields reliable cost tracking. Use app-scoped virtual credentials rather than exposing LiteLLM's master key to the frontend.
- **MCP is the database access protocol**: DBHub + Google MCP Toolbox + DuckDB MCP. FastMCP is an optional MCP client orchestration library, used only if a short comparison proves it simplifies authenticated multi-server operations vs the official MCP Python SDK. Record decision.
- **Data.gov acquisition is direct API/HTTP first**. Catalog search and backend download, parse, create tables, provenance, and live chat registration must all happen inside DataBridge, initiated by a visible Import action. Afterward, optionally expose approved catalog/import actions through FastMCP; do not block MVP on it.
- Never give the LLM raw OS access, arbitrary URL fetching, database write tools, or secrets. Queries are planned, checked, bounded, optionally approved and executed against read-only connections.
- Do not assume DuckDB's persistent file can be freely read by one process while another writes. Phase 0 must include a concurrency spike and select an explicitly tested approach before import/query integration.
- Retain synthetic/offline fixtures and live API adapters separately; initial demo may run offline after staging.
- Add tests, health checks, API schemas, error states, loading UI, migrations, documentation, and meaningful logs for each phase.

## Order of work

Read `docs/12_ROADMAP.md` and implement **one phase at a time**, with tests and a concise report after each. Make atomic commits/PRs if the environment permits. Do not skip security work to meet a demo deadline; instead narrow supported formats or connectors transparently.

1. **P0:** Baseline audit; verify image/runtime/module paths and DuckDB concurrency architecture.
2. **P1:** Compose/dependency wiring, LiteLLM integration, `.env` model and usage metering.
3. **P2:** MCP registry and adapters: DBHub, Google Toolbox, DuckDB; read-only SQL path and permissions.
4. **P3:** Data.gov v4 Explorer: search, dataset metadata, importability statuses, CSV/JSON/Parquet/ZIP/Excel adapters within guarded limits, background jobs, local DuckDB, registration into chat.
5. **P4:** LangGraph research workflow, multi-source data+document context, deterministic verification and evidence snapshots.
6. **P5:** Frontend polish, cost dashboard, DOT/Census/NOAA demo and recorded screenshots.
7. **P6:** Security/test hardening, documentation, Compose smoke tests, acceptance checklist.

## Required reporting after each phase

Include: changed files, architectural deviations from the design, exact commands/tests run and pass/fail counts, failures or unmet requirements, and next phase. Separate **implemented**, **tested**, **mocked**, and **planned**. Never claim all six DB engines are proven until real integration tests cover all six.

## Exit conditions

- Meets `docs/03_REQUIREMENTS.md` MVP acceptance criteria.
- `docker compose up --build` works with documented prerequisites, sensible health checks, and persistent data volumes; no real keys in tracked files.
- Full Data.gov golden path verified in app without manual steps outside it, using the official transit dataset where live access permits and a deterministic fixture otherwise.
- Imported dataset available in **the same active notebook chat** with accessible schema/metadata; no manual MCP registration.
- LLM default model and OpenAI-compatible endpoint set from `.env`, token/cost UI populated with genuine usage metadata.
- SQL query provenance, access restrictions and missing-data caveats are demonstrable.
- Usual upstream notebook/document workflows still work.

## What is NOT authorized in the MVP

No Trino/federation deployment; no MCP Alchemy/Teradata/AWS vendor server integrations; no automatic writes to connected agency databases; no unreviewed access to internal US DOT data; no LLM-generated external web crawls; no new public Internet-facing deployment; no access to confidential/PII data.

**Begin with P0.**
