from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from open_notebook.database.repository import repo_query
from open_notebook.databridge.mcp import service
from open_notebook.databridge.mcp.models import ConnectionWrite, MCPConnection, QueryRun
from open_notebook.exceptions import NotFoundError

router = APIRouter(prefix="/databridge")


def enabled():
    service.require_enabled()


def admin(x_databridge_admin: str | None = Header(default=None)):
    service.require_admin(x_databridge_admin)


class Approval(BaseModel):
    fingerprint: str = Field(min_length=64, max_length=64)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str
    notebook_id: str
    sql: str | None = Field(default=None, max_length=8192)
    tool: str | None = None
    parameters: dict = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notebook_id: str
    approval_token: str = Field(max_length=128)


class PublishRequest(BaseModel):
    staging_id: str
    dataset_id: str


@router.get("/mcp/status")
async def status():
    import os

    return {"enabled": os.getenv("DATABRIDGE_MCP_ENABLED", "false").lower() == "true"}


@router.get("/mcp/endpoints", dependencies=[Depends(admin)])
async def endpoints():
    import json
    import os

    return [
        {"ref": key, "backend": value["backend"]}
        for key, value in json.loads(
            os.getenv("DATABRIDGE_MCP_ENDPOINTS", "{}")
        ).items()
    ]


@router.get("/mcp/servers", dependencies=[Depends(enabled)])
async def connections(notebook_id: str):
    # Filter before returning registry metadata. This is notebook scoping within
    # the accepted single-user app, not a claim of tenant identity.
    from open_notebook.domain.notebook import Notebook

    await Notebook.get(notebook_id)
    records = await repo_query(
        "SELECT * FROM db_connection WHERE $notebook IN spec.notebooks LIMIT 100",
        {"notebook": notebook_id},
    )
    return [MCPConnection(**record).public() for record in records]


@router.post("/mcp/servers", dependencies=[Depends(admin)])
async def register(data: ConnectionWrite):
    return await service.write_connection(data)


@router.put("/mcp/servers/{connection_id}", dependencies=[Depends(admin)])
async def update(connection_id: str, data: ConnectionWrite):
    if not connection_id.startswith("db_connection:"):
        raise NotFoundError("Connection not found")
    return await service.write_connection(data, connection_id)


@router.post("/mcp/servers/{connection_id}/discover", dependencies=[Depends(admin)])
@router.post("/mcp/servers/{connection_id}/test", dependencies=[Depends(admin)])
async def discover(connection_id: str):
    if not connection_id.startswith("db_connection:"):
        raise NotFoundError("Connection not found")
    return await service.discover(connection_id)


@router.post("/mcp/servers/{connection_id}/approve", dependencies=[Depends(admin)])
async def approve(connection_id: str, data: Approval):
    if not connection_id.startswith("db_connection:"):
        raise NotFoundError("Connection not found")
    return await service.discover(connection_id, data.fingerprint)


@router.get("/mcp/servers/{connection_id}/schema", dependencies=[Depends(enabled)])
async def schema(connection_id: str, notebook_id: str):
    return await service.schema(connection_id, notebook_id)


@router.post("/query/plans", dependencies=[Depends(enabled)])
async def plan(data: PlanRequest):
    return await service.plan(**data.model_dump())


@router.post("/query/plans/{plan_id}/execute", dependencies=[Depends(enabled)])
async def execute(plan_id: str, data: ExecuteRequest):
    return await service.execute(plan_id, data.approval_token, data.notebook_id)


@router.get("/evidence/{run_id}", dependencies=[Depends(enabled)])
async def evidence(run_id: str, notebook_id: str):
    if not run_id.startswith("db_query_run:"):
        raise NotFoundError("Evidence not available")
    run = await QueryRun.get(run_id)
    if run.payload["notebook_id"] != notebook_id:
        raise NotFoundError("Evidence not available")
    await service.connection_for(
        run.payload["connection_id"], notebook_id, active=False
    )
    return {"id": run.id, **run.payload}


@router.get("/query/runs", dependencies=[Depends(enabled)])
async def runs(connection_id: str, notebook_id: str):
    await service.connection_for(connection_id, notebook_id, active=False)
    records = await repo_query(
        "SELECT * FROM db_query_run WHERE payload.connection_id=$connection AND payload.notebook_id=$notebook ORDER BY created DESC LIMIT 50",
        {"connection": connection_id, "notebook": notebook_id},
    )
    # List audit metadata without duplicating potentially large evidence rows.
    return [
        {"id": r["id"], **{k: v for k, v in r["payload"].items() if k != "rows"}}
        for r in records
    ]


@router.get("/dataset-versions", dependencies=[Depends(admin)])
async def versions():
    return await repo_query("SELECT * FROM db_dataset_version LIMIT 50")


@router.post("/dataset-versions/publish", dependencies=[Depends(admin)])
async def publish(data: PublishRequest):
    return await service.publish_version(data.staging_id, data.dataset_id)
