"""Notebook-scoped research orchestration around the unchanged P2 authority gate."""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from open_notebook.database.repository import ensure_record_id, repo_query, repo_upsert
from open_notebook.databridge.correlation import usage_context
from open_notebook.databridge.ingestion import catalog
from open_notebook.databridge.ingestion.service import job_for, notebook_context
from open_notebook.databridge.mcp import service as mcp
from open_notebook.databridge.mcp.client import digest
from open_notebook.databridge.mcp.models import ConnectionSpec
from open_notebook.databridge.research_models import Proposal, Synthesis
from open_notebook.domain.notebook import ChatSession, Source
from open_notebook.exceptions import InvalidInputError, NotFoundError, OpenNotebookError
from open_notebook.graphs.database_research import ResearchState, graph


def enabled() -> bool:
    return os.getenv("DATABRIDGE_RESEARCH_ENABLED", "false").lower() == "true"


def require_enabled():
    if not enabled():
        raise NotFoundError("Conversational database research is disabled")
    catalog.enabled()


def deadline():
    return (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()


def text(value) -> str:
    # Metadata/result text is evidence, not Markdown links, HTML or instructions.
    return re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", str(value)).replace("\n", " ")[
        :1000
    ]


async def session_scope(session_id: str, notebook_id: str):
    require_enabled()
    await ChatSession.get(session_id)
    linked = await repo_query(
        "SELECT id FROM refers_to WHERE in=$chat_session AND out=$notebook",
        {
            "chat_session": ensure_record_id(session_id),
            "notebook": ensure_record_id(notebook_id),
        },
    )
    if not linked:
        raise NotFoundError("Research session not available in this notebook")


async def context(notebook_id: str) -> dict:
    """Same service as the P3 dataset context API, filtered to current authority."""
    raw = await notebook_context(notebook_id)
    datasets = []
    for item in raw["datasets"]:
        connection = await mcp.connection_for(item["connection_id"], notebook_id)
        spec = ConnectionSpec(**connection.spec)
        if (
            not connection.approved_fingerprint
            or spec.backend != "duckdb"
            or spec.version_id != item["version_id"]
        ):
            continue
        allowed = spec.tables.get(item["table"], [])
        columns = [c for c in item["columns"] if c["column"] in allowed]
        if not columns:
            continue
        job = await job_for(item["import_id"], notebook_id)
        payload = job["payload"]
        metadata = payload["catalog_snapshot"]["metadata"].get("dcat", {})
        datasets.append(
            {
                **item,
                "columns": columns,
                "connection_revision": connection.revision,
                "publisher": payload["catalog_snapshot"]["publisher"],
                "description": payload["catalog_snapshot"].get("description", "")[
                    :4000
                ],
                "temporal": metadata.get("temporal"),
                "spatial": metadata.get("spatial"),
                "license": metadata.get("license"),
                "rights": metadata.get("rights"),
                "download_url": payload["download"]["final_url"],
                "retrieved_at": payload["download"]["retrieved_at"],
                "schema_sha256": payload["manifest"]["schema_sha256"],
                "semantic_status": "publisher metadata only; cross-source geography/time/units not certified",
            }
        )
    datasets.sort(key=lambda item: item["import_id"])
    # Fail closed instead of quietly omitting available versions from the planner.
    if len(datasets) > 20 or len(json.dumps(datasets).encode()) > 80000:
        raise InvalidInputError("Notebook dataset context exceeds the research limit")
    return {
        "datasets": datasets,
        "fingerprint": digest(datasets),
        "sql_policy": raw["sql_policy"],
    }


