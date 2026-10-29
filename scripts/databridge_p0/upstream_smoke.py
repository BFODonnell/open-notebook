"""No-provider smoke test against the isolated P0 app, DB and real worker."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx


async def main() -> None:
    base = os.environ["P0_API_URL"]  # Explicit opt-in; never assume a user's app.
    checks: list[str] = []
    notebook_id = None
    source_ids: list[str] = []
    async with httpx.AsyncClient(base_url=base, timeout=20) as client:

        async def request(method: str, path: str, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        async def processed(source: dict, expected: str) -> dict:
            source_ids.append(source["id"])
            assert source["command_id"], source
            for _ in range(120):
                response = await request("GET", f"/api/sources/{source['id']}/status")
                status = response.json()
                assert status["status"] != "failed", status
                if status["status"] == "completed":
                    result = (
                        await request("GET", f"/api/sources/{source['id']}")
                    ).json()
                    assert expected in result["full_text"], result
                    return result
                await asyncio.sleep(0.5)
            raise AssertionError("Real worker did not finish within 60 seconds")

        try:
            assert (await request("GET", "/health")).json() == {"status": "healthy"}
            checks.append("API health")
            await request("GET", "/api/providers")
            checks.append("existing provider registry reachable")
            notebook = (
                await request(
                    "POST",
                    "/api/notebooks",
                    json={
                        "name": "P0 synthetic smoke " + uuid.uuid4().hex,
                        "description": "Temporary public synthetic development fixture",
                    },
                )
            ).json()
            notebook_id = notebook["id"]
            await request(
                "PUT",
                f"/api/notebooks/{notebook_id}",
                json={"description": "Updated P0 fixture"},
            )
            assert (await request("GET", f"/api/notebooks/{notebook_id}")).json()[
                "description"
            ] == "Updated P0 fixture"
            checks.append("notebook create/read/update")
            text = "Synthetic P0 transit fixture: three routes and six journeys."
            source = (
                await request(
                    "POST",
                    "/api/sources/json",
                    json={
                        "type": "text",
                        "content": text,
                        "title": "P0 text",
                        "notebooks": [notebook_id],
                        "embed": False,
                        "async_processing": True,
                        "transformations": [],
                    },
                )
            ).json()
            await processed(source, text)
            checks.append("text source submitted and processed by real worker")
            document = b"Synthetic P0 document: this is an uploaded public fixture."
            source = (
                await request(
                    "POST",
                    "/api/sources",
                    data={
                        "type": "upload",
                        "title": "P0 document",
                        "notebooks": json.dumps([notebook_id]),
                        "embed": "false",
                        "async_processing": "true",
                        "transformations": "[]",
                    },
                    files={"file": ("fixture.txt", document, "text/plain")},
                )
            ).json()
            await processed(source, "Synthetic P0 document")
            assert (
                await request("GET", f"/api/sources/{source['id']}/download")
            ).content == document
            checks.append("uploaded document processed and original download preserved")
            context = (
                await request(
                    "POST",
                    "/api/chat/context",
                    json={
                        "notebook_id": notebook_id,
                        "context_config": {
                            "sources": {sid: "full content" for sid in source_ids}
                        },
                    },
                )
            ).json()
            assert "Synthetic P0" in json.dumps(context)
            session = (
                await request(
                    "POST",
                    "/api/chat/sessions",
                    json={"notebook_id": notebook_id, "title": "P0 smoke session"},
                )
            ).json()
            await request("GET", f"/api/chat/sessions/{session['id']}")
            checks.append("source context and existing chat session CRUD")
        finally:
            for source_id in source_ids:
                await request("DELETE", f"/api/sources/{source_id}")
            if notebook_id:
                await request("DELETE", f"/api/notebooks/{notebook_id}")
        checks.append("synthetic notebook/source cleanup")
    print(
        json.dumps(
            {
                "passed": len(checks),
                "checks": checks,
                "unrun": "Live LLM/embeddings/podcast calls require provider configuration",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
