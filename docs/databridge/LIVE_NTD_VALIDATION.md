# Live Data.gov / FTA NTD validation

Date: 2026-10-29, after Phase 4 commit `c0f2164`. The owner supplied a personal
Data.gov key in ignored `.env.databridge`. This closes the specific live catalog/
NTD import API-worker-MCP gate; it does not begin Phase 5 or certify browser/live
LLM behavior.

## Executed path

**DataBridge catalog search -> inspect official dataset/resources -> bounded CSV
preflight -> application Import -> real background worker -> immutable publication
and automatic notebook/MCP association -> reviewed read-only MCP query -> provenance
inspection -> full stack restart -> same query result and hashes.**

The existing P4 application image was used without changing application code,
SQL policy, download/parser limits, host allowlist or publication architecture.
The separate `databridge-live-validation` project has no synthetic catalog,
publisher DNS mappings or test CA. Its local model fixture makes no paid provider
calls. Catalog authentication uses the official v4 API's `X-Api-Key` mechanism;
see [official documentation](https://resources.data.gov/catalog-api/).

## Observed snapshot

| Item | Observed value |
|---|---|
| Dataset | 2022 - 2025 NTD Annual Data - Service (by Mode and Time Period) |
| Publisher asset | `wwdp-t4re`, Department of Transportation / FTA |
| Resource | `https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD` |
| Download | 19,906,329 bytes; CSV; no limit increases |
| Dataset | 51,716 rows; 69 columns |
| Raw SHA-256 | `b3285c378ebd774447d4b7547dad7db04c7578282734f068e20333970c2aa583` |
| Immutable version | `0230e685-eeeb-4b2a-aaff-7af3e25a4096` |
| Database SHA-256 | `0b03c4656c390de996d1c1d615f64dc44585788295d45bb18414a2b16d8e45b2` |
| Notebook | Live FTA NTD validation |

The real MCP query grouped **record counts**, not ridership, by Report Year:

| Report year | Rows |
|---|---:|
| 2022 | 12,906 |
| 2023 | 12,801 |
| 2024 | 12,966 |
| 2025 | 13,043 |
| Total | 51,716 |

Canonical SQL, query/plan/notebook/source IDs, timestamps, download metadata,
column mappings, processing stages, hashes and before/after restart evidence are
in [sanitized live evidence](evidence/live-ntd-2026-10-29.json). No API key or
approval bearer is included. The download hash matched preflight; the real worker
command completed; the schema Source was linked to the notebook; the immutable
manifest matched the imported version. The context API exposes the new dataset
with conversational research enabled, but no live model was tested.

## Analytical limitations

The publisher CSV contains comma-formatted measures, including **Unlinked Passenger
Trips (UPT)**. Conservative parsing correctly preserves that column as `VARCHAR`.
Its values must not be summed as integers without a reviewed numeric-normalization
adapter and checks for missing/suppressed/questionable values. Do not broaden SQL
functions or silently coerce publisher strings to work around this boundary.

Row counts are records, not agencies, trips or passengers. Report years are present;
that alone does not certify calendar/fiscal comparability, time-period/component
aggregation, geography, service coverage or units. No ridership total, per-capita
comparison, Census/NOAA join or causal finding was constructed. The preparation
contract and restrictive one-table policy remain in force.

## Verification and operational state

Repeatable commands: [live acceptance README](../../scripts/databridge_live/README.md).
Search, metadata/classification, preflight, import, completed worker/provenance,
MCP year counts and full-stack restart checks all passed. Ruff, formatting and
mypy pass for the two new validation scripts. No application dependency changed.
Earlier P4 regression evidence remains applicable; this follow-up adds real-source
integration evidence rather than relabeling fixtures as live tests.

The validation stack and imported dataset are retained on loopback port 18503 for
inspection; independent random local credentials are in the ignored
`.env.databridge-live-validation`. The personal catalog key remains only in its
original protected configuration and backend runtime. Other user containers and
the untracked design package were untouched. Browser E2E, live GPT-6 Astra and
remaining database certification are still outstanding.

## Browser connection correction

Subsequent owner-authorized [GPT-6 Astra validation](LIVE_OPENROUTER_VALIDATION.md)
replaced the model placeholder with the saved OpenRouter credential through
LiteLLM. The original acquisition evidence above remains unchanged.

The owner subsequently found the UI's API connection error. Container-local API
acceptance had missed that `/config` advertised the default host port 5055 while
the live stack published the API on 15056. Compose now supplies runtime `API_URL`
from `DATABRIDGE_API_PORT`, preserving an explicit `API_URL` override. The existing
application image needed only recreation; no dataset volumes were reset.

Verified after the correction: `/config` advertises `http://localhost:15056`;
host-side `/api/config` returns HTTP 200 with database online; the UI origin is
allowed by CORS; authorization/content-type preflight returns 200. Compose checks
cover default port, custom port and explicit URL override. All 18 existing frontend
configuration tests pass. The imported version and MCP year-count/hash checks also
pass after recreation. These protocol checks are not full browser E2E certification.
