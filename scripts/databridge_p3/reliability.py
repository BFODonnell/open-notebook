"""Fixture-only fault injection; the README coordinates real container outages."""

import asyncio
import json
import os
import ssl
import sys
from pathlib import Path
from uuid import uuid4

import httpx

from open_notebook.database.repository import ensure_record_id, repo_query

STATE = Path("/app/data/p3-reliability.json")


async def main(mode):
    assert os.getenv("DATAGOV_API_KEY") == "p3-synthetic-catalog-key-only"
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    seed = json.loads(Path("/app/data/p3-acceptance.json").read_text())
    notebook = seed["notebook"]
    checks = []

    def check(value, label):
        assert value, label
        checks.append(label)
        print("PASS:", label, flush=True)

    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer p1-fixture-password-only"},
        timeout=120,
    ) as client:

        async def api(method, path, body=None):
            response = await client.request(method, path, json=body)
            assert response.status_code == 200, (
                response.status_code,
                response.text[:200],
            )
            return response.json()

        async def get(job):
            return await api(
                "GET", "/databridge/imports/" + job["id"] + "?notebook_id=" + notebook
            )

        async def wait(job, stage=None):
            for _ in range(120):
                value = await get(job)
                if (
                    value["stage"] == stage
                    or stage is None
                    and value["status"] not in {"queued", "running"}
                ):
                    return value
                await asyncio.sleep(0.2)
            raise AssertionError("Job did not reach expected state")

        async def start(resource):
            return await api(
                "POST",
                "/databridge/imports",
                {
                    "notebook_id": notebook,
                    "resource_id": resource["id"],
                    "idempotency_key": str(uuid4()),
                },
            )

        async def retry(job):
            return await api(
                "POST",
                "/databridge/imports/" + job["id"] + "/retry",
                {"notebook_id": notebook},
            )

        async def expire(job):
            # Test clock advance avoids a 15 minute lease wait after actual SIGKILL.
            await repo_query(
                "UPDATE $id SET lease_until='2000-01-01'",
                {"id": ensure_record_id(job["id"])},
            )

        if mode in {"cancel", "changed", "outage", "interrupt-start"}:
            detail = await api(
                "GET", "/databridge/catalog/datasets/" + seed["jobs"][0]["catalog_id"]
            )
            name = (
                "Slow transfer"
                if mode in {"cancel", "interrupt-start"}
                else "Synthetic CSV"
            )
            resource = next(
                r for r in detail["resources"] if r["metadata"]["title"] == name
            )
            checked = await api(
                "POST", "/databridge/catalog/resources/" + resource["id"] + "/preflight"
            )
            assert checked["status"] == "ready", checked
            if mode == "changed":
                ctx = ssl.create_default_context(
                    cafile=os.environ["DATABRIDGE_DOWNLOAD_CA_FILE"]
                )
                async with httpx.AsyncClient(verify=ctx, trust_env=False) as fixture:
                    response = await fixture.post(
                        "https://data.transportation.gov/change"
                    )
                    assert response.status_code == 200 and response.json()["changed"]
                    try:
                        job = await wait(await start(resource))
                        check(
                            job["status"] == "failed"
                            and job["error"]["code"]
                            == "SOURCE_CHANGED_RECHECK_REQUIRED",
                            "Source mutation after preview fails before publication",
                        )
                        check(
                            "manifest" not in job,
                            "Changed source never becomes an immutable published dataset",
                        )
                    finally:
                        await fixture.post("https://data.transportation.gov/change")
            else:
                job = await start(resource)
                if mode in {"cancel", "interrupt-start"}:
                    await wait(job, "downloading")
                if mode == "cancel":
                    await api(
                        "POST",
                        "/databridge/imports/" + job["id"] + "/cancel",
                        {"notebook_id": notebook},
                    )
                    done = await wait(job)
                    check(
                        done["status"] == "cancelled" and "manifest" not in done,
                        "Running download cancellation stops before publication",
                    )
                elif mode == "interrupt-start":
                    state["interrupted"] = job
                    check(
                        True,
                        "Real worker is downloading when interruption is requested",
                    )
                else:
                    done = await wait(job)
                    check(
                        done["status"] == "failed"
                        and "manifest" in done
                        and "source_id" not in done,
                        "Broker outage retains publication but never marks import ready",
                    )
                    state["outage"] = done
        elif mode == "outage-recover":
            before = state["outage"]
            done = await wait(await retry(before))
            check(
                done["status"] == "ready" and done["manifest"] == before["manifest"],
                "Restored broker reconciles the existing immutable version",
            )
            check(
                done["download"] == before["download"],
                "Registration retry does not redownload source bytes",
            )
            state["outage"] = done
        elif mode == "interrupt-recover":
            before = await get(state["interrupted"])
            check(
                before["status"] == "running" and before["stage"] == "downloading",
                "SIGKILL preserves durable interrupted-worker state across restart",
            )
            await expire(before)
            done = await wait(await retry(before))
            check(
                done["status"] == "ready"
                and done["version_id"] == before["version_id"],
                "Expired interrupted job resumes through the real worker with the same version identity",
            )
            state["interrupted"] = done
        elif mode == "revocation":
            job = state["outage"]
            await repo_query(
                "UPDATE $id SET status='running', stage='registering', lease_until='2000-01-01'",
                {"id": ensure_record_id(job["id"])},
            )
            await repo_query(
                "UPDATE $id SET spec.enabled=false",
                {"id": ensure_record_id(job["connection_id"])},
            )
            denied = await wait(await retry(job))
            check(
                denied["status"] == "failed"
                and denied["error"]["code"] == "CONNECTION_CHANGED_REVIEW_REQUIRED",
                "Recovery cannot override administrator connection revocation",
            )
            row = await repo_query(
                "SELECT spec FROM $id", {"id": ensure_record_id(job["connection_id"])}
            )
            check(
                row[0]["spec"]["enabled"] is False,
                "Revoked connection remains disabled after recovery attempt",
            )
        else:
            raise ValueError(mode)
    STATE.write_text(json.dumps(state))
    print(
        json.dumps({"mode": mode, "passed": len(checks), "checks": checks}), flush=True
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
