# ADR-0XX: Immutable DuckDB publication for DataBridge

- **Status**: Accepted for the MVP; application integration remains P2/P3 work
- **Date**: 2026-10
- **Related**: [upstream audit](../../databridge/UPSTREAM_AUDIT.md), design package architecture chapter

## Context

An ingestion worker and an independent MCP query service must not assume they can
write/read one live DuckDB file concurrently. The selected MotherDuck MCP release
also requires SDK 2.x while Open Notebook locks SDK 1.28.1. Both process ownership
and dependency isolation need evidence before app integration.

## Decision

Use one immutable file per dataset version, written to a unique
staging path, committed/checkpointed, closed and validated before publication.
Publish under a unique final name on the same filesystem, then register its opaque
version ID. Existing queries and evidence retain the previous version. Use an
isolated MotherDuck MCP process per approved active version, with read-only access
and no database-switch tool. The application remains on its existing MCP SDK.

The executable experiment is
`scripts/databridge_p0/duckdb_concurrency.py`: four tests pass on Windows and Linux
named-volume storage. They demonstrate both same-file lock conflicts, forty real
MCP reads during a separate version's open write transaction, exact old/new totals,
unchanged old-file checksum, rollback isolation, denied write and MCP restart.

## Alternatives considered

- Shared mutable file plus reader drain: requires distributed leases, bounded
  draining and crash recovery; ephemeral connections alone do not eliminate overlap.
- One trusted writer/query process: possible fallback if version-scoped MCP fails.
- Upgrade MCP in the main application: rejected for P0; the server's dependency
  conflict does not justify changing upstream provider/content dependencies.

## Consequences

Version files simplify reproducible evidence and isolate refresh failure. They
require storage quotas, retention leases, bounded process count and reconciliation
between file publication and SurrealDB registration. The proof's local paths are
trusted test inputs, not an authorization or SQL sandbox. P2/P3 must add the broker,
read-only mounts, external-access restrictions, SQL policy and durable registration.
The Linux proof ran without network access. Container mounts, broker authorization,
timeouts and crash reconciliation still need product-level tests in P2/P3.
