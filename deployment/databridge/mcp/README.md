# Phase 2 MCP deployment

Layer this onto the accepted [Phase 1 deployment](../README.md). The upstream
Compose file and existing Esperanto/LangGraph/SurrealDB services remain intact.
See [acceptance reproduction](../../../scripts/databridge_p2/README.md) for public,
synthetic credentials; never use those fixtures for user data.

## Configure and start

Install Python dependencies with `uv sync --extra databridge`. The application
locks official MCP SDK 1.28.1, SQLGlot 30.25.0, DuckDB 1.5.6 and jsonschema via
the root lock. The broker has its own uv lock. MotherDuck retains the accepted
Phase 0 lock in a separate `/opt/motherduck/.venv`; it is not installed into the
application or broker environment.

In a protected, git-ignored environment file, retain Phase 1's settings and add:

```dotenv
DATABRIDGE_MCP_ADMIN_KEY=<separate-random-secret-at-least-20-characters>
DATABRIDGE_DBHUB_TOKEN=<unique-random-service-secret>
DATABRIDGE_TOOLBOX_TOKEN=<different-random-service-secret>
DATABRIDGE_DUCKDB_TOKEN=<different-random-service-secret>
DATABRIDGE_DBHUB_CONFIG=./.databridge-private/dbhub.toml
DATABRIDGE_TOOLBOX_CONFIG=./.databridge-private/tools.yaml
```

Use independent random values, not the application password or LiteLLM key. The
application also supports `DATABRIDGE_MCP_ADMIN_KEY_FILE` when configured directly;
the supplied overlay passes the environment value. Service credentials in TOML/YAML
must be readable only by the operator and container service account. They are
read-only mounts into their own MCP services, never API-returned DSNs. Database
credentials belong to those service files; the Settings token field is the MCP
bearer token, **not** the database password.

Store the real service configs in `.databridge-private/` (excluded from Git and
Docker build context), or outside the repository. Do not place them elsewhere
inside the build context: the upstream application Dockerfile copies project files
into its image. The committed `scripts/databridge_p2/` configs contain only public
synthetic fixture credentials and are unsuitable for real deployments.

DBHub's reviewed TOML must use a dedicated PostgreSQL login with only CONNECT,
schema USAGE and SELECT on approved columns/base tables. Set `readonly=true`,
`max_rows <= 1000`, `query_timeout`, and database `statement_timeout`/`lock_timeout`.
Revoke unneeded database CONNECT, schema CREATE, write and administrative grants.
Default read-only transactions are additional protection, not a replacement for
grants. The [synthetic role script](../../../scripts/databridge_p2/postgres.sql)
shows the tested shape. Certify roles against the actual target before use.

Toolbox must use reviewed fixed `postgres-sql` prepared statements with `$1`-style
bind parameters, finite limits, and a separate restricted login. No template SQL,
dynamic identifiers, write tools, arbitrary URLs or user-supplied SQL parameters.
Configure a fixed no-argument schema tool as well as analytical tools. The fixture
schema tool returns `table_name`, `column_name`, `data_type` rows, filtered to the
connection's schema allowlist. Analytical authorization for Toolbox is the approved
tool set and its database role; inspect the fixed SQL rather than assuming the
application can parse SQL hidden behind a remote tool. The fixture
includes intentional timeout/large-output probes: these are tests, not production
recommendations. Changing the SQL/config is an operator action requiring connection
reapproval, even if the tool signature stays the same.

```powershell
docker compose --env-file .env.databridge -f compose.databridge.yml -f compose.databridge-mcp.yml up -d --build --wait --wait-timeout 180
```

Only the existing loopback-bound app ports are published. MCP services join internal
networks and have no outbound internet route. The raw Toolbox port is reachable
only through its fixed-destination authenticated gateway. A database in another
network requires an explicitly reviewed Compose/network change; registering a
connection in the UI cannot grant that access. The app still retains its Phase 1
egress for ordinary document/provider features. This is not a system-wide firewall.

The operator-only `DATABRIDGE_MCP_ENDPOINTS` map binds opaque endpoint references
to exact URLs, backend types and a `readonly: true` deployment attestation. It is
set in the overlay, not accepted from browser clients. Each call also uses upstream
URL validation, no redirects and no environment HTTP proxy. Database grants and
network topology must match the attestation; the app cannot remotely prove every
database role's permissions.

## Use the controls

