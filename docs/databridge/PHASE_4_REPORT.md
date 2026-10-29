# Phase 4: conversational database research / DB-DATA-02

Date: 2026-10-29. Branch: `feature/databridge-mvp`. Builds on accepted P3 `5df3e12`,
P0 audit/publication architecture, P1 gateway and P2 MCP authorization decisions.
The approved design package and owner's untracked `design/` remain unchanged.
**Phase 5 has not begun.**

Follow-up: after this fixture report, the owner configured a Data.gov key and the
official FTA NTD CSV passed live API/worker/MCP import and restart validation.
See [live report](LIVE_NTD_VALIDATION.md). Historical fixture results below remain
unchanged; no live GPT-6 Astra or browser claim is added.

## Outcome and scope

The bounded DB-DATA-02 workflow is implemented in existing notebook chat:

**Search -> inspect/import -> open the existing notebook chat -> ask -> review and
approve canonical SQL -> execute through MCP -> receive a verified answer.**

The Phase 4 automated fixture gate passes **64 checks**. Data.gov/publisher and
model responses are deterministic fixtures. LangGraph, Esperanto, LiteLLM, its
PostgreSQL ledger, SurrealDB, background worker, HTTPS acquisition, parser,
immutable publication, official MCP SDK and isolated MotherDuck execution are real.
Tests invoke application APIs corresponding to the UI, not manual file ingestion
or external registration. This is API/worker/MCP acceptance plus component tests,
**not browser E2E, live model certification or official DOT analysis**.

The owner now has a Data.gov key. Its supported location is the ignored root
`.env.databridge` as `DATAGOV_API_KEY`; it has not been used for this acceptance.
The fixture's official-host DNS mappings/test CA must never receive that key.

## Implementation

- `open_notebook/graphs/database_research.py` and `prompts/databridge/`: async
  LangGraph plan/synthesis nodes, bounded validated JSON, ordinary Esperanto model
  provisioning and LiteLLM task/session/notebook usage correlation. No tool binding,
  independent model client, new framework or Python dependency.
- `open_notebook/databridge/research.py` and `research_models.py`: current notebook
  authority/version context, server-loaded document excerpts, canonical P2 planning,
  explicit approval, evidence validation, deterministic answers/trends, durable
  state and interrupted-state reconciliation.
- Existing chat router/graph: discover datasets on each question and store stable
  research messages in the original SqliteSaver history. Ordinary document/general
  chat and source chat preserve their existing pathways.
- Research router, migration 28 and explicit migration list: scoped
  get/review/execute/resume endpoints and durable records. No approval bearer is
  persisted in a research record or chat checkpoint.
- Frontend `ResearchTurn`, existing `ChatPanel`, API/types/query keys and all 14
  locale dictionaries: SQL/version, fresh review, explicit approval, progress/errors,
  evidence inspection, bounded trend and synthesis-only recovery. Tokens remain
  in component memory, not query cache or local storage.
- `compose.databridge-research.yml`: opt-in flag, default disabled. P3 context
  reports conversational availability according to this flag. Its acceptance
  assertion honors the flag while retaining standalone disabled behavior.

Imports are available in the same pre-existing chat without registration or reload.
Data records remain in DuckDB. Notebook schema documentation and selected document
excerpts remain a separate evidence class.

## Evidence and security

The synthetic four-year dataset produces **700 total boardings**, annual totals
100/150/200/250 and a deterministic 2022-to-2025 change of **150**. Answers identify
the dataset, immutable version, executed SQL, plan, evidence and result/database
SHA-256. A selected document identifies boardings as distinct from unique people;
a forged client excerpt is ignored. Actual sanitized IDs/hashes/rows are in
[query evidence](evidence/phase4-query-evidence.json).

The model never executes SQL. P2 SQLGlot, table/column scopes, one-use approval,
capability rediscovery, immutable version/hash checks, timeouts and result bounds
remain authoritative. No general joins, file access, writes, network destinations,
Trino or additional servers were introduced. Unsafe SQL, foreign datasets, joins,
incompatible units, missing denominators and causal requests are rejected in
acceptance. Empty results explicitly report insufficient evidence. Invented values
fail exact cell/type/hash checks; quotes must match a server-read notebook snapshot.

