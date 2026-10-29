# Phase 0 experiments

These developer experiments use temporary synthetic data and isolated services.
They do not enable DataBridge features or modify upstream dependencies. The two
uv environments have independent lockfiles: client MCP 1.28.1/FastMCP 3.2.0 and
server MotherDuck 1.1.0/FastMCP 4.1.4/MCP 2.3.0. Both pin DuckDB 1.5.6.

Run commands below from the repository root. Prerequisites: uv, Python 3.12, Docker
Desktop with Linux containers and sufficient disk space. Verification containers
have CPU/memory limits. Names beginning `databridge-p0` are reserved for these tests.
Do not run two copies of the named harness at once.

## Native DuckDB proof

```powershell
uv sync --project scripts/databridge_p0 --frozen --python 3.12
uv sync --project scripts/databridge_p0/motherduck --frozen --python 3.12
uv run --project scripts/databridge_p0 --frozen python scripts/databridge_p0/duckdb_concurrency.py
```

On this host an inherited Anaconda CA bundle blocked downloads. Removing
`SSL_CERT_FILE` only in the command process, then using `uv --native-tls sync ...`,
fixed installation. Do not disable TLS validation. Native Windows app/FastMCP
imports still have an OpenSSL runtime problem, so use Linux for the other checks.

## Linux named-volume proof

```powershell
docker build -f scripts/databridge_p0/Dockerfile -t databridge-p0-proof:local .
docker volume create databridge-p0-proof-data
docker run --rm --name databridge-p0-proof --cpus 2 --memory 1536m --network none --mount type=volume,source=databridge-p0-proof-data,target=/proof-data databridge-p0-proof:local
```

Four tests cover both directions of conflicting same-file read/write locks,
immutable publication during 40 real MCP queries from two reader processes,
exact numerical results and old-file hash retention, denied writes, restart and
aborted staging. Handshakes prove overlapping connection lifetimes without sleeps.
The controller awaits blocking DuckDB work via `asyncio.to_thread`; each child owns
its synchronous connection. Tests have bounded waits and clean up temporary files.
No LLM-supplied SQL or filesystem path is accepted. The code is a proof, not the
production authorization, SQL policy, registration or retention implementation.

## MCP transports and client comparison

Build the proof image above first. Create the dedicated network once (reuse it if
it already exists), then run:

```powershell
docker network create databridge-p0
docker build -f scripts/databridge_p0/Dockerfile.transports -t databridge-p0-transports:local .
docker run --rm --name databridge-p0-transports --cpus 1 --memory 768m --network databridge-p0 --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock --mount type=volume,source=databridge-p0-proof-data,target=/proof-data -e P0_DOCKER_NETWORK=databridge-p0 -e P0_DOCKER_VOLUME=databridge-p0-proof-data databridge-p0-transports:local
```

Only this trusted test orchestrator receives the Docker socket; the DBHub/Toolbox
servers do not. It creates two DBHub containers with different random test bearer
keys and one Toolbox container, using pinned image digests. They have read-only
root/filesystem mounts, CPU/memory limits and loopback-only ephemeral host ports.
Finally it removes its own generated container names, even on test failure.

The script asserts missing/invalid DBHub bearer rejection, exact SUM=6 from both
clients against both endpoints, denied DELETE, two-row truncation and Toolbox's
single curated tool/result/unknown-tool rejection. Configured fixture directory
permissions allow the Toolbox image's non-root user to read synthetic files.
It prints only synthetic results and check labels, never tokens.

Toolbox is isolated by network/mount/tool configuration here; its OAuth is not
configured. The test proves only SQLite, not the five other advertised DBHub engines.
Official SDK is the selected app client: it passes the same multi-server exercise
with a 17-line wrapper versus FastMCP's 15, retaining explicit per-server authority.

## Repeatable upstream source boot

This harness verifies the pinned source with real SurrealDB and a real worker.
It is not a production build of DataBridge or a clean-room release-image test.
First prepare the existing frontend build (from `frontend/`):

```powershell
npm ci --no-audit --no-fund
npm run test:coverage
npm run lint
npm run build
```

On this host, set `NODE_USE_SYSTEM_CA=1` for npm installation. Then return to the
repository root:

```powershell
docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml up --build -d
docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml exec -T api python -m pytest tests/ -q
docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml exec -T -e P0_API_URL=http://127.0.0.1:5055 api python /checks/upstream_smoke.py
```

`P0_API_URL` is mandatory to avoid accidentally targeting a user's existing app.
Seven smoke assertions exercise health, provider metadata, notebook edits, async
text and uploaded-document processing/download, source context and chat sessions,
then delete their synthetic records. No model call or embedding is requested.
SurrealDB is in-memory and uses throwaway local-only credentials. No host ports,
real credentials or user data directories are mounted. The app-data volume holds
only this harness's synthetic uploads/checkpoints.

The frontend uses the existing standalone build and shares API network namespace,
matching upstream's combined image. Rewrites captured `localhost:5055` at build
rather than adopting a changed runtime `INTERNAL_API_URL`. Verify all three HTTP
surfaces without exposing a host port:

```powershell
docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml exec -T api python -c "import httpx; c=httpx.Client(base_url='http://127.0.0.1:3000'); paths=['/notebooks','/api/notebooks','/api/config']; results=[(p,c.get(p)) for p in paths]; print([(p,r.status_code,len(r.content)) for p,r in results]); assert all(r.status_code==200 for _,r in results)"
```

## Static checks and cleanup

From PowerShell, check tracked source plus the new experiments without including
the owner's untracked design-package example scripts:

```powershell
$pythonFiles = @(git ls-files '*.py')
uv run --no-sync ruff check @pythonFiles scripts/databridge_p0
uv run --no-sync ruff format --check @pythonFiles scripts/databridge_p0
uv run --no-sync python -m mypy @pythonFiles scripts/databridge_p0
```

After a phase commit, the new files are already in `$pythonFiles`; use just that
argument (do not pass `scripts/databridge_p0` a second time to mypy).

Remove only this harness's disposable resources:

```powershell
docker compose -p databridge-p0-check -f scripts/databridge_p0/baseline.compose.yml down --volumes
docker volume rm databridge-p0-proof-data
docker network rm databridge-p0
```

Images/caches are reusable and may remain. Do not prune unrelated Docker resources,
run `git clean`, or delete the user's design package. Local logs live in
`temp/databridge-p0/`; retained synthetic MCP results are in
[the evidence file](../../docs/databridge/evidence/mcp-transports.json).

See [Phase 0 report](../../docs/databridge/PHASE_0_REPORT.md) for results, earlier
failures, remaining limitations and Phase 1 handoff.
