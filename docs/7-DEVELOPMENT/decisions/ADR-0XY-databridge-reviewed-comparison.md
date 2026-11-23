# Reviewed publisher selections and analytical datasets

Status: implemented; live verification recorded separately.

Data.gov can expose directory/API resources and lossy ISO rights classifications.
The general rights classifier must not infer reuse from public access or discard
restrictive metadata. Narrow publisher adapters therefore create separate,
release-reviewed distributions with their evidence in the catalog snapshot.

The Census adapter selects the exact federal-authored NST-EST2025-ALLDATA CSV.
It retains all published fields, text geography identifiers, Vintage 2025 and
July 1 reference dates. The NOAA adapter selects only the reviewed U.S. federal
Boston Logan station, bounded 2022–2025 years, TAVG/PRCP and metric units. It
re-fetches ISO metadata and requires the exact reviewed citation/warranty
constraints. Changed terms fail closed. The conflicting Data.gov entry remains
blocked. Neither adapter accepts arbitrary URLs or client-supplied rights.

The download allowlist adds only www2.census.gov and www.ncei.noaa.gov. Operator
overrides still apply; HTTPS, per-hop public IP checks, IP pinning, byte limits,
isolated parsing and immutable publication remain required.

Arbitrary cross-database SQL remains unsupported. A fixed Massachusetts/Logan
comparison creates an import in awaiting_approval state. Its review includes
canonical source SQL, immutable versions and the transformation contract. A
short-lived one-use approval atomically queues the existing durable importer.
The worker revalidates source grants, revisions, fingerprints, policy and hashes,
then queries only through MCP and publishes a normal immutable analytical table.
Identity includes notebook, source versions, policy and transformation contract;
retries reuse that import rather than creating another version.

NTD rows are restricted to Annual Total; each year/agency/mode/type-of-service
key must be unique. Population is attached only after annual aggregation.
Missing/questionable transit counts and weather measurement/source flags remain
visible; missing values are not zero-filled. The population-scaled contextual
ratio is withheld for incomplete/questionable trip inputs.

This is a descriptive year-label comparison. Agency report years may be fiscal;
Census estimates refer to July 1; NOAA summaries refer to calendar years.
Agency headquarters state is not a service boundary. Logan is a coastal-airport
indicator, not statewide exposure. No causal or statewide-weather claim follows.
