# Phase 1 acceptance

These are **synthetic fixtures**, not a real provider deployment. Public test
passwords/keys must never be used for user data. The OpenAI HTTP server returns
100 input / 20 output / 10 cached / 5 reasoning tokens; everything between the
application and this provider (including LiteLLM and both databases) is real.

Run from the repository root with Docker Desktop's Linux engine. The fixture
provider uses the isolated P0 image; build it if absent:

```powershell
docker build -t databridge-p0-baseline:local -f scripts/databridge_p0/Dockerfile.baseline .
docker compose --env-file scripts/databridge_p1/fixture.env -p databridge-p1-test -f compose.databridge.yml -f scripts/databridge_p1/provider.compose.yml up -d --build --wait --wait-timeout 180
docker exec -w /app databridge-p1-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py seed
```

The seed stage exercises notebook chat, genuine proxy token details/cost,
attribution, date filtering, provider failure/checkpoint rollback, key scoping,
admin denial, real key budget exhaustion, application error mapping and budget
visibility. It writes only disposable state into `notebook-data`.

Restart all accounting processes **without deleting volumes**, rerun key
provisioning, and verify durability and model-registration idempotence:

```powershell
docker compose --env-file scripts/databridge_p1/fixture.env -p databridge-p1-test -f compose.databridge.yml -f scripts/databridge_p1/provider.compose.yml stop open-notebook litellm litellm-db
docker compose --env-file scripts/databridge_p1/fixture.env -p databridge-p1-test -f compose.databridge.yml -f scripts/databridge_p1/provider.compose.yml up -d --no-build --wait --wait-timeout 180
docker exec -w /app databridge-p1-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py restart
```

Change the environment alias and routing target to an unknown-priced model;
Compose recreates affected services and preserves the databases:

```powershell
docker compose --env-file scripts/databridge_p1/fixture.env --env-file scripts/databridge_p1/unpriced.env -p databridge-p1-test -f compose.databridge.yml -f scripts/databridge_p1/provider.compose.yml up -d --no-build --wait --wait-timeout 180
docker exec -w /app databridge-p1-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p1/acceptance.py unpriced
```

Expected: **26 assertions** across seed (17), restart (5), unpriced (4). Run the
ordinary source/worker regression smoke too (the provider credentials are fake):

```powershell
docker exec -w /app -e P0_API_URL=http://localhost:5055 -e P0_API_PASSWORD=p1-fixture-password-only databridge-p1-test-open-notebook-1 /app/.venv/bin/python scripts/databridge_p0/upstream_smoke.py
```

Expected: seven checks covering notebook CRUD, asynchronous text/document
processing by the real worker, original-file download, context and chat-session
CRUD, and cleanup. Embedding/podcast provider calls are not asserted by this test.

The full app is available at `http://127.0.0.1:18502` with password
`p1-fixture-password-only`; the API is at port 15055. Settings displays the
initial usage panel. Existing user deployments and default ports are untouched.

Stop the fixture when finished. Add `--volumes` only to discard this explicitly
disposable project's databases; never use that flag on the real deployment:

```powershell
docker compose --env-file scripts/databridge_p1/fixture.env -p databridge-p1-test -f compose.databridge.yml -f scripts/databridge_p1/provider.compose.yml down
```

`acceptance.compose.yml` is a faster developer alternative that mounts current
source and runs API/worker separately using the P0 image (no frontend). Commands
then use `-w /workspace` instead of `/app`. It is not the final deployment proof.

## Regression commands

Use uv for Python. On the audited Windows host, native OpenSSL fails independently
of these changes; the Linux baseline image is the verified test runner:

```powershell
docker run --rm --cpus 2 --memory 2g -v "${PWD}:/workspace" -w /workspace databridge-p0-baseline:local /app/.venv/bin/python -m pytest tests/ -q
```

After staging the implementation (so `git ls-files` includes new modules), lint
and typecheck tracked source; the owner-supplied untracked design examples have
the Phase 0 baseline lint/type issues and are not implementation source:

```powershell
$trackedPython = @(git ls-files '*.py')
uv run --no-sync ruff check $trackedPython
uv run --no-sync ruff format --check $trackedPython
uv run --no-sync python -m mypy $trackedPython
```

Inside `frontend/`: `npm run lint`, `npm run test:coverage`, `npm run build`.
The usage panel tests assert unavailable pricing, actual token categories, small
cost display, period/pagination changes, budget exhaustion, failure/retry and
disabled behavior. The locale parity suite covers all 14 dictionaries.

No paid OpenAI requests, private databases, Data.gov downloads or Phase 2 MCP
operations are made by these tests.
