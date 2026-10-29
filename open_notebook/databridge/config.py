"""Deployment-only gateway configuration. Never serialize secrets to the API."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from open_notebook.exceptions import ConfigurationError


@dataclass(frozen=True)
class GatewaySettings:
    enabled: bool
    url: str = "http://litellm:4000"
    model: str = "gpt-6-astra"
    key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        enabled = os.getenv("DATABRIDGE_ENABLED", "false").lower() == "true"
        settings = cls(
            enabled=enabled,
            url=os.getenv("LITELLM_PROXY_URL", "http://litellm:4000").rstrip("/"),
            model=os.getenv("LLM_MODEL", "gpt-6-astra"),
            key=os.getenv("LITELLM_APP_VIRTUAL_KEY", ""),
        )
        if enabled:
            url = urlsplit(settings.url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
                or not settings.key.startswith("sk-")
                or not settings.model.strip()
            ):
                raise ConfigurationError("Invalid DataBridge gateway configuration")
        return settings
