# Live three-source DataBridge verification

Verified November 22, 2026 (local time; November 23 UTC). Real publisher bytes,
real catalog responses, real DuckDB/MCP execution and the configured live model
were used. No fixture publisher, substituted weather sample, direct database
registration or synthetic model answer was used for this workflow.

Fresh notebook: **Transit Population Weather - Verified Live Demo**,
`notebook:4mzyg2ostswv0un7d2gc`.
Open it at <http://localhost:18503/notebooks/notebook:4mzyg2ostswv0un7d2gc>.
The previously successful Full Demo notebook and version
`de1163f2-eb82-407d-baf6-c62347bad636` were preserved.

## Confirmed defects and repairs

| Finding | Evidence and change |
| --- | --- |
| Explicit CC0 incorrectly rejected | Catalog classification did not consistently receive the complete catalog envelope or normalize nested/array rights. Extraction now reads known root, DCAT and distribution fields, including arrays and supported identifier objects. Unknown/restrictive declarations still block. Both 2023 FTA records were inspected independently and contained CC0. |
| HTML landing pages treated as unsupported downloads | Added one-page bounded discovery, explicit file selection, safe XLSX parsing and worksheet selection. Catalog, landing and resolved URLs are retained. Actual FTA landing/file requests returned publisher HTTP 403 in this environment; that now reports `SOURCE_ACCESS_DENIED`, not a rights failure. Live 2023 XLSX import remains externally blocked. HTML/XLSX success is covered by fixtures, not claimed as a live success. |
| Misleading notebook/import UI | The old empty/loading branch displayed “Select a notebook” even when a valid notebook had no imports. The first Import click only exposed an inline second confirmation, easy to miss. The reported loss of selection/silent backend failure was not independently reproduced and is not claimed as a confirmed backend defect. A single validated destination ID now drives selection, queries and submission; confirmation is a visible dialog, errors and job IDs are visible, invalid selection disables Import. |
| Duplicate retry risk | A new client UUID could create a new import. Import identity now includes notebook, logical catalog identity, selected file/sheet and verified content hash, with atomic creation and compatibility lookup for older jobs. Comparison identity includes source versions, contract and SQL policy. |
| Census/NOAA acquisition unsupported | Default download hosts were DOT-only, and generic blocking hid host rejection. Added the two exact official hosts and bounded publisher selections. Census uses an appropriate direct federal file, avoiding incompatible state republications and old decades. NOAA uses an actual station API request. |
| NOAA rights conflict | Raw Data.gov data already contained `non-public`, CC0 and `otherRestrictions`; normalization did not introduce the conflict. The original catalog distributions remain blocked. A separate reviewed NOAA selection records publisher XML terms, their content hash, exact request and public-domain policy evidence. Changed publisher constraint text fails closed. |
| Numeric aggregation rejected | The read-only AST allowlist omitted `REPLACE`, `TRY_CAST`, scalar cast types and `CASE`/`IF`. The explicit demo SQL returned a generic policy rejection before repair. Narrow support was added; joins, subqueries, file/network functions, arrays/struct casts and writes remain forbidden. Rejections identify the unsupported construct. |
| Chat falsely rejected supported analysis | The live original question with a negated causal instruction was rejected before repair. Planner guidance did not describe the safe conversion functions or distinguish a negated constraint from a causal request. Both forms now generated and executed the intended aggregation using the live model. No keyword-based bypass was added. |
| Three-source comparison absent | Added an explicitly reviewed, fixed annual analytical dataset. Seven notebook-scoped MCP queries aggregate/check sources before a deterministic join. All source versions, SQL, query evidence and transformation contract remain attached. Arbitrary cross-database SQL is still unsupported. |
| Other live UI/catalog defects | Publisher names replace raw JSON on cards. One unrelated catalog entry with 31 distributions aborted the whole NOAA search; it now remains visibly limited without hiding other results. Chat displays actual verified query cells as a scrollable table. |

## Exact live selections

| Source | Selection | Observed shape | Immutable version |
| --- | --- | --- | --- |
| FTA NTD Service | [Official CSV](https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD), asset `wwdp-t4re`, report years 2022-2025 | 51,716 rows, 69 columns; 19,944,739 bytes | `54b66fa6-f5ac-40d7-84d9-2cb288ebd5ba` |
| Census | [Vintage 2025 state population CSV](https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv), July 1 `POPESTIMATE2022` through `POPESTIMATE2025` | 66 rows, 97 columns; 53,555 bytes | `dc0d489d-bfa0-471d-ad52-aeff0c5cf198` |
| NOAA | GSOY, station `USW00014739` (Boston Logan), 2022-01-01 through 2025-12-31, `TAVG,PRCP`, metric, attributes/name/location included | 4 rows, 10 columns; 587 bytes | `32e5f499-ae76-470b-9b98-1b820aa3c5aa` |
| Reviewed comparison | `ma-logan-annual-v1` | 4 rows, 15 columns | `e1473981-740f-474e-ac2a-641fb50b2264` |

