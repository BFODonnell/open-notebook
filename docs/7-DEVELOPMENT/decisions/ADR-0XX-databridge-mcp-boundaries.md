# ADR-0XX: DataBridge MCP trust boundaries and query approvals

- **Status**: Implemented for Phase 2; owner acceptance pending
- **Date**: 2026-10-29
- **Related**: [accepted immutable publication decision](ADR-0XX-databridge-duckdb-publication.md), [Phase 2 report](../../databridge/PHASE_2_REPORT.md)

## Context

The accepted architecture isolates MotherDuck's SDK 2.x dependencies from the
application's official MCP SDK 1.28.1. Server read-only flags alone do not restrict
external reads, catalog access, tool changes, or resource use. Upstream has one
shared application password, not tenant identities.

## Decision

Keep registry, encrypted bearer credentials, one-use approvals and query evidence
in upstream SurrealDB. A separate operator key controls connection changes and
capability approval. Browser clients select operator-configured endpoint references,
never arbitrary network destinations or process commands. Notebook scopes restrict
connections within the existing single-user trust boundary.

Use fresh official-SDK sessions and rediscover/fingerprint server tools on each
operation. DBHub SQL passes a conservative SQLGlot AST allowlist; Toolbox exposes
only administrator-approved, typed, fixed prepared statements. Require reviewed
database grants and database timeouts as independent controls. Bound application
concurrency, deadlines, wire bytes and result snapshots. No automatic query retry.

The internal DuckDB broker owns at most two active isolated MotherDuck subprocesses,
one per query against its explicitly selected immutable version. Each process exits
after the query or cancellation. This implements the accepted version-scoped process
decision without pooling or shared mutable connections. Disable external access and
extension loading, lock settings, mount published files read-only, and expose no
database-switch capability. Staging publication is serialized, quota-bound and
no-overwrite; manifest completion precedes durable registration.

## Alternatives considered

Upgrading the application's MCP dependencies, trusting server read-only hints,
accepting browser-supplied DSNs/URLs, and exposing raw Toolbox on the application
network were rejected. A bounded process pool can reduce cold starts later but
would require eviction/lease recovery. This phase deliberately uses process teardown.

## Consequences

Cold-start latency and a small SQL subset buy an auditable boundary. Connections
must be reapproved after configuration or capability changes. SQL Server and other
DBHub engines need separate certification. Full tenant authorization, ingestion,
automatic retention and conversational planning remain later-phase work. Completed
manifest retries repair registry interruption; incomplete publication files remain
unqueryable and count against quota until reviewed operator cleanup.
