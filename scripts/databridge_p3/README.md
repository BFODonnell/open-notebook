# Repeatable Phase 3 acceptance

Use an explicitly disposable Linux Docker project. No real API/provider keys or
user data. The owner approved fixtures for acceptance. Catalog and publisher are
synthetic; HTTPS/TLS, downloader, subprocess parser, worker, SurrealDB, immutable
publisher, official MCP SDK, isolated MotherDuck, API, frontend and LiteLLM are real.
The runner submits the same application requests as the Explorer. It never places
input files in staging or registers an external database for an import.

The TLS fixture uses an **internal** Docker network with a public-shaped address
`93.184.216.2`, exact test-only DNS mappings and a locally generated trusted CA.
This emulates public DNS/TLS without a production private-address or insecure-TLS
exception. Do not use this overlay for deployment. Keys are generated under ignored
`temp/databridge-p3/tls`, expire after seven days, and must not be committed.

## Build and run (PowerShell, repository root)

```powershell
docker build -t databridge-p2-tests:local -f scripts/databridge_p2/Dockerfile.tests .
docker build --build-arg UV_EXTRA=databridge -t open-notebook-databridge:local .
docker run --rm -v "${PWD}:/workspace" -w /workspace databridge-p2-tests:local /app/.venv/bin/python -m scripts.databridge_p3.make_fixture_certs
$p3 = @('--env-file','scripts/databridge_p1/fixture.env','--env-file','scripts/databridge_p2/fixture.env','--env-file','scripts/databridge_p3/fixture.env','-p','databridge-p3-test','-f','compose.databridge.yml','-f','compose.databridge-mcp.yml','-f','compose.databridge-ingestion.yml','-f','scripts/databridge_p2/provider.compose.yml','-f','scripts/databridge_p3/provider.compose.yml')
docker compose @p3 up -d --build --wait --wait-timeout 180
function P3-Test($module, $mode) {
    docker exec -w /app databridge-p3-test-open-notebook-1 /app/.venv/bin/python -m "scripts.databridge_p3.$module" $mode
    if ($LASTEXITCODE -ne 0) { throw "P3 $module $mode failed" }
}
P3-Test acceptance seed
P3-Test reliability changed
P3-Test reliability cancel
```

Expected 51 seed, 2 changed-source, 1 cancellation checks. Seed imports CSV, flat
JSON, Parquet and ZIP from HTTPS resources via the application API, verifies real
command completion, exact MCP total 700, provenance/scoping, notebook Source
association without raw-row embeddings, idempotency and recovery. It also tests
HTML masquerading, blocked redirects, oversized transfers and catalog rate limits.
Synthetic row years are 2022-2025, with leading-zero agency/county identifiers.

## Real outages and interrupted-worker recovery

```powershell
docker stop databridge-p3-test-duckdb-broker-1
P3-Test reliability outage
docker start databridge-p3-test-duckdb-broker-1
Start-Sleep -Seconds 3
P3-Test reliability outage-recover
P3-Test reliability interrupt-start
docker kill databridge-p3-test-open-notebook-1
docker start databridge-p3-test-open-notebook-1
docker compose @p3 up -d --no-build --wait --wait-timeout 180
P3-Test reliability interrupt-recover
P3-Test reliability revocation
```

Expected 1+2+1+2+2 checks. **Kill immediately after interrupt-start**: that mode
returns when a real worker has begun the slow HTTPS transfer. Recovery asserts the
durable `running/downloading` state after SIGKILL/restart. The helper advances the
record's lease clock to avoid a 15-minute test wait, then uses the normal recovery
endpoint and real worker. Production has no clock-advance endpoint. Registration
recovery also tests a real broker outage and an administrator-disabled connection;
it must not silently reenable that connection. This state is separate from the
four main acceptance versions.

## Persistence and earlier phases

Run Phase 1/2 seed and smoke before restart, using the commands in their READMEs
with container/project prefix `databridge-p3-test`. Then:

```powershell
docker compose @p3 stop
docker compose @p3 up -d --no-build --wait --wait-timeout 180
P3-Test acceptance restart
docker exec -w /app databridge-p3-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p2.acceptance restart
docker exec -w /app databridge-p3-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py restart
```

Expected P3 restart 9, P2 restart 8, P1 restart 5. Keep volumes intact. Phase 2's
outage/drift/native-defense and Phase 1's unpriced tests remain applicable; run
unpriced last because it changes environment-managed models. Full commands and
semantics are in [P2 acceptance](../databridge_p2/README.md). Restore the normal
fixture environment before repeating Phase 1 seed. No paid provider calls occur.

Regression commands (Python environments are uv-managed):

```powershell
docker run --rm --cpus 2 --memory 2g -v "${PWD}:/workspace" -w /workspace databridge-p2-tests:local /app/.venv/bin/python -m pytest tests/ -q
docker build -t databridge-p0-baseline:local -f scripts/databridge_p0/Dockerfile.baseline .
docker run --rm --cpus 2 --memory 2g -v "${PWD}:/workspace" -w /workspace databridge-p0-baseline:local /app/.venv/bin/python -m pytest tests/ -q
$pythonFiles = @(git ls-files '*.py')
uv run --no-sync ruff check $pythonFiles
uv run --no-sync ruff format --check $pythonFiles
uv run --no-sync python -m mypy $pythonFiles
```

Use tracked implementation files after staging new work; preserve the owner's
untracked design package. Inside `frontend/`, run `npm run lint`,
`npm run test:coverage`, `npm run build`. Browser host access was unavailable in
this session; component tests and API automation are not browser E2E. The fixture
UI is at `http://127.0.0.1:18502`, password `p1-fixture-password-only`. Follow the
[in-app steps](../../deployment/databridge/ingestion/README.md) when a browser is
available. No administrator registration/password is needed for importing.

Each acceptance runner emits a JSON check list. Store sanitized evidence under
`docs/databridge/evidence/`. Local logs, TLS keys and fixture state stay ignored.
After collecting evidence, `docker compose @p3 down --volumes` removes only this
explicitly disposable project's data. Never apply that command to a user deployment.
