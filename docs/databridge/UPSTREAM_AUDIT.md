# DataBridge Phase 0 upstream audit

Audit date: 2026-10-29. Status: **Phase 0 gate passed on Linux/Docker**; see
[PHASE_0_REPORT.md](PHASE_0_REPORT.md) for executed checks and blockers.

## Baseline and scope

- Baseline: `a0f6f3081ae06328f0a451b3a3ef2959ca25721d`, Open Notebook 1.15.0.
- Origin: `https://github.com/BFODonnell/open-notebook.git`; upstream design target:
  `https://github.com/lfnovo/open-notebook`. The checked-out SHA is the integration
  baseline; no claim that it equals current upstream HEAD.
- Started on `main`; created `feature/databridge-mvp` without moving existing work.
- Initial working tree: only `?? design/`. The supplied package remains untouched.
- Actual package location:
  `design/databridge/Open_Notebook_DataBridge_Codex_Design_Package_v1.0/Open_Notebook_DataBridge_Codex_Package_v1.0/`.
  There was no `design/databridge/CODEX_START_HERE.md` at the requested location.
- Read root/backend/API/frontend rules, architecture, credentials, content
  processing, change playbooks, code standards, testing and all 14 design chapters.

## Confirmed integration map

| Concern | Actual code and integration consequence |
|---|---|
| API | `api/main.py` registers routers under `/api`, installs password/body-size/CORS middleware and runs migrations at startup. Add routers here; do not create a second app. |
| Credentials | `open_notebook/domain/credential.py`: `Credential.to_esperanto_config()`; `api/credentials_service.py` and `api/routers/credentials.py` handle registration/discovery. Preserve encrypted credential records and metadata-only responses. |
| Model path | `open_notebook/ai/models.py`: `ModelManager.get_model()` resolves the linked credential and calls Esperanto `AIFactory`; `open_notebook/ai/provision.py` supplies LangChain models to graphs. `openai_compatible` already exists. |
| Defaults | `DefaultModels` in `open_notebook/ai/models.py`, freshly fetched each time. Chat, transformation, tools, large-context, embedding and speech defaults are distinct. P1 must use a managed credential/model and idempotent bootstrap after migrations; keep embedding/speech settings intact. |
| Notebook/source | `open_notebook/domain/notebook.py`: `Notebook`, `Source`, `Note`, `ChatSession`. Source-to-notebook edge is `reference`, note edge `artifact`, chat edge `refers_to`. `Source.save()` does not embed; `vectorize()` explicitly submits work. Store dataset descriptions/schema summaries, not table rows as document text. |
| Background work | `api/command_service.py` wraps `surreal_commands.submit_command`; commands use `@command(..., app="open_notebook")` and are imported in `commands/__init__.py`. `commands/source_commands.py` demonstrates progress and retry semantics. Submission itself is synchronous upstream; reuse the wrapper rather than assuming an awaitable submission API. |
| Persistence | Async `repo_*` functions in `open_notebook/database/repository.py`; migrations 1–25 are explicitly listed in `async_migrate.py`. Next schema change needs up/down files and registration, not a P0 migration. |
| Chat | `open_notebook/graphs/chat.py`, `source_chat.py`: existing synchronous SqliteSaver workaround. `open_notebook/config.py` owns `data/sqlite-db/checkpoints.sqlite`. Keep chat history and existing endpoints. New graph nodes must remain async. |
| UI | `frontend/src/lib/api/client.ts` is the shared axios client; `src/lib/hooks/` uses TanStack Query, cache invalidation and toasts. Respect auth storage, runtime API URL, i18n in all locales and design tokens. No `npm run typecheck` exists; build performs type checking. |
| Tests | Flat `tests/`, mocked DB/provider access; `tests/conftest.py` clears app password and loads `.env`. Frontend Vitest tests are colocated. Unit success is not live notebook/worker certification. |
| Containers | `Dockerfile` builds frontend with Node 22, backend/runtime with Python 3.12 slim-trixie. `runtime` is default; `single` adds SurrealDB. `supervisord.conf` runs `api.main:app`, worker `--import-modules commands`, and standalone UI on 8502. Dev UI is 3000; API 5055; SurrealDB 8000. |
| Compose | `docker-compose.yml` uses `lfnovo/open_notebook:v1-latest` and `surrealdb/surrealdb:v2`, bind mounts `notebook_data` and `surreal_data`, no build section or health gates. `docker compose up --build` alone does not build this fork. P1 needs an explicit build override and isolated internal services. The P0 source-verification Compose boots API, worker, SurrealDB and built UI independently of user data. |

