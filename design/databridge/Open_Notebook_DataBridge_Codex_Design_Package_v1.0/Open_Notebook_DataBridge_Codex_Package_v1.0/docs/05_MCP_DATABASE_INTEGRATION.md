# 05 — MCP Database Connectivity and Policy

## Core MCP servers

| Backend | Scope | Implementation priority |
|---|---|---|
| **DBHub** (`bytebase/dbhub`) | PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, SQLite, multiple named connections, `search_objects` + `execute_sql`, read-only mode and limits | Must support/configure; certify at least representative engines for demo |
| **DuckDB MCP** (`motherduckdb/mcp-server-motherduck`) | Local DuckDB query service, catalog introspection; read-only default, max rows/chars; local filesystem remains a danger even with read-only | Must integrate after concurrency and isolation spike |
| **Google MCP Toolbox for Databases** (`googleapis/mcp-toolbox`) | Selected extra relational/cloud/analytical/NoSQL or graph sources, prebuilt or curated parameterized tools | Must integrate controlled connection and approved toolset; extra engines optional/untested initially |
| **FastMCP client library** (`PrefectHQ/fastmcp`) | Optional multi-server client management, tool discovery/transport, proxy | P0 compare against official MCP SDK; choose only for measurable maintenance advantage |

**Do not deploy Trino, MCP Alchemy or specialist third-party MCP servers in MVP.** Their catalog remains a future-extensions note.

## Server registry contract

Persist an admin-managed registry of MCP endpoint records: `server_id`, type, transport (`streamable_http` preferred for containers; optional stdio for local), internal URL/launch reference, connection/credential reference, available tools and capabilities, allowed notebook/user scopes, enabled/healthy status, last test time, and version. Credentials must be encrypted server-side and **not exposed** in frontend JSON.

The registry needs `register`, `update`, `disable`, `test_connection`, `discover_tools`, `validate_capabilities`. Tool-list output is **not automatically trusted**; admin-approved `tool_id` and argument schemas are an allowlist. On server restart/reconnect, revalidate capabilities and tool identity.

## Normalized capability interface

Do not expose backend-specific tool names to the research agent when a normalized adapter can conceal them:

```text
list_sources(scope) -> named available connections
list_schema(connection, catalog?, schema?) -> tables/columns/relationships
preview_table(connection, table, limit<=configured) -> bounded records
execute_readonly_sql(connection, sql, parameters?, approval_token) -> result+execution metadata
```

For a Google Toolbox curated business tool, the adapter can expose a capability such as `run_ntd_summary` with typed parameters instead of arbitrary SQL; only map to `execute_readonly_sql` when the server actually supports safe execution.

## Query security pipeline

1. Resolve user/notebook authorization; select approved connection and catalog.
2. Retrieve **bounded schema metadata** and a business glossary; avoid unbounded data/schema/tool exposure to model.
3. Have agent draft one candidate SQL statement and expected result schema; present generated SQL in UI when approval mode is enabled.
4. Parse using SQLGlot with correct SQL dialect and enforce single read-only statement; use AST allowlists/deny unsafe functions. Reject DDL, DML, stored procedures, `COPY`, external file/network reads, dynamic SQL, multi-statement, comments used to bypass checks, and unknown constructs; do not attempt to prove SQL is safe with regex alone.
5. Check `connection/table/column/function` allowlists and parameterize values; enforce DB role with **server-side read-only credentials** and per-connection SQL/query timeout, row cap and bytes cap. SQL AST validation is defense in depth, not sufficient on its own.
6. Execute through the approved MCP tool with correlation ID; redact secrets and sensitive data in traces. Save query metadata, row count and result hash to evidence store.
7. Verify data types and calculations; show SQL, source and limitations to user.

### DuckDB specifics

- A query against a local DuckDB file is not safe simply because the server was started `--read-only` (functions can access filesystem/network, change settings, etc.). Lock the container filesystem down, disable external access/functions where possible, restrict extensions, use resource limits, and allowlist tables and SQL nodes.
- Never expose the dangerous `switch_database_connection` or database path arguments to the LLM. Server should access **only** approved versioned data files and be isolated from credentials and source volumes.
- Do not allow agent to attach arbitrary files/databases; import service is the only ingestion writer. See concurrency spike in `docs/02_ARCHITECTURE.md`.

### DBHub specifics

- Configure one or more named connections, with `readOnly`, row and timeout limits using actual DBHub configuration syntax verified by Codex. Default tools: `execute_sql` and `search_objects`; opt-in explain only when reviewed.
- SQL Server instance with multiple catalogs should be represented through separate authorized catalog entries/connection aliases with distinct grants. Test SQL Server catalog switching is denied when not in allowlist.
- DBHub's documented support is not evidence that every connector works in our Docker image; use integration tests for certification.

### Google Toolbox specifics

- Configure explicit YAML source/tool definitions or narrowly chosen prebuilt toolsets, **not all prebuilt actions**. Prefer parameterized, curated analytical tools. Restrict catalog rights in the database itself.
- Discover and validate tool argument/result types on startup, store approved signatures and versions, and surface missing dependencies/errors.
- Do not imply Trino is deployed simply because Toolbox can connect to Trino.

## MCP transport and network policy

- Prefer Streamable HTTP within an internal Docker network with authentication/TLS in environments where it crosses a trust boundary; pin server image digests, block external arbitrary endpoints, implement timeouts, backoff, cancellation and limits.
- Prevent arbitrary user registration of remote MCP URLs in default configuration; admin approval and network egress restrictions required.
- MCP errors are shown as typed issues: auth failure, server unreachable, tool missing, query denied, timeout, rate limit, result too large.

## Tests

- Registry discovery/integration test for DBHub, DuckDB and Google Toolbox.
- Two SQL Server catalogs under same instance with correct distinct grants.
- Denylist adversarial SQL incl comment/literal tricks, multiple statements, `ATTACH`, `read_csv`, `read_parquet`, extension loaders, `COPY`, `PRAGMA`/unsafe settings, exfil functions.
- Query cap and timeout enforced **at tool/database**, not merely after receiving all result rows.
- MCP server failure mid-query: UI shows error and evidence record is not mislabeled successful.
