# Cross-phase acceptance items

| Item | Status | Completion evidence required |
|---|---|---|
| Live GPT-6 Astra validation through accepted Esperanto → LiteLLM path | Outstanding from Phase 1 | Authorized live account/model, real request, actual provider usage and pricing availability, failure behavior. Synthetic provider regression does not certify live access or billing. |
| Browser end-to-end verification | Outstanding across Phases 1–3 | Real browser checks of Settings usage, connection administration, discovery/approval, schema inspection, query approval, historical evidence and Explorer search/inspect/import/progress/query/provenance. The P3 attempt returned `The browser access host is unavailable`. Component tests/build/real API-worker-MCP acceptance are not browser verification. |
| SQL Server multi-catalog and other DBHub engines | Uncertified | Actual engine instances, independent least-privilege catalog connections, scoped discovery/query and negative permissions tests. Not enabled by this phase's SQL execution path. |
| Human translations of MCP and Explorer UI text | Outstanding | Review translations in all supported locales; key parity is tested with explicit English text for new strings. |
| DB-DATA-01 bounded discovery/import | Implemented and fixture-verified in P3 | Direct v4 catalog integration; CSV/flat JSON/Parquet/single-data-member ZIP; real worker, immutable publication, automatic scoped MCP registration, notebook documentation and provenance. Owner explicitly authorized fixtures because no Data.gov key is configured. See P3 report and evidence. |
| Live Data.gov and real NTD 2022–2025 import | Outstanding live validation | Configure a personal catalog API key; complete the in-app path with the official FTA candidate. Actual export bytes/rows/schema remain unverified. No synthetic transit values may be described as official data. |
| DB-DATA-02 conversational database analysis | Not implemented; discovery interface prepared in P3 | Active-notebook dataset context exists. Still requires real chat-to-discovery-to-approved-query-to-evidence-backed-answer workflow and tests, plus preservation of existing chat behavior. |
| NTD/Census/NOAA cross-source analysis | Deferred, blocked by single-table policy and semantic alignment | Review SQL join/planner authorization, explicit geography crosswalks, time periods, units, reporting populations, Census estimate uncertainty and NOAA quality flags before constructing comparisons. Adapter contracts are documented; no new servers added. |
| Six-database certification roadmap | Retained, not expanded by P3 | SQL Server, PostgreSQL, MySQL, MariaDB, SQLite and Oracle remain the original DBHub targets. Prior PostgreSQL demonstration/SQLite audit and isolated DuckDB evidence do not certify the untested engines. |

The Phase 3 fixture automated gate is distinct from these external/later-phase items.
Do not describe component tests as browser E2E or fixture provider calls as live
GPT-6 Astra validation. Proceed to another implementation phase only after Phase 3
checks pass and the owner authorizes the phase transition. Phase 4 has not begun.
