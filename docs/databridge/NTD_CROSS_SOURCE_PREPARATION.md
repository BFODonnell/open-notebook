# NTD 2022-2025 and subsequent Census/NOAA preparation

Reviewed 2026-10-29. No cross-source comparison has been constructed. The owner
authorized synthetic fixtures for Phase 3 acceptance because no Data.gov key is
configured. The four-row fixture is explicitly synthetic and does not represent
actual transit service, agency coverage or county statistics.

## First live candidate

Search **National Transit Database**, then inspect **2022 - 2025 NTD Annual Data -
Service (by Mode and Time Period)**. Its official
[Data.gov catalog record](https://catalog.data.gov/dataset/2022-2024-ntd-annual-data-service-by-mode-and-time-period)
currently describes report years 2022-2025, publisher FTA, public access and rights,
and a 2026-10-14 update. The legacy slug still says 2022-2024. Publisher asset ID
is `wwdp-t4re`. The catalog lists JSON, XML and CSV resources; CSV is the initial
candidate, while XML requires an adapter. The CSV download is on the approved
`data.transportation.gov` host under `/api/v3/views/wwdp-t4re/export.csv`.

Live export byte count, row count and complete schema are **unverified**, and
import is not pre-enabled on these metadata claims. Live acceptance must run the
in-app bounded preview, record size/hash/actual years/schema and then import. An
export exceeding 32 MiB, 250,000 rows or 100 columns needs a reviewed subsetting
adapter; do not lift limits or silently truncate. No command-line ingestion or
manually registered database substitutes for this demonstration. The publisher
metadata endpoint was unavailable through the research browser tool during this
session, and there is no configured personal catalog API key.

## Compatibility checklist before comparison

| Dimension | Required decision/evidence |
|---|---|
| Grain | Inspect agency, mode, type-of-service and time-period fields; establish a unique key before aggregating. Do not sum totals with component rows. |
| Time | Confirm each row's actual report year and reporting period. Do not assume annual report year equals a common calendar-year window across agencies. |
| Measure | Preserve UPT, passenger miles, vehicle revenue miles and hours separately; record unit/definition and applicability. |
| Geography | Preserve NTD IDs and geographic codes as strings. Agency/urban-area service coverage is not a county population boundary. Require a reviewed crosswalk and allocation rule. |
| Quality | Check missing/suppressed values, reporting population changes, revisions and duplicate service before differences or ratios. |
| Size | Require the live preview's measured bytes, rows and columns, not the catalog title or file extension. |

FTA's [glossary](https://www.transit.dot.gov/ntd/national-transit-database-ntd-glossary)
distinguishes boardings (unlinked trips) from passenger distance and vehicle
service measures. Use those definitions rather than interpreting a column named
`trips` as unique people. The
[2024 publication guide](https://www.transit.dot.gov/sites/fta.dot.gov/files/2025-10/2024%20Annual%20NTD%20Data%20Publications%20Guide.pdf)
documents changes, reporting populations and cross-file reconciliation. Reconcile
each year's applicable guide before comparing releases. The synthetic fixture's
county column is a parser/scoping test, not an official NTD-to-county mapping.

## Deferred adapter contracts

**Census:** a reviewed adapter should select an explicit survey, vintage, geography,
variables and estimate/margin-of-error pairs, then turn the API's header-plus-rows
array into consistent scalar records before the same preview/import pipeline.
Generic JSON ingestion deliberately rejects that array-of-arrays structure.
The official [2024 ACS 5-year geography list](https://api.census.gov/data/2024/acs/acs5/profile/geography.html)
includes state/county and state/county/tract hierarchies. Treat 2020-2024 period
estimates as a different time support from an annual NTD total; record geography
vintage and a crosswalk before alignment. Publisher `api.census.gov` is not enabled
by default; add it only when this adapter and its bounded requests are reviewed.

**NOAA:** a reviewed NCEI adapter should fix dataset, stations or bounded geography,
date interval, variables, units and quality attributes. The official
[Access Data Service](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation)
supports bounded selections and CSV/JSON output, including station location and
metric/standard units. Preserve station/date grain and quality flags. An agreed
station-to-service-area mapping and temporal aggregation are prerequisites to
weather/transit comparisons. `www.ncei.noaa.gov` is not enabled by default. API
authentication requirements must be evaluated per chosen product, without placing
tokens in URLs or forwarding the Data.gov key.

Both future adapters must emit the same catalog/resource snapshot, bounded raw
download, checksum, schema mapping and immutable publication contract. Neither
adds an MCP server. **Phase 2 SQL permits one table only**, so cross-source joins
require a separate policy/planner review and tests; they are not delivered in P3.
DB-DATA-02 conversational discovery/planning/query/synthesis is also still pending.

The original DBHub certification roadmap remains SQL Server, PostgreSQL, MySQL,
MariaDB, SQLite and Oracle. This phase adds no certification claim beyond the
previously documented subset and the isolated DuckDB import/query checks.
