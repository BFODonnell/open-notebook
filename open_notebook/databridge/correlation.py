"""Attach non-content attribution after Esperanto has built the LangChain model."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from open_notebook.databridge.config import GatewaySettings

_context: ContextVar[dict[str, str] | None] = ContextVar(
    "databridge_usage", default=None
)


@contextmanager
def usage_context(**identifiers: str) -> Iterator[None]:
    token = _context.set({"trace_id": str(uuid4()), **identifiers})
    try:
        yield
    finally:
        _context.reset(token)


def attach_usage(model: BaseChatModel, task: str) -> BaseChatModel:
    settings = GatewaySettings.from_env()
    if not settings.enabled:
        return model
    # Only the configured application credential may receive this metadata.
    # Existing direct providers remain untouched and are explicitly unmetered.
    key = getattr(model, "openai_api_key", None)
    if (
        getattr(model, "openai_api_base", None) != settings.url + "/v1"
        or not key
        or key.get_secret_value() != settings.key
    ):
        return model
    metadata = {"task": task, **(_context.get() or {"trace_id": str(uuid4())})}
    model.extra_body = {  # type: ignore[attr-defined]
        **(getattr(model, "extra_body", None) or {}),
        "metadata": {
            "session_id": metadata.get("session_id"),
            "spend_logs_metadata": metadata,
        },
    }
    # Disable SDK retries: a charged upstream attempt must not be silently
    # repeated. Operator retries are separate, correctly billed requests.
    model.max_retries = 0  # type: ignore[attr-defined]
    # Esperanto's to_langchain() already constructed the SDK clients. Changing
    # only the Pydantic field above does not change those clients' retry policy.
    for name in ("root_client", "root_async_client"):
        client = getattr(model, name, None)
        if client is not None:
            client.max_retries = 0
    return model
