# Phase 1 — runtime and LLM plumbing

Date: 2026-10-29. Branch: `feature/databridge-mvp`. Inputs: accepted design package,
`UPSTREAM_AUDIT.md`, `PHASE_0_REPORT.md`, and the accepted DuckDB publication ADR.
Phase 0 commits `301e715` and `42f0db7` remain intact. Phase 2 was not started.

## Implemented

- `compose.databridge.yml`: opt-in source-built Open Notebook, pinned LiteLLM
  1.106.6 and PostgreSQL 17, pinned SurrealDB 2.6.4, durable named volumes, health
  dependencies, loopback application ports and internal database networks.
- `deployment/databridge/`: environment template, JSON/YAML-compatible proxy
  configuration renderer, restricted-key initializer and operator runbook. The
  app has no master key, provider key or PostgreSQL credentials. Initializer
  updates preserve spend; the running app uses only its own virtual key.
- `open_notebook/databridge/`: validated deployment settings, idempotent encrypted
  credential/model registration, environment-managed chat default, request
  correlation and a read-only projection of canonical LiteLLM spend records.
- `api/main.py`, `api/routers/databridge.py`, `api/routers/chat.py` and
  `open_notebook/ai/provision.py`: startup registration and protected usage API;
  notebook/session/trace/task correlation through the existing Esperanto and
  LangGraph path. Existing direct models, workflows and databases are preserved.
- Settings usage panel, shared API/query hook and all 14 locale dictionaries:
  UTC period filters, pagination, model identity, token categories, unavailable
  costs, lifetime budget and useful failure states. English text is supplied for
  the new keys in non-English locales pending translation.
- Explicit official MCP SDK 1.28.1 `databridge` extra and lock metadata. No
  application MCP adapter is introduced ahead of Phase 2. MotherDuck remains
  isolated in the accepted Phase 0 environment. No application dependency on
  LiteLLM or MotherDuck was added.
- Meaningful unit/component/acceptance tests, CHANGELOG entry, deployment docs
  and `ADR-0XX-databridge-gateway-accounting.md`. The existing smoke runner gained
  optional password support, preserving its default behavior.

## Validation

The exact repeatable acceptance commands are in
[`scripts/databridge_p1/README.md`](../../scripts/databridge_p1/README.md).
Assertions and runtime facts are retained in
[`evidence/phase1-acceptance.json`](evidence/phase1-acceptance.json).

| Check | Result |
|---|---|
| Full source-built app + real LiteLLM/PostgreSQL/SurrealDB: seed | 17 assertions passed |
| Stop/start database, gateway and application; rerun key provisioning | 5 assertions passed |
| Environment alias/target change to unknown-priced model | 4 assertions passed |
| Existing notebook/text/upload/context/session smoke with actual worker | 7 checks passed |
| Backend `pytest tests/ -q` in isolated Linux runner | 1,017 passed, 2 dependency deprecation warnings |
| Frontend `npm run test:coverage` | 187 passed across 36 files |
| Frontend `npm run lint` | 0 errors; same 7 upstream warnings |
| Frontend `npm run build` | Passed |
| Source deployment `docker compose … build open-notebook` | Passed; full API/worker/frontend booted |
| Tracked Python `ruff check`, `ruff format --check`, mypy | All 168 files passed |
| `git diff --check` | Passed |
| Built frontend `/` and `/settings` HTTP checks | Both 200 |
| Master key in app/proxy logs and frontend static bundle | Not found |
| Admin/provider/PostgreSQL secrets in app environment | Absent |

Regression commands actually executed, from the repository root unless stated:

```powershell
docker run --rm --cpus 2 --memory 2g -v "${PWD}:/workspace" -w /workspace databridge-p0-baseline:local /app/.venv/bin/python -m pytest tests/ -q
$trackedPython = @(git ls-files '*.py')
uv run --no-sync ruff check $trackedPython
uv run --no-sync ruff format --check $trackedPython
uv run --no-sync python -m mypy $trackedPython
git diff --cached --check
# In frontend/:
npm run lint
npm run test:coverage
npm run build
```

The final acceptance uses `provider.compose.yml` with the **full source-built
upstream combined image**, not only the faster API-only developer overlay.
Provider-attempt counting verifies a failing call is attempted exactly once.
The app maps LiteLLM's budget denial (HTTP 422 in this release) to an actionable
chat error (429), while usage remains readable. Subsequent key requests remain
denied after PostgreSQL and proxy restart. Spend is not reset by the initializer.