Wrong session/notebook access, expired/invalid/replayed approvals, changed datasets
and revoked connections are denied. A stopped real broker produces failed P2
evidence and no findings. Synthesis failure preserves successful evidence; retry
does not rerun SQL. Planning outages preserve existing chat history. The
post-MCP/pre-turn-write crash boundary recovers a unique result with an atomic
claim; concurrent recovery cannot overwrite active synthesis. Full stack stop/start
preserves answers, versions, hashes, chat messages and token/cost records.

## Executed verification

Reproduction: [P4 runner](../../scripts/databridge_p4/README.md), with existing
P1/P2/P3 runners applied to `databridge-p4-test`. Per-check lists are in
[acceptance evidence](evidence/phase4-acceptance.json).

| Check | Result |
|---|---|
| P4 search/import/chat/query/evidence seed | 48 passed |
| P4 real broker outage/recovery | 3 + 1 passed |
| P4 provider/permission/interrupted-state recovery | 6 passed |
| P4 full-stack restart | 6 passed |
| Full backend, DataBridge dependencies | 1,248 passed; 2 existing deprecation warnings |
| Base backend without optional dependencies | 1,098 passed, 23 skipped; 2 existing warnings |
| Frontend coverage suite | 205 passed, 40 files |
| Ruff / formatting / mypy | Passed, 200 tracked Python files |
| Frontend lint / production build | Passed; 0 errors, 7 existing lint warnings |
| Source-built Docker image | Passed |
| Final rebuilt-image recovery recheck | 6 passed |
| P3 real acquisition/worker/recovery/restart | 71 passed |
| P2 real MCP seed/outage/drift/restart | 75 passed |
| Native MotherDuck engine/child defenses | 6 passed |
| PostgreSQL role/write/column/catalog denials | 4 expected failures, all denied |
| P1 accounting/budget/restart/unpriced | 26 passed |
| Existing real-worker smoke | 7 passed |
| Browser | Blocked: connector unavailable; native URL-policy check stopped automation |
| Live Data.gov/NTD and GPT-6 Astra | Not executed |

Initial integration found a protected SurrealQL `$session` binding; it now uses
`$chat_session`. Regression found unwanted null fields in ordinary chat responses;
optional research IDs are omitted when absent, preserving existing API shapes.
A test-helper async generator bug was fixed before acceptance passed. Final review
also added a variable-length Markdown code fence so backticks inside a SQL literal
cannot terminate the rendered query block. Its negative security test passes.
No failing fixture check is waived.

## Decisions, limits and next steps

The [research ADR](../7-DEVELOPMENT/decisions/ADR-0XX-databridge-conversational-research.md)
records async subgraph/legacy checkpoint integration and bounded answer rendering.
Exact evidence-backed output is narrower than arbitrary freeform synthesis. A valid
result does not prove semantically correct SQL: review must inspect filters,
definitions, grain and denominators. Live-model competence remains unvalidated.
Fixture refusal tests verify orchestration, not a guarantee that every live model
will classify every unsupported natural-language request correctly.

Context limits: 20 imports / 80 KiB, five 3,000-character document excerpts, six
recent messages, 5,000-character questions, 30 result cells and two quotes. Oversized
context fails closed. Trends reject duplicate/invalid years, missing/nonfinite
values and possibly truncated results. Missing years are not zero. Evidence, quotes
and SQL are protected application data; retention remains manual. Shared-password
authorization is not multi-tenant security. Non-gateway Esperanto calls retain
existing accounting limitations. New UI strings await human translation.

The [NTD/Census/NOAA preparation note](NTD_CROSS_SOURCE_PREPARATION.md) compares
reviewed materialization with a possible narrow join extension. It specifies
geography keys/crosswalk/vintage, time support, units, cardinality, denominators
and NOAA quality/coverage checks. PEP remains preferred; no silent ACS substitution.
No materialization/join executor was enabled, and no synthetic comparison is
presented as a real DOT finding. The six-engine certification roadmap is intact.

**DB-DATA-01** remains accepted bounded fixture-tested acquisition. **DB-DATA-02**
now has the implemented, fixture-tested conversational approval/execution/verified
answer path. Live Data.gov/NTD, GPT-6 Astra, browser, translations and remaining
engine certification stay on the [tracker](ACCEPTANCE_TRACKER.md). Complete those
gates when environments are available and obtain owner authorization before
beginning another phase.

After collecting evidence, only the disposable `databridge-p4-test` containers,
networks and volumes were removed. User configuration, project files and the
untracked design package were preserved; build images remain cached.
