# DataBridge Phase 1 deployment

This opt-in environment preserves the upstream Compose file and existing data.
It adds a language-model gateway and its own PostgreSQL database. It does not
start MCP servers, ingestion, or Phase 2 database connectors.

## Start

Requirements: Docker Compose v2, sufficient Docker memory (8 GB recommended),
and credentials for an operator-approved OpenAI-compatible provider.

1. Copy `deployment/databridge/.env.example` to `.env.databridge` at the repo root.
2. Fill every secret with a separate strong random value. The master and app keys
   must start with `sk-` and be different. Use a URL-safe PostgreSQL password
   (random hex is suitable). Keep the encryption key, LiteLLM salt and database
   credentials stable and backed up. Do not commit the file.
3. Set `LLM_MODEL` (app alias), `LLM_PROVIDER_MODEL` (LiteLLM target),
   `OPENAI_API_BASE` and `OPENAI_API_KEY`. The default alias/target are
   `gpt-6-astra` / `openai/gpt-6-astra`. Account access has **not** been verified
   by this implementation; choose another supported model if necessary.
4. Run from the repository root:

```powershell
docker compose --env-file .env.databridge -f compose.databridge.yml up -d --build --wait --wait-timeout 180
```

Open `http://localhost:8502` and sign in with `OPEN_NOTEBOOK_PASSWORD`. The API is
on loopback port 5055. Override `DATABRIDGE_UI_PORT` / `DATABRIDGE_API_PORT` if
occupied. No database or gateway ports are published. Do not publish this
development password-based service to the Internet.

The frontend's runtime `API_URL` defaults to `http://localhost:` followed by
`DATABRIDGE_API_PORT`, so custom host port mappings also work in the browser.
Set `API_URL` explicitly for an operator-reviewed reverse proxy/public address.
Internal server-side API traffic retains container port 5055. Recreate with `up`
after changing these values; refresh the browser to reload `/config`.

The upstream image runs the API, real worker and frontend under supervisord.
The initializer provisions a restricted virtual key before API startup. Startup
runs normal migrations, encrypts the linked gateway credential and registers the
model/default automatically. `Settings → DataBridge model usage` shows UTC date
filters, paginated records, token categories and the lifetime key budget.

For native development, `uv sync --extra databridge` installs the pinned official
MCP SDK alongside upstream dependencies. Set `DATABRIDGE_ENABLED=true`,
`LITELLM_PROXY_URL`, `LITELLM_APP_VIRTUAL_KEY` and `LLM_MODEL` only in the backend
environment after provisioning a gateway. Never put the master/provider key in
frontend environment variables. The MotherDuck environment stays under
`scripts/databridge_p0/motherduck/`; no application client imports FastMCP.

## Model and budget changes

Edit `.env.databridge` and rerun the `up` command. A plain `docker compose restart`
does **not** load changed environment variables. The initializer updates key
access and `LITELLM_APP_MAX_BUDGET` without clearing spend. The cap is lifetime
USD estimated spend; there is no implicit periodic reset. Raise it explicitly
after reviewing usage. Use operator-only LiteLLM administration for deliberate
key rotation; do not reset/recreate the DB as a budget workaround.

Chat defaults follow `.env` on every API startup. Empty or previously managed
language defaults follow it too; explicitly selected transformation/tools/large
context models, embedding and speech defaults are preserved. Existing provider
credentials/models remain available. Per-session overrides remain explicit; an
old managed alias that is no longer authorized fails rather than silently
switching provider. The linked credential is labeled “managed by .env”.

Pricing uses the pinned LiteLLM image's bundled map. Records preserve their cost
and available rate snapshot, so changes do not reprice old calls. Review prices
when upgrading the image. Optional `LLM_INPUT_COST_PER_TOKEN` and
`LLM_OUTPUT_COST_PER_TOKEN` are **USD per token**, both or neither; cache/tier
rates still come from the map. Never fill unknown prices with zero.

Budget/log writes are asynchronous. In-flight requests can overshoot a cap;
unpriced usage is not covered by a monetary cap. Provider invoices can differ.
Zero/missing spend is displayed as unavailable, including genuinely free calls.
SDK/router retries are off, and there is no implicit fallback model. Unsupported
sampling options are dropped by LiteLLM's provider adapter.

Coverage is gateway language calls only, not total AI spend. Notebook chat has
notebook/session/trace/task attribution. Other provisioned calls have trace/task
labels; some direct Esperanto calls have no application attribution. Missing
provider token details stay unavailable. MCP/tool runtime is not billed as LLM
tokens. Phase 1 is a read model; charting, exports, full job correlation and
retention UI remain later-phase work. New UI strings have English text in all
14 locale dictionaries pending translation.

## Persistence, health and rollback

Named volumes hold notebook data/checkpoints, SurrealDB and LiteLLM PostgreSQL.
Back up **all three**, plus the secret environment file, using consistent
database backups. `down` preserves volumes; `down --volumes` destroys them.
Never point this test configuration at existing user databases.

```powershell
docker compose --env-file .env.databridge -f compose.databridge.yml ps
docker compose --env-file .env.databridge -f compose.databridge.yml logs --tail 100 open-notebook
docker compose --env-file .env.databridge -f compose.databridge.yml logs --tail 100 gateway-init litellm
docker compose --env-file .env.databridge -f compose.databridge.yml down
```

The usage API returns sanitized 502 errors when the gateway/database is
unavailable. Provider/budget failures use upstream error handling and remove
failed chat turns from checkpoints. Failed gateway logs may lag behind the chat.
Prompts/responses are not stored in spend logs; provider error diagnostics can
still be sensitive. Do not enable verbose proxy logging in a shared deployment.

Rollback: stop this opt-in stack and use the unchanged upstream environment/data.
If reusing the DataBridge database with the feature disabled, first select an
existing direct-provider chat default in Models. Disabling the flag does not
delete managed records or invent a replacement default. Keep gateway/DB volumes
for historical accounting. No Phase 1 schema migration needs reversing.

References: [LiteLLM deployment](https://docs.litellm.ai/docs/proxy/docker_quick_start),
[spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking),
[virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys), and
[OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra).
Exact behavior is tested against the pinned image, not inferred from latest docs.
## Phase 2 extension

The optional [MCP deployment guide](mcp/README.md) documents the Phase 2 overlay,
connection administration, SQL policy, immutable dataset versions and recovery.
The Phase 1 instructions above remain authoritative for the model gateway.

## Phase 3 extension

The [Open Data Explorer deployment guide](ingestion/README.md) documents direct
Data.gov discovery, bounded automated imports, notebook attachment, immutable
publication, provenance and interrupted-job recovery. It layers on Phase 2 and
preserves the existing model gateway. See the [Phase 3 report](../../docs/databridge/PHASE_3_REPORT.md)
for fixture acceptance and outstanding live/browser checks.

## Phase 4 extension

The [conversational research guide](research/README.md) enables imported-dataset
discovery in existing notebook chat, explicit SQL review/approval, verified answers,
provenance and synthesis recovery. It preserves all earlier deployment layers.
