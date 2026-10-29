# Repeatable Phase 4 acceptance

Use only a disposable project and the committed **synthetic** credentials. The
LLM and Data.gov/publisher responses are fixtures; LangGraph, Esperanto, LiteLLM,
PostgreSQL, SurrealDB, worker, downloader, parser, immutable publisher and MCP are
real. No manually downloaded input or external registration is used.

Follow the P3 README to build test images and generate the short-lived fixture
TLS certificates, then from the repository root:

```powershell
docker build --build-arg UV_EXTRA=databridge -t open-notebook-databridge:local .
$p4=@('--env-file','scripts/databridge_p1/fixture.env','--env-file','scripts/databridge_p2/fixture.env','--env-file','scripts/databridge_p3/fixture.env','-p','databridge-p4-test','-f','compose.databridge.yml','-f','compose.databridge-mcp.yml','-f','compose.databridge-ingestion.yml','-f','compose.databridge-research.yml','-f','scripts/databridge_p2/provider.compose.yml','-f','scripts/databridge_p3/provider.compose.yml','-f','scripts/databridge_p4/provider.compose.yml')
docker compose @p4 up -d --no-build --wait --wait-timeout 180
function P4-Test($mode) {
    docker exec -w /app databridge-p4-test-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_p4.acceptance $mode
    if ($LASTEXITCODE -ne 0) { throw "P4 $mode failed" }
}
P4-Test seed
docker stop databridge-p4-test-duckdb-broker-1
P4-Test outage
docker start databridge-p4-test-duckdb-broker-1
P4-Test recover
P4-Test recovery
docker compose @p4 stop
docker compose @p4 up -d --no-build --wait --wait-timeout 180
P4-Test restart
```

Expected check counts: seed 48, outage 3, recover 1, recovery 6, restart 6.
The helper emits a JSON checklist and stores disposable state in the test volume.
Seed verifies the entire API workflow: search/import into a pre-existing chat,
review/approve, exact 700 total, annual trend, server-loaded notebook quote,
SQL/permission/approval rejection, model failure, new-version invalidation and
real usage accounting. Recovery simulates the exact post-MCP/pre-research-write
crash boundary using the real persisted query; it never substitutes fake rows.
Lease timestamps are advanced in test-only database operations, with no production
clock override endpoint. Restart stops all services without deleting volumes.

Run the P1/P2/P3 regression runners and upstream smoke against this same project
using their READMEs, replacing their project/container prefix with `databridge-p4-test`.
Run P4 before P1 seed because the latter intentionally exhausts its fixture budget.
The P3 context assertions follow the enabled research flag; its standalone overlay
still reports conversational analysis disabled. Keep that distinction in evidence.

Run all backend tests in both uv-managed Linux images as in the P3 README; run
Ruff/format/mypy on tracked Python implementation files, frontend lint, coverage and
production build. The owner's untracked design package is not a lint target.
Record sanitized results under `docs/databridge/evidence/`; never copy test state
containing approval tokens into committed evidence. Browser checks use the normal
UI at `http://127.0.0.1:18502`, fixture password `p1-fixture-password-only`.

No fixture result certifies live GPT-6 Astra or real Data.gov/NTD. Do not combine
personal keys with the fixture DNS/TLS overlays. After evidence capture, remove
only the explicitly disposable project using `docker compose @p4 down --volumes`.