In **Settings → Database connections**, select a notebook. Open administrator
controls with the separate key, add a connection using an approved endpoint, set
notebook scopes, table/column allowlists, limits and a bearer token, then save.
Test/discover, inspect the tool signatures, and explicitly approve capabilities.
The key stays in page memory; clear it when finished. Updating or disabling a
connection invalidates old approvals. No existing credential value is returned.

Inspect schema, enter supported SQL or select a curated Toolbox tool, review the
canonical query and version, then approve execution. SQL parameters use `:name`
and JSON scalar values; they become escaped AST literals because these MCP tools
do not expose a SQL bind interface. Toolbox uses real database prepared parameters.
Approvals expire in five minutes and are atomically consumed once. Results and
recent audit activity are persisted; SQL errors are sanitized and require a fresh
plan before retry. Model-generated database planning/chat is not part of Phase 2.

The SQL subset is a single SELECT from one approved, unqualified base table with
approved columns, simple predicates, grouping, ordering and selected aggregates.
No joins, CTEs, subqueries, comments, wildcard columns (except COUNT(*)), catalog
qualification, casts, external functions, extension commands, DDL or DML. Only
PostgreSQL DBHub and local DuckDB execution are certified/enabled. Other DBHub
engines, including SQL Server multi-catalog use, fail closed until separately tested.

## Immutable dataset publication

Phase 2 provides an operator interface for **already prepared synthetic/approved
staging files**, not ingestion. A future importer must create
`/app/data/databridge/staging/<UUID>.duckdb`, checkpoint and close it, then call
`POST /api/databridge/dataset-versions/publish` with application authentication,
`X-DataBridge-Admin` and `{ "staging_id": "<UUID>", "dataset_id": "<UUID>" }`.
No endpoint accepts file paths or download URLs. Select the resulting version in
the connection form. Publication runs in the Linux deployment.

Publication takes an OS lock and source read lock, rejects live WAL/symlinks/views,
copies into the published volume, fsyncs, and hard-links final files without
overwriting. The final manifest contains content/schema hashes and schema metadata.
SurrealDB registration follows manifest completion. The broker verifies content
hashes and starts a read-only MotherDuck process pinned to that version. Existing
connections/evidence keep their old version. There is no current-version mutation
or database-switch tool.

Limits: 256 MiB/file, 50 published or pending database files, 2 GiB total published
storage, 30 tables and 100 columns/table. Names must be lowercase ASCII identifiers.
The app permits at most 1,000 rows, 256 KiB result snapshots, 512 KiB MCP responses
and 30-second operation deadlines; lower per-connection limits apply. The broker
permits two active processes, 256 MB DuckDB memory/process, one thread/process,
three-second native queries and a 20-second full operation deadline. Container
memory/CPU/PID limits are additional caps.

No automatic retention/deletion exists. All published versions stay available,
effectively retaining evidence references. At quota, publication fails closed.
Back up SurrealDB, `dataset-versions`, `notebook-data`, Phase 1 PostgreSQL and
encryption keys together. Retrying a completed staging/version ID safely repairs
registration after a crash. Incomplete `.pending` files or a final database without
a manifest are unqueryable and count against quota. Stop publication before
operator reconciliation; preserve registered versions, review orphan IDs, and
remove only confirmed unregistered incomplete files from the published volume.
Do not recycle a version ID. No automatic orphan cleanup or reference-aware GC
is claimed. Staging storage cleanup is an operator responsibility in this phase.

## Failures and rollback

Health, discovery and approval are distinct. If a service/token/capability changes,
execution fails closed and records failure without result rows. Fix the service,
rediscover/reapprove if needed, then create a new plan. Toolbox and DBHub readiness
is tested by real discovery, not merely container process health. Completed query
evidence remains readable after a connection is disabled. If the API dies after
claiming a plan, its running audit is an indeterminate operation; it is never
automatically replayed or relabeled successful. Reconcile it before a manual retry.

To disable Phase 2, recreate the app with `DATABRIDGE_MCP_ENABLED=false` or remove
the MCP overlay. Stop its services explicitly. Preserve all volumes and migration
26 records for recovery; do not run `down --volumes` on a user deployment. Version
26's down migration exists for a reviewed rollback after backup, not automatic
startup use. Phase 1 can run without optional MCP functionality.

This remains the upstream shared-password application. Notebook scoping and the
separate administrator key are not tenant/user identity isolation. Use approved
public/synthetic data until organizational access, retention and sensitive-data
controls are separately reviewed. Audit/evidence contains selected data and SQL
literals; protect it with the same care as its sources. Live provider validation
and browser E2E remain tracked [cross-phase items](../../../docs/databridge/ACCEPTANCE_TRACKER.md).
