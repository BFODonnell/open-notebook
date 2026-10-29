"""Render a JSON (YAML-compatible) LiteLLM config without shell interpolation."""

import json
import os
from pathlib import Path


def configuration() -> dict:
    params = {
        "model": os.environ["LLM_PROVIDER_MODEL"],
        "api_base": os.environ["OPENAI_API_BASE"],
        "api_key": "os.environ/OPENAI_API_KEY",
    }
    info = {}
    # Optional operator-reviewed per-token rates for compatible/custom models.
    # Do not guess pricing for an unknown model.
    for kind in ("input", "output"):
        value = os.getenv(f"LLM_{kind.upper()}_COST_PER_TOKEN")
        if value:
            rate = float(value)
            if rate < 0 or not rate < float("inf"):
                raise ValueError("Model prices must be finite and nonnegative")
            info[f"{kind}_cost_per_token"] = rate
    if len(info) == 1:
        raise ValueError("Configure both input and output pricing, or neither")
    return {
        "model_list": [
            {
                "model_name": os.environ["LLM_MODEL"],
                "litellm_params": params,
                "model_info": info,
            }
        ],
        "router_settings": {"num_retries": 0},
        "litellm_settings": {
            "num_retries": 0,
            "request_timeout": 120,
            "set_verbose": False,
            "drop_params": True,
        },
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "database_url": "os.environ/DATABASE_URL",
            "store_prompts_in_spend_logs": False,
            "disable_spend_logs": False,
        },
    }


if __name__ == "__main__":
    path = Path("/tmp/databridge-litellm.json")
    path.write_text(json.dumps(configuration()), encoding="utf-8")
    os.execv(
        "docker/prod_entrypoint.sh",
        ["docker/prod_entrypoint.sh", "--config", str(path), "--port", "4000"],
    )
