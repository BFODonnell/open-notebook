from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from open_notebook.databridge import research
from open_notebook.databridge.mcp.client import digest
from open_notebook.exceptions import InvalidInputError
from open_notebook.graphs import database_research


def evidence(rows):
    return {"status": "success", "rows": rows, "result_sha256": digest(rows)}


def test_exact_numeric_claim_and_quote_verification():
    result = research.verify_synthesis(
        {
            "status": "supported",
            "cells": [{"row": 0, "column": "trips", "value": 700}],
            "quotes": [{"source_id": "source:1", "quote": "boardings"}],
        },
        evidence([{"trips": 700}]),
        [{"source_id": "source:1", "excerpt": "Trips count boardings."}],
    )
    assert result.cells[0].value == 700


@pytest.mark.parametrize(
    "cell",
    [
        {"row": 0, "column": "trips", "value": 701},
        {"row": 0, "column": "trips", "value": "700"},
        {"row": 0, "column": "trips", "value": True},
        {"row": 1, "column": "trips", "value": 700},
        {"row": 0, "column": "secret", "value": 700},
    ],
)
def test_invented_values_and_cells_rejected(cell):
    with pytest.raises(InvalidInputError):
        research.verify_synthesis(
            {"status": "supported", "cells": [cell]}, evidence([{"trips": 700}]), []
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "supported", "cells": []},
        {
            "status": "insufficient",
            "cells": [{"row": 0, "column": "trips", "value": 700}],
        },
        {
            "status": "insufficient",
            "quotes": [{"source_id": "source:foreign", "quote": "invented"}],
        },
    ],
)
def test_unsupported_findings_and_quotes_rejected(payload):
    with pytest.raises(InvalidInputError):
        research.verify_synthesis(payload, evidence([{"trips": 700}]), [])


def test_modified_evidence_cannot_be_synthesized():
    value = evidence([{"trips": 700}])
    value["rows"][0]["trips"] = 42
    with pytest.raises(InvalidInputError):
        research.verify_synthesis({"status": "insufficient"}, value, [])


@pytest.mark.asyncio
async def test_async_graph_uses_existing_provisioning_and_no_tools(monkeypatch):
    model = AsyncMock()
    model.ainvoke.return_value = AIMessage(content='{"action":"unsupported"}')
    provision = AsyncMock(return_value=model)
    monkeypatch.setattr(database_research, "provision_langchain_model", provision)
    result = await database_research.graph.ainvoke(  # type: ignore[call-overload]
        {
            "phase": "plan",
            "model_id": "model:chosen",
            "input": {"question": "Delete records"},
        }
    )
    assert result["output"]["action"] == "unsupported"
    assert provision.await_args is not None
    assert provision.await_args.args[1:3] == ("model:chosen", "chat")
    assert not model.bind_tools.called


@pytest.mark.asyncio
async def test_invalid_model_json_fails_closed(monkeypatch):
    model = AsyncMock()
    model.ainvoke.return_value = AIMessage(content="DELETE FROM data")
    monkeypatch.setattr(
        database_research, "provision_langchain_model", AsyncMock(return_value=model)
    )
    with pytest.raises(InvalidInputError):
        await database_research.graph.ainvoke(  # type: ignore[call-overload]
            {"phase": "plan", "model_id": None, "input": {}}
        )


@pytest.mark.asyncio
async def test_disabled_research_preserves_upstream(monkeypatch):
    monkeypatch.setenv("DATABRIDGE_RESEARCH_ENABLED", "false")
    assert (
        await research.prepare("session", "notebook", "question", {}, None, []) is None
    )


@pytest.mark.asyncio
async def test_changed_catalog_invalidates_before_execution(monkeypatch):
    monkeypatch.setattr(
        research, "context", AsyncMock(return_value={"fingerprint": "new"})
    )
    with pytest.raises(InvalidInputError, match="changed"):
        await research.current(
            {"notebook_id": "notebook:1", "payload": {"catalog_fingerprint": "old"}}
        )


