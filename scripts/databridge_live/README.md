# Live Data.gov / FTA validation

This is a separate controlled validation project, not a production deployment.
It uses the real official catalog and publisher, the existing application worker,
immutable publication and MCP. Its model endpoint is a local deterministic fixture;
no paid LLM calls or live conversational-model claims are made. DBHub and Toolbox
are configured by the existing overlay but not started or queried here.

Requirements: existing cached P4 application, P0 baseline and isolated DuckDB
images; Docker Desktop Linux; `uv`; a personal `DATAGOV_API_KEY` in the root
`.env.databridge`. Do not paste a key into commands or source files.

```powershell
uv run --no-sync python scripts/databridge_live/run.py up
docker cp scripts/databridge_live databridge-live-validation-open-notebook-1:/app/scripts/databridge_live
function Live-Test($mode) {
    docker exec -w /app databridge-live-validation-open-notebook-1 /app/.venv/bin/python -m scripts.databridge_live.acceptance $mode
    if ($LASTEXITCODE -ne 0) { throw "Live $mode failed" }
}
Live-Test search
Live-Test inspect
Live-Test preflight
Live-Test import
Live-Test status
Live-Test verify
Live-Test query
uv run --no-sync python scripts/databridge_live/run.py stop
uv run --no-sync python scripts/databridge_live/run.py up
Live-Test restart
```

Also verify the host/browser route, which container-local API tests do not cover:

```powershell
$runtime = Invoke-RestMethod 'http://localhost:18503/config'
if ($runtime.apiUrl -ne 'http://localhost:15056') { throw 'Browser API port mismatch' }
$response = Invoke-WebRequest -UseBasicParsing ($runtime.apiUrl + '/api/config') -Headers @{Origin='http://localhost:18503'}
if ($response.StatusCode -ne 200 -or $response.Headers['Access-Control-Allow-Origin'] -ne 'http://localhost:18503') { throw 'Browser API connection failed' }
```

These HTTP checks complement, but do not replace, browser end-to-end testing.

The search targets **2022 - 2025 NTD Annual Data - Service (by Mode and Time
Period)**. All acquisition/import/query actions use application API endpoints.
There is no direct file download, CLI ingestion, manual staging or external DB
registration. The `verify` mode independently inspects real command completion
and notebook association. Preflight must return `ready` before import. Status polls
for up to three minutes; a timeout/failure does not authorize query execution.
Live publisher bytes and counts may change; tests compare the actual import,
preview hash, manifest and MCP row counts rather than hardcoding historical totals.

The launcher reads only the catalog key from `.env.databridge`, passes it to the
backend through Compose, and never prints or copies it into a second file. It
creates independent random local service credentials in the Git/Docker-excluded
`.env.databridge-live-validation`. Preserve that file with the validation volumes.
Rendered Compose is inspected only in memory; fixture DNS/test CA configurations
are rejected. The local model fixture mounts only `scripts/`, not the root secret
files. Never use the P3 publisher fixture overlay for live validation.

UI: `http://localhost:18503`. The password is the `OPEN_NOTEBOOK_PASSWORD` entry
in `.env.databridge-live-validation`; do not post it in chat. API: loopback 15056.
Notebook, import, evidence and restart state persist in named volumes. Use `stop`
to save resources while preserving data; do not delete volumes as a restart method.
This stack's model is a fixture, so it is not ready for real conversational analysis.

The accepted native Windows OpenSSL issue also affects the HTTP test client;
therefore execute acceptance inside the Linux application container as above.
Full evidence: [live NTD validation](../../docs/databridge/LIVE_NTD_VALIDATION.md).
