"""Release-reviewed publisher distributions, separate from Data.gov snapshots.

These are narrow source adapters, not a rights override for catalog records.
No arbitrary URL, station, dataset, variable or rights declaration is accepted.
"""

from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator

from open_notebook.databridge.ingestion import catalog
from open_notebook.databridge.ingestion.download import AcquisitionError, fetch
from open_notebook.databridge.ingestion.runtime import workspace

CENSUS_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"
CENSUS_PAGE = (
    "https://www.census.gov/data/tables/time-series/demo/popest/2020s-state-total.html"
)
NOAA_METADATA = "https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc%3AC00947/xml"
NOAA_DOC = "https://www.ncei.noaa.gov/pub/data/cdo/documentation/GSOY_documentation.pdf"
NOAA_POLICY = "https://www.ncei.noaa.gov/data-submission/data-licensing"


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publisher: Literal["census", "noaa"]
    start_year: int = Field(default=2022, ge=2022, le=2025)
    end_year: int = Field(default=2025, ge=2022, le=2025)
    station: Literal["USW00014739"] = "USW00014739"
    variables: Literal["TAVG,PRCP", "TAVG", "PRCP"] = "TAVG,PRCP"
    units: Literal["metric"] = "metric"

    @model_validator(mode="after")
    def ordered_years(self):
        if self.start_year > self.end_year:
            raise ValueError("Start year must not follow end year")
        return self


def noaa_constraints(xml: bytes) -> list[str]:
    from defusedxml.ElementTree import fromstring

    root = fromstring(xml)
    ns = {
        "gmd": "http://www.isotc211.org/2005/gmd",
        "gco": "http://www.isotc211.org/2005/gco",
    }
    constraints = root.findall(".//gmd:resourceConstraints", ns)
    texts = [" ".join(node.itertext()).split() for node in constraints]
    normalized = [" ".join(parts) for parts in texts]
    # Only the independently reviewed citation and warranty declarations. An
    # added access restriction or changed terms must trigger a new review.
    expected = [
        "otherRestrictions Cite as: Lawrimore, Jay H.; Ray, Ron; Applequist, Scott; Korzeniewski, Bryant; Menne, Matthew J. (2016): Global Summary of the Year (GSOY), Version 1. [indicate subset used]. NOAA National Centers for Environmental Information. https://doi.org/10.7289/JWPF-Y430. [access date].",
        "otherRestrictions Distribution liability: NOAA and NCEI make no warranty, expressed or implied, regarding these data, nor does the fact of distribution constitute such a warranty. NOAA and NCEI cannot assume liability for any damages caused by any errors or omissions in these data. If appropriate, NCEI can only certify that the data it distributes are an authentic copy of the records that were accepted for inclusion in the NCEI archives.",
        "otherRestrictions Use liability: NOAA and NCEI cannot provide any warranty as to the accuracy, reliability, or completeness of furnished data. Users assume responsibility to determine the usability of these data. The user is responsible for the results of any application of this data for other than its intended purpose.",
    ]
    if normalized != expected:
        raise AcquisitionError("PUBLISHER_RIGHTS_CHANGED")
    return normalized


async def select(selection: Selection) -> dict:
    catalog.enabled()
    if selection.publisher == "census":
        title = "Census Vintage 2025 — State population estimates, 2020–2025"
        publisher, url, landing = "U.S. Census Bureau", CENSUS_URL, CENSUS_PAGE
        description = "Official Census resident population estimates. Use SUMLEV 040 for states; STATE is a text FIPS identifier. POPESTIMATE2022–2025 are July 1 resident counts, all revised to Vintage 2025. The full published CSV includes all states and components; select Massachusetts (25) and the required years in the reviewed comparison. Do not sum national, regional and state rows."
        evidence = {
            "review": "census-nst-est2025-v1",
            "basis": "Federal-authored Census Population Estimates Program statistical table; U.S. government work under 17 USC 105, reviewed for this exact distribution, not inferred from public access.",
            "references": [
                CENSUS_PAGE,
                "https://www.copyright.gov/title17/92chap1.html#105",
            ],
            "vintage": 2025,
            "reference_date": "July 1 of each estimate year",
            "geography": "SUMLEV=040; STATE FIPS as text",
            "units": "resident persons",
            "variables": [f"POPESTIMATE{year}" for year in range(2020, 2026)],
        }
    else:
        async with workspace() as folder:
            metadata = await fetch(
                NOAA_METADATA, folder / "metadata.xml", limit=2 * 1024**2
            )
            constraints = noaa_constraints((folder / "metadata.xml").read_bytes())
        parameters = {
            "dataset": "global-summary-of-the-year",
            "startDate": f"{selection.start_year}-01-01",
            "endDate": f"{selection.end_year}-12-31",
            "stations": selection.station,
            "dataTypes": selection.variables,
            "format": "csv",
            "units": selection.units,
            "includeAttributes": "true",
            "includeStationName": "true",
            "includeStationLocation": "true",
        }
        url = "https://www.ncei.noaa.gov/access/services/data/v1?" + urlencode(
            parameters
        )
        title = f"NOAA GSOY — Boston Logan, {selection.start_year}–{selection.end_year}"
        publisher, landing = (
            "NOAA National Centers for Environmental Information",
            NOAA_METADATA,
        )
        description = "Actual annual Boston Logan station observations, not the example file. TAVG: degrees Celsius; PRCP: millimetres. Empty measurements remain missing. PRCP_ATTRIBUTES contains measurement/source flags; TAVG_ATTRIBUTES contains a source flag. Logan represents a coastal airport, not a Massachusetts statewide weather average. No daily completeness measure is asserted from annual flags."
        evidence = {
            "review": "noaa-c00947-usw00014739-v1",
            "publisher_metadata_sha256": metadata.sha256,
            "publisher_constraints": constraints,
            "references": [NOAA_METADATA, NOAA_POLICY, NOAA_DOC],
            "basis": "Reviewed U.S. federal station observations under NCEI Open Data Policy. Original ISO otherRestrictions entries are citation and warranty notices, not private access restrictions. The conflicting Data.gov snapshot remains blocked.",
            "selection": parameters,
            "missing_values": "Empty cells are NULL; never zero-fill. Preserve publisher flags verbatim.",
            "citation": "Lawrimore et al. (2016), Global Summary of the Year, Version 1, NOAA NCEI, doi:10.7289/JWPF-Y430; Boston Logan subset; retrieval date recorded at import.",
        }
    return await catalog.cache_dataset(
        {
            "access_level": "public",
            "rights_review": evidence,
            "dcat": {
                "identifier": landing,
                "title": title,
                "description": description,
                "publisher": {"name": publisher},
                "accessLevel": "public",
                "rights": "public domain",
                "distribution": [
                    {
                        "title": title,
                        "downloadURL": url,
                        "mediaType": "text/csv",
                        "rights_evidence": evidence,
                    }
                ],
            },
        }
    )
