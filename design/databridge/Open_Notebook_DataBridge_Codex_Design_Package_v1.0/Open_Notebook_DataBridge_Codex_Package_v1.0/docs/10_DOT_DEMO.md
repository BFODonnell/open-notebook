# 10 — Hackathon Demo: DOT NTD + Census + NOAA Weather

## Objective

Demonstrate a real user finding a publicly listed FTA transit dataset, importing it into local DuckDB without manual steps, enriching context with Census population and NOAA climate/weather information, and asking a natural-language question that yields SQL-backed tables/charts and cautious interpretation.

## Verified real source

**FTA, “2022 - 2025 NTD Annual Data - Service (by Mode and Time Period)”**

- Data.gov catalog: https://catalog.data.gov/dataset/2022-2024-ntd-annual-data-service-by-mode-and-time-period (URL slug says 2022–2024, page title and contents currently say **2022–2025**).
- Publishing agency: Federal Transit Administration, U.S. DOT.
- Socrata asset: `wwdp-t4re`, landing https://data.transportation.gov/d/wwdp-t4re.
- Published CSV distribution documented at: `https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD`.
- Data.gov page reports modified October 14, 2026 and CSV/JSON/XML distributions. Validate live current metadata at runtime; do not bake a static row count or claim live download succeeds before testing.

## Companion sources

**Census:** U.S. Census Bureau Population Estimates Program (PEP), preferably a single consistent 2025 vintage covering 2022–2025 and the exact geographies relevant to selected transit service areas; if unavailable or incompatible, use approved 2022–2024 overlapping years and show the limitation. Census official APIs may require an API key. Store variable definitions, vintage, time/year and geography identifiers rather than joining by place names.

**NOAA:** NOAA NCEI Access Data Service (`https://www.ncei.noaa.gov/access/services/data/v1`), e.g. daily summaries for selected stations/time windows. Keep station IDs, QC flags, units, and date coverage. Aggregate to years or months only after verified station/geography mapping; do not equate one station with a full transit-service region by default.

Neither Census nor NOAA requires a different MCP server: ingest their approved public API results into DuckDB via in-app adapters.

## Data harmonization plan

### NTD facts

Use transit agency ID, mode, time period/report year, service metric (e.g., unlinked passenger trips), and service area data only when field definitions and grain are confirmed from metadata/dictionary. Avoid summing duplicated totals across temporal partitions or inconsistent service modes. Audit NTD granularity before deriving year-over-year comparisons.

### Census denominator

**Do not blindly divide an agency's unlinked passenger trips by the city population.** Agencies and their service areas may cross municipality boundaries. Build a verified agency-to-urbanized-area/county/other Census geography crosswalk and document the denominator. If such a crosswalk is unavailable for the live demo, show overall NTD trend and a separate population trend instead of a misleading 'per capita' figure.

### NOAA context

Map station ↔ geography and time coverage; aggregate daily precipitation/temperature to year or month with missing-day rules. Treat associations as descriptive or exploratory; explicitly say that weather fluctuations do not demonstrate causality in ridership.

## Seven-minute live script

1. **0:00–0:45:** Show Open Notebook DataBridge and MCP connection registry (DBHub, DuckDB, Google Toolbox).
2. **0:45–1:30:** Search Data.gov `NTD annual service`, open FTA record, show CSV Ready and other resource statuses; present metadata.
3. **1:30–2:30:** Click Import; show backend progress, local DuckDB schema and provenance. If live source is unavailable, use identical app flow against a seeded offline resource fixture and label it clearly synthetic.
4. **2:30–3:30:** Import/add Census and NOAA companion resources through in-app catalog/API adapters or preloaded public snapshots with provenance.
5. **3:30–4:45:** Ask: “How did annual transit use change by mode from 2022 through 2025? Where appropriate, compare with population, and summarize major weather anomalies as context.”
6. **4:45–5:45:** Show planned SQL, approval, table/chart, dataset version citations and a caveat on geography/denominators.
7. **5:45–6:30:** Save a notebook research report and reopen SQL + exact source references.
8. **6:30–7:00:** Open usage dashboard and show tokens, estimated USD spend, per-task request count; close with reproducibility and security.

## Offline fallback

`fixtures/` contains **clearly synthetic, non-real** mini-data with normalized keys, known results, and a deliberate coverage gap. Ship a demo fixture-loader inside DataBridge in a controlled `demo` Compose profile; do not mislabel fixtures as real FTA/Census/NOAA values. The offline mode should exercise the exact import and query code path where possible, not a special UI-only mock.

## Demo answer safeguards

- “Transit use” is not automatically “service supplied”; confirm correct NTD measure (e.g., unlinked passenger trips) and label it precisely.
- Warn about NTD reporter coverage/method changes; missing 2025 rows are not necessarily zero.
- Trend chart must show units, aggregation definition, year, sample count and dataset freshness.
- For weather, report a source/context association only. Any causal assertion requires a separately designed statistical study.

## Stretch report

Optionally generate a one-page research memo: question, dates/geography, headline findings, a chart, executed SQL and data source citations, missing-data warnings, and token/cost usage.
