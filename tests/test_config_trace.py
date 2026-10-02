import json

import pytest

from chem_agent.config import Settings
from chem_agent.trace import RunTrace


def test_key_file_read_without_public_exposure(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY_FILE", raising=False)
    (tmp_path / "key.txt").write_text("sk-dummy-secret-not-a-real-key\n")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY_FILE=key.txt\n")
    settings = Settings.load(tmp_path)
    assert settings.api_key == "sk-dummy-secret-not-a-real-key"
    assert settings.api_key not in repr(settings)
    assert settings.api_key not in json.dumps(settings.public())


def test_trace_redacts_nested_credentials(tmp_path):
    secret = "private-dummy-key"
    trace = RunTrace(tmp_path, f"用户输入{secret}", {}, "v1", (secret,))
    trace.data["calls"].append({"arguments": {"api_key": "other", "text": secret}})
    trace.finish("failed", "sk-abcdefghijklmnop")
    text = trace.path.read_text()
    assert secret not in text
    assert "sk-abcdefghijklmnop" not in text
    assert json.loads(text)["calls"][0]["arguments"]["api_key"] == "[redacted]"


@pytest.mark.parametrize(
    "url",
    ["http://example.com", "https://user:password@example.com", "https://example.com?key=secret"],
)
def test_insecure_or_credential_bearing_endpoint_rejected(tmp_path, monkeypatch, url):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    with pytest.raises(ValueError):
        Settings.load(tmp_path)
