# ADR: notebook research proposals with verified database evidence

Date: 2026-10-29. Status: Phase 4 implementation; controlled synthetic/public scope.

## Decision

Extend existing notebook chat with an asynchronous LangGraph planning/synthesis
subgraph. Discover imported datasets from the Phase 3 notebook context service on
every question. Re-read approved connections, version, allowed columns and catalog
provenance on the server; never accept these authorities from chat context. Keep
the original synchronous SqliteSaver graph as the sole conversation history. An
additional response node records research messages in that same history. Source
chat and ordinary notebook chat retain their existing model node.

Both planning and synthesis use `provision_langchain_model` and Esperanto, honoring
the request/session/default model selection and existing LiteLLM accounting.
The planner returns bounded, validated JSON. It receives no tools, credentials,
network access or executable Python. SQL goes through unchanged Phase 2 SQLGlot
authorization. Review creates a fresh plan; explicit approval submits its one-use
token. Tokens stay out of research records, checkpoints and frontend query caches.

Migration 28 persists research state separately from conversation history. The
record binds the question, notebook/session, selected import/version, full catalog
fingerprint, document excerpts, canonical plan and query evidence. A new import,
connection revision or permission change invalidates pending conversational
approval. Phase 2 independently rechecks the plan, version, capabilities, expiry
and token before execution. Historical answers retain their original version.

The model selects exact result cells and exact quotes from bounded server-loaded
notebook excerpts. The application verifies cell coordinates, types, values,
result digest and query/version binding, then renders the answer. It deterministically
computes a trend only for unique numeric annual results below the truncation limit.
This deliberately narrows freeform prose: verifying a source citation alone cannot
prove that an arbitrary generated analytical claim is supported. This is evidence
validation, not proof that every safe SQL query answers the user's intended question;
the user must inspect the proposed SQL and dataset definition.

## Recovery and limits

Atomic state claims prevent concurrent review/execution/synthesis. Ten-minute
leases allow explicit recovery. A successful MCP run persisted before an interrupted
research write can be reconciled by its unique plan/notebook; SQL is never replayed.
An indeterminate/failed MCP outcome requires a new question or fresh review. Model
failure after execution preserves evidence and allows synthesis-only retry. Stable
message IDs repair interrupted checkpoint writes without duplicate answers.

Limits: 20 datasets / 80 KiB context; question 5,000 characters; five notebook
documents with 3,000-character excerpts; six bounded history messages; 30 selected
result cells and two quotes. Phase 2 query/result/time/file limits remain unchanged.
Raw records remain in DuckDB; document evidence and database evidence are distinct.
Metadata and result strings are escaped before Markdown output.

## Cross-source decision

Keep one-table SQL. General joins, CTEs, external file functions and unrestricted
SQL remain denied. Prefer a future reviewed materialized analytical table over a
new join surface: explicitly version input datasets and a reviewed geography
crosswalk, validate keys/cardinality/coverage/time/units/quality, then publish via
the same immutable interface. No materialization executor is authorized in P4.
See [preparation contract](../../databridge/NTD_CROSS_SOURCE_PREPARATION.md).

## Consequences

No new provider framework, dependencies, MCP servers, network routes or database
engine are introduced. Opt-in deployment preserves existing behavior by default.
Existing shared-password/operator-key security is not multi-tenant authorization.
Evidence snapshots contain selected data and SQL and need normal protected backups
and retention; they are not a signed audit ledger. Human translations, live model
semantic validation, live NTD ingestion and browser acceptance remain separate
gates. Fixtures verify orchestration and known answers, not real model competence.
