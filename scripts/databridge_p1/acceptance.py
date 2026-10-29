"""Real proxy/Postgres/Esperanto acceptance with a deterministic HTTP provider.

Run ONLY inside the isolated fixture Compose project. Modes bracket a real
container restart and a deployment model change; see README.md.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import httpx

STATE = Path("data/p1-acceptance.json")
APP_KEY = "sk-p1-fixture-application-only"
ADMIN_KEY = "sk-p1-fixture-master-only"
CHECKS: list[str] = []


def check(condition, description):
    assert condition, description
    CHECKS.append(description)
    print("PASS:", description, flush=True)


async def poll(callback, predicate, attempts=45):
    for _ in range(attempts):
        result = await callback()
        if predicate(result):
            return result
        await asyncio.sleep(2)
    raise AssertionError("Timed out waiting for durable gateway data")


async def main(mode):
    assert os.getenv("SURREAL_PASSWORD") == "p1-fixture-only", "Fixture-only runner"
    async with (
        httpx.AsyncClient(
            base_url="http://localhost:5055",
            headers={"Authorization": "Bearer p1-fixture-password-only"},
            timeout=180,
        ) as app,
        httpx.AsyncClient(
            base_url="http://litellm:4000",
            headers={"Authorization": "Bearer " + ADMIN_KEY},
            timeout=30,
        ) as proxy,
    ):

        async def api(method, path, **kwargs):
            r = await app.request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()

        async def usage():
            return await api("GET", "/api/databridge/usage")

        async def chat(session, message="What is the fixture answer?"):
            return await app.post(
                "/api/chat/execute",
                json={"session_id": session, "message": message, "context": {}},
            )

        async def key_info(key):
            r = await proxy.get(
                "/key/info", params={"key": sha256(key.encode()).hexdigest()}
            )
            r.raise_for_status()
            return r.json()["info"]

        async def budget_call(key):
            return await proxy.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": "gpt-6-astra",
                    "messages": [{"role": "user", "content": "budget test"}],
                },
            )

        if mode == "seed":
            unauth = await app.get(
                "/api/databridge/usage", headers={"Authorization": ""}
            )
            check(
                unauth.status_code == 401,
                "usage retains upstream password authentication",
            )
            denied = await proxy.post(
                "/key/generate", headers={"Authorization": "Bearer " + APP_KEY}, json={}
            )
            check(
                denied.status_code in (401, 403),
                "application key cannot administer gateway keys",
            )
            notebook = await api(
                "POST",
                "/api/notebooks",
                json={"name": "P1 acceptance", "description": "synthetic"},
            )
            session = await api(
                "POST",
                "/api/chat/sessions",
                json={"notebook_id": notebook["id"], "title": "P1"},
            )
            result = await chat(session["id"])
            check(
                result.status_code == 200 and "42" in result.text,
                "notebook question reaches real LiteLLM through Esperanto and LangGraph",
            )
            logs = await poll(
                usage,
                lambda x: any(
                    r["session_id"] == session["id"] and r["status"] == "success"
                    for r in x["records"]
                ),
            )
            row = next(
                r
                for r in logs["records"]
                if r["session_id"] == session["id"] and r["status"] == "success"
            )
            check(
                (
                    row["input_tokens"],
                    row["output_tokens"],
                    row["cached_input_tokens"],
                    row["reasoning_tokens"],
                )
                == (100, 20, 10, 5),
                "all four provider-reported token categories persist",
            )
            check(
                row["estimated_cost_usd"] > 0 and row["pricing_status"] == "estimated",
                "canonical proxy cost uses USD per-token units",
            )
            check(
                row["trace_id"]
                and row["notebook_id"] == notebook["id"]
                and row["task"] == "chat",
                "request, notebook, session and task attribution persists",
            )
            raw = json.dumps(logs)
            check(
                all(
                    secret not in raw
                    for secret in (
                        APP_KEY,
                        ADMIN_KEY,
                        "fixture-only",
                        "messages",
                        "api_base",
                    )
                ),
                "usage projection contains no keys, provider URL or prompts",
            )
            future = datetime.now(timezone.utc) + timedelta(days=2)
            empty = await api(
                "GET",
                "/api/databridge/usage",
                params={
                    "start": future.isoformat(),
                    "end": (future + timedelta(days=1)).isoformat(),
                },
            )
            check(
                empty["total"] == 0,
                "UTC date filtering excludes outside-window records",
            )
            failed_prompt = "fixture-fail-" + uuid4().hex
            failed = await chat(session["id"], failed_prompt)
            check(
                failed.status_code == 502 and "detail" in failed.json(),
                "provider failure returns a useful typed API error",
            )
            async with httpx.AsyncClient() as fixture_client:
                count = await fixture_client.get(
                    "http://fixture:8080/attempts", params={"message": failed_prompt}
                )
                count.raise_for_status()
                check(
                    count.json()["count"] == 1,
                    "failed provider call is attempted exactly once without SDK/router retries",
                )
            failed_logs = await poll(
                usage,
                lambda x: any(
                    r["session_id"] == session["id"] and r["status"] == "failure"
                    for r in x["records"]
                ),
            )
            failure = next(
                r
                for r in failed_logs["records"]
                if r["session_id"] == session["id"] and r["status"] == "failure"
            )
            check(
                failure["estimated_cost_usd"] is None
                and failure["input_tokens"] is None,
                "failed provider attempt never fabricates free cost or usage",
            )
            # The upstream graph removes the failed turn from its checkpoint.
            history = await api("GET", "/api/chat/sessions/" + session["id"])
            check(
                "fixture-fail" not in json.dumps(history["messages"]),
                "failed chat turn is removed from persistent checkpoint",
            )
            budget_key = "sk-p1-budget-" + uuid4().hex
            generated = await proxy.post(
                "/key/generate",
                json={
                    "key": budget_key,
                    "models": ["gpt-6-astra"],
                    "max_budget": 0.00001,
                },
            )
            generated.raise_for_status()
            first = await budget_call(budget_key)
            check(
                first.status_code == 200, "limited key makes its first billable request"
            )
            await poll(
                lambda: key_info(budget_key), lambda x: x["spend"] > x["max_budget"]
            )
            second = await poll(
                lambda: budget_call(budget_key), lambda r: r.status_code != 200
            )
            print("Budget denial HTTP", second.status_code, flush=True)
            check(
                second.status_code == 422 and "budget" in second.text.lower(),
                "real persistent key budget denies subsequent requests",
            )
            own = await usage()
            check(
                all(r["session_id"] for r in own["records"]),
                "usage excludes requests made with another key",
            )
            try:
                lowered = await proxy.post(
                    "/key/update", json={"key": APP_KEY, "max_budget": 0.000000001}
                )
                lowered.raise_for_status()
                app_denied = await chat(session["id"])
                check(
                    app_denied.status_code == 429
                    and "deployment operator" in app_denied.text,
                    "exhausted application budget produces an actionable chat error",
                )
                check(
                    (await usage())["budget_remaining_usd"] == 0,
                    "usage remains readable when the application budget is exhausted",
                )
            finally:
                restored = await proxy.post(
                    "/key/update", json={"key": APP_KEY, "max_budget": 20}
                )
                restored.raise_for_status()
            models = await api("GET", "/api/models")
            state = {
                "request": row,
                "budget_key": budget_key,
                "notebook": notebook["id"],
                "session": session["id"],
                "model_count": len(models),
                "app_spend": (await key_info(APP_KEY))["spend"],
            }
            STATE.write_text(json.dumps(state))
        elif mode == "restart":
            state = json.loads(STATE.read_text())
            logs = await usage()
            check(
                any(r == state["request"] for r in logs["records"]),
                "token/cost/attribution record survives PostgreSQL and LiteLLM restart",
            )
            check(
                logs["budget_spend_usd"] == state["app_spend"],
                "application spend is not reset by key provisioning",
            )
            denied = await budget_call(state["budget_key"])
            check(
                denied.status_code == 422 and "budget" in denied.text.lower(),
                "budget denial survives database and proxy restart",
            )
            check(
                len(await api("GET", "/api/models")) == state["model_count"],
                "model bootstrap is idempotent after application restart",
            )
            history = await api("GET", "/api/chat/sessions/" + state["session"])
            check(
                "42" in json.dumps(history["messages"]),
                "existing notebook and LangGraph conversation survive restart",
            )
        elif mode == "unpriced":
            state = json.loads(STATE.read_text())
            check(
                (await usage())["managed_model"] == "p1-unpriced",
                "environment change selects a new deployment default",
            )
            result = await chat(state["session"])
            check(
                result.status_code == 200,
                "changed default reaches provider without manual model setup",
            )
            logs = await poll(
                usage,
                lambda x: any(
                    r["model_alias"] == "p1-unpriced" and r["status"] == "success"
                    for r in x["records"]
                ),
            )
            row = next(
                r
                for r in logs["records"]
                if r["model_alias"] == "p1-unpriced" and r["status"] == "success"
            )
            check(
                row["estimated_cost_usd"] is None
                and row["pricing_status"] == "unpriced"
                and row["input_tokens"] == 100,
                "unknown model pricing remains unavailable while real usage persists",
            )
            check(
                any(
                    r["request_id"] == state["request"]["request_id"]
                    and r["model_alias"] == "gpt-6-astra"
                    for r in logs["records"]
                ),
                "model change preserves historical attribution",
            )
        else:
            raise ValueError("Expected seed, restart or unpriced")
    print(json.dumps({"mode": mode, "passed": len(CHECKS), "checks": CHECKS}, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
