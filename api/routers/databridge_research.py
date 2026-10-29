from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from open_notebook.databridge import research

router = APIRouter(
    prefix="/databridge/research", dependencies=[Depends(research.require_enabled)]
)


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(max_length=100)
    notebook_id: str = Field(max_length=100)


class Approval(Scope):
    plan_id: str = Field(max_length=100)
    approval_token: str = Field(max_length=128)


@router.get("/{turn_id}")
async def get(turn_id: str, session_id: str, notebook_id: str):
    turn = await research.get(turn_id, session_id, notebook_id)
    # Repair a persisted answer whose checkpoint write was interrupted.
    if turn["state"] in {"completed", "answer_failed", "failed"}:
        await research.checkpoint(turn)
    return research.public(turn)


@router.post("/{turn_id}/review")
async def review(turn_id: str, data: Scope):
    turn = await research.get(turn_id, data.session_id, data.notebook_id)
    return await research.review(turn)


@router.post("/{turn_id}/execute")
async def execute(turn_id: str, data: Approval):
    turn = await research.get(turn_id, data.session_id, data.notebook_id)
    return await research.execute(turn, data.plan_id, data.approval_token)


@router.post("/{turn_id}/resume")
async def resume(turn_id: str, data: Scope):
    turn = await research.get(turn_id, data.session_id, data.notebook_id)
    return await research.resume(turn)