async def documents(notebook_id: str, selected: dict) -> list[dict]:
    result = []
    sources = selected.get("sources", [])
    if not isinstance(sources, list):
        raise InvalidInputError("Selected document context must be a list")
    for item in sources[:5]:
        source_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(source_id, str) or not source_id.startswith("source:"):
            continue
        linked = await repo_query(
            "SELECT id FROM reference WHERE in=$source AND out=$notebook",
            {
                "source": ensure_record_id(source_id),
                "notebook": ensure_record_id(notebook_id),
            },
        )
        if not linked:
            continue
        source = await Source.get(source_id)
        excerpt = (source.full_text or "")[:3000]
        result.append(
            {
                "source_id": source_id,
                "title": source.title,
                "excerpt": excerpt,
                "sha256": digest(excerpt),
            }
        )
    return result


async def model_call(
    phase: str, payload: dict, model_id: str | None, session_id: str, notebook_id: str
) -> dict:
    with usage_context(
        session_id=session_id,
        notebook_id=notebook_id,
        research_phase=phase,
        task="database_" + phase,
    ):
        state: ResearchState = {"phase": phase, "model_id": model_id, "input": payload}
        result = await graph.ainvoke(state)  # type: ignore[arg-type]
    return result["output"]


async def save(turn: dict, state: str):
    turn["state"] = state
    await repo_upsert(
        "db_research_turn",
        turn["id"],
        {k: turn[k] for k in ("state", "session_id", "notebook_id", "payload")},
        True,
    )


def message(turn: dict) -> AIMessage:
    return AIMessage(
        id="research-" + turn["id"].split(":", 1)[1],
        content=turn["payload"]["answer"],
        additional_kwargs={"database_turn_id": turn["id"]},
    )


async def checkpoint(turn: dict):
    from open_notebook.graphs.chat import graph as chat_graph

    await asyncio.to_thread(
        chat_graph.update_state,
        RunnableConfig(configurable={"thread_id": turn["session_id"]}),
        {"messages": [message(turn)]},
    )


async def get(turn_id: str, session_id: str, notebook_id: str) -> dict:
    await session_scope(session_id, notebook_id)
    if not re.fullmatch(r"db_research_turn:[a-f0-9]{32}", turn_id):
        raise NotFoundError("Research turn not found")
    rows = await repo_query("SELECT * FROM $id", {"id": ensure_record_id(turn_id)})
    if (
        not rows
        or rows[0]["session_id"] != session_id
        or rows[0]["notebook_id"] != notebook_id
    ):
        raise NotFoundError("Research turn not available in this session")
    if dataset := rows[0]["payload"].get("dataset"):
        await mcp.connection_for(dataset["connection_id"], notebook_id, active=False)
    return rows[0]


def public(turn: dict) -> dict:
    return {
        "id": turn["id"],
        "state": turn["state"],
        "session_id": turn["session_id"],
        "notebook_id": turn["notebook_id"],
        **turn["payload"],
    }


