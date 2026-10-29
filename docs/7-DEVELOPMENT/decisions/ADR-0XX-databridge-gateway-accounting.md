# ADR-0XX: DataBridge gateway and usage accounting

- **Status**: Accepted
- **Date**: 2026-10
- **Related**: accepted DataBridge design and Phase 0 audit; DuckDB publication ADR

## Context

DataBridge needs persistent spend and budget controls without replacing
Esperanto, LangGraph, SurrealDB or existing provider configuration. Phase 0 chose
the official MCP SDK for the application and isolated MotherDuck dependencies.

## Decision

Run a pinned LiteLLM proxy with dedicated PostgreSQL in an opt-in Compose stack.
A one-shot administrator provisions a restricted application key without
resetting spend; the app never holds the master key or PostgreSQL credentials.
Register an encrypted upstream Credential and Model after migrations, with the
environment controlling chat defaults and preserving unrelated model settings.
Keep inference through Esperanto and add attribution at its LangChain boundary.
Disable both SDK-client and router retries; do not add fallback models.

Read canonical `/spend/logs/v2` records through the application key. Project only
allowlisted metadata and historical costs; keep missing usage/cost null. Zero
spend is conservatively unpriced. Use the pinned local price map and disclose
metering coverage and asynchronous budget limitations. Do not create a second
ledger. Detailed behavior and evidence: [Phase 1 report](../../databridge/PHASE_1_REPORT.md).

## Alternatives considered

- Raw OpenAI graph calls would bypass upstream model management.
- A master key in application runtime would unnecessarily grant administration.
- A SurrealDB cost ledger would require reconciliation and risk double counting.
- A memory-only gateway would lose spend/budget state after restart.

## Consequences

Existing provider/document workflows remain available. Only gateway language
usage is metered; embeddings, speech and tools are not mislabeled as total AI
spend. Budgets are estimated asynchronous limits, so in-flight calls can exceed
them and unpriced calls cannot be cost-limited. The UI states these limits.
Prompt/response storage is disabled, but operator error diagnostics remain
sensitive. This introduces no MCP connectors or changes to the DuckDB decision.
