# Phase 0 report — 2026-10-29

**Gate: PASSED on Linux/Docker.** The upstream audit, dependency review, reproducible
source boot, and real DuckDB read/write contention proof are complete. Phase 1 has
not been implemented; this is not a completed DataBridge application.

## Implemented and changed files

- `docs/databridge/UPSTREAM_AUDIT.md`: baseline SHA, actual integration points,
  compatibility matrix, pinned image digests, tested transport syntax and risks.
- `docs/7-DEVELOPMENT/decisions/ADR-0XX-databridge-duckdb-publication.md`:
  accepted immutable-version publication strategy, with evidence and limits.
- `scripts/databridge_p0/`: independent client/server uv projects and lockfiles;
  `duckdb_concurrency.py`, `mcp_transports.py`, `upstream_smoke.py`; isolated Docker
  test images and `baseline.compose.yml`; reproducible README commands.
- `docs/databridge/evidence/mcp-transports.json`: real synthetic query results,
  authentication rejection, write denial and row-cap evidence; no keys.
- `CHANGELOG.md`: developer-tooling entry under Unreleased/Added.

Branch: `feature/databridge-mvp`, starting at
`a0f6f3081ae06328f0a451b3a3ef2959ca25721d` (Open Notebook 1.15.0).
Application code, root Python/npm dependencies and lockfiles, and the supplied
untracked design package remain unchanged. No push or public deployment is performed.

## Tests and commands actually executed

Full rerun commands and prerequisites are in
[the experiment runbook](../../scripts/databridge_p0/README.md).
Temporary diagnostic logs are in `temp/databridge-p0/` (gitignored).

| Check / exact command | Result |
|---|---|
| `uv sync --frozen --python 3.12`, retried with process-local system trust | Installed pinned upstream dependencies; no lock update. Initial TLS failure documented below. |
| `npm ci --no-audit --no-fund --fetch-retries=1` with `NODE_USE_SYSTEM_CA=1`, in `frontend/` | Passed; 722 packages installed. |
| `npm run test:coverage`, in `frontend/` | **181 passed**, 35 files; 0 failed. Statements 44.79%, branches 46.28%, functions 38.81%, lines 45.72%. |
| `npm run lint`, in `frontend/` | Passed: 0 errors, 7 existing warnings. |
| `npm run build`, in `frontend/` | Passed, production routes generated. |
| `docker exec -w /app databridge-p0-baseline /opt/venv/bin/python -m pytest tests/ -q` | **1,000 passed**, 0 failed, 2 warnings; Linux/Python 3.12.11, frozen root dependencies. |
| `uv run --project scripts/databridge_p0 --frozen python scripts/databridge_p0/duckdb_concurrency.py` | **4 passed**, 0 failed on Windows; final run 10.520s. |
| `docker run --rm --name databridge-p0-proof --cpus 2 --memory 1536m --network none --mount type=volume,source=databridge-p0-proof-data,target=/proof-data databridge-p0-proof:local` | **4 passed**, 0 failed on Linux named volume; final run 7.117s. |
| Linux `mcp_transports.py` via `Dockerfile.transports` (full command in runbook) | Passed: SDK and FastMCP each query two bearer-authenticated DBHub services; missing/invalid tokens rejected; DELETE denied; two-row limit enforced; curated Toolbox SELECT returns exact 6, unknown SQL tool denied. |
| `docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml up --build -d` | Passed after removing duplicate image-build declarations; API healthy, all 25 migrations, worker and built UI started. No user-data mounts or host ports. |
| `docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml exec -T api python -m pytest tests/ -q` | **1,000 passed**, 0 failed, 2 warnings in 5.84s in the final reproducible harness. |
| `docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml exec -T -e P0_API_URL=http://127.0.0.1:5055 api python /checks/upstream_smoke.py` | **7 checks passed**, no mocks: health, providers, notebook create/read/update, real queued text and uploaded-document processing, original-file download, context/chat sessions, cleanup. |
| HTTP checks through built UI | `/notebooks`, `/api/notebooks`, `/api/config` each HTTP 200 using API-shared network namespace. This is an HTTP boot check, not browser E2E certification. |
| `ruff check .`, `ruff format --check .`, `python -m mypy .` in isolated baseline source snapshot | Passed: 151 application/test files. |
| `$pythonFiles = @(git ls-files '*.py'); uv run --no-sync ruff check @pythonFiles scripts/databridge_p0` | Passed for all tracked baseline Python plus new spike files. |
| `uv run --no-sync ruff format --check @pythonFiles scripts/databridge_p0` | Passed: 157 files. |
| `uv run --no-sync python -m mypy @pythonFiles scripts/databridge_p0` | Passed: 157 files. |
| `uv run --no-sync python -X utf8 <package>/tools/validate_package.py` | **4 fixture tests passed**; validator passed 28 required files, 19 Markdown documents, 4 schemas. |