## Compatibility matrix

| Component | Checked baseline / observation | Decision |
|---|---|---|
| Python | Constraint `>=3.11,<3.13`; host 3.12.11; Docker targets 3.12 | Use 3.12; do not raise upstream runtime floor casually. |
| uv | Host 0.8.3 | Frozen upstream sync succeeded after using system trust; pin build tool instead of `latest` in future deployment. |
| Node/npm | Host 24.13.0 / 11.6.2; Docker Node 22 | Host frontend checks passed; container build remains a separate gate. |
| FastAPI/Pydantic | 0.136.3 / 2.12.5 in `uv.lock` | Preserve. |
| Esperanto/LangChain/LangGraph | 2.28.0 / 1.3.9 / 1.2.5 | Extend existing provider/graph path. |
| Surreal client/commands | 1.0.8 / 1.3.1 | Preserve queue and migration conventions. |
| HTTPX/AnyIO | 0.28.1 / 4.14.2 | Existing async transport libraries suffice initially. |
| MCP/FastMCP | 1.28.1 / 3.2.0 already transitively locked | Use SDK 1.28.1 as initial app-client candidate. Declare directly in P2 if imported by app. |
| Next/React/TypeScript/Vitest | 16.3.8 / 19.3.0 / 5.8.3 / 4.1.9 in npm lock | Preserve npm lock. |
| DuckDB | Latest registry metadata showed 2.0.0; MotherDuck MCP 1.1.0 explicitly requires 1.5.6 | Pin importer/spike to 1.5.6 for parity with selected server, not the latest engine. |
| MotherDuck MCP | 1.1.0 requires FastMCP >=4.0.11, hence MCP >=2 | Resolver **proved unsatisfiable** alongside app MCP 1.28.1. Use an isolated service/environment, not an in-process upgrade. |
| SQLGlot | Not added in P0 | Pin/test dialect AST policy in P2; it is not a security boundary alone. |
| LiteLLM | Release API returned v1.106.6 | Candidate only, no tested image/config/model call. Dedicated PostgreSQL and application virtual key remain mandatory. |

The spike has independent `scripts/databridge_p0/pyproject.toml` and
`motherduck/pyproject.toml` environments with their own uv locks. Root `pyproject.toml`,
`uv.lock`, npm lock and application behavior are unchanged.

## Image and transport verification

Verified Linux amd64 images. All three below subsequently booted; DBHub and Toolbox
were exercised through real Streamable HTTP against synthetic SQLite. Other engines
remain untested:

| Image | Registry digest |
|---|---|
| `surrealdb/surrealdb:v2.6.4` | `sha256:0f36bc8972e172e4768db8e32507cd22c4db8f47cbcee0ae5753cc6db00b96b4` |
| `bytebase/dbhub:1.5.0` | `sha256:aa04093100a15911c7ee326e870fa11480e1466342e8433fdd67b45c9af52ccf` |
| `us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:1.15.0` | `sha256:7e4f7bfd93ccec33c066563a4ca700572e4ce95a8d45ba18577df8ee50b9481a` |

Verified source references:

