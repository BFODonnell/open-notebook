# Cross-phase acceptance items

| Item | Status | Completion evidence required |
|---|---|---|
| Live GPT-6 Astra validation through accepted Esperanto → LiteLLM path | Outstanding from Phase 1 | Authorized live account/model, real request, actual provider usage and pricing availability, failure behavior. Synthetic provider regression does not certify live access or billing. |
| Browser end-to-end verification | Outstanding across Phases 1–2 | Real browser checks of Settings usage, connection administration, discovery/approval, schema inspection, query approval and historical evidence. Component tests/build/HTTP smoke are not browser verification. Prior browser host was unavailable. |
| SQL Server multi-catalog and other DBHub engines | Uncertified | Actual engine instances, independent least-privilege catalog connections, scoped discovery/query and negative permissions tests. Not enabled by this phase's SQL execution path. |
| Human translations of new MCP UI text | Outstanding | Review translations in all supported locales; Phase 2 keeps key parity with explicit English text. |
| Ingestion and conversational database use | Planned P3/P4 | Data.gov acquisition/import workflow, immediate notebook dataset attachment, planner/evidence synthesis and golden-path browser tests. Not started in Phase 2. |

The Phase 2 automated gate is distinct from these external/later-phase items.
Do not describe component tests as browser E2E or fixture provider calls as live
GPT-6 Astra validation. Proceed to another implementation phase only after Phase 2
tests pass and the owner authorizes the phase transition.