The exact NOAA request is:

```text
https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-summary-of-the-year&startDate=2022-01-01&endDate=2025-12-31&stations=USW00014739&dataTypes=TAVG%2CPRCP&format=csv&units=metric&includeAttributes=true&includeStationName=true&includeStationLocation=true
```

Rights review used the [publisher GSOY metadata](https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc%3AC00947/xml),
[NCEI licensing policy](https://www.ncei.noaa.gov/data-submission/data-licensing),
and [GSOY attribute documentation](https://www.ncei.noaa.gov/pub/data/cdo/documentation/GSOY_documentation.pdf).
The Census selection is the specific federal-authored population estimate work,
with [17 USC 105](https://www.copyright.gov/title17/92chap1.html#105) recorded as
evidence. This is not a blanket rule for all publicly accessible or government-hosted data.

## Actual comparison and interpretation

| Report year | NTD records | Reported UPT | Questionable UPT records | July 1 population | Logan TAVG (C) | Logan PRCP (mm) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 55 | 227,309,167 | 3 | 7,025,465 | 12.0 | 794.9 |
| 2023 | 53 | 262,844,430 | 2 | 7,073,479 | 12.2 | 1,264.6 |
| 2024 | 53 | 284,112,207 | 2 | 7,138,560 | 12.1 | 1,153.3 |
| 2025 | 50 | 306,786,051 | 2 | 7,154,084 | 11.2 | 943.6 |

Reported boardings increase across these four annual extracts; population also
increases. Logan temperature and precipitation do not follow the same monotonic
pattern. This is descriptive context, not an estimate of weather or population
effects on transit.

The mapping is NTD agency headquarters `State=MA` to Census `STATE='25'`,
`SUMLEV='040'`. These strings retain geographic leading zeros in the source.
NTD filters only `Annual Total`, then checks unique year/NTD ID/mode/type-of-service
keys. Population and station observations are attached once per year after
aggregation, never once per transit row. All four years have zero missing or
unparseable UPT values but some `W`/`Q` questionable flags, so every per-resident
ratio is deliberately NULL. A separate MCP `IS NULL` query verified all four.

Reporting coverage changes (55 to 50 records); this is not a balanced agency panel.
UPT measures boardings, not unique people. Agency headquarters do not define where
every trip occurred. Agency fiscal report years, Census July 1 estimates and NOAA
calendar summaries share year labels but are not identical exposure periods.
Logan is a coastal airport, not a statewide weather mean or agency service-area
weather measure. NOAA source flags `W`/`1` and precipitation attributes ` ,W`/` ,1`
are retained; they do not certify daily completeness. Flagged precipitation and
missing observations are withheld rather than zero-filled. No unavailable years
were invented.

## Live acceptance evidence

1. Native Chrome automation created the fresh notebook, searched Data.gov for
   the NTD Service title, inspected/validated it, selected Census and NOAA through
   the new application controls, and confirmed all three imports. Each showed
   its accepted job and reached “Ready - database query verified.”
2. Browser controls selected all three versions and displayed seven canonical
   queries plus the transformation contract. Explicit approval created the
   fourth, analytical dataset. Four schema sources appeared in notebook chat.
3. The application MCP schema endpoint and reviewed/executed `COUNT(*)` queries
   verified each real table's schema, count and immutable provenance. A further
   query read all 15 comparison fields.
4. In notebook chat, the browser asked for the annual trips/population/weather
   table, quality flags and limitations, ending “Do not infer causality.” It
   reviewed and approved the generated SQL, and observed `completed` with all
   four years' values and the exact dataset version. Evidence:
   `db_query_run:uof6oj8epfp93vxtzmks`; result SHA-256
   `60d5c63f66f6467572c1abaa91700dfd8efe61308a9112745700ec6a6d7beaed`.
5. Independent verification downloaded the publisher files again, matched all
   three raw SHA-256 values, parsed them with Python `csv`, and recomputed the
   grouping, unique keys, counts, sums, flags, population and weather checks.
   It did not call the comparison implementation or DuckDB for the independent
   arithmetic. All checks passed.
6. Additional live model/API regressions asked the original single-table
   aggregation both with and without the negated causal sentence. Both produced
   safe numeric conversion and conditional missing counts, executed successfully
   and matched the independent results.
7. The application was recreated and the browser reloaded. Sources and completed
   query evidence persisted. A new request UUID for the same transit file returned
   the existing import, keeping the notebook at four datasets. Re-reviewing the
   same source versions also returned the existing ready comparison without a
   second materialization.

The [machine-readable evidence](evidence/three_source_live.json) records complete
schemas, raw hashes, selected URLs, reviewed comparison SQL and actual chat rows.
It contains no credentials or approval tokens. Local detailed evidence remains
under `data/three-source-live/` and the live container's `/app/data/three-source-live/`.

Final visual check passed after the user restored browser access. The saved
comparison conversation was reopened in the final build, showing `completed`
and the same immutable version. All four annual rows were visually inspected.
The table stays within the chat panel, and horizontal scrolling exposes the
population, quality flags and reported-trip columns without widening the page.
The updated Open Notebook DataBridge sidebar name is also visible. This closes
the earlier Windows activation blocker and verifies the final layout adjustment.

## Tests and limits

Offline automated checks are separate from the live run above: full Python suite
1,322 passed before the final missing-key regression; final affected backend
suite 144 passed. Full frontend suite 211 passed across 40 files; final affected
UI/i18n suite 43 passed. These include mocked HTTP/DB tests, HTML/XLSX fixtures,
real local DuckDB numeric-policy tests, duplicate-grain/missing/flag cases and
React interaction tests. They do not establish publisher availability.

Full mypy passed (214 files), scoped Ruff lint/format passed, TypeScript passed,
and production application/DuckDB images built successfully. Frontend lint has
zero errors and seven existing warnings. Windows native OpenSSL failure requires
running Python application tests in the Linux test container, using `uv`.

The older 2024 Reporter Agency Information regression imported real CSV asset
`ccvf-fykn` into Demo and verified 2,914 rows and 43 columns through MCP and chat
(version `5e8f123f-a94f-43a5-84eb-785ba5b123f7`). Dimensions are observations, not
permanent upstream assertions. Agency information is not evidence of ridership
or operating-expense trends.

The original FTA 2023 HTML/XLSX endpoints still deny access with HTTP 403 from this
environment. Security/TLS/redirect controls were not weakened to bypass that
external restriction. The new three-source demo uses the live supported Service
CSV. The reviewed comparison currently supports the explicit Massachusetts/Logan
contract and 2022-2025 range; general geography mapping and arbitrary joins are
not implemented. New UI keys exist in all locales; new non-English entries retain
English text pending translation.

## Reproduce

Start the existing configured live stack using `uv run --no-sync python
scripts/databridge_live/run.py up`; see the [live launcher README](../../scripts/databridge_live/README.md)
for model/key setup. Do not replace it with the fixture publisher overlay.

1. At `http://localhost:18503`, create a fresh notebook. In Explorer select it.
2. Search `2022 - 2025 NTD Annual Data - Service`. Inspect the matching dataset,
   validate its CSV, click Import and confirm the named destination. Wait for Ready.
3. Under Official publisher selections, inspect Census population; validate and
   import. Select NOAA Boston Logan, 2022 to 2025, TAVG and PRCP in metric units;
   inspect, validate and import.
4. Under Reviewed annual comparison, assign the three imported versions to their
   roles. Review the contract and all SQL. Approve creation; wait for Ready.
5. Open the notebook and ask: “Using the reviewed Massachusetts transit,
   population and Boston Logan weather annual context dataset, show a comparison
   table for 2022 through 2025 with report year, reported passenger trips,
   questionable trip record count, July 1 population, Logan average temperature
   in Celsius and precipitation in millimetres. Explain the reporting-period,
   geography and quality limitations. Do not infer causality.” Review SQL, then
   approve MCP execution. Inspect the verified result table and provenance.
6. Reload. Select the saved conversation under Sessions if another test session
   is newer. Confirm the sources and completed answer remain.

For this exact notebook, independently rerun:

```powershell
docker cp scripts/databridge_live/verify_three_source.py databridge-live-validation-open-notebook-1:/app/verify_three_source.py
docker exec databridge-live-validation-open-notebook-1 uv run --no-sync python /app/verify_three_source.py
docker cp scripts/databridge_live/verify_three_source_chat.py databridge-live-validation-open-notebook-1:/app/verify_three_source_chat.py
docker exec databridge-live-validation-open-notebook-1 uv run --no-sync python /app/verify_three_source_chat.py capture
docker exec databridge-live-validation-open-notebook-1 uv run --no-sync python /app/verify_three_source_chat.py plan
# Inspect the printed SQL before the following explicit execution step:
docker exec databridge-live-validation-open-notebook-1 uv run --no-sync python /app/verify_three_source_chat.py execute
```

Scripts target the fresh notebook name above; pass `docker exec -e
DATABRIDGE_DEMO_NOTEBOOK="Your notebook name" ...` for a new named run. The
independent verifier fails if upstream bytes changed, rather than
comparing a newer publication to an older immutable import. `three_source.py`
is a diagnostic probe of the preserved Full Demo, not a substitute for browser
acceptance; new probes write timestamped directories and omit approval tokens.
