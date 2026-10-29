"""Read-only projection of canonical LiteLLM records; never a second ledger."""

from datetime import datetime
from hashlib import sha256
from math import isfinite
from typing import Any

import httpx
from pydantic import BaseModel

from open_notebook.databridge.config import GatewaySettings
from open_notebook.exceptions import ExternalServiceError


class UsageRecord(BaseModel):
    request_id: str
    timestamp: str
    model: str
    model_alias: str | None = None
    trace_id: str | None = None
    notebook_id: str | None = None
    session_id: str | None = None
    task: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    estimated_cost_usd: float | None = None
    pricing_status: str
    status: str
    latency_ms: float | None = None
    retries: int | None = None
    error_code: str | None = None
    pricing_snapshot: dict[str, float] = {}


class UsagePage(BaseModel):
    enabled: bool
    managed_model: str | None = None
    currency: str = "USD"
    records: list[UsageRecord] = []
    page: int = 1
    total: int = 0
    total_pages: int = 0
    total_is_capped: bool = False
    budget_limit_usd: float | None = None
    budget_spend_usd: float | None = None
    budget_remaining_usd: float | None = None


def _tokens(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def project_record(row: dict) -> UsageRecord:
    metadata = row.get("metadata") or {}
    attribution = metadata.get("spend_logs_metadata") or {}
    usage = metadata.get("usage_object") or {}
    price_map = (metadata.get("model_map_information") or {}).get(
        "model_map_value"
    ) or {}
    rates = {
        key: value
        for key, value in price_map.items()
        if key
        in {
            "input_cost_per_token",
            "output_cost_per_token",
            "cache_read_input_token_cost",
        }
        and isinstance(value, (int, float))
        and isfinite(value)
        and value >= 0
    }
    raw_cost = row.get("spend")
    # LiteLLM can record 0 when pricing is absent. Never label that free.
    # This deliberately also treats free/zero-token requests as unavailable.
    cost = (
        float(raw_cost)
        if isinstance(raw_cost, (int, float)) and isfinite(raw_cost) and raw_cost > 0
        else None
    )
    return UsageRecord(
        request_id=str(row["request_id"]),
        timestamp=str(row.get("startTime", "")),
        model=str(row.get("model", "unknown")),
        model_alias=row.get("model_group"),
        trace_id=attribution.get("trace_id"),
        notebook_id=attribution.get("notebook_id"),
        session_id=row.get("session_id") or attribution.get("session_id"),
        task=attribution.get("task"),
        input_tokens=_tokens(usage.get("prompt_tokens")),
        output_tokens=_tokens(usage.get("completion_tokens")),
        cached_input_tokens=_tokens(
            (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        ),
        reasoning_tokens=_tokens(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        ),
        estimated_cost_usd=cost,
        pricing_status="estimated" if cost is not None else "unpriced",
        status=row.get("status") or metadata.get("status") or "unknown",
        latency_ms=row.get("request_duration_ms"),
        retries=_tokens(metadata.get("attempted_retries")),
        error_code=str(
            (metadata.get("error_information") or {}).get("error_code") or ""
        )
        or None,
        pricing_snapshot=rates,
    )


async def read_usage(start: datetime, end: datetime, page: int) -> UsagePage:
    settings = GatewaySettings.from_env()
    if not settings.enabled:
        return UsagePage(enabled=False)
    digest = sha256(settings.key.encode()).hexdigest()
    try:
        async with httpx.AsyncClient(
            base_url=settings.url,
            headers={"Authorization": "Bearer " + settings.key},
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            logs = await client.get(
                "/spend/logs/v2",
                params={
                    "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "api_key": digest,
                    "page": page,
                    "page_size": 50,
                    "sort_by": "startTime",
                    "sort_order": "desc",
                },
            )
            logs.raise_for_status()
            info = await client.get("/key/info", params={"key": digest})
            info.raise_for_status()
        payload = logs.json()
        budget = info.json()["info"]
        limit = budget.get("max_budget")
        spend = budget.get("spend")
        # Canonical request IDs are the ledger key. Never sum a retried response
        # twice; separately charged provider attempts retain different IDs.
        records = {row["request_id"]: project_record(row) for row in payload["data"]}
        return UsagePage(
            enabled=True,
            managed_model=settings.model,
            records=list(records.values()),
            page=page,
            total=payload["total"],
            total_pages=payload["total_pages"],
            total_is_capped=payload.get("total_is_capped", False),
            budget_limit_usd=limit,
            budget_spend_usd=spend,
            budget_remaining_usd=max(0, limit - spend)
            if limit is not None and spend is not None
            else None,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        # No remote error body, keys, URLs or prompt metadata reach the browser.
        raise ExternalServiceError(
            "Gateway usage is unavailable. Ask the deployment operator to check LiteLLM and its database."
        ) from None