`<package>` is
`design/databridge/Open_Notebook_DataBridge_Codex_Design_Package_v1.0/Open_Notebook_DataBridge_Codex_Package_v1.0`.
Frontend and design-fixture results are from the initial run; no frontend or design
files changed afterward. Repeating them solely because the machine restarted was
unnecessary. Backend and corrected spike checks were completed after recovery.

## Decisions, deviations and proven scope

**DuckDB:** immutable dataset/version files, pinned engine 1.5.6. Two real MCP
readers execute 40 queries while a third process holds a staging write transaction.
Old rows remain exactly `(100, 4950)`; the published version sums to 19900. Old-file
hash stays unchanged, failed staging rolls back, same-file lock conflicts are
explicitly demonstrated in both directions, and a new MCP process reopens the
published file. SQL paths are fixed test inputs; the production broker is P2/P3.

**Dependency isolation:** MotherDuck MCP 1.1.0 requires FastMCP 4.x/MCP 2.x; solving
it together with app MCP 1.28.1 fails. Its separate lock resolves FastMCP 4.1.4 and
MCP 2.3.0. Root libraries remain untouched. Both clients work across the protocol
boundary. Choose official SDK 1.28.1 for app-side integration: equivalent checked
wrappers are 17 versus 15 lines, no demonstrated advantage sufficient to add an
extra app-client abstraction. The server may keep its own FastMCP dependency.

**Upstream topology:** production rewrites captured `localhost:5055` at build time.
Runtime `INTERNAL_API_URL` alone did not change that build. The baseline harness
shares UI/API network namespace, matching the original combined image's routing.
The harness is source verification, not the final production Dockerfile.

**Certification:** DuckDB and SQLite (through DBHub and Toolbox) are integration
exercised. PostgreSQL, SQL Server, MySQL, MariaDB and Oracle are **untested**.
Toolbox uses a curated fixed SELECT and read-only fixture mount/SQLite URI; its
OAuth/identity integration is not certified. DBHub bearer authentication is tested.

**Mocked versus live:** upstream unit suites retain their upstream mocks. P0
content/worker, DuckDB and MCP checks use actual running services and synthetic
data, with no LLM calls or fake external provider responses.

## Failures encountered and remaining limitations

- Initial shutdown interrupted execution. No saved source damage or leftover
  task container was found on recovery; tests were resumed from the saved branch.
- Native Windows backend and some client imports still terminate with
  `OPENSSL_Uplink(...): no OPENSSL_Applink`. Certificate/PATH/OpenSSL-env experiments
  did not provide a reliable fix. Linux/Docker is the tested backend environment;
  this host-specific issue is not a blocker for that selected runtime.
- Inherited Anaconda `SSL_CERT_FILE` caused uv download failures. Removing it only
  for the command and using `uv --native-tls` succeeded. npm required
  `NODE_USE_SYSTEM_CA=1`. TLS verification was never disabled.
- Early proof failures were harness issues: CRLF handshakes, nonexistent package
  `__main__`, guessed query-tool name and resolving a POSIX venv symlink to base
  Python. Corrected proof passes on both platforms.
- Toolbox initially could not traverse the temporary 0700 fixture directory;
  synthetic directory now permits traversal for its non-root container user.
  Unknown tools raise `McpError` rather than a normal `isError` result; tested handling
  now accepts only the expected invalid-tool rejection.
- Baseline smoke initially used the wrong context payload shape; corrected to
  `context_config.sources`. All seven checks then pass. No app fix was needed.
- Unqualified repository-wide local lint/mypy also discover the owner's untracked
  reference-package scripts: six lint issues and one missing YAML-stub issue.
  The application/new-code checks above pass without modifying that package or
  adding exclusions to CI. The reference package is not included in this commit.
- No real provider credentials were used. Live chat generation, embeddings,
  podcasts, LiteLLM metering/budgets, all-engine certification and full DataBridge
  browser workflow are not claimed. These are later-phase acceptance work.
- No product identity/tenant boundary exists yet; single-user auth, strict public
  download policy, SQL sandbox and immutable registry/retention remain mandatory
  future work. DBHub read-only mode alone permits more SQL than the design allows.

## Next phase

P1: explicit Compose/build/dependency wiring, LiteLLM plus dedicated PostgreSQL,
managed Esperanto-compatible credentials/models and env-authoritative default,
then persistent usage/budget and provider-failure verification. Do not route around
upstream model management or claim costs from invented records.

Rollback and cleanup commands target only the P0 project/resources in the runbook.
Application behavior needs no rollback. Preserve the user's untracked `design/`.
