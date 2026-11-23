"""Render a LiteLLM reference config from `.env` model alias without leaking secrets.

Design-package utility, NOT yet wired into Open Notebook's container startup.
Use it as a starting point in Codex's P1 implementation.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def render(template: str, model: str) -> str:
    if not MODEL_ID.fullmatch(model):
        raise ValueError("Invalid LLM_MODEL identifier")
    # JSON strings are valid YAML scalars; secrets are symbolic env references.
    return template.replace("${LLM_MODEL}", json.dumps(model))


def main() -> None:
    model = os.environ.get("LLM_MODEL", "gpt-6-astra")
    root = Path(__file__).resolve().parent
    template = (root / "litellm-config.template.yaml").read_text()
    destination = Path(os.environ.get("LITELLM_RENDERED_CONFIG", "/tmp/databridge-litellm.yaml"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render(template, model))
    print(f"Rendered LiteLLM config at {destination} with model alias {model}")


if __name__ == "__main__":
    main()
