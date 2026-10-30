import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scripts.databridge_live import run
from scripts.databridge_live.model_unconfigured import app


def setup_launcher(
    monkeypatch,
    tmp_path,
    *,
    endpoint="https://openrouter.ai/api/v1",
    extra_hosts=None,
    ca=None,
    reader_ok=True,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    config = tmp_path / ".env.databridge-live-validation"
    monkeypatch.setattr(run, "CONFIG", config)
    (tmp_path / ".env.databridge").write_text("DATAGOV_API_KEY=catalog-test-only\n")
    config.write_text(
        f"DATABRIDGE_OPENROUTER_CREDENTIAL=credential:test\nOPENAI_API_BASE={endpoint}\nLLM_PROVIDER_MODEL=openrouter/openai/gpt-6-astra\n"
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "up"])
    calls = []

    def invoke(args, **kwargs):
        calls.append((args, dict(kwargs.get("env", {}))))
        if "--entrypoint" in args:
            return SimpleNamespace(
                returncode=0 if reader_ok else 1,
                stdout="sk-or-test-only" if reader_ok else "",
                stderr="private-test-diagnostic",
            )
        if "--format" in args:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "services": {
                            "open-notebook": {
                                "extra_hosts": extra_hosts,
                                "environment": {"DATABRIDGE_DOWNLOAD_CA_FILE": ca},
                            },
                            "litellm": {"environment": {"OPENAI_API_BASE": endpoint}},
                        }
                    }
                ),
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run.subprocess, "run", invoke)
    return calls, config


def test_cold_start_loads_existing_encrypted_key_without_writing_or_printing_it(
    monkeypatch, tmp_path, capsys
):
    calls, config = setup_launcher(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as result:
        run.main()
    assert result.value.code == 0
    assert calls[0][0][-1] == "surrealdb"
    assert "--entrypoint" in calls[1][0]
    assert calls[-1][1]["OPENAI_API_KEY"] == "sk-or-test-only"
    assert "sk-or-test-only" not in config.read_text()
    assert "sk-or-test-only" not in capsys.readouterr().out


def test_credential_cannot_be_routed_to_an_unapproved_provider(monkeypatch, tmp_path):
    calls, _ = setup_launcher(
        monkeypatch, tmp_path, endpoint="https://unapproved.example/v1"
    )
    with pytest.raises(SystemExit, match="official OpenRouter endpoint"):
        run.main()
    assert calls == []


@pytest.mark.parametrize(
    "settings",
    [{"extra_hosts": ["api.gsa.gov:93.184.216.2"]}, {"ca": "/fixture/ca.pem"}],
)
def test_live_provider_never_bypasses_catalog_fixture_exclusion(
    monkeypatch, tmp_path, settings
):
    calls, _ = setup_launcher(monkeypatch, tmp_path, **settings)
    with pytest.raises(SystemExit, match="fixture DNS or TLS"):
        run.main()
    assert "--format" in calls[-1][0]


def test_credential_read_failure_is_safe_and_never_launches_provider(
    monkeypatch, tmp_path, capsys
):
    calls, _ = setup_launcher(monkeypatch, tmp_path, reader_ok=False)
    with pytest.raises(SystemExit, match="Could not load the encrypted"):
        run.main()
    assert "--entrypoint" in calls[-1][0]
    assert "private-test-diagnostic" not in capsys.readouterr().out


def test_unconfigured_live_endpoint_returns_error_instead_of_fake_answer():
    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Describe NTD"}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert "choices" not in response.json()
    assert "fixture answer is 42" not in response.text