async def prepare(
    session_id: str,
    notebook_id: str,
    question: str,
    selected: dict,
    model_id: str | None,
    history: list,
) -> dict | None:
    if not enabled():
        return None
    await session_scope(session_id, notebook_id)
    if len(question) > 5000:
        raise InvalidInputError(
            "Database research questions are limited to 5000 characters"
        )
    available = await context(notebook_id)
    if not available["datasets"]:
        return None
    docs = await documents(notebook_id, selected)
    proposal = Proposal(
        **await model_call(
            "plan",
            {
                "question": question,
                "datasets": available["datasets"],
                "documents": docs,
                "history": [
                    {"role": m.type, "text": str(m.content)[:2000]}
                    for m in history[-6:]
                ],
            },
            model_id,
            session_id,
            notebook_id,
        )
    )
    if proposal.action == "document":
        return None
    turn: dict = {
        "id": "db_research_turn:" + uuid4().hex,
        "session_id": session_id,
        "notebook_id": notebook_id,
        "payload": {
            "question": question,
            "model_id": model_id,
            "catalog_fingerprint": available["fingerprint"],
            "documents": docs,
        },
    }
    refusal = {
        "insufficient": "Insufficient data: clarify the dataset/version, reporting grain, dates or required denominator before querying.",
        "incompatible": "Comparison unavailable: geography, temporal granularity or measurement units have not been verified as compatible.",
        "unsupported": "Unsupported analysis: cross-table SQL, unrestricted operations, forecasts and causal claims are not authorized. Use a reviewed analytical dataset or a supported single-table question.",
    }
    if proposal.action != "query":
        turn["payload"]["answer"] = refusal[proposal.action]
        await save(turn, "blocked")
        return turn
    chosen = next(
        (d for d in available["datasets"] if d["import_id"] == proposal.import_id), None
    )
    if not chosen:
        turn["payload"]["answer"] = (
            "Query rejected: the model selected a dataset outside the active notebook's approved context."
        )
        await save(turn, "blocked")
        return turn
    try:
        plan = await mcp.plan(
            chosen["connection_id"], notebook_id, proposal.sql, None, {}
        )
    except (InvalidInputError, NotFoundError):
        turn["payload"]["answer"] = (
            "Query rejected by the database authorization policy. No SQL was executed. Ask a new supported question."
        )
        await save(turn, "blocked")
        return turn
    plan.pop(
        "approval_token"
    )  # Review explicitly issues a fresh token; never checkpoint it.
    turn["payload"].update(
        dataset=chosen,
        plan=plan,
        proposal=proposal.model_dump(),
        answer="A database query is proposed. Review its dataset version and canonical SQL, then explicitly approve execution. No database findings are available yet.",
    )
    await save(turn, "awaiting_review")
    return turn


async def current(turn: dict):
    available = await context(turn["notebook_id"])
    if available["fingerprint"] != turn["payload"]["catalog_fingerprint"]:
        raise InvalidInputError(
            "Dataset context or permissions changed; ask a new question"
        )


async def review(turn: dict) -> dict:
    if "plan" not in turn["payload"]:
        raise InvalidInputError("This turn has no authorized SQL proposal")
    await current(turn)
    claimed = await repo_query(
        "UPDATE $id SET state='reviewing', payload.deadline=$deadline WHERE state IN ['awaiting_review','awaiting_approval','failed'] OR (state='reviewing' AND payload.deadline < $now) RETURN AFTER",
        {"id": ensure_record_id(turn["id"]), "deadline": deadline(), "now": mcp.now()},
    )
    if not claimed:
        raise InvalidInputError("Research turn is active or complete")
    try:
        old = turn["payload"]["plan"]
        await repo_query(
            "UPDATE $id SET state='superseded' WHERE state='pending'",
            {"id": ensure_record_id(old["id"])},
        )
        plan = await mcp.plan(
            turn["payload"]["dataset"]["connection_id"],
            turn["notebook_id"],
            old["sql"],
            None,
            {},
        )
        approval = plan.pop("approval_token")
        turn["payload"]["plan"] = plan
        await save(turn, "awaiting_approval")
        return {**public(turn), "approval_token": approval}
    except Exception:
        await save(turn, "failed")
        raise


def verify_binding(payload: dict):
    run, plan, dataset = payload["evidence"], payload["plan"], payload["dataset"]
    if (
        run.get("plan_id") != plan["id"]
        or run.get("sql") != plan["sql"]
        or run.get("version_id") != dataset["version_id"]
        or run.get("connection_id") != dataset["connection_id"]
        or run.get("dataset_sha256") != dataset["database_sha256"]
    ):
        raise InvalidInputError(
            "Query evidence does not match the approved dataset/version"
        )