- [MotherDuck 1.1.0 CLI](https://github.com/motherduckdb/mcp-server-motherduck/blob/v1.1.0/src/mcp_server_motherduck/__init__.py): stdio default, `--transport http`, read-only default, `--no-ephemeral-connections`, `--max-rows`, `--max-chars`, `--query-timeout`; database switching requires an explicit flag. Its Python package has **no `__main__`**; use console entry point or `from mcp_server_motherduck import main; main()`.
- [DBHub 1.5.0 example](https://github.com/bytebase/dbhub/blob/v1.5.0/dbhub.toml.example): `[[sources]]` with `id`/`dsn`; `[[tools]]` with `name`, `source`, `readonly`, `max_rows`. The design's conceptual `readOnly` is not the TOML key. Source `query_timeout` excludes SQLite according to comments. Database grants and app policy are still needed.
- [Toolbox 1.15.0 README](https://github.com/googleapis/mcp-toolbox/blob/v1.15.0/README.md): actual image repository above. Tested flat multi-document YAML (`kind: source`, `type: sqlite`; `kind: tool`, `type: sqlite-sql`), `--config`, `--address`, `--disable-reload`, `--disable-version-check` and `/mcp`. Container is non-root: synthetic fixture directory must be traversable. `file:...?mode=ro` and read-only mount used. No Toolbox identity/OAuth certification is implied.
- [MotherDuck package metadata](https://pypi.org/pypi/mcp-server-motherduck/1.1.0/json) establishes its DuckDB and FastMCP requirements.

`scripts/databridge_p0/mcp_transports.py` verifies two independent DBHub endpoints:
missing/invalid bearer returns 401, both clients discover tools and return exact
SUM=6, DELETE returns `READONLY_VIOLATION`, and three rows truncate to two.
Toolbox exposes exactly one fixed SELECT tool, returns SUM=6 and rejects an unknown
arbitrary SQL tool. DBHub health is `/healthz`; HTTP bearer uses `DBHUB_AUTH_TOKEN`
and host allowlisting uses `DBHUB_ALLOWED_HOSTS`. DBHub's read-only policy still
allows some PRAGMA statements, so P2 must enforce the stricter design policy.

**Client decision:** official MCP SDK 1.28.1. Both clients passed authenticated
two-server discovery/query. The equivalent checked wrappers are 17 lines (SDK) and
15 (FastMCP 3.2.0), with the same per-server scopes. Two lines saved do not remove
registry, capability checking or policy work. No substantive maintenance advantage
was demonstrated. FastMCP 4.1.4/MCP 2.3.0 stays confined to the MotherDuck process.

## Risks and deviations requiring gates

1. **Single-user authorization**: `api/auth.py` is a shared password boundary, not
   admin/analyst/viewer identities or tenant ownership. Do not claim SEC-04/IDOR
   isolation without identity work; deployment must remain within approved scope.
2. **SSRF**: upstream `validate_url()` intentionally permits private addresses for
   local model endpoints. Downloads require a separate strict public-egress policy;
   changing the shared validator would break self-hosted providers.
3. **DuckDB**: immutable version files selected after four contention tests passed
   on Windows and Linux named-volume storage, including real MCP queries/restart.
   New files close/checkpoint before publication; readers retain old version IDs.
   No LLM-supplied path or switch tool. Publication registry, failure recovery,
   retention and read-only mounts remain application work.
4. **Native runtime**: Windows API import terminates with
   `OPENSSL_Uplink(...): no OPENSSL_Applink`, before pytest collection. Process-local
   certificate, OpenSSL config and PATH experiments did not reliably fix it. Linux
   passes 1,000 backend tests and real source/worker smoke. Use Linux/Docker for
   backend work; a Windows import workaround is not claimed.
5. **TLS**: inherited `SSL_CERT_FILE` points to Anaconda certifi. Removing it only
   from the command environment and using `uv --native-tls` fixed downloads;
   `NODE_USE_SYSTEM_CA=1` fixed npm installation. No certificate verification disabled.
6. **Mutable upstream deployment**: upstream Docker base tags, uv `latest`, app
   `v1-latest` and SurrealDB `v2` need exact tested pins in the DataBridge override.
7. **Models/costs**: `gpt-6-astra` remains the approved configuration string, not a
   provider availability claim. No credentials or paid model calls were used in P0.
   P1 must verify chat parameters, genuine usage, missing-price behavior and restart
   persistence without replacing Esperanto.
8. **Design artifact checks**: root lint/mypy discover untracked design scripts.
   Keep artifact check results distinct from baseline application checks; do not
   silently rewrite the owner's design package to make CI green.
9. **Frontend rewrite binding**: the tested production build captured
   `http://localhost:5055` in rewrites. Setting `INTERNAL_API_URL` only at runtime
   did not retarget it (HTTP 500). Sharing the API's network namespace restored
   `/api/notebooks` and `/api/config` HTTP 200, matching upstream's combined image.
   Preserve that topology or rebuild with the intended destination in P1.

The P0 runbook pins uv/Python and Node images by digest too. This is a source boot
test using the already verified frontend build, **not** certification of a new
production image or the complete DataBridge stack. LiteLLM/PostgreSQL restart,
budget, usage and model-parameter compatibility remain P1 acceptance work.
