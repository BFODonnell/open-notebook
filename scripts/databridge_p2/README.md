# Phase 2 real-protocol acceptance

Run only in this disposable Compose project. All credentials/databases are public
synthetic fixtures. No production DB, paid provider, Data.gov or Trino is used.
DBHub, Toolbox, the isolated MotherDuck server, PostgreSQL, SurrealDB, LiteLLM,
API, worker and frontend are real. Only the external LLM provider is a fixture.

From the repository root in PowerShell (Docker Desktop Linux engine):

```powershell
docker build -t databridge-p0-baseline:local -f scripts/databridge_p0/Dockerfile.baseline .
docker build -t databridge-p2-tests:local -f scripts/databridge_p2/Dockerfile.tests .
$p2 = @('--env-file', 'scripts/databridge_p1/fixture.env', '--env-file', 'scripts/databridge_p2/fixture.env', '-p', 'databridge-p2-test', '-f', 'compose.databridge.yml', '-f', 'compose.databridge-mcp.yml', '-f', 'scripts/databridge_p2/provider.compose.yml')
docker compose @p2 up -d --build --wait --wait-timeout 180
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p2.acceptance seed
```

Expected: 65 checks. The runner creates two notebooks, two immutable dataset
versions and scoped connections. Tests use the application API for real discovery,
approval, schema, policy rejection, queries, evidence and encrypted persistence.
It also calls MCP directly to verify server/role defenses below the app gate.
Assertions cover exact totals (6 and 21), limits, scope, tokens, concurrent/replayed/
expired/stale approvals, version integrity and credential isolation. No mock MCP
sessions or invented usage records are substituted.

Inject a real service outage, then an actual tool-list change:

```powershell
docker stop databridge-p2-test-dbhub-1
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p2.acceptance outage
docker start databridge-p2-test-dbhub-1
docker compose @p2 -f scripts/databridge_p2/drift.compose.yml up -d --no-build --no-deps dbhub
Start-Sleep -Seconds 3
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p2.acceptance drift
docker compose @p2 up -d --no-build --no-deps dbhub
```

Each mode asserts durable failed evidence without result rows. Drift removes
`search_objects` while retaining `execute_sql`; the application must rediscover
and refuse the changed fingerprint before executing the query.

Verify engine protections directly through the official MCP SDK, bypassing the
application and broker AST gates. The helper mirrors the broker's pinned launch
configuration and runs its MotherDuck executable, not an in-process DuckDB mock:

```powershell
Get-Content scripts/databridge_p2/duckdb_defense.py -Raw | docker exec -i databridge-p2-test-duckdb-broker-1 python -
docker exec -e PGPASSWORD=p2-dbhub-db-only databridge-p2-test-fixture-pg-1 psql -h localhost -U dbhub_reader -d analytics -v ON_ERROR_STOP=1 -c 'DELETE FROM sample'
docker exec -e PGPASSWORD=p2-dbhub-db-only databridge-p2-test-fixture-pg-1 psql -h localhost -U dbhub_reader -d analytics -v ON_ERROR_STOP=1 -c 'SET default_transaction_read_only=off' -c 'DELETE FROM sample'
docker exec -e PGPASSWORD=p2-dbhub-db-only databridge-p2-test-fixture-pg-1 psql -h localhost -U dbhub_reader -d analytics -v ON_ERROR_STOP=1 -c 'SELECT secret FROM sample'
docker exec -e PGPASSWORD=p2-dbhub-db-only databridge-p2-test-fixture-pg-1 psql -h localhost -U dbhub_reader -d hidden -c 'SELECT 1'
```

Expected: six helper checks pass; all four psql commands **fail** with read-only,
table/column permission, or catalog CONNECT denial. A successful psql query is a
test failure here. Fixture credentials are intentionally printed in these commands.
The helper verifies native timeout, blocked file/extension/config/write operations
and child credential isolation. It never prints secret values.

Run the unchanged Phase 1 acceptance seed and upstream worker smoke, then restart
all persistent services without deleting volumes:

```powershell
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py seed
docker exec -w /app -e P0_API_URL=http://localhost:5055 -e P0_API_PASSWORD=p1-fixture-password-only databridge-p2-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p0/upstream_smoke.py
docker compose @p2 stop open-notebook surrealdb litellm litellm-db dbhub toolbox toolbox-gateway duckdb-broker fixture-pg
docker compose @p2 up -d --no-build --wait --wait-timeout 180
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p2.acceptance restart
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py restart
```

Expected: P2 restart 8 checks; P1 seed 17 and restart 5; upstream smoke 7. Then
verify the P1 environment model change/unavailable-pricing path (four checks):

```powershell
docker compose @p2 --env-file scripts/databridge_p1/unpriced.env up -d --no-build --wait --wait-timeout 180
docker exec -w /app databridge-p2-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py unpriced
```

Regression suites use uv-managed dependencies. On the audited Windows host, native
backend OpenSSL is unreliable, so run pytest in the Linux test image:

```powershell
docker run --rm --cpus 2 --memory 2g -v "${PWD}:/workspace" -w /workspace databridge-p2-tests:local /app/.venv/bin/python -m pytest tests/ -q
$pythonFiles = @(git ls-files '*.py')
uv run --no-sync ruff check $pythonFiles
uv run --no-sync ruff format --check $pythonFiles
uv run --no-sync python -m mypy $pythonFiles
```

Lint/typecheck tracked implementation after staging new files, preserving the
owner's untracked reference design. Inside `frontend/`, run `npm run lint`,
`npm run test:coverage`, and `npm run build`. Expected current totals: 1,145 backend
and 193 frontend tests. Browser interaction and live GPT-6 Astra are separate
[outstanding items](../../docs/databridge/ACCEPTANCE_TRACKER.md).

The fast developer `acceptance.compose.yml` substitutes mounted-source API only
and can replace `provider.compose.yml` while iterating. It has no frontend/worker
and is **not** the final full-deployment proof. Use `/workspace` there. The full
fixture exposes UI 18502/API 15055 on loopback, password `p1-fixture-password-only`.

After collecting evidence, `docker compose @p2 down --volumes` removes only this
explicitly disposable fixture's data. Never run it against a user deployment.
