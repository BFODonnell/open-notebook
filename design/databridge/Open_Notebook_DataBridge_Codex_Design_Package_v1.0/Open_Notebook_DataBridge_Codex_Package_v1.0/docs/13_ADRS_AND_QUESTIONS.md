# 13 — Architecture Decision Records and Investigations

## Approved decisions (ADRs)

| ADR | Decision | Rationale / consequence |
|---|---|---|
| ADR-001 | Fork/extend upstream Open Notebook | Reuse mature notebook/chat/data/source layers; follow upstream `AGENTS.md` conventions. |
| ADR-002 | DuckDB default local analytical engine | Fast columnar analytics and no server required for imported public files; requires careful concurrency and sandbox handling. |
| ADR-003 | Data.gov v4 direct API + server-side importer first | Reliable in-app acquisition; Data.gov is metadata catalog and resources live at publisher. FastMCP ingestion tools stretch only. |
| ADR-004 | DBHub + local DuckDB MCP + Google MCP Toolbox | Broad relational and cloud/database reach without implementing engines from scratch; curated tool exposure. |
| ADR-005 | LiteLLM Proxy + dedicated PostgreSQL | OpenAI-compatible model routing, persistent model spend and budgets; keep upstream Esperanto abstraction. |
| ADR-006 | Model default and provider config from `.env` | Reproducible deployment; GPT-6 Astra initial default; no manual model selection required after setup. |
| ADR-007 | Dataset/version + immutable query provenance | Reproducibility and explainability; don't silently rewrite past evidence. |
| ADR-008 | Admin-approved read-only tools/query execution | MCP and LLM are untrusted orchestration surfaces; bounded SQL, least privilege and approval. |
| ADR-009 | Trino/other MCP servers deferred | Minimize MVP integration complexity; preserve extension point. |
| ADR-010 | Synthetic offline demo fixtures + live public endpoints | Demo reliability and no need for sensitive DOT systems; fixtures must be explicitly labeled. |

## Implementation investigations to resolve in P0

1. **DuckDB reader/writer synchronization:** use versioned staged files or coordinated reader drain; verify real MCP server behavior, mounts and safe re-opening.
2. **Open Notebook model bootstrap:** determine exact Esperanto/provider registration path; preserve UI model settings and default-from-env semantics without corrupting stored settings.
3. **LiteLLM Responses/chat parameter compatibility:** does pinned LiteLLM version proxy `gpt-6-astra` and OpenAI-compatible alternate endpoints correctly? Confirm request/usage metadata.
4. **FastMCP vs official MCP Python SDK:** small comparative POC for authenticated multi-server client + transport; use only if advantage measurable. Do not confuse the FastMCP library with the separate `MCPServer` class naming in SDK v2.
5. **DBHub, Google Toolbox, DuckDB MCP images:** verify actual release/tag/digest, commands, network paths, health checks, CLI flags, read-only configuration. Do not invent working config semantics.
6. **Data.gov search metadata identification:** use `results[].identifier` and cached `dcat`, optional harvest record link; don't assume a `/datasets/{id}` external endpoint.
7. **Data.gov external publisher source rate/size limits:** decide default max size, timeout, API rate handling and source-level policy on real NTD file.
8. **Census population denominator crosswalk:** establish consistent PEP vintage and correct urban/service-area geography; otherwise restrict comparisons.
9. **NOAA weather alignment:** choose stations/county/metro aggregation with completeness thresholds and noncausal language.
10. **Upstream authentication scope:** identify single-user v. multi-user behavior and reduce MVP claims accordingly.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Invalid denominator/geography joins in demo | High | Crosswalk validation and caveats; fall back to separate trends |
| DuckDB file lock prevents one-click import | High | P0 concurrency POC; versioned files or coordinated read drain |
| Insecure arbitrary source fetch / MCP request | Critical | Shared SSRF policy, allowlist and network egress isolation |
| LiteLLM spend dashboard not accurate | High | PostgreSQL-backed spend logs and pricing-status flags |
| Upstream model/provider breakage | High | Existing Esperanto provider path and regression tests |
| Upstream/third-party APIs change | Medium | Pin versions and use typed adapters and fixtures |
| Demo data unexpectedly unavailable | Medium | Offline fixture integrated through same pipeline |
| Too much scope for hackathon | High | Strict phase gates; defer extra servers, Trino, automation |

## Future considerations (record only)

Trino federated SQL, MCP Alchemy (SQLAlchemy fallback), vendor-specialized MCPs (Teradata, AWS Redshift/DynamoDB/DocumentDB/Neptune, IBM i/Db2, ClickHouse, MongoDB, Neo4j, Snowflake, Databricks), automatic incremental refresh, wider data portals, geospatial enrichment, production identity/governance.
