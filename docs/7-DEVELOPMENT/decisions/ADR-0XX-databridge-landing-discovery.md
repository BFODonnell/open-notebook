# ADR: bounded landing-page and workbook discovery

Date: 2026-11-22. Status: implemented; live FTA acquisition blocked by publisher HTTP 403.

Extends the ingestion ADR. Explicit reuse declarations are evaluated at catalog,
DCAT and selected distribution scope. Known CC0 names/URLs, public-domain and the
government-works license are supported; accessLevel=public and legacy rights=public
alone do not grant reuse. Unknown/conflicting declarations fail closed. Cached
classifications are recomputed and import admission rechecks the policy.

An HTML candidate is fetched once, with a 2 MiB cap, through the existing pinned-IP
HTTPS transport. No browser automation, JavaScript execution, recursive crawling,
new host authorization or credential forwarding is introduced. At most 2,000
anchors and 30 unique supported download links are inspected. Relative links use
the validated final response URL, not an untrusted HTML base element. Users select
a candidate before preflight; every candidate retains the catalog identity,
landing URL and landing response hash. Final download URLs remain in provenance.

XLSX parsing uses openpyxl plus defusedxml in the existing isolated parser process.
ZIP container paths, entries, ratios and expanded size are bounded before parsing.
Macros, external workbook links, formulas and error cells are rejected. External
hyperlinks are inert cell values, never followed. Multiple worksheets require an
explicit selection; sheet identity is preserved in the profile and import snapshot.
The first row must be unique nonempty text headers. Existing row, column, memory,
CPU, disk and file size limits still apply. This is not general Excel evaluation.

Import identity includes notebook, catalog identifier, selected URL/sheet and raw
checksum. Atomic CREATE prevents concurrent retries from creating duplicate jobs;
legacy identical jobs are reused. Failed jobs require explicit retry, and changed
bytes require another preview. The browser retains the request key and presents a
modal confirmation naming the destination. Empty notebook state is distinct from
missing selection or request failure.

The demo reproduced valid notebook selection and successful submission after the
existing second confirmation. It did not reproduce a backend or state-propagation
failure. A single Import click previously only expanded an inline confirmation;
it did not submit a job. The historical report of no visible expansion is not
proved to have the same cause.

Live verification must report upstream rejection separately from mocked discovery
and workbook tests. Do not claim the 2023 FTA workbooks are certified until their
actual bytes pass the same application path.