def verify_synthesis(output: dict, evidence: dict, docs: list[dict]) -> Synthesis:
    answer = Synthesis(**output)
    if (
        evidence.get("status") != "success"
        or digest(evidence["rows"]) != evidence["result_sha256"]
    ):
        raise InvalidInputError("Evidence integrity validation failed")
    if answer.status == "supported" and not answer.cells:
        raise InvalidInputError("A supported answer must cite result cells")
    if answer.status == "insufficient" and answer.cells:
        raise InvalidInputError("Insufficient evidence cannot include findings")
    for cell in answer.cells:
        if (
            cell.row >= len(evidence["rows"])
            or cell.column not in evidence["rows"][cell.row]
        ):
            raise InvalidInputError("Model cited an unavailable result cell")
        actual = evidence["rows"][cell.row][cell.column]
        if type(actual) is not type(cell.value) or actual != cell.value:
            raise InvalidInputError(
                "Model numeric/value claim does not match executed evidence"
            )
    for quote in answer.quotes:
        source = next((d for d in docs if d["source_id"] == quote.source_id), None)
        if not source or quote.quote not in source["excerpt"]:
            raise InvalidInputError("Model document citation is not a verified excerpt")
    return answer


def render_answer(answer: Synthesis, payload: dict) -> tuple[str, dict | None]:
    evidence, dataset = payload["evidence"], payload["dataset"]
    # SQL literals may contain Markdown fences; preserve the exact executed SQL
    # without letting a literal terminate its code block in chat.
    fence = "`" * max(
        3, 1 + max((len(s) for s in re.findall(r"`+", evidence["sql"])), default=0)
    )
    lines = ["Database evidence for " + text(dataset["title"]) + "."]
    if answer.status == "insufficient":
        lines.append(
            "The executed query returned insufficient evidence to answer this question. No finding is asserted."
        )
    else:
        lines.append("The executed query returned these verified values:")
        for cell in answer.cells:
            lines.append(
                f"- Result row {cell.row + 1}, {text(cell.column)}: {text(cell.value)}."
            )
    chart = None
    proposal = payload["proposal"]
    year, value = proposal.get("year_column"), proposal.get("value_column")
    if answer.status == "supported" and year and value:
        try:
            rows = evidence["rows"]
            if any(
                isinstance(r[year], bool)
                or str(int(r[year])) != str(r[year])
                or not 1000 <= int(r[year]) <= 9999
                for r in rows
            ):
                raise ValueError()
            points = sorted([(int(r[year]), Decimal(str(r[value]))) for r in rows])
            if (
                len(points) < 2
                or len({p[0] for p in points}) != len(points)
                or len(rows) >= 100
                or any(not v.is_finite() for _, v in points)
            ):
                raise ValueError()
            change = points[-1][1] - points[0][1]
            lines.append(
                f"Across the returned years {points[0][0]} to {points[-1][0]}, {text(value)} changed by {change}. Missing years are not treated as zero."
            )
            chart = {
                "year_column": year,
                "value_column": value,
                "points": [{"year": y, "value": str(v)} for y, v in points],
                "change": str(change),
            }
        except (KeyError, ValueError, TypeError, InvalidOperation):
            lines.append(
                "A trend could not be verified from unique, complete numeric year/value results."
            )
    for quote in answer.quotes:
        doc = next(d for d in payload["documents"] if d["source_id"] == quote.source_id)
        lines.append(
            "Notebook document evidence (distinct from database results): "
            + text(quote.quote)
            + " ["
            + text(doc["source_id"])
            + "; snapshot SHA-256 "
            + doc["sha256"]
            + "]"
        )
    lines.extend(
        [
            "Attribution: dataset "
            + text(dataset["dataset_id"])
            + "; immutable version "
            + dataset["version_id"]
            + "; evidence "
            + evidence["id"]
            + "; query plan "
            + evidence["plan_id"]
            + ".",
            "Executed SQL:\n" + fence + "sql\n" + evidence["sql"] + "\n" + fence,
            "Result SHA-256: "
            + evidence["result_sha256"]
            + ". Database SHA-256: "
            + dataset["database_sha256"]
            + ".",
            "These findings describe only the selected dataset and returned query scope. Synthetic fixtures are not official DOT findings. Geography, time support and units are not certified for cross-source comparisons; no causal inference is made.",
        ]
    )
    return "\n\n".join(lines), chart


