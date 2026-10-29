"""One-shot admin operation; never resets accumulated spend on restart."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(path: str, data: dict | None = None) -> dict:
    request = Request(
        os.environ["LITELLM_PROXY_URL"] + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"],
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    key = os.environ["LITELLM_APP_VIRTUAL_KEY"]
    if not key.startswith("sk-") or key == os.environ["LITELLM_MASTER_KEY"]:
        raise ValueError("A separate sk- application key is required")
    budget = float(os.environ["LITELLM_APP_MAX_BUDGET"])
    if not 0 < budget < float("inf"):
        raise ValueError("A finite positive application budget is required")
    payload = {
        "key": key,
        "key_alias": "open-notebook-databridge",
        "models": [os.environ["LLM_MODEL"]],
        "max_budget": budget,
        # Lifetime cap: automatic budget resets are deliberately not implicit.
        "allowed_routes": [
            "/chat/completions",
            "/v1/chat/completions",
            "/spend/logs/v2",
            "/key/info",
            "/model/info",
            "/v1/model/info",
        ],
    }
    # A hash in the query string avoids putting the actual key into access logs.
    from hashlib import sha256

    digest = sha256(key.encode()).hexdigest()
    try:
        call("/key/info?key=" + digest)
    except HTTPError as error:
        if error.code not in {400, 404}:
            raise RuntimeError(
                f"Gateway provisioning failed (HTTP {error.code})"
            ) from None
        call("/key/generate", payload)
    else:
        call("/key/update", payload)
    print("DataBridge application key provisioned; existing spend preserved")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Provider/admin error bodies can contain credentials. No traceback.
        raise SystemExit(
            "DataBridge key provisioning failed; check gateway configuration"
        ) from None
