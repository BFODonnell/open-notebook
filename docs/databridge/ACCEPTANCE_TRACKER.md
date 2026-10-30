# Cross-phase acceptance items

Updated for Phase 4, 2026-10-29. Earlier acceptance remains limited to each phase's
documented demonstration scope; external gates are not silently waived.

| Item | Status | Completion evidence required |
|---|---|---|
| Live GPT-6 Astra through Esperanto -> LiteLLM | Passed for the bounded OpenRouter scenario, 2026-10-29 | [Live evidence](LIVE_OPENROUTER_VALIDATION.md): real source chat, count-query planning, approved MCP execution and verified synthesis, tokens/estimated costs and restart persistence. Arbitrary questions, every pricing tier and live outage behavior are not certified; prior controlled failure tests remain applicable. |
| Browser end-to-end verification | Outstanding across P1-P4 | Usage, connection administration/discovery/schema/approval/evidence and full Explorer -> import -> chat -> review/approve -> verified answer. P4 browser connector returned `The browser access host is unavailable`. Native Chrome fallback stopped because it could not determine the current URL confidently enough to enforce policy. No browser acceptance is claimed. |
| SQL Server multi-catalog and other DBHub engines | Uncertified | Real engines, independent least-privilege catalog connections, scoped discovery/query and negative permissions tests. Not enabled by the current SQL execution path. |
| Human translations of MCP, Explorer and research UI | Outstanding | Review all 14 locales. Key parity is tested; new strings currently have explicit English text. |
| DB-DATA-01 bounded discovery/import | Implemented; fixture-verified in P3 and regressed in P4 | Direct v4 catalog integration; CSV/flat JSON/Parquet/single-data-member ZIP; real worker, immutable publication, automatic scoped registration, notebook documentation and provenance. Live acceptance is separate. |
| Live Data.gov and real NTD 2022-2025 import | Passed for the official FTA service CSV via API/worker/MCP, 2026-10-29 | [Live evidence](LIVE_NTD_VALIDATION.md): 19,906,329 bytes, 51,716 rows, 69 columns, years 2022-2025; real worker/publication/notebook association, authorized MCP row counts and restart persistence. Browser and live-model gates remain separate. Comma-formatted measures need reviewed normalization before numerical analysis. |
| DB-DATA-02 bounded conversational research | Implemented and fixture-verified in P4 | Existing chat discovers imports, uses Esperanto/LiteLLM planning, P2 SQL review/one-use approval, real MCP results and verified answer/version/query/provenance. Known-answer, failure, recovery and persistence checks pass; live-model/browser gates remain above. |
| NTD/Census/NOAA cross-source analysis | Prepared, not implemented | Reviewed materialized-table investigation and explicit geography/time/unit/key/coverage contract documented. Keep single-table policy. PEP remains preferred denominator; no unreviewed joins or synthetic causal/per-capita findings. |
| Six-database certification roadmap | Retained, not expanded | SQL Server, PostgreSQL, MySQL, MariaDB, SQLite and Oracle remain original DBHub targets. PostgreSQL demonstration, SQLite audit and isolated DuckDB evidence do not certify untested engines. |

Do not call component tests browser E2E or a fixture provider live GPT-6 Astra.
Phase 5 has not begun; require owner acceptance and authorization before transition.
