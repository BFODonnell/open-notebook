"""Register ordinary upstream credentials/models after schema migrations."""

from hashlib import sha256

from pydantic import SecretStr

from open_notebook.ai.models import DefaultModels, Model
from open_notebook.database.repository import repo_upsert
from open_notebook.databridge.config import GatewaySettings
from open_notebook.domain.credential import Credential
from open_notebook.utils.url_validation import validate_url

CREDENTIAL_ID = "credential:databridge_gateway"
MODEL_PREFIX = "model:databridge_"


async def bootstrap_gateway() -> None:
    settings = GatewaySettings.from_env()
    if not settings.enabled:
        return
    await validate_url(settings.url, "openai_compatible")
    credential = Credential(
        name="DataBridge gateway (managed by .env)",
        provider="openai_compatible",
        modalities=["language"],
        api_key=SecretStr(settings.key),
        base_url=settings.url + "/v1",
    )
    # Use the existing encryption serializer. Fixed IDs make restarts idempotent;
    # a new alias gets a new model record so old selections retain their identity.
    await repo_upsert(
        "credential", CREDENTIAL_ID, credential._prepare_save_data(), True
    )
    model_id = MODEL_PREFIX + sha256(settings.model.encode()).hexdigest()[:20]
    model = Model(
        name=settings.model,
        provider="openai_compatible",
        type="language",
        credential=CREDENTIAL_ID,
    )
    await repo_upsert("model", model_id, model._prepare_save_data(), True)
    defaults = await DefaultModels.get_instance()
    defaults.default_chat_model = model_id
    for name in (
        "default_transformation_model",
        "large_context_model",
        "default_tools_model",
    ):
        previous = getattr(defaults, name)
        if not previous or previous.startswith(MODEL_PREFIX):
            setattr(defaults, name, model_id)
    await defaults.update()