async def synthesize(turn: dict) -> dict:
    claimed = await repo_query(
        "UPDATE $id SET state='synthesizing', payload.deadline=$deadline WHERE state IN ['evidence_ready','answer_failed'] OR (state='synthesizing' AND payload.deadline < $now) RETURN AFTER",
        {"id": ensure_record_id(turn["id"]), "deadline": deadline(), "now": mcp.now()},
    )
    if not claimed:
        raise InvalidInputError("Answer generation is active or unavailable")
    turn = claimed[0]
    payload = turn["payload"]
    try:
        verify_binding(payload)
        output = await model_call(
            "synthesize",
            {
                "question": payload["question"],
                "dataset": payload["dataset"],
                "evidence": payload["evidence"],
                "documents": payload["documents"],
            },
            payload.get("model_id"),
            turn["session_id"],
            turn["notebook_id"],
        )
        verified = verify_synthesis(output, payload["evidence"], payload["documents"])
        payload["answer"], payload["chart"] = render_answer(verified, payload)
        payload["verification"] = {
            "method": "exact-result-cell-and-document-excerpt",
            "result_sha256": payload["evidence"]["result_sha256"],
        }
        await save(turn, "completed")
    except OpenNotebookError:
        payload["answer"] = (
            "The query evidence was saved, but an answer could not be verified or the model was unavailable. No unsupported findings are shown. Resume answer generation without rerunning SQL, or ask a new question."
        )
        await save(turn, "answer_failed")
    await checkpoint(turn)
    return public(turn)


async def execute(turn: dict, plan_id: str, approval_token: str) -> dict:
    await current(turn)
    claimed = await repo_query(
        "UPDATE $id SET state='executing', payload.deadline=$deadline WHERE state='awaiting_approval' AND payload.plan.id=$plan RETURN AFTER",
        {"id": ensure_record_id(turn["id"]), "plan": plan_id, "deadline": deadline()},
    )
    if not claimed:
        raise InvalidInputError("Research approval is stale or already used")
    turn = claimed[0]
    try:
        evidence = await mcp.execute(plan_id, approval_token, turn["notebook_id"])
    except OpenNotebookError:
        turn["payload"]["answer"] = (
            "Database query failed or approval was invalid/expired. No result is asserted. Review a fresh plan before retrying."
        )
        await save(turn, "failed")
        await checkpoint(turn)
        return public(turn)
    turn["payload"]["evidence"] = evidence
    await save(turn, "evidence_ready")
    return await synthesize(turn)


async def resume(turn: dict) -> dict:
    # Reconcile a crash after MCP persisted success but before the turn stored it.
    # Never execute SQL again; a claimed one-use approval remains consumed.
    if turn["state"] == "executing" and turn["payload"].get("deadline", "") < mcp.now():
        runs = await repo_query(
            "SELECT * FROM db_query_run WHERE payload.plan_id=$plan AND payload.notebook_id=$notebook AND payload.status='success'",
            {"plan": turn["payload"]["plan"]["id"], "notebook": turn["notebook_id"]},
        )
        if len(runs) != 1:
            raise InvalidInputError(
                "Execution outcome is not a unique successful result; inspect query evidence and ask a new question"
            )
        recovered = await repo_query(
            "UPDATE $id SET state='evidence_ready', payload.evidence=$evidence WHERE state='executing' AND payload.deadline < $now RETURN AFTER",
            {
                "id": ensure_record_id(turn["id"]),
                "evidence": {"id": runs[0]["id"], **runs[0]["payload"]},
                "now": mcp.now(),
            },
        )
        if not recovered:
            raise InvalidInputError("Execution recovery is already claimed")
        turn = recovered[0]
    await mcp.connection_for(
        turn["payload"]["dataset"]["connection_id"], turn["notebook_id"]
    )
    return await synthesize(turn)
