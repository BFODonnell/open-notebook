from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from open_notebook.databridge.ingestion import catalog, service
from open_notebook.databridge.ingestion.download import AcquisitionError
from open_notebook.exceptions import ExternalServiceError

router = APIRouter(prefix="/databridge", dependencies=[Depends(catalog.enabled)])


async def acquire(operation):
    try:
        return await operation
    except AcquisitionError as error:
        raise ExternalServiceError("Catalog operation failed: " + error.code) from None


@router.get("/catalog/search")
async def search(
    q: str = Query(default="", max_length=250),
    org_slug: str = Query(default="", max_length=100),
    keyword: str = Query(default="", max_length=100),
    after: str = Query(default="", max_length=4096),
    per_page: int = Query(default=10, ge=1, le=20),
):
    return await acquire(catalog.search(q, org_slug, keyword, after, per_page))


@router.get("/catalog/datasets/{dataset_ref}")
async def dataset(dataset_ref: str):
    return await acquire(catalog.dataset(dataset_ref))


@router.post("/catalog/resources/{resource_ref}/preflight")
async def preflight(resource_ref: str):
    return await acquire(service.preflight(resource_ref))


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str
    notebook_id: str
    idempotency_key: UUID


class NotebookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notebook_id: str


@router.post("/imports")
async def create(data: ImportRequest):
    return await service.create_import(
        data.resource_id, data.notebook_id, str(data.idempotency_key)
    )


@router.get("/imports")
async def imports(notebook_id: str):
    return await service.list_jobs(notebook_id)


@router.get("/imports/{job_id}")
async def status(job_id: str, notebook_id: str):
    return service.public_job(await service.job_for(job_id, notebook_id))


@router.post("/imports/{job_id}/cancel")
async def cancel(job_id: str, data: NotebookRequest):
    return await service.cancel(job_id, data.notebook_id)


@router.post("/imports/{job_id}/retry")
async def retry(job_id: str, data: NotebookRequest):
    return await service.retry(job_id, data.notebook_id)


@router.get("/notebooks/{notebook_id}/datasets/context")
@router.get("/datasets")
async def datasets(notebook_id: str):
    return await service.notebook_context(notebook_id)
