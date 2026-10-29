"""Real API -> LangGraph -> Esperanto -> LiteLLM -> MCP acceptance, synthetic model/data."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

from open_notebook.database.repository import ensure_record_id, repo_query

STATE = Path("/app/data/p4-acceptance.json")
CHECKS = []


def check(value, label):
    assert value, label
    CHECKS.append(label)
    print("PASS:", label, flush=True)


async def main(mode):
    assert os.getenv("DATAGOV_API_KEY") == "p3-synthetic-catalog-key-only"
    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer p1-fixture-password-only"},
        timeout=240,
    ) as client:

        async def api(method, path, body=None, expected=200):
            response = await client.request(method, path, json=body)
            assert response.status_code == expected, (
                path,
                response.status_code,
                response.text[:500],
            )
            return response.json()

        if mode == "seed":
            notebook = (
                await api(
                    "POST",
                    "/notebooks",
                    {
                        "name": "P4 synthetic transit research",
                        "description": "Not real DOT findings",
                    },
                )
            )["id"]
            session = (
                await api(
                    "POST",
                    "/chat/sessions",
                    {
                        "notebook_id": notebook,
                        "title": "Research before and after import",
                    },
                )
            )["id"]
            state = {"notebook": notebook, "session": session}
        else:
            state = json.loads(STATE.read_text())
            notebook, session = state["notebook"], state["session"]
        scope = {"notebook_id": notebook, "session_id": session}

        async def chat(question, selected=None):
            return await api(
                "POST",
                "/chat/execute",
                {"session_id": session, "message": question, "context": selected or {}},
            )

        async def get(turn, alternate=None):
            target = alternate or scope
            return await api(
                "GET",
                "/databridge/research/"
                + turn["id"]
                + "?session_id="
                + target["session_id"]
                + "&notebook_id="
                + target["notebook_id"],
            )

        async def ask(question, selected=None):
            response = await chat(question, selected)
            message = response["messages"][-1]
            check(
                bool(message.get("database_turn_id")),
                "Current notebook chat routes database question to research workflow",
            )
            return await get({"id": message["database_turn_id"]})

        async def review(turn):
            return await api(
                "POST", "/databridge/research/" + turn["id"] + "/review", scope
            )

        async def execute(turn, token=None, expected=200):
            return await api(
                "POST",
                "/databridge/research/" + turn["id"] + "/execute",
                {
                    **scope,
                    "plan_id": turn["plan"]["id"],
                    "approval_token": token or turn["approval_token"],
                },
                expected,
            )

        async def runs(turn):
            return await repo_query(
                "SELECT * FROM db_query_run WHERE payload.plan_id=$plan",
                {"plan": turn["plan"]["id"]},
            )

        async def import_resource(resource):
            checked = await api(
                "POST", "/databridge/catalog/resources/" + resource + "/preflight"
            )
            assert checked["status"] == "ready", checked
            job = await api(
                "POST",
                "/databridge/imports",
                {
                    "resource_id": resource,
                    "notebook_id": notebook,
                    "idempotency_key": str(uuid4()),
                },
            )
            for _ in range(90):
                current = await api(
                    "GET",
                    "/databridge/imports/" + job["id"] + "?notebook_id=" + notebook,
                )
                if current["status"] not in {"queued", "running"}:
                    assert current["status"] == "ready", current.get("error")
                    return current
                await asyncio.sleep(1)
            raise AssertionError("Import timed out")

        if mode == "seed":
            anonymous = await client.get(
                "/databridge/research/db_research_turn:unauthorized",
                params=scope,
                headers={"Authorization": ""},
            )
            check(
                anonymous.status_code == 401,
                "Research routes retain application authentication",
            )
            plain = await chat("Hello before importing")
            check(
                plain["messages"][-1]["content"] == "The fixture answer is 42.",
                "Existing notebook chat works before any dataset is imported",
            )
            page = await api(
                "GET", "/databridge/catalog/search?q=National%20Transit%20Database"
            )
            detail = await api(
                "GET", "/databridge/catalog/datasets/" + page["results"][0]["id"]
            )
            resource = next(
                r["id"]
                for r in detail["resources"]
                if r["metadata"]["title"] == "Synthetic CSV"
            )
            imported = await import_resource(resource)
            check(
                imported["profile"]["rows"] == 4,
                "Search, inspect, preview and Import complete through DataBridge's real worker",
            )
            state.update(resource=resource, imported=imported)
            total = await ask("What is the total unlinked passenger trips?")
            check(
                total["state"] == "awaiting_review"
                and total["dataset"]["version_id"] == imported["version_id"],
                "New import is available in the same pre-existing chat without registration or reload",
            )
            check(
                await runs(total) == [],
                "Generated SQL is only a proposal; planning does not execute MCP",
            )
            reviewed = await review(total)
            check(
                "SUM(" in reviewed["plan"]["sql"]
                and "LIMIT 100" in reviewed["plan"]["sql"],
                "Review shows Phase 2 canonical authorized SQL and bounded limit",
            )
            history = await api("GET", "/chat/sessions/" + session)
            check(
                reviewed["approval_token"] not in json.dumps(history)
                and "approval_token" not in json.dumps(await get(total)),
                "Approval bearer is absent from checkpoint and durable research response",
            )
            completed = await execute(reviewed)
            check(
                completed["state"] == "completed"
                and completed["evidence"]["rows"] == [{"trips": 700}],
                "Natural-language total executes through real MCP and returns exactly 700",
            )
            check(
                completed["verification"]["result_sha256"]
                == completed["evidence"]["result_sha256"],
                "Answer numeric claims are checked against the exact stored result hash",
            )
            check(
                all(
                    value in completed["answer"]
                    for value in [
                        imported["version_id"],
                        completed["evidence"]["id"],
                        completed["plan"]["id"],
                        imported["manifest"]["sha256"],
                    ]
                ),
                "Answer identifies immutable dataset, executed query, evidence and database hash",
            )
            evidence = await api(
                "GET",
                "/databridge/evidence/"
                + completed["evidence"]["id"]
                + "?notebook_id="
                + notebook,
            )
            check(
                evidence["result_sha256"] == completed["evidence"]["result_sha256"],
                "Existing evidence viewer returns the same query result attribution",
            )
            await execute(reviewed, expected=400)
            check(
                len(await runs(reviewed)) == 1, "One-time approval cannot execute twice"
            )
            state["total"] = completed

            source = await api(
                "POST",
                "/sources/json",
                {
                    "type": "text",
                    "content": "Synthetic transit fixture: unlinked passenger trips count boardings, not unique people.",
                    "title": "Measurement definition",
                    "notebooks": [notebook],
                    "embed": False,
                    "async_processing": True,
                    "transformations": [],
                },
            )
            for _ in range(50):
                doc = await api("GET", "/sources/" + source["id"])
                if doc.get("full_text"):
                    break
                await asyncio.sleep(0.3)
            selected = {
                "sources": [{"id": source["id"], "full_text": "FORGED CLIENT QUOTE"}]
            }
            trend = await execute(
                await review(
                    await ask("Show the annual trend and document definition", selected)
                )
            )
            check(
                trend["state"] == "completed"
                and trend["chart"]["change"] == "150"
                and [p["year"] for p in trend["chart"]["points"]]
                == [2022, 2023, 2024, 2025],
                "Verified annual trend shows four known years and deterministic change of 150",
            )
            check(
                "boardings" in trend["answer"]
                and source["id"] in trend["answer"]
                and "FORGED CLIENT" not in trend["answer"],
                "Answer combines database cells and an independently verified notebook excerpt",
            )
            check(
                "not official DOT findings" in trend["answer"],
                "Synthetic findings carry explicit provenance and causal/compatibility caveats",
            )
            state["trend"] = trend

            for question, expected in [
                ("unsafe query", "blocked"),
                ("outside notebook dataset", "blocked"),
                ("join two tables", "blocked"),
                ("incompatible units comparison", "blocked"),
                ("weather caused transit changes", "blocked"),
                ("missing denominator", "blocked"),
            ]:
                rejected = await ask(question)
                check(
                    rejected["state"] == expected and "evidence" not in rejected,
                    question + " is rejected without findings",
                )
            empty = await execute(await review(await ask("Return empty year results")))
            check(
                empty["state"] == "completed"
                and empty["evidence"]["rows"] == []
                and "insufficient evidence" in empty["answer"],
                "Empty query explicitly reports insufficient evidence rather than inventing zero",
            )
            invalid = await execute(
                await review(await ask("Return an invalid numeric claim"))
            )
            check(
                invalid["state"] == "answer_failed"
                and "999999" not in invalid["answer"]
                and invalid["evidence"]["rows"] == [{"trips": 700}],
                "Fabricated model numeric claim is rejected while real evidence remains intact",
            )

            expired = await review(await ask("Total trips with expired approval"))
            await repo_query(
                "UPDATE $id SET expires_at='2000-01-01'",
                {"id": ensure_record_id(expired["plan"]["id"])},
            )
            denied = await execute(expired)
            check(
                denied["state"] == "failed"
                and not any(
                    r["payload"]["status"] == "success" for r in await runs(expired)
                ),
                "Expired approval never reaches successful MCP execution",
            )
            wrong = await review(await ask("Total trips with invalid token"))
            check(
                (await execute(wrong, "invalid"))["state"] == "failed",
                "Invalid approval token cannot authorize model-generated SQL",
            )

            other = (await api("POST", "/notebooks", {"name": "Excluded P4 scope"}))[
                "id"
            ]
            await api(
                "GET",
                "/databridge/research/"
                + total["id"]
                + "?session_id="
                + session
                + "&notebook_id="
                + other,
                expected=404,
            )
            other_session = (
                await api("POST", "/chat/sessions", {"notebook_id": notebook})
            )["id"]
            await api(
                "GET",
                "/databridge/research/"
                + total["id"]
                + "?session_id="
                + other_session
                + "&notebook_id="
                + notebook,
                expected=404,
            )
            check(
                True,
                "Research records require both the correct notebook and chat session",
            )

            async with httpx.AsyncClient() as fixture:
                await fixture.post("http://fixture:8080/synthesis-failure/true")
                try:
                    failed = await execute(
                        await review(
                            await ask("Total trips with synthesis interruption")
                        )
                    )
                    check(
                        failed["state"] == "answer_failed"
                        and failed["evidence"]["rows"] == [{"trips": 700}],
                        "Provider failure after execution saves evidence without inventing an answer",
                    )
                finally:
                    await fixture.post("http://fixture:8080/synthesis-failure/false")
            resumed = await api(
                "POST", "/databridge/research/" + failed["id"] + "/resume", scope
            )
            check(
                resumed["state"] == "completed" and len(await runs(failed)) == 1,
                "Explicit synthesis retry uses saved evidence without rerunning SQL",
            )

            stale = await review(await ask("Total trips before a dataset change"))
            new_import = await import_resource(resource)
            await execute(stale, expected=400)
            check(
                await runs(stale) == [],
                "New dataset version invalidates an earlier conversational approval",
            )
            old = await get(total)
            check(
                old["evidence"]["version_id"] == imported["version_id"]
                and new_import["version_id"] != imported["version_id"],
                "Historical answer remains attributed to its original immutable version",
            )
            pending = await review(await ask("Total trips pending a restart"))
            state["pending"] = pending
            regular = await chat("Hello documents")
            check(
                regular["messages"][-1]["content"] == "The fixture answer is 42.",
                "Document/general chat still uses the original LangGraph model node",
            )
            for _ in range(60):
                usage = await api("GET", "/databridge/usage")
                rows = [r for r in usage["records"] if r["session_id"] == session]
                if {"database_plan", "database_synthesize"} <= {
                    r["task"] for r in rows
                }:
                    break
                await asyncio.sleep(1)
            check(
                {"database_plan", "database_synthesize"} <= {r["task"] for r in rows}
                and all(
                    r["input_tokens"] is not None
                    for r in rows
                    if r["status"] == "success"
                ),
                "Actual LiteLLM usage persists for both research phases with notebook/session attribution",
            )
            state["usage_ids"] = [r["request_id"] for r in rows]
            public_evidence = json.dumps(await get(total))
            check(
                not any(
                    secret in public_evidence
                    for secret in [
                        os.environ["DATABRIDGE_DUCKDB_TOKEN"],
                        os.environ["DATAGOV_API_KEY"],
                    ]
                ),
                "Chat research evidence contains no catalog or MCP service credentials",
            )
        elif mode == "outage":
            reviewed = await review(await ask("Total trips during broker outage"))
            failed = await execute(reviewed)
            check(
                failed["state"] == "failed" and "evidence" not in failed,
                "Real broker outage yields failed conversation state without fabricated results",
            )
            check(
                any(r["payload"]["status"] == "failed" for r in await runs(reviewed)),
                "Broker failure retains normal Phase 2 query audit evidence",
            )
            state["outage"] = failed
        elif mode == "recover":
            done = await execute(await review(state["outage"]))
            check(
                done["state"] == "completed"
                and done["evidence"]["rows"] == [{"trips": 700}],
                "Service recovery requires fresh review/approval and returns verified results",
            )
        elif mode == "recovery":
            before = await api("GET", "/chat/sessions/" + session)
            response = await client.post(
                "/chat/execute",
                json={
                    "session_id": session,
                    "message": "provider outage",
                    "context": {},
                },
            )
            after = await api("GET", "/chat/sessions/" + session)
            check(
                response.status_code >= 400 and before["messages"] == after["messages"],
                "Planning provider outage leaves existing chat history intact",
            )

            revoked = await review(await ask("Total trips with changed permissions"))
            connection_id = revoked["dataset"]["connection_id"]
            await repo_query(
                "UPDATE $id SET spec.enabled=false",
                {"id": ensure_record_id(connection_id)},
            )
            try:
                await execute(revoked, expected=400)
                check(
                    await runs(revoked) == [],
                    "Disabled connection invalidates conversational approval before execution",
                )
            finally:
                await repo_query(
                    "UPDATE $id SET spec.enabled=true",
                    {"id": ensure_record_id(connection_id)},
                )

            interrupted = await review(
                await ask("Total trips with interrupted checkpoint")
            )
            # Simulate the exact crash boundary: the normal MCP API persists a run,
            # but the research turn has not stored the returned evidence yet.
            await repo_query(
                "UPDATE $id SET state='executing', payload.deadline='2000-01-01'",
                {"id": ensure_record_id(interrupted["id"])},
            )
            from open_notebook.databridge.mcp import service as mcp

            saved_run = await mcp.execute(
                interrupted["plan"]["id"], interrupted["approval_token"], notebook
            )
            recovered = await api(
                "POST", "/databridge/research/" + interrupted["id"] + "/resume", scope
            )
            check(
                recovered["state"] == "completed"
                and recovered["evidence"]["id"] == saved_run["id"]
                and len(await runs(interrupted)) == 1,
                "Interrupted research recovers the unique durable MCP evidence without replay",
            )
            await api(
                "POST",
                "/databridge/research/" + interrupted["id"] + "/resume",
                scope,
                expected=400,
            )
            check(
                len(await runs(interrupted)) == 1,
                "Completed recovery cannot consume another query approval",
            )
        elif mode == "restart":
            for name in ["total", "trend"]:
                saved = state[name]
                restored = await get(saved)
                check(
                    restored["evidence"] == saved["evidence"]
                    and restored["answer"] == saved["answer"],
                    "Research answer, exact version and evidence survive full stack restart",
                )
            history = await api("GET", "/chat/sessions/" + session)
            check(
                any(
                    m.get("database_turn_id") == state["total"]["id"]
                    and "700" in m["content"]
                    for m in history["messages"]
                ),
                "Verified database answer remains in the existing LangGraph conversation",
            )
            old = state["pending"]
            fresh = await review(old)
            await execute(old, expected=400)
            check(
                fresh["approval_token"] != old["approval_token"],
                "Post-restart review invalidates the old one-time approval",
            )
            check(
                (await execute(fresh))["state"] == "completed",
                "Freshly approved query executes after restart",
            )
            usage = await api("GET", "/databridge/usage")
            check(
                bool(
                    set(state["usage_ids"])
                    & {r["request_id"] for r in usage["records"]}
                ),
                "Research token/cost records survive proxy and PostgreSQL restart",
            )
        else:
            raise ValueError(mode)
        STATE.write_text(json.dumps(state))
        print(
            json.dumps({"mode": mode, "passed": len(CHECKS), "checks": CHECKS}),
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
