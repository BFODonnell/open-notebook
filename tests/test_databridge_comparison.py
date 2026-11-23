"""Offline regression fixtures; live observations are verified separately."""

from copy import deepcopy
from unittest.mock import AsyncMock

import duckdb
import pytest
from pydantic import ValidationError

from open_notebook.databridge import comparison
from open_notebook.databridge.ingestion.download import AcquisitionError
from open_notebook.databridge.ingestion.publishers import Selection, noaa_constraints
from open_notebook.databridge.mcp.policy import readonly_sql
from open_notebook.exceptions import InvalidInputError


def test_safe_numeric_aggregation_executes_and_counts_missing():
    sql = """SELECT year, COUNT(*) AS records,
        SUM(TRY_CAST(REPLACE(trips, ',', '') AS BIGINT)) AS reported_trips,
        SUM(CASE WHEN TRY_CAST(REPLACE(trips, ',', '') AS BIGINT) IS NULL THEN 1 ELSE 0 END) AS missing
        FROM data WHERE state='MA' AND period='Annual Total' GROUP BY year ORDER BY year"""
    canonical = readonly_sql(
        sql, "duckdb", {"data": ["year", "trips", "state", "period"]}, 100
    )
    assert canonical == readonly_sql(
        canonical, "duckdb", {"data": ["year", "trips", "state", "period"]}, 100
    )
    with duckdb.connect() as db:
        db.execute(
            "CREATE TABLE data(year INT, trips VARCHAR, state VARCHAR, period VARCHAR)"
        )
        db.executemany(
            "INSERT INTO data VALUES (?, ?, ?, ?)",
            [
                (2022, "1,234", "MA", "Annual Total"),
                (2022, "unknown", "MA", "Annual Total"),
                (2022, None, "MA", "Annual Total"),
                (2022, "900", "MA", "Average Weekday"),
                (2023, "56", "MA", "Annual Total"),
            ],
        )
        assert db.execute(canonical).fetchall() == [
            (2022, 3, 1234, 2),
            (2023, 1, 56, 0),
        ]


@pytest.mark.parametrize(
    "expression",
    [
        "CAST(trips AS INT[])",
        "TRY_CAST(trips AS STRUCT(x INT))",
        "CASE WHEN true THEN read_blob('/etc/passwd') ELSE trips END",
        "REPLACE(trips, ',', (SELECT trips FROM data))",
    ],
)
def test_numeric_support_does_not_enable_unsafe_constructs(expression):
    with pytest.raises(ValueError):
        readonly_sql(
            f"SELECT {expression} FROM data", "duckdb", {"data": ["trips"]}, 100
        )


@pytest.mark.parametrize(
    "change",
    [
        {"station": "arbitrary"},
        {"start_year": 2019},
        {"end_year": 2026},
        {"start_year": 2025, "end_year": 2022},
        {"variables": "all"},
        {"units": "standard"},
        {"url": "https://localhost"},
    ],
)
def test_publisher_selection_is_bounded(change):
    with pytest.raises(ValidationError):
        Selection(publisher="noaa", **change)


def test_noaa_terms_cannot_be_ignored():
    with pytest.raises(AcquisitionError, match="PUBLISHER_RIGHTS_CHANGED"):
        noaa_constraints(b"<root/>")


@pytest.fixture
def evidence():
    return {
        "transit": {
            "rows": [
                {
                    "report_year": 2022,
                    "records": 2,
                    "reported_trips": 1200,
                    "missing_trips": 0,
                    "questionable_trips": 0,
                }
            ]
        },
        "grain_2022": {"rows": [{"records": 1}, {"records": 1}]},
        "population": {"rows": [{"pop_2022": 100}]},
        "weather": {
            "rows": [
                {
                    "report_year": 2022,
                    "tavg": 12,
                    "prcp": 80,
                    "tavg_flags": "W",
                    "prcp_flags": " ,W",
                }
            ]
        },
    }


def test_aggregate_before_join_prevents_population_duplication(evidence):
    row = comparison.combine(evidence)[0]
    assert row["population_july1"] == 100
    assert row["trips_per_resident_context"] == 12
    assert row["state_fips"] == "25"
    assert row["logan_prcp_mm"] == 80


def test_all_missing_upt_stays_null_when_evidence_omits_null_key(evidence):
    evidence["transit"]["rows"][0].pop("reported_trips")
    evidence["transit"]["rows"][0]["missing_trips"] = 2
    row = comparison.combine(evidence)[0]
    assert row["reported_trips"] is None
    assert row["trips_per_resident_context"] is None


@pytest.mark.parametrize(
    "change", ["missing", "questionable", "weather_missing", "weather_flagged"]
)
def test_missing_and_quality_flags_are_not_silently_zero_filled(evidence, change):
    if change == "missing":
        evidence["transit"]["rows"][0]["missing_trips"] = 1
    elif change == "questionable":
        evidence["transit"]["rows"][0]["questionable_trips"] = 1
    elif change == "weather_missing":
        evidence["weather"]["rows"] = []
    else:
        evidence["weather"]["rows"][0]["prcp_flags"] = "T,W"
    row = comparison.combine(evidence)[0]
    if change in {"missing", "questionable"}:
        assert row["trips_per_resident_context"] is None
    else:
        assert row["logan_prcp_mm"] is None


@pytest.mark.parametrize("role", ["transit", "population", "weather"])
def test_duplicate_join_keys_rejected(evidence, role):
    evidence[role]["rows"].append(deepcopy(evidence[role]["rows"][0]))
    with pytest.raises(AcquisitionError):
        comparison.combine(evidence)


def test_duplicate_ntd_grain_is_not_summed(evidence):
    evidence["grain_2022"]["rows"] = [{"records": 2}]
    with pytest.raises(AcquisitionError, match="TRANSIT_GRAIN_REVIEW_REQUIRED"):
        comparison.combine(evidence)


@pytest.mark.asyncio
async def test_invalid_approval_never_queues(monkeypatch):
    monkeypatch.setattr(
        comparison.service,
        "job_for",
        AsyncMock(return_value={"payload": {"analysis": {"approval_hash": "bad"}}}),
    )
    submit = AsyncMock()
    monkeypatch.setattr(comparison.service, "submit", submit)
    with pytest.raises(InvalidInputError, match="approval is invalid"):
        await comparison.approve("db_import:x", "notebook:x", "wrong")
    submit.assert_not_called()