The deterministic HTTP provider reports 100 input, 20 output, 10 cached input
and 5 reasoning tokens. The real gateway stores these, notebook/session/trace
attribution and estimated spend; the reviewed fixture rates produce $0.00131
per successful Astra call (including the bundled cache rate). An unknown model
still stores tokens but returns null cost / `unpriced`, never a fake free call.
Old records retain their original model alias after changing the environment.
Failed chat questions are removed from LangGraph checkpoints as upstream intends.

The 17 new backend cases test disabled behavior, URL configuration, encryption
serialization/default preservation, correlation isolation, unavailable pricing,
token categories, budget classification, scoped/deduplicated reads and sanitized
errors. Six frontend tests cover the initial usage panel. Existing regression
suites remained green. No paid provider requests were made.

## Decisions and deviations

See the gateway/accounting ADR for reasoning. The design's prose is implemented
against the pinned upstream interfaces rather than copying its illustrative code.

- Use a separate opt-in Compose file so existing deployments are not replaced.
  Keep the upstream combined image and worker startup behavior. Existing root
  Dockerfile base-image tags remain upstream-managed; newly introduced service
  images are pinned by digest. Builds use the frozen lock.
- One-shot administration and a restricted runtime key avoid placing the proxy
  master key in application runtime. Usage uses the official scoped log API,
  with no new application PostgreSQL access and no duplicate SurrealDB ledger.
- No new schema migration is needed: existing credential/model/default records
  support registration. Explicit unrelated language defaults and embedding/speech
  settings are preserved; only chat and already-managed/empty language defaults
  are deployment-managed.
- Price map is the pinned image's bundled map; per-record available rates are
  projected from historical metadata. Zero-cost records are conservatively
  treated as unavailable, including genuinely free calls.
- Unsupported sampling arguments are dropped by LiteLLM after the initial Astra
  test exposed Esperanto's `top_p` incompatibility. No model fallback is added.
  Both constructed SDK clients and router retries are explicitly disabled;
  setting only the LangChain field was insufficient and was fixed before exit.
- The initial UI is in Settings. Session headers, charts, exports, budget admin
  UI and retention policy UI remain later-phase work, consistent with the Phase
  1 “initial read model” scope. Environment/operator configuration controls caps.
- `uv add --optional databridge mcp==1.28.1 --no-sync` retained package versions;
  host uv 0.8.3 rewrote lock-format/platform metadata. Full build also verified
  this lock with uv 0.13.6. Runtime MCP 1.28.1 and Esperanto 2.28.0 were inspected.

## Limitations and external validation

- **Mocked:** only the external OpenAI-compatible provider. The proxy, databases,
  application adapter, graphs, worker, persistence and budget checks are real.
  GPT-6 Astra live account access, provider billing, streaming, embeddings and
  podcast provider calls were not certified by these tests.
- **Budgets are estimated, asynchronous limits**, not prepaid reservations.
  Concurrent/in-flight calls can overshoot. Unknown pricing cannot enforce a
  monetary ceiling. The UI and runbook state this. Logging can lag by tens of
  seconds; tests poll for durable records before restarting services.
- **Coverage is gateway language usage**, not total AI cost. Direct provider,
  embedding/speech and tool calls are excluded. Notebook chat has full available
  attribution; background command IDs and user/tenant identity are not invented.
  Missing usage categories remain null.
- **Browser automation host unavailable:** opening the isolated app through the
  browser tool failed with “The browser access host is unavailable”. Component
  tests, locale parity, production build and HTTP routes passed; no visual/browser
  interaction verification or screenshots are claimed.
- Native Windows OpenSSL remains the accepted Phase 0 environment issue; backend
  tests ran successfully in Linux. The untracked owner-supplied `design/` package
  remains untouched and retains its previously recorded lint/type errors. Tracked
  implementation source passes all checks.
- Existing single-password auth is retained, not upgraded to multi-tenant auth.
  The Compose egress network preserves ordinary upstream document/provider
  access; it is not an outbound allowlist firewall. No new MCP/database targets
  or public deployment were introduced. Provider diagnostics in canonical error
  records should be treated as sensitive despite disabled prompt/response logs.

Phase 1's automated acceptance gate is satisfied with the documented fixture
provider. Live account and visual verification remain external validation items.
The next implementation phase is Phase 2; it has not begun.

After collecting evidence, only the disposable `databridge-p1-test` containers,
networks and named volumes were removed. The project, user design package and
existing user data were not deleted. Build images remain cached for reproduction.
