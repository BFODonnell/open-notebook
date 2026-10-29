"""Separate live-catalog validation project; never prints or copies the catalog key."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".env.databridge-live-validation"
PROJECT = "databridge-live-validation"


def main():
    os.chdir(ROOT)
    key = dotenv_values(ROOT / ".env.databridge").get("DATAGOV_API_KEY")
    if not key or key in {"DEMO_KEY", "your-key-here"}:
        raise SystemExit("A personal DATAGOV_API_KEY is required in .env.databridge")
    if not CONFIG.exists():
        values = {
            name: secrets.token_hex(24)
            for name in (
                "SURREAL_PASSWORD",
                "LITELLM_POSTGRES_PASSWORD",
                "LITELLM_SALT_KEY",
                "OPEN_NOTEBOOK_ENCRYPTION_KEY",
                "OPEN_NOTEBOOK_PASSWORD",
                "DATABRIDGE_MCP_ADMIN_KEY",
                "DATABRIDGE_DBHUB_TOKEN",
                "DATABRIDGE_TOOLBOX_TOKEN",
                "DATABRIDGE_DUCKDB_TOKEN",
            )
        }
        values.update(
            {
                name: "sk-" + secrets.token_hex(24)
                for name in ("LITELLM_MASTER_KEY", "LITELLM_APP_VIRTUAL_KEY")
            }
        )
        values.update(DATABRIDGE_UI_PORT="18503", DATABRIDGE_API_PORT="15056")
        CONFIG.write_text(
            "# Local validation credentials; no personal catalog/provider key.\n"
            + "\n".join(f"{k}={v}" for k, v in values.items())
            + "\n"
        )
    env = dict(os.environ)
    for file in (
        ROOT / "scripts/databridge_p1/fixture.env",
        ROOT / "scripts/databridge_p2/fixture.env",
        CONFIG,
    ):
        env.update({k: v for k, v in dotenv_values(file).items() if v is not None})
    env["DATAGOV_API_KEY"] = key
    args = [
        "docker",
        "compose",
        "--env-file",
        "scripts/databridge_p1/fixture.env",
        "--env-file",
        "scripts/databridge_p2/fixture.env",
        "--env-file",
        str(CONFIG),
        "-p",
        PROJECT,
    ]
    for compose_file in (
        "compose.databridge.yml",
        "compose.databridge-mcp.yml",
        "compose.databridge-ingestion.yml",
        "compose.databridge-research.yml",
        "scripts/databridge_live/compose.yml",
    ):
        args += ["-f", compose_file]
    # Inspect in memory only: rendered Compose includes secrets and must not be logged.
    rendered = subprocess.run(
        args + ["config", "--format", "json"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if rendered.returncode:
        raise SystemExit("Live validation Compose configuration failed")
    services = json.loads(rendered.stdout)["services"]
    application = services["open-notebook"]
    if (
        application.get("extra_hosts")
        or application.get("environment", {}).get("DATABRIDGE_DOWNLOAD_CA_FILE")
        or "publisher-fixture" in services
    ):
        raise SystemExit(
            "Live catalog credentials cannot be used with fixture DNS or TLS"
        )
    if (
        services["litellm"]["environment"]["OPENAI_API_BASE"]
        != "http://fixture:8080/v1"
    ):
        raise SystemExit("This validation requires the local model fixture")
    if sys.argv[1:] == ["up"]:
        args += [
            "up",
            "-d",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "180",
            "open-notebook",
            "duckdb-broker",
            "fixture",
        ]
    elif sys.argv[1:] == ["stop"]:
        args += ["stop"]
    else:
        raise SystemExit("Usage: uv run python scripts/databridge_live/run.py up|stop")
    result = subprocess.run(args, env=env, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
