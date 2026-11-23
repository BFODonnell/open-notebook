# 14 — Technical References and Verification Notes

Sources checked **October 29, 2026**. URLs are reference documentation; Codex must re-read live upstream docs before changing repository code and pin exact tested versions. No external repository contents have been copied into this design package.

## Upstream Open Notebook

- Repository: https://github.com/lfnovo/open-notebook
- Architecture and processes: https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/architecture.md
- Development setup/Python constraints: https://github.com/lfnovo/open-notebook/blob/main/docs/1-INSTALLATION/from-source.md
- Credential, model, Esperanto interface: https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/credentials.md
- Code change playbooks: https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/change-playbooks.md
- API reference: https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/api-reference.md
- Read before coding: https://github.com/lfnovo/open-notebook/blob/main/AGENTS.md , https://github.com/lfnovo/open-notebook/blob/main/open_notebook/AGENTS.md , https://github.com/lfnovo/open-notebook/blob/main/frontend/AGENTS.md

## MCP/database infrastructure

- DBHub support, multi-connection, SQL tools: https://github.com/bytebase/dbhub
- Google MCP Toolbox prebuilt/curated sources and tools: https://github.com/googleapis/mcp-toolbox
- DuckDB/MotherDuck local MCP (read-only default, security caveats): https://github.com/motherduckdb/mcp-server-motherduck
- FastMCP (potential Python client): https://github.com/PrefectHQ/fastmcp
- SQLGlot: https://github.com/tobymao/sqlglot
- DuckDB documented concurrency constraints: https://duckdb.org/docs/stable/connect/concurrency

## Data.gov and demo data

- Official Data.gov Catalog API v4: https://resources.data.gov/catalog-api/
- Catalog API base: https://api.gsa.gov/technology/datagov/v4/
- FTA 2022–2025 NTD Annual Service by Mode and Time Period catalog: https://catalog.data.gov/dataset/2022-2024-ntd-annual-data-service-by-mode-and-time-period
- Source Socrata landing: https://data.transportation.gov/d/wwdp-t4re
- Source CSV distribution from metadata: https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD
- U.S. Census Population Estimates APIs: https://www.census.gov/data/developers/data-sets/popest-popproj/popest.html
- NOAA NCEI Access Data Service: https://www.ncei.noaa.gov/access/search/documentation/data-service/

## LLM provider and metering

- GPT-6 Astra model ID/pricing: https://developers.openai.com/api/docs/models/gpt-6-astra
- OpenAI model overview: https://developers.openai.com/api/docs/models
- LiteLLM proxy quickstart/DB requirement: https://docs.litellm.ai/docs/proxy/docker_quick_start
- LiteLLM spend tracking and `/spend/logs/v2`: https://docs.litellm.ai/docs/proxy/cost_tracking
- LiteLLM model cost map caveats: https://docs.litellm.ai/docs/proxy/model_cost_map
- LiteLLM production deployment/pinning: https://docs.litellm.ai/docs/proxy/deploy

## Verified details relevant to implementation

- Data.gov official v4 uses `X-Api-Key`; search pagination uses an `after` cursor; `DEMO_KEY` is not suitable for automated use. Search results can contain DCAT data and references to harvest records.
- NTD page **title** is 2022–2025 despite older `2022-2024` slug; CSV distribution is a Socrata export; verify current release at runtime.
- DBHub advertises six engines (including Oracle) but require actual integration testing for each.
- LiteLLM requires a PostgreSQL-backed DB for reliable spend tracking and key budgets; separate service is in the target architecture.
- Open Notebook uses its existing model registry and Esperanto abstraction; don't replace it with direct unregistered SDK calls.
- For self-hosted local DuckDB, read-only MCP operation alone is insufficient to prevent local file/network access; use layered safety and isolation.