def test_no_sensitive_values_in_new_model_prompts():
    # Input schema offers no credential, path, tool or execution argument.
    from open_notebook.databridge.research_models import Proposal

    assert set(Proposal.model_fields) == {
        "action",
        "import_id",
        "sql",
        "year_column",
        "value_column",
    }


def test_metadata_is_not_executable_markdown():
    assert "![" not in research.text("![tracker](https://evil.test) <script>")


def test_sql_literal_cannot_terminate_markdown_code_block():
    from open_notebook.databridge.research_models import Synthesis

    sql = "SELECT year FROM data WHERE note='```\n![tracker](https://evil.test)' LIMIT 100"
    answer, _ = research.render_answer(
        Synthesis(status="insufficient"),
        {
            "evidence": {
                **evidence([]),
                "id": "run:1",
                "plan_id": "plan:1",
                "sql": sql,
            },
            "dataset": {
                "title": "Synthetic",
                "dataset_id": "dataset:1",
                "version_id": "v1",
                "database_sha256": "hash",
            },
            "proposal": {},
            "documents": [],
        },
    )
    assert "Executed SQL:\n````sql\n" + sql + "\n````" in answer


@pytest.mark.parametrize(
    "field", ["plan_id", "sql", "version_id", "connection_id", "dataset_sha256"]
)
def test_evidence_cannot_be_rebound_to_another_query_or_version(field):
    payload = {
        "plan": {"id": "plan:1", "sql": "SELECT SUM(trips) FROM data LIMIT 100"},
        "dataset": {
            "version_id": "v1",
            "connection_id": "c1",
            "database_sha256": "hash",
        },
        "evidence": {
            "plan_id": "plan:1",
            "sql": "SELECT SUM(trips) FROM data LIMIT 100",
            "version_id": "v1",
            "connection_id": "c1",
            "dataset_sha256": "hash",
        },
    }
    research.verify_binding(payload)
    payload["evidence"][field] = "foreign"
    with pytest.raises(InvalidInputError, match="approved dataset/version"):
        research.verify_binding(payload)


@pytest.mark.parametrize(
    "rows",
    [
        [{"year": 2022, "trips": 1}, {"year": 2022, "trips": 2}],
        [{"year": 2022, "trips": None}, {"year": 2023, "trips": 2}],
        [{"year": "2022.5", "trips": 1}, {"year": 2023, "trips": 2}],
        [{"year": 2022, "trips": "NaN"}, {"year": 2023, "trips": 2}],
        [{"year": 2000 + i, "trips": i} for i in range(100)],
    ],
)
def test_invalid_or_possibly_truncated_trends_have_no_chart(rows):
    from open_notebook.databridge.research_models import Synthesis

    payload = {
        "evidence": {
            **evidence(rows),
            "id": "run:1",
            "plan_id": "plan:1",
            "sql": "SELECT year, trips FROM data LIMIT 100",
        },
        "dataset": {
            "title": "Synthetic",
            "dataset_id": "dataset:1",
            "version_id": "v1",
            "database_sha256": "hash",
        },
        "proposal": {"year_column": "year", "value_column": "trips"},
        "documents": [],
    }
    answer, chart = research.render_answer(Synthesis(status="supported"), payload)
    assert chart is None
    assert "trend could not be verified" in answer


@pytest.mark.asyncio
async def test_recovery_loser_cannot_overwrite_an_active_synthesis(monkeypatch):
    monkeypatch.setattr(
        research,
        "repo_query",
        AsyncMock(
            side_effect=[[{"id": "run:1", "payload": {"status": "success"}}], []]
        ),
    )
    synthesis = AsyncMock()
    monkeypatch.setattr(research, "synthesize", synthesis)
    with pytest.raises(InvalidInputError, match="already claimed"):
        await research.resume(
            {
                "id": "db_research_turn:1",
                "notebook_id": "notebook:1",
                "state": "executing",
                "payload": {"deadline": "2000-01-01", "plan": {"id": "plan:1"}},
            }
        )
    synthesis.assert_not_awaited()
