"""Live model regression and capture of the UI-completed comparison (no fixtures).

Run inside the app. ``plan`` proposes two NTD questions; inspect printed SQL,
then ``execute`` renews each review and executes only that same SQL. ``capture``
saves the completed browser turn. Approval tokens are never written or printed.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

NOTEBOOK = os.getenv(
    "DATABRIDGE_DEMO_NOTEBOOK", "Transit Population Weather - Verified Live Demo"
)
QUESTION = "For the imported NTD Service dataset, calculate the sum of Unlinked Passenger Trips (UPT) by Report Year where State is MA and Time Period is Annual Total. Convert comma-formatted trip values to numbers. Include the number of records for each year and missing or unparseable trip counts."


async def main(mode):
    root = Path("/app/data/three-source-live")
    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=240,
    ) as client:

        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        notebook = next(
            n for n in await api("GET", "/notebooks") if n["name"] == NOTEBOOK
        )
        scope = {"notebook_id": notebook["id"]}
        state_file = root / "aggregation-chat.json"
        if mode == "capture":
            sessions = await api("GET", "/chat/sessions", params=scope)
            captures = []
            for session in sessions:
                saved = await api("GET", "/chat/sessions/" + session["id"])
                for message in saved["messages"]:
                    turn_id = message.get("database_turn_id")
                    if turn_id:
                        turn = await api(
                            "GET",
                            "/databridge/research/" + turn_id,
                            params={**scope, "session_id": session["id"]},
                        )
                        if (
                            turn.get("dataset", {})
                            .get("title", "")
                            .startswith("Massachusetts transit")
                        ):
                            assert turn["state"] == "completed"
                            assert len(turn["evidence"]["rows"]) == 4
                            captures.append(turn)
            assert captures
            (root / "browser-chat.json").write_text(json.dumps(captures, indent=2))
            print(
                "BROWSER_CHAT_VERIFIED",
                [(t["id"], t["evidence"]["id"]) for t in captures],
            )
        elif mode == "plan":
            turns = []
            for suffix in ("", " Do not infer causality."):
                session = await api(
                    "POST",
                    "/chat/sessions",
                    json={
                        **scope,
                        "title": "Live numeric aggregation regression"
                        + (" (negated causality)" if suffix else ""),
                    },
                )
                result = await api(
                    "POST",
                    "/chat/execute",
                    json={
                        "session_id": session["id"],
                        "context": {},
                        "message": QUESTION + suffix,
                    },
                )
                turn_id = result["messages"][-1]["database_turn_id"]
                turn = await api(
                    "GET",
                    "/databridge/research/" + turn_id,
                    params={**scope, "session_id": session["id"]},
                )
                assert turn["state"] == "awaiting_review", turn["answer"]
                turns.append(
                    {"scope": {**scope, "session_id": session["id"]}, "turn": turn}
                )
                print(
                    "PROPOSED",
                    json.dumps(
                        {
                            "question": turn["question"],
                            "version": turn["dataset"]["version_id"],
                            "sql": turn["plan"]["sql"],
                        }
                    ),
                    flush=True,
                )
                state_file.write_text(json.dumps(turns, indent=2))
        elif mode == "execute":
            turns = json.loads(state_file.read_text())
            for saved in turns:
                turn = saved["turn"]
                review = await api(
                    "POST",
                    "/databridge/research/" + turn["id"] + "/review",
                    json=saved["scope"],
                )
                assert review["plan"]["sql"] == turn["plan"]["sql"]
                result = await api(
                    "POST",
                    "/databridge/research/" + turn["id"] + "/execute",
                    json={
                        **saved["scope"],
                        "plan_id": review["plan"]["id"],
                        "approval_token": review["approval_token"],
                    },
                )
                assert result["state"] == "completed", result["answer"]
                saved["result"] = result
                print("EXECUTED", json.dumps(result["evidence"]["rows"]), flush=True)
                state_file.write_text(json.dumps(turns, indent=2))
        else:
            raise ValueError("Choose capture, plan or execute")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
