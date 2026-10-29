"""Gateway extension contracts; real proxy/DB acceptance lives in scripts/."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from pydantic import SecretStr

from open_notebook.databridge.bootstrap import bootstrap_gateway
from open_notebook.databridge.config import GatewaySettings
from open_notebook.databridge.correlation import attach_usage, usage_context
from open_notebook.databridge.usage import project_record, read_usage
from open_notebook.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    RateLimitError,
)
from open_notebook.utils.error_classifier import classify_error


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("DATABRIDGE_ENABLED", "true")
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://litellm:4000")
    monkeypatch.setenv("LITELLM_APP_VIRTUAL_KEY", "sk-test-app")
    monkeypatch.setenv("LLM_MODEL", "gpt-6-astra")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://u:p@litellm",
        "http://litellm?key=secret",
        "http://litellm/v1",
    ],
)
def test_invalid_operator_url(gateway, monkeypatch, url):
    monkeypatch.setenv("LITELLM_PROXY_URL", url)
    with pytest.raises(ConfigurationError):
        GatewaySettings.from_env()


def test_secrets_are_not_repr(gateway):
    assert "sk-test-app" not in repr(GatewaySettings.from_env())


@pytest.mark.asyncio
async def test_disabled_bootstrap_has_no_database_access(monkeypatch):
    monkeypatch.delenv("DATABRIDGE_ENABLED", raising=False)
    with patch(
        "open_notebook.databridge.bootstrap.repo_upsert", new_callable=AsyncMock
    ) as upsert:
        await bootstrap_gateway()
        upsert.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_preserves_other_defaults_and_encrypts(gateway, monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", "test-encryption")
    defaults = Mock(
        default_transformation_model="model:custom",
        large_context_model=None,
        default_tools_model="model:databridge_old",
        default_embedding_model="model:embed",
        update=AsyncMock(),
    )
    with (
        patch(
            "open_notebook.databridge.bootstrap.validate_url", new_callable=AsyncMock
        ),
        patch(
            "open_notebook.databridge.bootstrap.repo_upsert", new_callable=AsyncMock
        ) as upsert,
        patch(
            "open_notebook.databridge.bootstrap.DefaultModels.get_instance",
            new_callable=AsyncMock,
            return_value=defaults,
        ),
    ):
        await bootstrap_gateway()
        first = defaults.default_chat_model
        await bootstrap_gateway()
        assert defaults.default_chat_model == first
        assert defaults.default_tools_model == first
        assert defaults.large_context_model == first
        assert defaults.default_transformation_model == "model:custom"
        assert defaults.default_embedding_model == "model:embed"
        assert upsert.call_args_list[0].args[2]["api_key"] != "sk-test-app"
        monkeypatch.setenv("LLM_MODEL", "other-alias")
        await bootstrap_gateway()
        assert defaults.default_chat_model != first


def test_correlation_is_scoped_and_legacy_models_unchanged(gateway):
    legacy = Mock(openai_api_base="http://other/v1", extra_body=None)
    assert attach_usage(legacy, "chat") is legacy
    assert legacy.extra_body is None
    model = Mock(
        openai_api_base="http://litellm:4000/v1",
        openai_api_key=SecretStr("sk-test-app"),
        extra_body=None,
    )
    with usage_context(session_id="chat_session:test", notebook_id="notebook:test"):
        attach_usage(model, "chat")
    meta = model.extra_body["metadata"]["spend_logs_metadata"]
    assert meta["session_id"] == "chat_session:test"
    assert meta["notebook_id"] == "notebook:test"
    assert model.max_retries == 0
    assert model.root_client.max_retries == 0
    assert model.root_async_client.max_retries == 0
    attach_usage(model, "transform")
    assert "session_id" not in model.extra_body["metadata"]["spend_logs_metadata"]


@pytest.mark.parametrize("cost", [None, 0, -1, float("nan"), float("inf")])
def test_unknown_cost_is_not_free(cost):
    row = project_record({"request_id": "r", "spend": cost})
    assert row.estimated_cost_usd is None
    assert row.pricing_status == "unpriced"
    assert row.cached_input_tokens is None
    assert row.input_tokens is None


def test_usage_details_are_provider_reported():
    row = project_record(
        {
            "request_id": "r",
            "spend": 0.004,
            "metadata": {
                "usage_object": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 10},
                    "completion_tokens_details": {"reasoning_tokens": 5},
                },
                "spend_logs_metadata": {"trace_id": "trace"},
            },
        }
    )
    assert (
        row.input_tokens,
        row.output_tokens,
        row.cached_input_tokens,
        row.reasoning_tokens,
    ) == (100, 20, 10, 5)
    assert row.trace_id == "trace"
    assert row.estimated_cost_usd == 0.004


def test_budget_error_is_actionable():
    kind, message = classify_error(
        Exception("BudgetExceededError: exceeded your budget")
    )
    assert kind is RateLimitError
    assert "deployment operator" in message


@pytest.mark.asyncio
async def test_usage_scopes_key_deduplicates_and_hides_secrets(gateway):
    responses = [
        httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={
                "data": [{"request_id": "r", "spend": 0.1, "api_key": "sensitive"}] * 2,
                "total": 1,
                "total_pages": 1,
            },
        ),
        httpx.Response(
            200,
            request=httpx.Request("GET", "http://test"),
            json={"info": {"key": "sensitive", "max_budget": 2, "spend": 0.1}},
        ),
    ]
    client = AsyncMock()
    client.get.side_effect = responses
    with patch("open_notebook.databridge.usage.httpx.AsyncClient") as constructor:
        constructor.return_value.__aenter__.return_value = client
        now = datetime.now(timezone.utc)
        result = await read_usage(now, now, 1)
        assert len(result.records) == 1
        assert result.budget_remaining_usd == 1.9
        assert "sensitive" not in result.model_dump_json()
        assert client.get.call_args_list[0].kwargs["params"]["api_key"] != "sk-test-app"


@pytest.mark.asyncio
async def test_usage_failure_is_sanitized(gateway):
    with patch("open_notebook.databridge.usage.httpx.AsyncClient") as constructor:
        constructor.return_value.__aenter__.return_value.get.side_effect = (
            httpx.ConnectError("secret upstream URL")
        )
        now = datetime.now(timezone.utc)
        with pytest.raises(
            ExternalServiceError, match="Gateway usage is unavailable"
        ) as exc:
            await read_usage(now, now, 1)
        assert "secret" not in str(exc.value)
