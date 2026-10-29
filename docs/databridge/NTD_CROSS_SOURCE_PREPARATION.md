# NTD 2022-2025 and subsequent Census/NOAA preparation

Reviewed 2026-10-29. No cross-source comparison has been constructed. The owner
authorized synthetic fixtures for Phase 3 acceptance because no Data.gov key was
then configured. A subsequent [live validation](LIVE_NTD_VALIDATION.md) imported the
official FTA candidate after the owner supplied a key. The four-row fixture remains
explicitly synthetic and does not represent
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

Live acceptance subsequently measured **19,906,329 bytes, 51,716 rows and 69 columns**,
confirmed Report Year 2022-2025 through MCP, and verified restart persistence.
Full hashes/schema/provenance are in the [live report](LIVE_NTD_VALIDATION.md).
Each later import must still pass bounded preview and publication checks. An
export exceeding 32 MiB, 250,000 rows or 100 columns needs a reviewed subsetting
adapter; do not lift limits or silently truncate. No command-line ingestion or
manually registered database substitutes for this demonstration. The publisher
metadata endpoint was unavailable through the research browser tool during this
initial Phase 3 session; the subsequent live check used the application's backend
download path and the owner's configured personal catalog key successfully.

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
Phase 4 adds bounded conversational discovery/planning/approval/query/synthesis;
it does not authorize general cross-source SQL or certify these live adapters.

The original DBHub certification roadmap remains SQL Server, PostgreSQL, MySQL,
MariaDB, SQLite and Oracle. This phase adds no certification claim beyond the
previously documented subset and the isolated DuckDB import/query checks.

## Phase 4 investigation: reviewed analytical materialization

The approved design's preferred population denominator remains **PEP**, using one
consistent 2025 vintage for 2022-2025 where the exact geography and estimates are
available. If unavailable, restrict to the approved overlapping 2022-2024 years
and disclose the gap. The ACS example above documents an adapter/temporal pitfall;
it is not a silent replacement for that PEP decision. Live availability is still
unverified for PEP. Live NTD acquisition has now passed separately from fixture
DNS/TLS; this does not validate a Census denominator or NOAA mapping.

Prefer a reviewed materialized table over enabling joins in chat. The relationship
contract for a subsequent implementation must include:

| Input or relationship | Required validation before publication |
|---|---|
| NTD facts | Explicit unique agency/mode/type-of-service/report-period key; identify total vs component rows; exclude double counting; store measure definitions and units. |
| Agency to Census geography | Versioned crosswalk keyed by stable NTD ID and geography code/vintage, with validity dates and documented allocation weights. Names alone are forbidden. Reject duplicate/conflicting keys and allocations whose weights do not sum to the reviewed total. |
| PEP denominator | Same approved geography support and annual vintage across selected years; one population per geography/year; positive denominator; reject missing or incompatible coverage. Do not equate service coverage to city/county residence without a reviewed rule. |
| NOAA observations | Station/date/variable key, geographic mapping and weights, QC flags, completeness threshold and exact unit conversions. Preserve missing days; do not fill them with zero. |
| Annual alignment | Explicit annual support for all inputs; reject fiscal/calendar mismatches, partial years, nonoverlapping dates or unreviewed aggregation. |
| Published analytical table | Immutable input version IDs/hashes, crosswalk version, transformation hash, reviewer decision, validation totals, excluded coverage and output schema/unit definitions in provenance. Same P2 quotas, staging checks and publication interface. |

One possible future output grain is a reviewed service-geography/year with separate
columns for boardings, population, boardings-per-resident (never unique riders),
weather summaries and coverage flags. This is a proposed schema, not a computed
comparison or an enabled execution path. Many-to-many expansion, name-based joins,
zero denominators, mixed vintages, incompatible units and insufficient station
coverage must fail before publication. The P4 synthetic acceptance rejects join
requests, incompatible units, missing denominators and weather-causality requests;
its annual transit trend alone is not evidence of geographic compatibility.

No narrow join extension was enabled: the current parser, table allowlists and
read-only MCP boundary remain unchanged. The next review should compare materialized
tables against allowlisted foreign-key equijoins with explicit cardinality and
negative escape tests. General joins remain outside the authorized scope. Until
those checks pass, present separate transit/population/weather descriptions and
explicit incompatibility rather than per-capita or causal claims.
